"""Eval: deterministic tagger precision on the golden set (>= 0.8)."""

import json
from pathlib import Path

from app.ingest.tagger import assign_passages

GOLDEN = json.loads((Path(__file__).parent / "tagger_golden.json").read_text())


def test_golden_precision():
    cases = GOLDEN["cases"]
    out = assign_passages(
        [
            {"id": c["id"], "content": c["content"], "section_path": c["section_path"]}
            for c in cases
        ],
        GOLDEN["topics"],
    )
    hits = sum(1 for c in cases if out[c["id"]]["primary"] == c["expected"])
    precision = hits / len(cases)
    assert precision >= 0.8, f"tagger precision {precision:.2f} ({hits}/{len(cases)})"
