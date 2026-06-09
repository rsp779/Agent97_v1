from __future__ import annotations  # 🧠 MUST BE LINE 1 (or right below top-level docstring)

from typing import Annotated, TypedDict, List, Dict, Any
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """Global execution matrix handling messages, security metadata, and tracking keys.

    * ``messages`` – a list of messages, automatically extended by the
      ``add_messages`` annotation from LangGraph.
    * ``is_in_scope`` – a flag indicating whether the current execution context
      is within the permitted scope.
    * ``customer_id`` – the permanent global primary key used across everything.
    * ``extracted_data`` – a dictionary that stores data extracted from
      messages or external sources.
    """
    messages: Annotated[List[Any], add_messages]
    is_in_scope: bool
    customer_id: str
    extracted_data: Dict[str, Any]


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def initialise_state(customer_id: str) -> AgentState:
    """Create a fresh ``AgentState`` with sensible defaults."""
    return AgentState(
        messages=[],
        is_in_scope=False,
        customer_id=customer_id,
        extracted_data={},
    )


def add_message(state: AgentState, message: Any) -> None:
    """Append a single message to ``state['messages']``."""
    state.setdefault("messages", []).append(message)


def append_short_term_memory(state: AgentState, memory: Any) -> None:
    """Add a turn-level memory entry for the current session."""
    extracted = state.setdefault("extracted_data", {})
    history = extracted.setdefault("short_term_memory", [])
    history.append(memory)
    if len(history) > 10:
        history.pop(0)


def update_extracted(state: AgentState, **kwargs: Any) -> None:
    """Merge key/value pairs into ``state['extracted_data']``."""
    state.setdefault("extracted_data", {}).update(kwargs)