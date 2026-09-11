"""Deterministic passage→topic assignment. No LLM.

Each topic contributes weighted terms (name ×3, description ×1, stemmed,
stopword-filtered). A chunk scores matched_weight / total_topic_weight, plus
a heading bonus when the chunk's section names the topic outright. Best
score above threshold wins; strong runners-up are kept as extras.

Why deterministic: uploads are module-scoped (≤ ~15 topics), so the choice
set is small and vocabulary overlap decides correctly. The LLM tagger's
failure mode was confident misfiling with no audit trail; here every
assignment carries its score and matched terms.
"""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[a-z][a-z0-9+#-]*")

_STOPWORDS = frozenset(
    "the a an and or of to in on for with is are was were be been by as at "
    "from that this it its into over under about between through during each "
    "such other more most some any all can will just than then there their "
    "what when which who how why not no yes do does did done have has had "
    "having would could should may might must shall will you your we our they "
    "them his her him she its our ours yours theirs this that these those am "
    "an if else also very really much many lot thing things get got going go "
    "goes one two three use used using make made like know look see saw show "
    "shown take took part because while where here out off per via within "
    "will would can could should there their what which when who whom whose "
    "this that these those then than thus hence while where when how what "
    "such only own same than too very".split()
)

NAME_WEIGHT = 3.0
DESC_WEIGHT = 1.0
HEADING_BONUS = 0.25
ASSIGN_THRESHOLD = 0.25
EXTRA_THRESHOLD = 0.45


def _stem(word: str) -> str:
    # crude English plural strip — enough for topic vocabulary matching
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("sses", "shes", "ches")):
        return word[:-2]
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _terms(text: str) -> set[str]:
    return {
        _stem(w)
        for w in _WORD_RE.findall((text or "").lower())
        if w not in _STOPWORDS and len(w) > 2
    }


def topic_terms(name: str, description: str = "") -> dict[str, float]:
    """Weighted term map for one topic: name terms ×3, description ×1."""
    weights: dict[str, float] = {}
    for t in _terms(name):
        weights[t] = weights.get(t, 0.0) + NAME_WEIGHT
    for t in _terms(description or ""):
        weights[t] = weights.get(t, 0.0) + DESC_WEIGHT
    return weights


def score_chunk(
    content: str, section_path: str, terms: dict[str, float]
) -> tuple[float, list[str]]:
    """(score 0..1, matched terms) of one chunk against one topic."""
    if not terms:
        return 0.0, []
    chunk = _terms(content) | _terms(section_path)
    matched = [t for t in terms if t in chunk]
    total = sum(terms.values())
    score = sum(terms[t] for t in matched) / total if total else 0.0
    section_terms = _terms(section_path)
    if any(t in section_terms for t in terms):
        score = min(1.0, score + HEADING_BONUS)
    return round(score, 3), sorted(matched)


def assign_passages(
    passages: list[dict], topics: list[dict]
) -> dict[int, dict]:
    """Deterministic assignment → {passage_id: {primary, extras, confidence}}.

    passages: [{id, content, section_path?}]; topics: [{id, name, description?}].
    primary is None when nothing clears ASSIGN_THRESHOLD (stays untagged and
    visible instead of force-filed).
    """
    term_maps = {
        int(t["id"]): topic_terms(t.get("name", ""), t.get("description", ""))
        for t in topics
    }
    out: dict[int, dict] = {}
    for p in passages:
        pid = int(p["id"])
        content = p.get("content", "")
        section = p.get("section_path", "")
        scored = [
            (tid, *score_chunk(content, section, terms))
            for tid, terms in term_maps.items()
        ]
        scored.sort(key=lambda s: s[1], reverse=True)
        primary = None
        confidence = 0.0
        extras: list[int] = []
        if scored and scored[0][1] >= ASSIGN_THRESHOLD:
            primary, confidence = scored[0][0], scored[0][1]
            extras = [tid for tid, s, _ in scored[1:] if s >= EXTRA_THRESHOLD]
        out[pid] = {
            "primary": primary,
            "extras": extras,
            "confidence": confidence,
            "matched": scored[0][2] if scored else [],
        }
    return out
