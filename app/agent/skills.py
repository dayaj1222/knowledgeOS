"""Skill system — a minimal, extensible registry.

A Skill is a named capability the agent can invoke. Future skills (web search,
shell commands, file ops) register here WITHOUT touching agent core — they
just implement the Skill protocol and get added to the registry.

For now the registry is empty by design; the protocol is what matters so
adding skills later is a drop-in, not a refactor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class Skill(Protocol):
    """A named capability. Implemented by future skills (search, commands...)."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    async def run(self, **kwargs: Any) -> Any: ...


@dataclass
class SkillRegistry:
    """Holds registered skills; the agent introspects this to expose tools."""

    _skills: dict[str, Skill]

    def __init__(self) -> None:
        self._skills = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def all(self) -> list[Skill]:
        return list(self._skills.values())


# The process-wide registry. Import this and .register() your skill.
registry = SkillRegistry()
