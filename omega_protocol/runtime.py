"""Runtime helpers for bundled and source-based execution."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_root() -> Path:
    """Return the root directory for bundled resources."""

    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(bundled_root)
    return Path(__file__).resolve().parent.parent


def application_root() -> Path:
    """Return the directory that contains the running executable or script."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def packaged_resource(*parts: str) -> Path:
    """Resolve a resource path in both source and frozen builds."""

    return resource_root().joinpath(*parts)
