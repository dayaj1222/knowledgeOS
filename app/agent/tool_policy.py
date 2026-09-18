"""Model-visible tool policy for the local tutor agent."""

from ..config import settings

# These tools cross the normal application boundary. Confirmation text is not
# a security boundary against prompt injection, so they require local opt-in.
ADMIN_TOOLS = frozenset({"db_query", "db_modify"})
CODE_TOOLS = frozenset({"run_code", "plot_chart"})


def tool_enabled(name: str) -> bool:
    if name in ADMIN_TOOLS:
        return settings.agent.enable_admin_tools
    if name in CODE_TOOLS:
        return settings.agent.enable_code_execution
    return True
