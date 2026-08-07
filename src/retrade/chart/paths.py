"""Chart package helpers."""

from __future__ import annotations

from importlib import resources
from pathlib import Path


def chart_web_dir() -> Path:
    """Return filesystem path to bundled Lightweight Charts web assets."""
    root = resources.files("retrade.chart") / "web"
    # Prefer Traversable as Path when possible (editable install).
    return Path(str(root))
