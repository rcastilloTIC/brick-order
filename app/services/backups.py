"""Backup and restore helpers for phase transitions."""

from __future__ import annotations
from app.services.campaign_phase import set_campaign_phase

import json
import os
import shutil
import sqlite3
import tempfile
import traceback
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

from flask import current_app

from app.models import Config

MANIFEST_NAME = "manifest.json"


class BackupError(Exception):
    """Raised when creating a backup fails."""


class RestoreError(Exception):
    """Raised when restoring from a backup fails."""


def _db_path() -> str:
    uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    prefix = "sqlite:///"
    if not uri.startswith(prefix):
        raise BackupError("Solo se admiten backups con SQLite.")
    path = uri[len(prefix) :]
    if not path:
        raise BackupError("Ruta de base de datos SQLite no encontrada.")
    return path


def _copy_sqlite(src_path: str, dest_path: str) -> None:
    if not os.path.exists(src_path):
        raise BackupError(f"No se encontró la base de datos en {src_path}.")
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with sqlite3.connect(f"file:{src_path}?mode=ro", uri=True) as src_conn:
        with sqlite3.connect(dest_path) as dest_conn:
            src_conn.backup(dest_conn)


def _copy_optional_folder(src: str, dest: str) -> None:
    if not src:
        return
    if os.path.isdir(dest):
        shutil.rmtree(dest, ignore_errors=True)
    if os.path.isdir(src):
        shutil.copytree(src, dest)
    else:
        os.makedirs(dest, exist_ok=True)


def _zip_directory(source_dir: str, target_zip: str) -> None:
    with zipfile.ZipFile(target_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(source_dir):
            for filename in files:
                full_path = os.path.join(root, filename)
                arcname = os.path.relpath(full_path, source_dir)
                zf.write(full_path, arcname)


def _safe_extract(zip_path: str, dest_dir: str) -> None:
    """Unpack a trusted-format backup defensively.

    Reject zip-slip paths, symlinks, duplicate names, excessive file counts,
    and oversized decompressed archives before touching the destination.
    A backup is sensitive input even when it came from an administrator.
    """
    import stat
    from pathlib import PurePosixPath

    max_files = 10000
    max_uncompressed = 2 * 1024 * 1024 * 1024
    target_root = Path(dest_dir).resolve()
    with zipfile.ZipFile(zip_path, "r") as archive:
        infos = archive.infolist()
        if len(infos) > max_files:
            raise RestoreError("El ZIP contiene demasiados archivos.")
        if sum(info.file_size for info in infos) > max_uncompressed:
            raise RestoreError("El ZIP supera el tamaño máximo permitido.")
        seen = set()
        for info in infos:
            # ZIP member names use forward slashes regardless of host OS.
            name = info.filename
            path = PurePosixPath(name)
            if (not name or "\\" in name or path.is_absolute()
                    or any(part in ("", ".", "..") for part in path.parts)
                    or name.startswith("/") or ":" in path.parts[0]):
                raise RestoreError("El ZIP contiene rutas no seguras.")
            normalized = str(path).rstrip("/")
            if normalized in seen:
                raise RestoreError("El ZIP contiene nombres duplicados.")
            seen.add(normalized)
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise RestoreError("El ZIP contiene enlaces simbólicos.")
            resolved = (target_root / normalized).resolve()
            if not resolved.is_relative_to(target_root):
                raise RestoreError("El ZIP contiene rutas fuera del destino.")
        archive.extractall(target_root)


def create_phase_backup(*, phase_at_backup: str, target_phase: str) -> str:
    """Create a ZIP with DB + user files and record it on disk."""
    backup_dir = current_app.config.get("BACKUP_FOLDER")
    if not backup_dir:
        raise BackupError("BACKUP_FOLDER no está configurado.")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    archive_name = f"backup_{phase_at_backup}_to_{target_phase}_{timestamp}.zip"
    archive_path = os.path.join(backup_dir, archive_name)

    temp_dir = tempfile.mkdtemp(prefix="backup_tmp_")
    try:
        db_src = _db_path()
        db_dest = os.path.join(temp_dir, "database.sqlite3")
        _copy_sqlite(db_src, db_dest)

        declarations_src = current_app.config.get("DECLARATION_UPLOAD_FOLDER")
        exports_src = current_app.config.get("ORDER_EXPORT_FOLDER")
        _copy_optional_folder(declarations_src, os.path.join(temp_dir, "declarations"))
        _copy_optional_folder(exports_src, os.path.join(temp_dir, "exports"))

        manifest: Dict[str, str | Dict[str, str]] = {
            "version": 1,
            "created_at": datetime.utcnow().isoformat(),
            "phase_at_backup": phase_at_backup,
            "target_phase": target_phase,
            "db_filename": os.path.basename(db_dest),
            "paths": {
                "declarations": "declarations",
                "exports": "exports",
            },
        }
        manifest_path = os.path.join(temp_dir, MANIFEST_NAME)
        with open(manifest_path, "w", encoding="utf-8") as manifest_file:
            json.dump(manifest, manifest_file, indent=2)

        _zip_directory(temp_dir, archive_path)

        Config.set("last_backup_file", archive_path)
        Config.set("last_backup_phase", phase_at_backup)
        Config.set("last_backup_target_phase", target_phase)
        Config.set("last_backup_created_at", manifest["created_at"])
        Config.set("last_backup_error_log", "")
        return archive_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def restore_backup(zip_path: str) -> Dict[str, str]:
    """Restore DB and files from a ZIP; force phase to manifest target."""
    if not zip_path or not os.path.isfile(zip_path):
        raise RestoreError("Archivo de backup no encontrado.")

    temp_dir = tempfile.mkdtemp(prefix="restore_tmp_")
    try:
        _safe_extract(zip_path, temp_dir)
        manifest_file = os.path.join(temp_dir, MANIFEST_NAME)
        if not os.path.exists(manifest_file):
            raise RestoreError("El backup no tiene manifest.json.")
        with open(manifest_file, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)

        target_phase = manifest.get("target_phase")
        phase_at_backup = manifest.get("phase_at_backup")
        db_filename = manifest.get("db_filename", "database.sqlite3")
        if not target_phase or not phase_at_backup:
            raise RestoreError("El manifest no incluye las fases requeridas.")

        db_src = os.path.join(temp_dir, db_filename)
        if not os.path.isfile(db_src):
            raise RestoreError("La base de datos no está presente en el backup.")

        db_dest = _db_path()
        os.makedirs(os.path.dirname(db_dest), exist_ok=True)
        _copy_sqlite(db_src, db_dest)

        declarations_src = os.path.join(temp_dir, manifest.get("paths", {}).get("declarations", "declarations"))
        exports_src = os.path.join(temp_dir, manifest.get("paths", {}).get("exports", "exports"))
        _copy_optional_folder(declarations_src, current_app.config.get("DECLARATION_UPLOAD_FOLDER"))
        _copy_optional_folder(exports_src, current_app.config.get("ORDER_EXPORT_FOLDER"))

        set_campaign_phase(target_phase)
        Config.set("last_backup_restored_at", datetime.utcnow().isoformat())
        Config.set("last_backup_restored_from", os.path.abspath(zip_path))
        Config.set("last_backup_error_log", "")

        return manifest
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def write_backup_error_log(exc: Exception) -> str:
    """Persist an error log and return its path."""
    backup_dir = current_app.config.get("BACKUP_FOLDER") or "."
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    log_path = os.path.join(backup_dir, f"backup_error_{timestamp}.log")
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write(f"{datetime.utcnow().isoformat()} UTC\n")
        fh.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    Config.set("last_backup_error_log", log_path)
    return log_path
