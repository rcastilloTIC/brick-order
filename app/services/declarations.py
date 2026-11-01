from __future__ import annotations

import os
from typing import Optional

from flask import current_app

from app.models import Config, User

_ISSUE_KEY_PREFIX = "user_decl_issue_"


def _issue_key(user_id: int) -> str:
    return f"{_ISSUE_KEY_PREFIX}{user_id}"


def get_declaration_issue(user_id: int) -> str:
    """Return the persistent warning shown to a user when their DJ was rejected."""
    return Config.get(_issue_key(user_id)) or ""


def set_declaration_issue(user_id: int, message: Optional[str]) -> None:
    """Store a warning message so the user knows their previous DJ was invalid."""
    Config.set(_issue_key(user_id), (message or "").strip())


def clear_declaration_issue(user_id: int) -> None:
    """Remove any stored warning for the given user."""
    Config.set(_issue_key(user_id), "")


def remove_declaration_file(user: User) -> bool:
    """Delete the stored DJ file from disk and reset the DB fields."""
    removed = False
    folder = current_app.config.get("DECLARATION_UPLOAD_FOLDER")
    had_file = bool(user.declaration_file)
    if had_file and folder:
        path = os.path.join(folder, user.declaration_file)
        try:
            if os.path.exists(path):
                os.remove(path)
                removed = True
        except OSError:
            pass
    if had_file:
        removed = removed or True
    user.declaration_file = None
    user.declaration_validated = False
    return removed
