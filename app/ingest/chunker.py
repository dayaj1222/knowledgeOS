"""Split extracted text into overlapping passages with accurate page ranges.

Takes the extractor's per-page output [(page_number, page_text), ...] so page
provenance is correct by construction — NOT derived from form-feed markers
(which pdftotext emits at column/slide breaks, not page ends, producing wrong
page numbers).

Fixed ~800-token chunks with ~100-token overlap, splitting on paragraph
boundaries where possible. When pages are empty/unknown, page_start/page_end
are omitted rather than fabricated.
"""

from __future__ import annotations

CHUNK_TOKENS = 800
OVERLAP_TOKENS = 100


def _approx_tokens(text: str) -> int:
    # crude but stable: ~4 chars per token for English prose
    return len(text) // 4


def chunk_text(text: str, pages: list[tuple[int, str]] | None = None) -> list[dict]:
    """Return a list of chunk dicts: {content, index_order, page_start, page_end}.

    `pages` is the extractor's [(page_number, text), ...]; when provided, page
    ranges are accurate. When absent, page_start/page_end are omitted.
    """
    if pages is None:
        pages = []
    has_pages = bool(pages)

    # Build an ordered paragraph stream with page attribution.
    paragraphs: list[tuple[int | None, str]] = []
    if has_pages:
        for page_num, page_text in pages:
            for para in page_text.split("\n\n"):
                p = para.strip()
                if p:
                    paragraphs.append((page_num, p))
    else:
        paragraphs = [(None, p.strip()) for p in text.split("\n\n") if p.strip()]

    if not paragraphs:
        return []

    chunks: list[dict] = []
    buf: list[tuple[int | None, str]] = []
    buf_tokens = 0
    page_start: int | None = paragraphs[0][0]
    page_end: int | None = paragraphs[0][0]

    def flush() -> None:
        nonlocal buf, buf_tokens, page_start
        if buf:
            chunk: dict = {"content": "\n\n".join(p for _, p in buf)}
            if has_pages:
                chunk["page_start"] = page_start
                chunk["page_end"] = page_end
            chunks.append(chunk)
            # Overlap: carry trailing paragraphs (~OVERLAP_TOKENS) into the
            # next chunk so context continues across boundaries instead of
            # cutting mid-thought. Nothing is dropped; boundaries just share
            # a strip of text.
            carry: list[tuple[int | None, str]] = []
            carry_tokens = 0
            for page, para in reversed(buf):
                t = _approx_tokens(para)
                if carry_tokens + t > OVERLAP_TOKENS and carry:
                    break
                carry.append((page, para))
                carry_tokens += t
            buf = list(reversed(carry))
            buf_tokens = carry_tokens
            page_start = buf[0][0] if (buf and has_pages) else None

    for page, para in paragraphs:
        t = _approx_tokens(para)
        if buf_tokens + t > CHUNK_TOKENS and buf:
            flush()
        if page_start is None and has_pages:
            page_start = page
        buf.append((page, para))
        buf_tokens += t
        if has_pages and page is not None:
            page_end = page

    flush()

    for i, c in enumerate(chunks):
        c["index_order"] = i
    return chunks
