"""Web capability for the tutor agent — search + page fetch.

Clean split from tutor_tools.py on purpose:

- This module owns ALL HTTP/outbound logic (DuckDuckGo search, page fetch,
  HTML→text). It is pure: no DB, no models, no confirmation protocol.
- tutor_tools.py owns the TOOL REGISTRY (signatures, descriptions, dispatch).
  It imports thin wrappers from here and registers them in TOOLS.

Both tools are read-only → no confirmation step, same as search_knowledge.
"""

from __future__ import annotations

import html as _html
import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

DDG_ENDPOINT = "https://api.duckduckgo.com/"
DDG_HTML_ENDPOINT = "https://html.duckduckgo.com/html/"
WIKI_ENDPOINT = "https://en.wikipedia.org/w/api.php"
HTTP_TIMEOUT = 15.0
SEARCH_TIMEOUT = 20.0
MAX_RESULTS = 6
FETCH_DEFAULT_CHARS = 3000
FETCH_MAX_CHARS = 8000

# Browser-like headers: DDG's bot blocker challenges bare/script UAs.
# Verified live — GET with a plain UA gets the anomaly-modal page; POST
# with these headers returns 10 clean results.
_DDG_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://html.duckduckgo.com/",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
}

_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


# ---------- search ----------


def _flatten_related(topics: list[dict], out: list[dict]) -> None:
    """DDG nests results under 'Topics' groups — flatten recursively."""
    for t in topics:
        if not isinstance(t, dict):
            continue
        if "Topics" in t and isinstance(t["Topics"], list):
            _flatten_related(t["Topics"], out)
        elif t.get("FirstURL") or t.get("Text"):
            out.append(t)


def search_web(query: str, count: int = 5) -> dict:
    """Public-web search with no API key.

    Chain (first non-empty wins):
    1. DDG Instant Answer — entity summaries (fast, narrow).
    2. DDG HTML endpoint — full organic results via POST + browser headers.
    3. Wikipedia search API — reliable fallback, great for study topics.

    Returns {"results": [{title, url, snippet}], "source": ...} — empty list
    (not an exception) when nothing found, so the tutor degrades gracefully.
    """
    query = query.strip()
    if not query:
        return {"results": [], "error": "empty query"}
    count = max(1, min(int(count or 5), MAX_RESULTS))
    results = _ddg_search(query, count)
    if results:
        return {"results": results, "source": "ddg-instant"}
    results = _ddg_html_search(query, count)
    if results:
        return {"results": results, "source": "ddg"}
    results = _wiki_search(query, count)
    return {"results": results, "source": "wikipedia"}


def _ddg_search(query: str, count: int) -> list[dict]:
    """DDG Instant Answer → [{title, url, snippet}]. Empty when DDG has nothing."""
    params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
    try:
        r = httpx.get(DDG_ENDPOINT, params=params, timeout=HTTP_TIMEOUT,
                      headers={"User-Agent": "knowledge-base-tutor/1.0"})
        r.raise_for_status()
        data = r.json()
    except Exception:  # noqa: BLE001 — fall through to Wikipedia
        return []

    flat: list[dict] = []
    _flatten_related(data.get("RelatedTopics") or [], flat)
    results: list[dict] = []
    abstract_url = (data.get("AbstractURL") or "").strip()
    abstract_text = (data.get("AbstractText") or "").strip()
    if abstract_url and abstract_text:
        results.append({
            "title": data.get("Heading") or abstract_url,
            "url": abstract_url,
            "snippet": abstract_text[:400],
        })
    for t in flat:
        if len(results) >= count:
            break
        url = str(t.get("FirstURL") or "").strip()
        text = str(t.get("Text") or "").strip()
        if not url or not text:
            continue
        title, _, snippet = text.partition(" - ")
        results.append({
            "title": (title or url)[:200],
            "url": url,
            "snippet": (snippet or text)[:400],
        })
    return results[:count]


_RESULT_LINK_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
_SNIPPET_RE = re.compile(
    r'class="result__snippet"[^>]*>(.*?)</', re.DOTALL)


def _unwrap_ddg_link(href: str) -> str | None:
    """DDG routes clicks through /l/?uddg=<encoded real url> — decode it."""
    href = (href or "").strip()
    if href.startswith("//"):
        href = "https:" + href
    parts = urlparse(href)
    if "uddg" in (parts.query or ""):
        target = parse_qs(parts.query).get("uddg", [None])[0]
        if target:
            return unquote(target)
    if parts.scheme in ("http", "https"):
        return href
    return None


def _ddg_html_search(query: str, count: int) -> list[dict]:
    """DDG organic results via the no-JS HTML endpoint.

    Must be POST with form data + browser headers — GET gets the bot
    challenge page. Single first page only (no vqd needed for page 1).
    """
    try:
        r = httpx.post(
            DDG_HTML_ENDPOINT,
            data={"q": query, "kl": "us-en", "b": ""},
            headers=_DDG_HEADERS,
            timeout=SEARCH_TIMEOUT,
        )
        r.raise_for_status()
        body = r.text
    except Exception:  # noqa: BLE001 — fall through to Wikipedia
        return []
    if "anomaly-modal" in body:
        return []
    links = _RESULT_LINK_RE.findall(body)
    snippets = _SNIPPET_RE.findall(body)
    out = []
    for i, (href, title_html) in enumerate(links):
        if len(out) >= count:
            break
        url = _unwrap_ddg_link(_html.unescape(href))
        title = _html_to_text(title_html)[:200]
        if not url or not title:
            continue
        snippet = _html_to_text(snippets[i])[:400] if i < len(snippets) else ""
        out.append({"title": title, "url": url, "snippet": snippet})
    return out


def _wiki_search(query: str, count: int) -> list[dict]:
    """Wikipedia full-text search → [{title, url, snippet}]. No key needed."""
    params = {"action": "query", "list": "search", "srsearch": query,
              "format": "json", "srlimit": count}
    try:
        r = httpx.get(WIKI_ENDPOINT, params=params, timeout=HTTP_TIMEOUT,
                      headers={"User-Agent": "knowledge-base-tutor/1.0"})
        r.raise_for_status()
        hits = (r.json().get("query") or {}).get("search") or []
    except Exception:  # noqa: BLE001 — empty results degrade gracefully
        return []
    out = []
    for h in hits[:count]:
        title = str(h.get("title") or "").strip()
        if not title:
            continue
        url = "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")
        out.append({"title": title, "url": url,
                    "snippet": _html_to_text(str(h.get("snippet") or ""))[:400]})
    return out


# ---------- video search (YouTube, no API key) ----------

_YT_WATCH_RE = re.compile(
    r"(?:youtube\.com/watch\?[^\"'\s]*?v=|youtu\.be/)([A-Za-z0-9_-]{11})"
)


def _video_id(url: str) -> str | None:
    """Pull the 11-char YouTube video id out of a watch/share URL."""
    m = _YT_WATCH_RE.search(url or "")
    return m.group(1) if m else None


def search_videos(query: str, count: int = 3) -> dict:
    """Find YouTube videos for a study topic — no API key.

    Reuses the DDG HTML endpoint restricted to youtube.com watch links, then
    derives embeds + thumbnails from the video id (both keyless conventions):
      embed:     https://www.youtube-nocookie.com/embed/{id}
      thumbnail: https://i.ytimg.com/vi/{id}/hqdefault.jpg

    Returns {"videos": [{video_id, title, url, embed_url, thumbnail,
    snippet}]} — titles/snippets only, no transcript, so the tutor must
    frame these as supplements to the passages, not syllabus truth.
    """
    query = query.strip()
    if not query:
        return {"videos": [], "error": "empty query"}
    count = max(1, min(int(count or 3), 5))
    hits = _ddg_html_search(f"site:youtube.com {query}", count * 2)
    videos: list[dict] = []
    seen: set[str] = set()
    for h in hits:
        vid = _video_id(h.get("url") or "")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        videos.append({
            "video_id": vid,
            "title": h.get("title") or vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "embed_url": f"https://www.youtube-nocookie.com/embed/{vid}",
            "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "snippet": h.get("snippet") or "",
        })
        if len(videos) >= count:
            break
    return {"videos": videos}


# ---------- transcript fetch + relevance (YouTube, no API key) ----------
# Method stolen from the hermes `youtube-content` skill: youtube-transcript-api
# v1.x pulls caption tracks keylessly. Used to VERIFY a found video actually
# covers the topic (keyword overlap vs the topic's own passages) instead of
# trusting the title.

TRANSCRIPT_MAX_CHARS = 6000

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
    "above after again against almost always among another anyone anything "
    "around away become becomes becoming before behind being below both but "
    "came cannot dear down either else elsewhere enough even ever every "
    "everyone everything everywhere except few first five following four "
    "further gave get gets getting given gives hence however indeed into "
    "itself keep keeps kept latter latterly least less made many meanwhile "
    "might mine more moreover myself namely neither never nevertheless next "
    "nine nobody none noone nor often once only onto others otherwise ours "
    "over own same seem seemed seeming seems seven several since six someone "
    "something sometime sometimes somewhere still stop though threw thru "
    "thus together toward towards twelve twenty twice upon us used very "
    "wanted wants way ways well went were whatever whereas whereby wherein "
    "whether whose within without yet your yourselves across behind beyond "
    "plus done end start middle entire whole half quarter bit put set fit "
    "even every full".split()
)

_WORD_RE = re.compile(r"[a-z][a-z0-9+#-]*")


def _keywords(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower()) if w not in _STOPWORDS and len(w) > 2}


def fetch_transcript(video_id: str, max_chars: int = TRANSCRIPT_MAX_CHARS) -> dict:
    """Pull a video's caption track as plain text (stolen pattern: v1.x fetch).

    Returns {"video_id", "language", "full_text"} truncated to max_chars, or
    {"video_id", "error"}. Never raises — failures degrade to unverified.
    """
    video_id = (video_id or "").strip()
    if not video_id:
        return {"video_id": video_id, "error": "empty video id"}
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {"video_id": video_id, "error": "youtube-transcript-api not installed"}
    try:
        result = YouTubeTranscriptApi().fetch(video_id)
        segs = list(result)
        language = getattr(result, "language_code", None) or getattr(result, "language", None) or ""
    except Exception as e:  # noqa: BLE001 — disabled/private/no-captions → unverified
        return {"video_id": video_id, "error": f"{type(e).__name__}: {e}"[:300]}
    full = " ".join(getattr(s, "text", "") for s in segs)
    full = _WS_RE.sub(" ", full).strip()
    if not full:
        return {"video_id": video_id, "error": "empty transcript"}
    limit = max(1000, min(int(max_chars or TRANSCRIPT_MAX_CHARS), 12000))
    return {"video_id": video_id, "language": language, "full_text": full[:limit],
            "truncated": len(full) > limit}


def score_relevance(transcript: str, topic_text: str, topic_name: str = "") -> dict:
    """Two-part overlap between a transcript and the topic's own text.

    0.6 × name coverage (fraction of the TOPIC NAME's keywords spoken in the
    video — a video truly about the topic says its name words) plus 0.4 ×
    passage overlap (fraction of the broader passage vocabulary present).
    Name-heavy on purpose: titles lie, but a 10-minute video on X says "X".

    Returns {"relevance": 0.0-1.0, "matched": [name hits + sample]}.
    """
    trans_keys = _keywords(transcript)
    name_keys = _keywords(topic_name)
    name_cov = len(name_keys & trans_keys) / len(name_keys) if name_keys else 0.0
    topic_keys = _keywords(topic_text)
    overlap = len(topic_keys & trans_keys) / len(topic_keys) if topic_keys else 0.0
    matched = sorted(name_keys & trans_keys) + sorted((topic_keys & trans_keys) - name_keys)[:8]
    return {"relevance": round(0.6 * name_cov + 0.4 * overlap, 3),
            "matched": matched[:12]}


# ---------- fetch ("curl a url") ----------


def _html_to_text(raw: str) -> str:
    """Minimal HTML→text: drop scripts/styles, strip tags, unescape, collapse."""
    no_script = _TAG_RE.sub(" ", raw)
    no_tags = _HTML_TAG_RE.sub(" ", no_script)
    return _WS_RE.sub(" ", _html.unescape(no_tags)).strip()


def _allowed_url(url: str) -> str | None:
    """Return an error string, or None if the URL is fetchable."""
    try:
        parts = urlparse(url.strip())
    except ValueError as e:
        return f"invalid URL: {e}"
    if parts.scheme not in ("http", "https"):
        return f"blocked scheme '{parts.scheme or '(none)'}' — http(s) only"
    if not parts.netloc:
        return "invalid URL: missing host"
    if parts.hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return "blocked host (loopback)"
    return None


def fetch_url(url: str, max_chars: int = FETCH_DEFAULT_CHARS) -> dict:
    """GET a page and return its text content (the agent's 'curl').

    Returns {"url", "content"} truncated to max_chars, or {"url", "error"}.
    Single request, bounded size/time — never raises on network failure.
    """
    url = (url or "").strip()
    if not url:
        return {"url": url, "error": "empty url"}
    blocked = _allowed_url(url)
    if blocked:
        return {"url": url, "error": blocked}
    limit = max(500, min(int(max_chars or FETCH_DEFAULT_CHARS), FETCH_MAX_CHARS))
    try:
        r = httpx.get(url, timeout=HTTP_TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": "knowledge-base-tutor/1.0"})
        r.raise_for_status()
        text = _html_to_text(r.text)
        return {"url": str(r.url), "content": text[:limit],
                "truncated": len(text) > limit}
    except Exception as e:  # noqa: BLE001 — network errors go back to the model
        return {"url": url, "error": f"{type(e).__name__}: {e}"}
