"""App configuration — loads config.toml with env-var override.

Precedence (highest wins): env vars, then config.toml, then built-in defaults.
Mirrors the pattern used in the deepseek proxy so decisions like batch size are
tunable without code edits.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("KB_CONFIG", str(ROOT / "config.toml")))


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (FileNotFoundError, OSError, tomllib.TOMLDecodeError):
        return {}


_TOML = _load_toml(CONFIG_PATH)


def _get(section: str, key: str, default: Any) -> Any:
    env = os.environ.get(f"KB_{section.upper()}_{key.upper()}")
    if env is not None:
        return env
    return _TOML.get(section, {}).get(key, default)


@dataclass(frozen=True)
class LLMConfig:
    base_url: str = field(default_factory=lambda: _get("llm", "base_url", "http://127.0.0.1:9173/v1"))
    model: str = field(default_factory=lambda: _get("llm", "model", "EXPERT"))


@dataclass(frozen=True)
class AgentConfig:
    tag_batch_size: int = field(default_factory=lambda: int(_get("agent", "tag_batch_size", 5)))
    tag_parallel: bool = field(default_factory=lambda: str(_get("agent", "tag_parallel", "false")).lower() in ("1", "true", "yes", "on"))


@dataclass(frozen=True)
class IngestConfig:
    chunk_tokens: int = field(default_factory=lambda: int(_get("ingest", "chunk_tokens", 800)))
    overlap_tokens: int = field(default_factory=lambda: int(_get("ingest", "overlap_tokens", 100)))
    max_upload_mb: int = field(default_factory=lambda: int(_get("ingest", "max_upload_mb", 50)))


@dataclass(frozen=True)
class Settings:
    llm: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    ingest: IngestConfig = field(default_factory=IngestConfig)


settings = Settings()
