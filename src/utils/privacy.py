from __future__ import annotations

from typing import Any


def strip_reasoning_fields(value: Any) -> Any:
    """Recursively remove private model-reasoning fields from transport data."""
    if isinstance(value, dict):
        return {
            key: strip_reasoning_fields(item)
            for key, item in value.items()
            if str(key).lower() != "reasoning"
        }
    if isinstance(value, list):
        return [strip_reasoning_fields(item) for item in value]
    if isinstance(value, tuple):
        return tuple(strip_reasoning_fields(item) for item in value)
    return value
