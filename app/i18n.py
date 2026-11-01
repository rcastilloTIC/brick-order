from __future__ import annotations

import json
from pathlib import Path
import os
import tempfile
from urllib.parse import urlparse

from flask import current_app, request, session

LANGUAGE_LABELS = {
    "es": "Español",
    "en": "English",
}


def init_app(app) -> None:
    @app.context_processor
    def inject_i18n_context():
        current_language = get_current_language()
        languages = []
        for code in get_supported_languages():
            languages.append({"code": code, "label": LANGUAGE_LABELS.get(code, code.upper())})
        return {
            "_": translate,
            "tm": translate_message,
            "current_language": current_language,
            "supported_languages": languages,
        }


def get_supported_languages() -> tuple[str, ...]:
    configured = current_app.config.get("SUPPORTED_LANGUAGES", ("es",))
    if isinstance(configured, str):
        values = tuple(item.strip() for item in configured.split(",") if item.strip())
        return values or ("es",)
    values = tuple(item for item in configured if item)
    return values or ("es",)


def get_default_language() -> str:
    default_language = current_app.config.get("DEFAULT_LANGUAGE", "es")
    return default_language if default_language in get_supported_languages() else "es"


def get_current_language() -> str:
    selected = session.get("language")
    if selected in get_supported_languages():
        return selected
    preferred = request.accept_languages.best_match(get_supported_languages())
    return preferred or get_default_language()


def set_current_language(language: str) -> bool:
    if language not in get_supported_languages():
        return False
    session["language"] = language
    return True


def translate(key: str, **kwargs) -> str:
    language = get_current_language()
    message = get_messages(language).get(key)
    if message is None and language != get_default_language():
        message = get_messages(get_default_language()).get(key)
    if message is None:
        message = key
    if kwargs:
        try:
            message = message.format(**kwargs)
        except Exception:
            return message
    return message


def translate_message(message: str) -> str:
    if not message:
        return ""
    language = get_current_language()
    translated = get_messages(language).get("_messages", {}).get(message)
    if translated is None and language != get_default_language():
        translated = get_messages(get_default_language()).get("_messages", {}).get(message)
    return translated or message


def is_safe_local_url(target: str | None) -> bool:
    if not target:
        return False
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return False
    return target.startswith("/")


def translation_storage_path(language: str) -> Path:
    if language not in get_supported_languages():
        raise ValueError("Unsupported language")
    base = Path(current_app.config.get("TRANSLATIONS_DATA_DIR", "/data/translations"))
    return base / (language + ".json")


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def get_base_messages(language: str) -> dict:
    return _read_json(Path(current_app.root_path) / "translations" / (language + ".json"))


def get_override_messages(language: str) -> dict:
    return _read_json(translation_storage_path(language))


def get_messages(language: str) -> dict:
    messages = get_base_messages(language)
    messages.update(get_override_messages(language))
    return messages


def save_override_messages(language: str, overrides: dict) -> None:
    path = translation_storage_path(language)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement: readers never see partially written JSON.
    fd, temp_name = tempfile.mkstemp(prefix=".translations-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            json.dump(overrides, target, ensure_ascii=False, indent=2, sort_keys=True)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
