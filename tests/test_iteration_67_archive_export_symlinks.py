"""Executable archive export path regression without Flask dependencies."""
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def archive_with_export(tmp_path, export_kind):
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    outside = tmp_path / "outside.xlsx"
    outside.write_bytes(b"unrelated export")
    target = export_dir / "order.xlsx"
    if export_kind == "outside_symlink":
        target.symlink_to(outside)
    elif export_kind == "inside_symlink":
        real = export_dir / "another.xlsx"
        real.write_bytes(b"another campaign")
        target.symlink_to(real)
    elif export_kind == "regular":
        from openpyxl import Workbook
        book = Workbook()
        book.active.title = "Pedido"
        book.active.append(["Referencia", "Nombre", "Color", "Precio unitario", "Cantidad total", "Importe total"])
        book.active.append(["3001", "Brick", 1, 0.1, 10, 1.0])
        book.active.append(["", "", "", "", "Total", 1.0])
        book.save(target)
    elif export_kind == "renamed_text":
        target.write_bytes(b"this is not an xlsx")
    elif export_kind == "empty":
        target.write_bytes(b"")
    class Campaign:
        id = 1
        year = 2026
        status = "legacy_active"
        archived_at = None
    campaign = Campaign()
    events = []
    app = types.ModuleType("app")
    app.db = types.SimpleNamespace(session=types.SimpleNamespace(commit=lambda: events.append("commit")))
    models = types.ModuleType("app.models")
    models.Campaign = types.SimpleNamespace(query=types.SimpleNamespace(all=lambda: [campaign]))
    phase = types.ModuleType("app.services.campaign_phase")
    phase.get_campaign_phase = lambda: "order"
    settings = types.ModuleType("app.services.campaign_settings")
    settings.get_annual_setting = lambda key: {"final_order_generated_at": "2027-03-01", "final_order_excel": "order.xlsx"}[key]
    audit = types.ModuleType("app.services.activity_log")
    audit.log_user_action = lambda *args: events.append("audit")
    exports = types.ModuleType("app.services.order_exports")
    exports.build_final_order_context = lambda: {"products": [{"product": types.SimpleNamespace(reference="3001", name="Brick", colour_id=1, price=0.1), "total_quantity": 10, "total_amount": 1.0}], "base_total": 1.0}
    modules = {"app": app, "app.models": models, "app.services": types.ModuleType("app.services"),
               "app.services.campaign_phase": phase, "app.services.campaign_settings": settings,
               "app.services.activity_log": audit, "app.services.order_exports": exports}
    with patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location("archive_iteration_67", ROOT / "app/services/campaign_archive.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        try:
            module.archive_completed_campaign(year=2026, export_folder=str(export_dir), actor_id=1)
            error = None
        except module.CampaignArchiveError as exc:
            error = str(exc)
    return campaign, events, error

def test_rejects_symlink_to_file_outside_export_directory(tmp_path):
    campaign, events, error = archive_with_export(tmp_path, "outside_symlink")
    assert error is not None
    assert campaign.status == "legacy_active"
    assert events == []

def test_rejects_symlink_to_another_export_inside_directory(tmp_path):
    campaign, events, error = archive_with_export(tmp_path, "inside_symlink")
    assert error is not None
    assert campaign.status == "legacy_active"
    assert events == []

def test_rejects_empty_export(tmp_path):
    campaign, events, error = archive_with_export(tmp_path, "empty")
    assert error is not None
    assert events == []

def test_accepts_regular_nonempty_export(tmp_path):
    campaign, events, error = archive_with_export(tmp_path, "regular")
    assert error is None
    assert campaign.status == "archived"
    assert events == ["audit", "commit"]


def test_rejects_nonempty_file_disguised_as_excel(tmp_path):
    campaign, events, error = archive_with_export(tmp_path, "renamed_text")
    assert error is not None
    assert campaign.status == "legacy_active"
    assert events == []
