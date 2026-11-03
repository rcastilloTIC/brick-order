import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

ROOT = Path(__file__).resolve().parents[1]


def _module():
    app = types.ModuleType('app')
    app.db = None
    models = types.ModuleType('app.models')
    models.Campaign = object
    phase = types.ModuleType('app.services.campaign_phase')
    phase.get_campaign_phase = lambda: 'order'
    settings = types.ModuleType('app.services.campaign_settings')
    settings.get_annual_setting = lambda _: None
    with patch.dict(sys.modules, {'app': app, 'app.models': models, 'app.services': types.ModuleType('app.services'), 'app.services.campaign_phase': phase, 'app.services.campaign_settings': settings}):
        spec = importlib.util.spec_from_file_location('archive69', ROOT / 'app/services/campaign_archive.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


def _fixture(tmp_path):
    path = tmp_path / 'order.xlsx'
    wb = Workbook()
    ws = wb.active
    ws.title = 'Pedido'
    ws.append(['Referencia', 'Nombre', 'Color', 'Precio unitario', 'Cantidad total', 'Importe total'])
    ws.append(['3001', 'Brick', 1, 0.1, 10, 1.0])
    ws.append(['', '', '', '', 'Total', 1.0])
    wb.save(path)
    summary = {'products': [{'product': types.SimpleNamespace(reference='3001', name='Brick', colour_id=1, price=0.1), 'total_quantity': 10, 'total_amount': 1.0}], 'base_total': 1.0}
    return path, summary


def test_valid_export_matches(tmp_path):
    path, summary = _fixture(tmp_path)
    assert _module().final_workbook_matches_order(path, summary)


def test_quantity_tampering_is_rejected(tmp_path):
    path, summary = _fixture(tmp_path)
    wb = load_workbook(path)
    wb.active['E2'] = 11
    wb.save(path)
    assert not _module().final_workbook_matches_order(path, summary)


def test_foreign_reference_is_rejected(tmp_path):
    path, summary = _fixture(tmp_path)
    wb = load_workbook(path)
    wb.active['A2'] = '9999'
    wb.save(path)
    assert not _module().final_workbook_matches_order(path, summary)


def test_duplicate_reference_is_rejected(tmp_path):
    path, summary = _fixture(tmp_path)
    wb = load_workbook(path)
    wb.active.insert_rows(3)
    for column in range(1, 7):
        wb.active.cell(3, column).value = wb.active.cell(2, column).value
    wb.save(path)
    assert not _module().final_workbook_matches_order(path, summary)


def test_formula_is_rejected(tmp_path):
    path, summary = _fixture(tmp_path)
    wb = load_workbook(path)
    wb.active['F2'] = '=D2*E2'
    wb.save(path)
    assert not _module().final_workbook_matches_order(path, summary)


def test_changed_live_order_is_rejected(tmp_path):
    path, summary = _fixture(tmp_path)
    summary['products'][0]['total_quantity'] = 11
    assert not _module().final_workbook_matches_order(path, summary)
