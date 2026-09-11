"""Structured chunker: cuts along markdown structure, never blindly.

Contract: headings open chunks (section_path), tables/fences/figures/lists
are atomic, oversized prose splits at sentences, boilerplate stripped with
a report, no text ever dropped.
"""

from app.ingest.chunker import chunk_text, strip_boilerplate

DOC = """# Priority Inversion

A low task holds a resource the high task needs.

## Bounded Waiting

- Rule one: inherit priority.
- Rule two: release promptly.

| Step | Action |
| ---- | ------ |
| 1 | Inherit |
| 2 | Release |

# Deadlocks

Four conditions must all hold.
"""


def test_headings_open_sections():
    chunks = chunk_text(DOC)
    paths = [c["section_path"] for c in chunks]
    assert any("Priority Inversion" in p for p in paths)
    assert any(p == "Deadlocks" or p.endswith("Deadlocks") for p in paths)


def test_table_never_splits():
    big_table = "# T\n\n" + "\n".join(
        ["| A | B |", "| --- | --- |"] + [f"| {i} | x |" for i in range(60)]
    )
    chunks = chunk_text(big_table)
    table_chunks = [c for c in chunks if "| A | B |" in c["content"]]
    assert len(table_chunks) == 1
    assert "| 59 | x |" in table_chunks[0]["content"]


def test_list_stays_together():
    chunks = chunk_text(DOC)
    together = [c for c in chunks if "Rule one" in c["content"]]
    assert len(together) == 1
    assert "Rule two" in together[0]["content"]


def test_boilerplate_stripped_with_report():
    md = "Module 3\n\n# Real Content\n\ntext here\n\nModule 3\n\nMore\n\nModule 3\n\nEnd"
    clean, stripped = strip_boilerplate(md)
    assert "Module 3" in stripped
    assert "Module 3" not in clean
    assert "# Real Content" in clean  # headings are content, never stripped


def test_code_fences_and_tables_exempt_from_stripping():
    md = "```\nModule 3\n```\n\n# T\n\nbody\n\nModule 3\n\ntail\n\nModule 3\n\nend"
    clean, stripped = strip_boilerplate(md)
    assert "```\nModule 3\n```" in clean  # fenced occurrence survives


def test_no_text_dropped():
    chunks = chunk_text(DOC)
    joined = "\n".join(c["content"] for c in chunks)
    for needle in ["low task holds", "Rule one", "Inherit", "Four conditions"]:
        assert needle in joined


def test_index_order_dense_and_paths_present():
    chunks = chunk_text(DOC)
    assert [c["index_order"] for c in chunks] == list(range(len(chunks)))
    assert all("section_path" in c for c in chunks)


def test_long_prose_splits_at_sentences():
    prose = "# Essay\n\n" + " ".join(f"Sentence number {i} makes a claim." for i in range(120))
    chunks = chunk_text(prose)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c["content"]) // 4 <= 900  # cap respected (soft for atomic)


def test_empty_input_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []
