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
