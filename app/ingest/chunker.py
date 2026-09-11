"""Structure-aware chunking for markitdown output.

Cuts ALONG document structure instead of every N characters:
- headings open a new chunk (the heading stack becomes `section_path`)
- tables, code fences, figure blocks, and list runs are atomic (never split)
- oversized prose splits at sentence boundaries, never mid-sentence
- boilerplate (headers/footers) is stripped first by exact-repeat detection;
  conservative by design — a surviving header is noise, eaten content is loss

Each chunk carries `section_path` ("A > B") so it reads standalone. Page
ranges are attributed only when the caller supplies per-page text (the
pdftotext fallback path); markitdown output carries no page info and page
keys are omitted rather than fabricated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CHUNK_TOKENS = 800

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")
_IMAGE_OPEN_RE = re.compile(r"^\s*<image-text\b[^>]*>\s*$")
_IMAGE_CLOSE_RE = re.compile(r"^\s*</image-text>\s*$")
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def _approx_tokens(text: str) -> int:
    # crude but stable: ~4 chars per token for English prose
    return len(text) // 4


def strip_boilerplate(markdown: str, min_repeats: int = 3) -> tuple[str, list[str]]:
    """Drop exact-repeat lines (running heads/feet) outside code/tables.

    Headings (#), table rows, and fenced code are never boilerplate — a
    repeated slide title is content, not chrome. Returns (clean, stripped)
    where stripped is the sorted report of removed lines.
    """
    lines = [line.rstrip() for line in markdown.split("\n")]
    masked = [False] * len(lines)
    in_fence = False
    for i, line in enumerate(lines):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            masked[i] = True
        elif in_fence or _TABLE_ROW_RE.match(line) or _HEADING_RE.match(line):
            masked[i] = True

    counts: dict[str, int] = {}
    for i, line in enumerate(lines):
        if masked[i]:
            continue
        norm = " ".join(line.split())
        if len(norm) >= 3:
            counts[norm] = counts.get(norm, 0) + 1

    boiler = {n for n, c in counts.items() if c >= min_repeats}
    kept: list[str] = []
    for i, line in enumerate(lines):
        if not masked[i] and " ".join(line.split()) in boiler:
            continue
        kept.append(line)
    return "\n".join(kept), sorted(boiler)


@dataclass
class _Unit:
    kind: str  # heading | para | list | table | fence | figure
    text: str
    level: int = 0


def _parse_units(markdown: str) -> list[_Unit]:
    """Split markdown into typed units (headings, lists, tables, ...)."""
    units: list[_Unit] = []
    lines = markdown.split("\n")
    i, n = 0, len(lines)
    para_buf: list[str] = []
    list_buf: list[str] = []

    def flush_para() -> None:
        if para_buf:
            # sentence-split long prose walls into cap-fittable pieces later;
            # here just emit the paragraph run as one unit
            units.append(_Unit("para", "\n".join(para_buf)))
            para_buf.clear()

    def flush_list() -> None:
        if list_buf:
            units.append(_Unit("list", "\n".join(list_buf)))
            list_buf.clear()

    while i < n:
        line = lines[i]
        m = _HEADING_RE.match(line)
        if m:
            flush_para()
            flush_list()
            units.append(_Unit("heading", line.strip(), len(m.group(1))))
            i += 1
            continue
        if _FENCE_RE.match(line):
            flush_para()
            flush_list()
            fence = [line]
            i += 1
            while i < n and not _FENCE_RE.match(lines[i]):
                fence.append(lines[i])
                i += 1
            if i < n:
                fence.append(lines[i])
                i += 1
            units.append(_Unit("fence", "\n".join(fence)))
            continue
        if _IMAGE_OPEN_RE.match(line):
            flush_para()
            flush_list()
            fig = [line]
            i += 1
            while i < n and not _IMAGE_CLOSE_RE.match(lines[i]):
                fig.append(lines[i])
                i += 1
            if i < n:
                fig.append(lines[i])
                i += 1
            units.append(_Unit("figure", "\n".join(fig)))
            continue
        if _TABLE_ROW_RE.match(line):
            flush_para()
            flush_list()
            tbl = [line]
            i += 1
            while i < n and _TABLE_ROW_RE.match(lines[i]):
                tbl.append(lines[i])
                i += 1
            units.append(_Unit("table", "\n".join(tbl)))
            continue
        if _LIST_ITEM_RE.match(line):
            flush_para()
            list_buf.append(line)
            i += 1
            continue
        if not line.strip():
            flush_para()
            flush_list()
            i += 1
            continue
        flush_list()
        para_buf.append(line)
        i += 1
    flush_para()
    flush_list()
    return units


@dataclass
class _Chunk:
    units: list[_Unit] = field(default_factory=list)
    tokens: int = 0
    section: str = ""


def _split_long_para(text: str, cap: int) -> list[str]:
    """Split an oversized paragraph at sentence boundaries."""
    if _approx_tokens(text) <= cap:
        return [text]
    sents = _SENT_SPLIT_RE.split(text)
    parts, cur, cur_t = [], [], 0
    for s in sents:
        t = _approx_tokens(s)
        if cur and cur_t + t > cap:
            parts.append(" ".join(cur))
            cur, cur_t = [], 0
        cur.append(s)
        cur_t += t
    if cur:
        parts.append(" ".join(cur))
    return parts or [text]


def _attribute_pages(chunks: list[dict], pages: list[tuple[int, str]]) -> None:
    """Best-effort page ranges by matching chunk edges to page texts."""
    if not pages:
        return
    page_texts = [(num, re.sub(r"\s+", " ", t)) for num, t in pages]
    for c in chunks:
        flat = re.sub(r"\s+", " ", c["content"])
        head, tail = flat[:80], flat[-80:]
        start = end = None
        for num, pt in page_texts:
            if start is None and head and head[:40] in pt:
                start = num
            if tail and tail[-40:] in pt:
                end = num
        if start is not None:
            c["page_start"] = start
            c["page_end"] = end if end is not None else start


def chunk_text(text: str, pages: list[tuple[int, str]] | None = None) -> list[dict]:
    """Split markdown into section-aware chunks.

    Returns [{content, index_order, section_path, (page_start, page_end?)}].
    `pages` (pdftotext fallback) only feeds page attribution; structure always
    comes from the markdown itself.
    """
    clean, _ = strip_boilerplate(text or "")
    units = _parse_units(clean)
    if not units:
        return []

    chunks: list[dict] = []
    stack: list[tuple[int, str]] = []  # (level, title)
    cur = _Chunk()
    held: list[_Unit] = []  # headings awaiting content — never emitted alone

    def section_path() -> str:
        return " > ".join(t for _, t in stack)

    def push_unit(u: _Unit, content: str) -> None:
        cur.units.append(_Unit(u.kind, content, u.level))
        cur.tokens += _approx_tokens(content)

    def flush() -> None:
        nonlocal cur
        if cur.units:
            body = "\n\n".join(u.text for u in cur.units)
            chunks.append({"content": body, "section_path": cur.section})
            cur = _Chunk(section=section_path())

    def take_held() -> None:
        nonlocal held
        if held and not cur.units:
            for h in held:
                push_unit(h, h.text)
            held = []

    for u in units:
        if u.kind == "heading":
            flush()
            while stack and stack[-1][0] >= u.level:
                stack.pop()
            title = _HEADING_RE.match(u.text).group(2)  # type: ignore[union-attr]
            stack.append((u.level, title))
            cur.section = section_path()
            held.append(u)
            continue
        take_held()
        if u.kind == "para":
            for piece in _split_long_para(u.text, CHUNK_TOKENS):
                if cur.tokens + _approx_tokens(piece) > CHUNK_TOKENS and cur.units:
                    flush()
                    take_held()
                push_unit(u, piece)
            continue
        # atomic: table, fence, figure, list — flush first if they overflow
        if cur.tokens + _approx_tokens(u.text) > CHUNK_TOKENS and cur.units:
            flush()
            take_held()
        push_unit(u, u.text)

    flush()
    if held:
        # trailing headings with no content (doc ends on a heading): fold
        # into the last chunk so no text is ever dropped
        tail = "\n\n".join(h.text for h in held)
        if chunks:
            chunks[-1]["content"] += "\n\n" + tail
        else:
            chunks.append({"content": tail, "section_path": section_path()})
    # prepend section context when a chunk doesn't open with its own heading
    for c in chunks:
        first = c["content"].lstrip().split("\n", 1)[0]
        if c["section_path"] and not first.startswith("#"):
            head_title = c["section_path"].split(" > ")[-1]
            c["content"] = f"# {head_title}\n\n{c['content']}"

    _attribute_pages(chunks, pages or [])
    for i, c in enumerate(chunks):
        c["index_order"] = i
    return chunks
