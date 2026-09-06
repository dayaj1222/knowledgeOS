"""Extract text from uploaded files via a cheap-first detection ladder.

Detection order (cheapest first), per the Feature 2 design:
1. pdftotext PER-PAGE for PDFs — gives accurate page provenance (a naive
   whole-doc pdftotext emits \f at column/slide breaks, not page ends, so page
   numbers derived from it are wrong).
2. tesseract OCR for PDFs with no text layer (printed text; fails handwriting)
3. marker-pdf for handwriting/equations (heavy, ~5GB install; opt-in only)
4. markitdown for pptx/docx (preserves structure)

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


def _with_image_text(pages: list[tuple[int, str]], path: Path) -> list[tuple[int, str]]:
    """Append `<image-text>` markers to pages that carry embedded images.

    The marker tells downstream readers (chunker → LLM) that the text came
    from an image via OCR, so it is graded as diagram/figure content rather
    than body prose. Pages without images pass through untouched.
    """
    out: list[tuple[int, str]] = []
    for page_num, page_text in pages:
        images = _ocr_embedded_images(path, page_num)
        if not images:
            out.append((page_num, page_text))
            continue
        markers = "\n\n".join(
            f'<image-text page="{page_num}" image="{i}">\n{text}\n</image-text>'
            for i, text in enumerate(images, 1)
        )
        out.append((page_num, page_text + "\n\n" + markers))
    return out


def _markitdown(path: Path) -> str:
    if not _have("markitdown"):
        return ""
    r = subprocess.run(
        ["markitdown", str(path)], capture_output=True, text=True, timeout=180
    )
    return r.stdout


def extract_text(path: Path, file_type: str) -> tuple[str, str, list[tuple[int, str]]]:
    """Return (text, status, pages).

    text = concatenated text; status ∈ {ok, empty, failed};
    pages = [(page_number, page_text), ...] when the source has page info,
    else [] (and page provenance is silently absent).
    """
    ext = path.suffix.lower()
    if ext in (".pptx", ".docx") or file_type in ("pptx", "docx"):
        text = _markitdown(path)
        if text.strip():
            return text, "ok", []
        return text, "empty" if text is not None else "failed", []

    # PDFs (and slides/notes which are pdfs)
    pages = _pdftotext_per_page(path)
    text = "\n\n".join(t for _, t in pages)
    if text.strip() and len(pages) > 0:
        # Hybrid PDFs: body text + diagrams/figures as images. OCR the
        # embedded images so image-only content isn't silently dropped.
        pages = _with_image_text(pages, path)
        text = "\n\n".join(t for _, t in pages)
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
