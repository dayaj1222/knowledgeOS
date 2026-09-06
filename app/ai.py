"""Live LLM client (OpenAI-compatible) + content-understanding helpers.

Calls the local model at :9173/v1 (EXPERT by default) for the tasks that
need semantic judgment:

- extract_syllabus_topics  — syllabus text -> [{module_name, topics:[...]}]
- tag_passages_to_topics   — passages + candidate topics -> per-passage topic ids

Passage grounding downstream is plain SQL on topic_id, not vectors.
"""

from __future__ import annotations

import json
import os

import httpx

LLM_BASE_URL = os.environ.get("KB_LLM_BASE_URL", "http://127.0.0.1:9173/v1")
LLM_MODEL = os.environ.get("KB_LLM_MODEL", "EXPERT")
_HTTP_TIMEOUT = 300.0  # local model can be slow


async def _chat(messages: list[dict], temperature: float = 0.2) -> str:
    """One-shot chat completion against the local OpenAI-compatible endpoint."""
    msg = await chat_with_tools(messages, temperature=temperature)
    return msg.get("content") or ""


async def chat_with_tools(
    messages: list[dict],
    tools: list[dict] | None = None,
    temperature: float = 0.2,
    tool_choice: str = "auto",
) -> dict:
    """Chat completion with native OpenAI tool-calling. Returns the raw
    assistant message dict (may contain `tool_calls`)."""
    payload: dict = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.post(f"{LLM_BASE_URL}/chat/completions", json=payload)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]


async def chat_stream(messages: list[dict], tools: list[dict] | None = None):
    """Stream a chat completion. Yields ("token", text) deltas, then finally
    ("done", {"content": str, "tool_calls": [...]}). Tool-call argument
    fragments are accumulated by index — some gateways stream them in pieces.
    """
    payload: dict = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    content_parts: list[str] = []
    pending: dict[int, dict] = {}
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        async with client.stream(
            "POST", f"{LLM_BASE_URL}/chat/completions", json=payload
        ) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                if delta.get("content"):
                    content_parts.append(delta["content"])
                    yield ("token", delta["content"])
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    slot = pending.setdefault(
                        idx, {"id": None, "name": None, "args": ""}
                    )
                    slot["id"] = tc.get("id") or slot["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] = fn["name"]
                    if fn.get("arguments"):
                        slot["args"] += fn["arguments"]
    calls = [
        {
            "id": slot["id"],
            "function": {"name": slot["name"], "arguments": slot["args"]},
        }
        for slot in pending.values()
        if slot["name"]
    ]
    yield ("done", {"content": "".join(content_parts), "tool_calls": calls})


def _extract_json(text: str) -> dict | list:
    """Pull the first JSON object/array out of an LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start == -1:
        raise ValueError("no JSON in response")
    # find matching close by scanning
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("unterminated JSON in response")


async def extract_syllabus_topics(syllabus_text: str) -> list[dict]:
    """Parse a syllabus into modules + topics.

    Returns [{"module": str, "topics": [{"name": str, "description": str}]}].
    """
    prompt = (
        "You are parsing a university course syllabus. Extract the module structure "
        "and topics. Return ONLY JSON (no prose) in this exact shape:\n"
        '[{"module": "Module name", "topics": [{"name": "Topic name", '
        '"description": "One-sentence description"}]}]\n\n'
        f"Syllabus:\n{syllabus_text[:12000]}"
    )
    raw = await _chat([
        {"role": "system", "content": "You extract structured data from syllabi. JSON only."},
        {"role": "user", "content": prompt},
    ])
    parsed = _extract_json(raw)
    if not isinstance(parsed, list):
        raise ValueError("expected a list of modules")
    return parsed


async def tag_passages_to_topics(
    passages: list[dict], topics: list[dict]
) -> dict[int, list[int]]:
    """Assign each passage to the best-matching topic(s).

    passages: [{"id": int, "content": str}]
    topics:   [{"id": int, "name": str}]
    Returns:  {passage_id: [topic_id, ...]} (empty list = no good match).
    """
    if not topics:
        return {p["id"]: [] for p in passages}

    topic_list = "\n".join(f"- id {t['id']}: {t['name']}" for t in topics)
    passages_list = "\n\n".join(
        f"PASSAGE {p['id']}:\n{p['content'][:1500]}" for p in passages
    )
    prompt = (
        "Match each passage to the topic(s) it belongs to. A passage may match "
        "zero or more topics. Return ONLY JSON (no prose) as an object mapping "
        "passage id (integer) to a list of topic ids (integers), e.g. "
        '{"1": [3], "2": [3, 5], "3": []}.\n\n'
        f"TOPICS:\n{topic_list}\n\nPASSAGES:\n{passages_list}"
    )
    raw = await _chat([
        {"role": "system", "content": "You associate text passages with topics. JSON only."},
        {"role": "user", "content": prompt},
    ])
    parsed = _extract_json(raw)
    if not isinstance(parsed, dict):
        raise ValueError("expected an object mapping passage ids to topic ids")
    # normalize keys to int and values to list[int]
    result: dict[int, list[int]] = {}
    for k, v in parsed.items():
        pid = int(k)
        tids = [int(x) for x in v] if isinstance(v, list) else []
        result[pid] = tids
    return result


async def is_available() -> bool:
    """True if the LLM endpoint answers a trivial ping."""
    try:
        await _chat([{"role": "user", "content": "ping"}], temperature=0.0)
        return True
    except Exception:
        return False
