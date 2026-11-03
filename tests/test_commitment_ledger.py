"""Executable tests of the transitional commitment union, no Flask required."""
import importlib.util
from pathlib import Path
from decimal import Decimal
import pytest

spec = importlib.util.spec_from_file_location('ledger', Path(__file__).resolve().parents[1] / 'app/services/commitment_ledger.py')
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)


def test_disjoint_references_are_added():
    assert ledger.committed_total([(1, '100', 1)], [(2, '100', 1)]) == Decimal('200')


def test_same_reference_not_counted_twice():
    assert ledger.committed_total([(1, '10', 2)], [(1, '10', 2)]) == Decimal('20')


def test_new_order_conservatively_adds_to_order_side():
    assert ledger.committed_total([(1, '10', 2)], [(1, '10', 3)], additional=(1, '10', 2)) == Decimal('40')


def test_multiple_orders_same_reference_are_summed():
    assert ledger.committed_total([(1, '5', 2), (1, '5', 2)], [(1, '5', 3)]) == Decimal('20')

@pytest.mark.parametrize('bad', ['NaN', 'Infinity', '-1', 'oops'])
def test_invalid_prices_fail_closed(bad):
    with pytest.raises(ValueError):
        ledger.committed_total([(1, bad, 1)], [])


def test_conflicting_prices_fail_closed():
    with pytest.raises(ValueError):
        ledger.committed_total([(1, '2', 1)], [(1, '3', 1)])


def test_zero_and_negative_quantities_fail_closed():
    with pytest.raises(ValueError):
        ledger.committed_total([(1, '1', 0)], [])
