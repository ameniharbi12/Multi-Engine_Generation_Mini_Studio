"""Capture the runtime environment, so hash differences can be explained honestly."""
from __future__ import annotations

import platform
from importlib import metadata


def capture_environment() -> dict:
    try:
        pillow = metadata.version("pillow")
    except metadata.PackageNotFoundError:
        pillow = None
    return {"python": platform.python_version(), "pillow": pillow, "os": platform.system()}


def describe_differences(stored: dict, current: dict) -> list[str]:
    """Human readable list of what changed between two environments."""
    return [
        f"{key} was {stored.get(key)}, now {current.get(key)}"
        for key in sorted(set(stored) | set(current))
        if stored.get(key) != current.get(key)
    ]
