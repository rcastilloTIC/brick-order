"""Regression tests for the financial cutoff, without Flask dependencies."""
import importlib.util
from decimal import Decimal
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('commitment_ledger_iteration49', Path(__file__).resolve().parents[1] / 'app/services/commitment_ledger.py')
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)


def test_eighty_five_selected_release_rejected_budget_without_mutation():
    votes = [(i, '2.50', 1) for i in range(1, 87)]
    original = list(votes)
    selected = set(range(1, 86))
    assert ledger.effective_commitment([], votes, phase='order', selected_product_ids=selected) == Decimal('212.50')
    assert votes == original
    assert ledger.effective_commitment([], votes, phase='order', selected_product_ids=selected, additional=(1, '2.50', 1)) == Decimal('215.00')


@pytest.mark.parametrize('invalid', [0, -1, True, '1', None])
def test_invalid_selection_identifiers_fail_closed(invalid):
    with pytest.raises(ValueError):
        ledger.effective_commitment([], [(1, '10', 1)], phase='order', selected_product_ids=[invalid])


def test_unhashable_selection_fails_with_domain_error():
    with pytest.raises(ValueError, match='Invalid confirmed selection'):
        ledger.effective_commitment([], [(1, '10', 1)], phase='order', selected_product_ids=[[1]])


def test_no_selection_is_not_an_implicit_release():
    with pytest.raises(ValueError):
        ledger.effective_commitment([], [(1, '10', 1)], phase='order')


def test_conflicting_prices_on_selected_reference_fail_closed():
    with pytest.raises(ValueError):
        ledger.effective_commitment([(1, '12', 1)], [(1, '10', 1)], phase='order', selected_product_ids={1})
