"""Admin-only translation editor; data persists in the Docker /data volume."""
import json
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from io import BytesIO
from app.i18n import (
    get_supported_languages, get_base_messages, get_override_messages,
    get_messages, save_override_messages,
)

translations_bp = Blueprint("translations_admin", __name__)
MAX_VALUE = 2000
MAX_IMPORT = 512 * 1024


def _admin_only():
    if not current_user.is_admin:
        abort(403)


def _valid_entry(key, value, permitted):
    return (isinstance(key, str) and key in permitted and isinstance(value, str)
            and 0 < len(value) <= MAX_VALUE and "\x00" not in value)


@translations_bp.route("/admin/translations", methods=["GET"])
@login_required
def index():
    _admin_only()
    languages = get_supported_languages()
    language = request.args.get("lang", "en")
    if language not in languages:
        language = languages[0]
    base = get_base_messages(language)
    effective = get_messages(language)
    overrides = get_override_messages(language)
    spanish = get_messages("es") if "es" in languages else {}
    source_keys = set()
    for code in languages:
        source_keys.update(k for k in get_base_messages(code) if k != "_messages")
    query = request.args.get("q", "").strip().lower()[:120]
    only_missing = request.args.get("missing") == "1"
    rows = []
    for key in sorted(source_keys):
        value = effective.get(key, "")
        if query and query not in key.lower() and query not in str(value).lower():
            continue
        if only_missing and value:
            continue
        rows.append(dict(key=key, source=spanish.get(key, ""), value=value, missing=not bool(value), customized=key in overrides))
    return render_template("admin_translations.html", rows=rows, language=language,
                           languages=languages, query=query, only_missing=only_missing,
                           total=len(source_keys), missing_total=sum(not effective.get(k) for k in source_keys))


@translations_bp.route("/admin/translations/save", methods=["POST"])
@login_required
def save():
    _admin_only()
    language = request.form.get("lang", "")
    if language not in get_supported_languages():
        abort(400)
    key, value = request.form.get("key", ""), request.form.get("value", "")
    permitted = set()
    for code in get_supported_languages():
        permitted.update(get_base_messages(code))
    permitted.discard("_messages")
    if not _valid_entry(key, value, permitted):
        abort(400)
    overrides = get_override_messages(language)
    if value == get_base_messages(language).get(key):
        overrides.pop(key, None)
    else:
        overrides[key] = value
    save_override_messages(language, overrides)
    flash("Traducción guardada.", "success")
    return redirect(url_for("translations_admin.index", lang=language, q=request.form.get("q", "")[:120]))


@translations_bp.route("/admin/translations/reset", methods=["POST"])
@login_required
def reset():
    _admin_only()
    language, key = request.form.get("lang", ""), request.form.get("key", "")
    if language not in get_supported_languages():
        abort(400)
    permitted = set()
    for code in get_supported_languages():
        permitted.update(get_base_messages(code))
    permitted.discard("_messages")
    if key not in permitted:
        abort(400)
    overrides = get_override_messages(language)
    overrides.pop(key, None)
    save_override_messages(language, overrides)
    flash("Traducción restaurada.", "success")
    return redirect(url_for("translations_admin.index", lang=language))


@translations_bp.route("/admin/translations/export/<language>", methods=["GET"])
@login_required
def export(language):
    _admin_only()
    if language not in get_supported_languages():
        abort(404)
    content = json.dumps(get_messages(language), ensure_ascii=False, indent=2).encode("utf-8")
    return send_file(BytesIO(content), mimetype="application/json", as_attachment=True,
                     download_name="valbrick-"+language+".json")


@translations_bp.route("/admin/translations/import", methods=["POST"])
@login_required
def import_file():
    _admin_only()
    language = request.form.get("lang", "")
    if language not in get_supported_languages():
        abort(400)
    upload = request.files.get("file")
    if not upload:
        abort(400)
    raw = upload.stream.read(MAX_IMPORT+1)
    if len(raw) > MAX_IMPORT:
        abort(413)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        abort(400)
    allowed = set()
    for code in get_supported_languages():
        allowed.update(get_base_messages(code))
    allowed.discard("_messages")
    if not isinstance(data, dict) or not all(_valid_entry(k,v,allowed) for k,v in data.items()):
        abort(400)
    overrides = get_override_messages(language)
    base = get_base_messages(language)
    for key, value in data.items():
        if value == base.get(key):
            overrides.pop(key,None)
        else:
            overrides[key] = value
    save_override_messages(language,overrides)
    flash("Traducciones importadas.", "success")
    return redirect(url_for("translations_admin.index",lang=language))
