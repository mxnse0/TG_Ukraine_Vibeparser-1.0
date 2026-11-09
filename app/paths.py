"""Filesystem locations that work both from source and from a frozen .exe."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """True when the code runs from a PyInstaller executable."""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Directory that holds .env and the data folder.

    For a frozen app this is the folder next to the .exe, not the temporary
    extraction directory (``sys._MEIPASS``), so settings and the database
    survive restarts and are easy to find.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """Directory with bundled read-only resources (templates, data files)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_dir())).resolve()
    return app_dir()


BASE_DIR = app_dir()
RESOURCE_DIR = resource_dir()
