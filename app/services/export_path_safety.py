"""Resolve only regular export files directly within the configured directory."""
from pathlib import Path


def safe_export_path(folder, filename, *, suffix=None):
    if not isinstance(filename, str) or not filename or filename in (".", ".."):
        return None
    if filename != Path(filename).name or "/" in filename or "\\" in filename:
        return None
    if suffix is not None and not filename.lower().endswith(suffix.lower()):
        return None
    base = Path(folder).resolve()
    candidate = base / filename
    try:
        # Resolve symlinks: a link pointing outside the export directory is invalid.
        if candidate.resolve().parent != base or not candidate.is_file():
            return None
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate
