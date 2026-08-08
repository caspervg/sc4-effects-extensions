"""Application version and display-title helpers."""

import os
from importlib import metadata

VERSION = "0.1.0"


def get_version() -> str:
    """Return the baked release version, with an override for local builds."""
    override = os.environ.get("EFFDIR_EDITOR_VERSION")
    if override:
        return override.removeprefix("v")
    if VERSION:
        return VERSION
    try:
        return metadata.version("effdir-editor")
    except metadata.PackageNotFoundError:
        return "unknown"


def app_title(document: str | None = None) -> str:
    """Build the versioned main-window title."""
    title = f"EFFDIR Editor {get_version()}"
    return f"{title} — {document}" if document else title
