"""Extraction quality gate: mangled markitdown output must fail over.

Locked from live evidence: markitdown rendered a text-heavy PDF as 0
headings + table-salad (positioned prose misread as tables). Such output
is worse than plain text — the gate sends it to the pdftotext fallback.
"""

from app.ingest.extractor import _markitdown_quality

MANGLED = "\n".join(
    ["| 4 | # Step | 3: normalize | by | sum |", "| --- | --- | --- | --- | --- |"]
    + [f"| {i} | x | y | z |" for i in range(40)]
)

HEADED = "# Arrays\n\nClean prose about arrays here.\n\n## Shapes\n\nMore prose."


def test_table_salad_without_headings_rejected():
    assert _markitdown_quality(MANGLED) is False


def test_headed_markdown_accepted():
    assert _markitdown_quality(HEADED) is True


def test_empty_rejected():
    assert _markitdown_quality("") is False
    assert _markitdown_quality("   \n  ") is False


def test_vision_failure_returns_empty_string(monkeypatch):
    """Unreachable endpoint → '' so the caller falls back to tesseract."""
    import app.ai as ai_mod
    from app.ingest.extractor import _describe_image_vision

    monkeypatch.setattr(ai_mod, "LLM_BASE_URL", "http://127.0.0.1:1/v1")
    assert _describe_image_vision(b"\x89PNGfakepng") == ""


def test_figure_blocks_skip_non_pdf(tmp_path):
    from app.ingest.extractor import _figure_blocks

    f = tmp_path / "notes.txt"
    f.write_text("hello")
    assert _figure_blocks(f) == []


def test_vision_turns_rotate_across_three_threads(monkeypatch, tmp_path):
    """Parallel image turns spread over 3 thread ids (3 proxy conns)."""
    import itertools
    from pathlib import Path

    import app.ingest.extractor as ex

    for i in range(5):
        (tmp_path / f"img-{i:03d}.png").write_bytes(
            # Real figures must pass the extractor's minimum-size filter.
            f"PNG-{i}".encode() + b"\x00" * 12_000)

    class FakeCompleted:
        stdout = ""

    def fake_run(cmd, **kw):
        return FakeCompleted()

    seen: list = []

    def fake_describe(png: bytes, thread_id=None):
        seen.append(thread_id)
        return f"got-{png.decode().replace(chr(0), '')}"

    monkeypatch.setattr(ex.subprocess, "run", fake_run)
    monkeypatch.setattr(ex, "_image_dims", lambda path, page: [])
    monkeypatch.setattr(ex, "_describe_image_vision", fake_describe)
    # Point the extractor's temp glob at our dir by stubbing TemporaryDirectory.
    import tempfile

    class FakeTD:
        def __enter__(self):
            return tmp_path

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(tempfile, "TemporaryDirectory", lambda: FakeTD())

    threads = ["t1", "t2", "t3"]
    out = ex._page_image_texts(Path("doc.pdf"), 1, threads, itertools.count())
    assert out == [f"got-PNG-{i}" for i in range(5)], "order must follow input order"
    assert set(seen) == {"t1", "t2", "t3"}, f"rotation missed a connection: {seen}"
    assert len(seen) == 5


def test_tiny_images_skipped_before_vision(monkeypatch, tmp_path):
    """Sub-1.5KB files (spacers/glyphs) never reach vision or OCR."""
    import itertools
    from pathlib import Path

    import app.ingest.extractor as ex

    (tmp_path / "img-000.png").write_bytes(b"\x89PNG" + b"\x00" * 287)  # 291 bytes

    def fake_run(cmd, **kw):
        class FakeCompleted:
            stdout = ""

        return FakeCompleted()

    def boom(png: bytes, thread_id=None):
        raise AssertionError("vision must not be called for tiny images")

    def boom_ocr(img):
        raise AssertionError("ocr must not be called for tiny images")

    monkeypatch.setattr(ex.subprocess, "run", fake_run)
    monkeypatch.setattr(ex, "_image_dims", lambda path, page: [])
    monkeypatch.setattr(ex, "_describe_image_vision", boom)
    monkeypatch.setattr(ex, "_ocr_image_file", boom_ocr)
    import tempfile

    class FakeTD:
        def __enter__(self):
            return tmp_path

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(tempfile, "TemporaryDirectory", lambda: FakeTD())
    assert ex._page_image_texts(Path("doc.pdf"), 1, ["t1"], itertools.count()) == []


def test_no_content_reply_yields_empty(monkeypatch):
    """A literal NO_CONTENT vision reply is treated as no text (skip)."""
    import httpx

    import app.ingest.extractor as ex

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "NO_CONTENT"}}]}

    class FakeClient:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None):
            assert json.get("thread_id") == "abc", "thread_id must ride along"
            return FakeResp()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    assert ex._describe_image_vision(b"\x89PNGx", "abc") == ""


def test_fallback_path_still_injects_figures(monkeypatch, tmp_path):
    """pdftotext fallback must not skip vision figure blocks (regression:
    14 Econ files took the fallback and lost all their diagrams)."""
    from app.ingest import extractor as ex

    f = tmp_path / "notes.pdf"
    f.write_bytes(b"%PDF-fake")
    monkeypatch.setattr(ex, "_markitdown", lambda path: "| a | b |\n| c | d |\n" * 10)
    monkeypatch.setattr(ex, "_pdftotext_per_page", lambda path: [(1, "real text")])
    monkeypatch.setattr(
        ex, "_figure_blocks",
        lambda path: ['<image-text page="1" image="1">\nA demand curve.\n</image-text>'])
    text, status, pages = ex.extract_text(f, "pdf")
    assert status == "ok"
    assert pages == [(1, "real text")]
    assert "A demand curve." in text
    assert "real text" in text
