from typing import Any


def update_state(state: dict[str, Any], **updates: Any) -> dict[str, Any]:
    """Single-writer merge point for fields owned by a supervisor stage."""
    return {**state, **updates}
