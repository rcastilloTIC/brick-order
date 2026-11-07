"""Regression tests for invalid numeric cells and trailing data."""
import importlib.util
from pathlib import Path
from openpyxl import load_workbook

SPEC = importlib.util.spec_from_file_location('archive69tests', Path(__file__).with_name('test_iteration_69_archive_semantics.py'))
previous = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(previous)


def _tamper(tmp_path, cell, value):
    path, summary = previous._fixture(tmp_path)
    wb = load_workbook(path)
    wb.active[cell] = value
    wb.save(path)
    return previous._module().final_workbook_matches_order(path, summary)


def test_reject_extra_column(tmp_path):
    assert not _tamper(tmp_path, 'G2', 'unexpected')


def test_reject_boolean_price(tmp_path):
    assert not _tamper(tmp_path, 'D2', True)


def test_reject_infinite_total(tmp_path):
    assert not _tamper(tmp_path, 'F3', float('inf'))


def test_reject_text_numeric_cell(tmp_path):
    assert not _tamper(tmp_path, 'D2', '0.1')


def test_accept_original(tmp_path):
    path, summary = previous._fixture(tmp_path)
    assert previous._module().final_workbook_matches_order(path, summary)
