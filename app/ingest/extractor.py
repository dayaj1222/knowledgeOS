"""Extract text from uploaded files, markitdown-first.

Primary: markitdown for every type (pdf/pptx/docx) — it preserves document
structure as markdown (headings, lists, tables), which the structured
chunker cuts along. Page numbers are NOT available from markitdown, so
page_start/page_end are omitted rather than fabricated.

Fallback ladder when markitdown yields nothing:
1. pdftotext PER-PAGE for PDFs — restores page provenance for the fallback.
2. tesseract OCR for scanned PDFs (page provenance lost → single page).
3. marker-pdf for handwriting/equations (heavy, opt-in, may be absent).

Embedded figures (diagrams, scanned figures) are vision-described per
image (tesseract fallback) on EVERY pdf path — markitdown or fallback —
and appended as typed <image-text> blocks with page attribution.

Embedded figures (diagrams, scanned figures) are described per image through
the vision-capable chat endpoint (OpenAI-compatible, image_url parts) and
stored as typed <image-text> blocks. Tesseract OCR is the per-image fallback
when vision is unreachable — callers treat "no image text" as skip, never as
failure.

Every tool runs as a subprocess; if a tool is missing, degrade rather than crash.
"""

from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path

VISION_PROMPT = (
    "Describe ONLY the document figure in this image (diagram, chart, "
    "table, photo, or screenshot OF DOCUMENT CONTENT). "
    "IGNORE browser chrome, PDF viewer toolbars, tabs, address bars, "
    "taskbars, window frames, and page numbers — never transcribe them. "
    "If the image has no meaningful figure (blank, logo fragment, single "
    "glyph, decorative line, icon), reply with exactly: NO_CONTENT. "
    "Otherwise give: the type of visual; every text label and value you "
    "can actually READ — never invent text, mark unreadable parts "
    "[illegible]; axes and legend if any; relationships and arrows shown. "
    "Literal transcription, no interpretation."
)
NO_CONTENT = "NO_CONTENT"
VISION_TIMEOUT = 240.0  # seconds per image; vision backends can be slow
MAX_IMAGES_PER_PAGE = 6


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _pdfinfo_pages(path: Path) -> int:
    try:
        out = subprocess.run(
            ["pdfinfo", str(path)], capture_output=True, text=True, timeout=30
        )
        for line in out.stdout.splitlines():
            if line.lower().startswith("pages"):
                return int(line.split(":")[1].strip())
    except Exception:
        pass
    return 0


def _pdftotext_per_page(path: Path) -> list[tuple[int, str]]:
    """Extract text page-by-page so page numbers are accurate.

    Returns [(page_number, page_text), ...]. Falls back to whole-doc if
    pdfinfo is missing (then page numbers are unreliable → use 1 for all).
    """
    pages = _pdfinfo_pages(path)
    if pages <= 0:
        r = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True, text=True, timeout=120,
        )
        return [(1, r.stdout)] if r.stdout.strip() else []

    out: list[tuple[int, str]] = []
    for page in range(1, pages + 1):
        r = subprocess.run(
            ["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(path), "-"],
            capture_output=True, text=True, timeout=60,
        )
        if r.stdout.strip():
            out.append((page, r.stdout))
    return out


def _ocr_pdf(path: Path) -> str:
    """OCR a scanned PDF page-by-page using pdftoppm + tesseract."""
    if not (_have("pdftoppm") and _have("tesseract")):
        return ""
    from tempfile import TemporaryDirectory
    parts: list[str] = []
    with TemporaryDirectory() as td:
        tdp = Path(td)
        subprocess.run(
            ["pdftoppm", "-png", "-r", "150", str(path), str(tdp / "page")],
            capture_output=True, timeout=300,
        )
        for img in sorted(tdp.glob("page-*.png")):
            r = subprocess.run(
                ["tesseract", str(img), "stdout", "-l", "eng"],
                capture_output=True, text=True, timeout=60,
            )
            if r.stdout.strip():
                parts.append(r.stdout)
    return "\n\n".join(parts)


def _ocr_image_file(img: Path) -> str:
    """Tesseract fallback for a single extracted image file."""
    if not _have("tesseract"):
        return ""
    try:
        r = subprocess.run(
            ["tesseract", str(img), "stdout", "-l", "eng"],
            capture_output=True, text=True, timeout=60,
        )
    except Exception:
        return ""
    return r.stdout.strip()


def _describe_image_vision(png: bytes, thread_id: str | None = None) -> str:
    """Describe one image via the vision chat endpoint (OpenAI image_url).

    thread_id pins the turn to one proxy connection; callers rotate a
    small pool of ids so parallel workers land on parallel connections.
    Returns "" on any failure — the caller falls back to tesseract.
    A literal NO_CONTENT reply (decorative/blank image) also yields "".
    """
    try:
        import httpx

        from ..ai import LLM_BASE_URL, LLM_MODEL
    except Exception:
        return ""
    b64 = base64.b64encode(png).decode()
    payload = {
        "model": LLM_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }],
    }
    if thread_id:
        payload["thread_id"] = thread_id
    try:
        with httpx.Client(timeout=VISION_TIMEOUT) as client:
            r = client.post(f"{LLM_BASE_URL}/chat/completions", json=payload)
        r.raise_for_status()
        text = str(r.json()["choices"][0]["message"]["content"] or "").strip()
        return "" if text.strip() == NO_CONTENT else text
    except Exception:
        return ""


MIN_IMAGE_DIM = 120  # px; below this are glyphs/lines, not figures
MIN_IMAGE_BYTES = 10240  # 10 KB; below this are spacers/glyphs/logos — too small
# to carry a describable figure, so skip before paying a vision call


def _image_dims(path: Path, page: int) -> list[tuple[int, int]]:
    """(width, height) per image on the page, in `pdfimages -list` order.

    `-list` prints no filenames, but rows follow extraction sequence, so
    row i matches img-{i:03d}.png. Empty list when the tool is missing —
    callers then keep every image.
    """
    try:
        r = subprocess.run(
            ["pdfimages", "-list", "-f", str(page), "-l", str(page), str(path)],
            capture_output=True, text=True, timeout=60,
        )
    except Exception:
        return []
    dims: list[tuple[int, int]] = []
    for line in r.stdout.splitlines()[2:]:  # skip 2 header lines
        parts = line.split()
        # cols: page num type width height color ...
        if len(parts) >= 6:
            try:
                dims.append((int(parts[3]), int(parts[4])))
            except ValueError:
                continue
    return dims


VISION_THREADS = 3  # parallel proxy connections; rotate image turns across them


def _new_vision_threads(n: int = VISION_THREADS) -> list[str]:
    """Random thread ids, one per proxy connection (parallel uploads)."""
    import secrets

    return [secrets.token_hex(8) for _ in range(n)]


def _page_image_texts(
    path: Path,
    page: int,
    threads: list[str] | None = None,
    counter: object = None,
) -> list[str]:
    """Vision-describe every embedded image on one PDF page, in order.

    Images run on a 3-worker pool with turns rotated across the given
    thread ids (one proxy connection each). Falls back to tesseract per
    image when vision yields nothing. Empty list when the tools are
    missing or the page holds no images.
    """
    if not _have("pdfimages"):
        return []
    import itertools
    import logging
    from concurrent.futures import ThreadPoolExecutor

    log = logging.getLogger(__name__)
    from tempfile import TemporaryDirectory
    texts: list[str] = []
    stats = {"vision": 0, "ocr": 0, "skipped_small": 0, "empty": 0}
    threads = threads or []
    count = counter if counter is not None else itertools.count()

    def describe_one(img: Path) -> str:
        tid = threads[next(count) % len(threads)] if threads else None
        try:
            text = _describe_image_vision(img.read_bytes(), tid)
        except Exception:
            text = ""
        if text:
            return ("vision", text)
        text = _ocr_image_file(img)
        return ("ocr" if text else "empty", text)

    with TemporaryDirectory() as td:
        tdp = Path(td)
        try:
            subprocess.run(
                ["pdfimages", "-png", "-f", str(page), "-l", str(page),
                 str(path), str(tdp / "img")],
                capture_output=True, timeout=120,
            )
        except Exception:
            return []
        # Largest first: glyphs and line fragments sort last, so the
        # per-page cap keeps real figures instead of crowding them out.
        # -list rows follow extraction sequence = img-{i:03d} name order.
        ordered = sorted(tdp.glob("img-*.png"))
        dims = _image_dims(path, page)
        sized = []
        for i, img in enumerate(ordered):
            if img.stat().st_size < MIN_IMAGE_BYTES:
                stats["skipped_small"] += 1
                continue
            if dims and i < len(dims):
                w, h = dims[i]
                if w < MIN_IMAGE_DIM or h < MIN_IMAGE_DIM:
                    stats["skipped_small"] += 1
                    continue
            sized.append(img)
        imgs = sorted(sized, key=lambda p: p.stat().st_size, reverse=True)
        targets = imgs[:MAX_IMAGES_PER_PAGE]
        with ThreadPoolExecutor(max_workers=VISION_THREADS) as pool:
            # executor.map preserves input order → texts stay in size order.
            for kind, text in pool.map(describe_one, targets):
                stats[kind] += 1
                if text:
                    texts.append(text)
    if any(stats.values()):
        log.info("page_images page=%s %s", page, stats)
    return texts


def _markitdown(path: Path) -> str:
    if not _have("markitdown"):
        return ""
    r = subprocess.run(
        ["markitdown", str(path)], capture_output=True, text=True, timeout=180
    )
    return r.stdout


def _figure_blocks(path: Path) -> list[str]:
    """Describe embedded figures page by page (pdfs only) as typed blocks.

    Needs only pdfinfo (page count) + pdfimages + vision endpoint (tesseract
    fallback) — no text layer. Returns [] when tools are missing or no
    figure text is found.
    """
    if path.suffix.lower() != ".pdf":
        return []
    pages = _pdfinfo_pages(path)
    if pages <= 0:
        return []
    import itertools

    threads = _new_vision_threads()  # 3 ids, rotated across parallel turns
    count = itertools.count()
    out: list[str] = []
    for page in range(1, pages + 1):
        for i, text in enumerate(_page_image_texts(path, page, threads, count), 1):
            out.append(
                f'<image-text page="{page}" image="{i}">\n{text}\n</image-text>'
            )
    return out


def _markitdown_quality(text: str) -> bool:
    """Gate markitdown output: reject heading-less, table-mangled text.

    Failure signature seen live: zero '#' headings plus a high fraction of
    table rows (positioned prose misread as tables, words scattered across
    cells). Such output is worse than plain text — fall back to pdftotext,
    which preserves reading order for text-heavy PDFs.
    """
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return False
    headings = sum(1 for line in lines if line.lstrip().startswith("#"))
    table_rows = sum(1 for line in lines if line.strip().startswith("|"))
    if headings == 0 and table_rows / len(lines) > 0.3:
        return False
    return True


def extract_text(path: Path, file_type: str) -> tuple[str, str, list[tuple[int, str]]]:
    """Return (text, status, pages).

    text = markdown (primary) or fallback plain text; status ∈ {ok, empty,
    failed}; pages = [(page_number, page_text), ...] ONLY when the pdftotext
    fallback produced them — markitdown output carries no page info, and page
    provenance is omitted rather than fabricated.
    """
    text = _markitdown(path)
    if text.strip() and _markitdown_quality(text):
        figures = _figure_blocks(path)
        if figures:
            text = text + "\n\n" + "\n\n".join(figures)
        return text, "ok", []

    # Type comes from suffix OR the declared upload type (custom names often
    # carry no extension — never let a missing suffix skip the PDF ladder).
    is_pdf = path.suffix.lower() == ".pdf" or (file_type or "").lower() == "pdf"
    if is_pdf:
        # Fallback restores page provenance when markitdown finds nothing.
        # Figures still get vision descriptions — image extraction is
        # independent of which text path won.
        pages = _pdftotext_per_page(path)
        text = "\n\n".join(t for _, t in pages)
        if text.strip() and len(pages) > 0:
            figures = _figure_blocks(path)
            if figures:
                text = text + "\n\n" + "\n\n".join(figures)
            return text, "ok", pages

        # No usable text layer — try OCR (page provenance lost → single page)
        ocr = _ocr_pdf(path)
        if ocr.strip():
            return ocr, "ok", [(1, ocr)]

    # Last resort: marker-pdf (handwriting/equations) — opt-in, may be absent
    if _have("marker_single"):
        subprocess.run(
            ["marker_single", str(path), "--output_dir", str(path.parent / "marker_out")],
            capture_output=True, text=True, timeout=600,
        )
        md = path.with_suffix(".md")
        if md.exists():
            return md.read_text(), "ok", []

    return "", "failed", []
