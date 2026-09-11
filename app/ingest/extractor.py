"""Extract text from uploaded files, markitdown-first.

Primary: markitdown for every type (pdf/pptx/docx) — it preserves document
structure as markdown (headings, lists, tables), which the structured
chunker cuts along. Page numbers are NOT available from markitdown, so
page_start/page_end are omitted rather than fabricated.

Fallback ladder when markitdown yields nothing:
1. pdftotext PER-PAGE for PDFs — restores page provenance for the fallback.
2. tesseract OCR for scanned PDFs (page provenance lost → single page).
3. marker-pdf for handwriting/equations (heavy, opt-in, may be absent).

Embedded figures (diagrams, scanned figures) are OCRed per page and appended
as typed <image-text> blocks — OCR only ever describes images, never prose.

Every tool runs as a subprocess; if a tool is missing, degrade rather than crash.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


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


MAX_IMAGES_PER_PAGE = 6


def _ocr_embedded_images(path: Path, page: int) -> list[str]:
    """OCR the images embedded in one PDF page (diagrams, scanned figures).

    Returns the non-empty OCR texts in page order. Empty list when the tools
    are missing or the page holds no readable images — callers treat this as
    "no image text", never as failure.
    """
    if not (_have("pdfimages") and _have("tesseract")):
        return []
    from tempfile import TemporaryDirectory
    texts: list[str] = []
    with TemporaryDirectory() as td:
        tdp = Path(td)
        subprocess.run(
            ["pdfimages", "-png", "-f", str(page), "-l", str(page),
             str(path), str(tdp / "img")],
            capture_output=True, timeout=120,
        )
        for img in sorted(tdp.glob("img-*.png"))[:MAX_IMAGES_PER_PAGE]:
            r = subprocess.run(
                ["tesseract", str(img), "stdout", "-l", "eng"],
                capture_output=True, text=True, timeout=60,
            )
            if r.stdout.strip():
                texts.append(r.stdout.strip())
    return texts


def _markitdown(path: Path) -> str:
    if not _have("markitdown"):
        return ""
    r = subprocess.run(
        ["markitdown", str(path)], capture_output=True, text=True, timeout=180
    )
    return r.stdout


def _figure_blocks(path: Path) -> list[str]:
    """OCR embedded figures page by page (pdfs only) as typed blocks.

    Needs only pdfinfo (page count) + pdfimages/tesseract — no text layer.
    Returns [] when tools are missing or no figure text is found.
    """
    if path.suffix.lower() != ".pdf":
        return []
    pages = _pdfinfo_pages(path)
    if pages <= 0:
        return []
    out: list[str] = []
    for page in range(1, pages + 1):
        for i, text in enumerate(_ocr_embedded_images(path, page), 1):
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
        pages = _pdftotext_per_page(path)
        text = "\n\n".join(t for _, t in pages)
        if text.strip() and len(pages) > 0:
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
