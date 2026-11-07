"""Confirmed 85-reference cutoff releases the budget of rejected votes."""
import importlib.util
from decimal import Decimal
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('ledger', Path(__file__).resolve().parents[1] / 'app/services/commitment_ledger.py')
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)

VOTES = [(1, '65', 1), (2, '45', 1), (3, '80', 1), (4, '35', 1)]

def test_all_voting_promises_are_active():
    assert ledger.effective_commitment([], VOTES, phase='second') == Decimal('225')

def test_cutoff_releases_rejected_references_without_deleting_history():
    assert ledger.effective_commitment([], VOTES, phase='order', selected_product_ids={1,3}) == Decimal('145')
    assert len(VOTES) == 4

def test_released_budget_can_be_spent_on_selected_reference():
    total = ledger.effective_commitment([], VOTES, phase='order', selected_product_ids={1,3}, additional=(1, '65', 1))
    assert total == Decimal('210')
    assert Decimal('235') - total == Decimal('25')

def test_rejected_reference_cannot_be_ordered():
    with pytest.raises(ValueError):
        ledger.effective_commitment([], VOTES, phase='order', selected_product_ids={1,3}, additional=(2, '45', 1))

def test_missing_confirmed_selection_fails_closed():
    with pytest.raises(ValueError):
        ledger.effective_commitment([], VOTES, phase='order')

def test_selected_vote_not_double_counted_with_order():
    assert ledger.effective_commitment([(1,'65',1)], VOTES, phase='order', selected_product_ids={1,3}) == Decimal('145')
