"""Regression tests for defensive backup extraction (pytest)."""
from pathlib import Path
import zipfile
import pytest
from app.services.backups import _safe_extract, RestoreError

@pytest.mark.parametrize("entry", ["../escape", "/tmp/escape", "one/../../escape", "C:/escape", "dir\\escape"])
def test_disallows_unsafe_members(tmp_path, entry):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(entry, "secret")
    with pytest.raises(RestoreError):
        _safe_extract(str(archive), str(tmp_path / "out"))

def test_valid_archive_extracts(tmp_path):
    archive = tmp_path / "safe.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("manifest.json", "{}")
        z.writestr("exports/order.txt", "ok")
    dest = tmp_path / "out"
    _safe_extract(str(archive), str(dest))
    assert (dest / "exports/order.txt").read_text() == "ok"

def test_rejects_duplicate_members(tmp_path):
    archive = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("manifest.json", "one")
        z.writestr("manifest.json", "two")
    with pytest.raises(RestoreError):
        _safe_extract(str(archive), str(tmp_path / "out"))
