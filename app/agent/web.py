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
