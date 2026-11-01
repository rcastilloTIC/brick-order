"""Central quantity rule, independent of Flask and safe to unit-test.

The thresholds are the existing production rules. They are intentionally not
changed during refactoring: changing a quantity tier affects commitments.
"""
from decimal import Decimal, InvalidOperation


def validate_quantity(price, quantity, *, low_price_max='1.35',
                      low_price_min=25, low_price_step=25,
                      high_price_min=10, high_price_step=10):
    """Return (valid, human-readable explanation) for a product quantity.

    Reject bool, NaN, infinity, fractional and negative quantities. Values
    should be loaded from validated campaign configuration in a later phase.
    """
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        return False, 'La cantidad debe ser un entero positivo.'
    try:
        cost = Decimal(str(price))
        threshold = Decimal(str(low_price_max))
    except (InvalidOperation, TypeError, ValueError):
        return False, 'El precio no es válido.'
    if not cost.is_finite() or cost < 0 or not threshold.is_finite() or threshold < 0:
        return False, 'El precio no es válido.'
    if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in
           (low_price_min, low_price_step, high_price_min, high_price_step)):
        return False, 'La configuración de cantidades no es válida.'
    minimum, increment = ((low_price_min, low_price_step) if cost <= threshold
                           else (high_price_min, high_price_step))
    if quantity < minimum or quantity % increment:
        return False, f'Mínimo {minimum} unidades y múltiplos de {increment}.'
    return True, ''
