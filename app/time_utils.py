"""Single source of the current time for VALBRICK.

Contract: every datetime the application persists (SQLite DateTime columns and
ISO strings stored in Config) is *naive UTC*. SQLite has no time-zone type and
SQLAlchemy returns stored values without tzinfo, so mixing in timezone-aware
values would raise ``TypeError`` on comparison (e.g. a shortage deadline read
back from the database). ``utc_now()`` keeps that contract and replaces the
deprecated ``datetime.utcnow()`` (deprecated in Python 3.12): same value, same
type, no data migration.
"""
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Current UTC time as a naive datetime (the persisted convention)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
