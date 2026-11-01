"""Conservative commitment calculation for the transitional Order/UserVote model.

Both records can represent the same purchase commitment. Counting their grand
 totals independently can undercount distinct products, while summing both
can double-count identical products. For each product, take the greater total
quantity represented by either source. This module is pure and uses Decimal.

Until there is a single canonical ledger, callers must fail closed on invalid
prices or quantities rather than silently accepting inconsistent commitments.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation


def committed_total(order_lines, vote_lines, *, additional=None):
    """Return conservative monetary commitment from (product_id, price, quantity).

    Quantities within *one* source for a product are summed; sources are then
    combined using the maximum for that product. ``additional`` represents an
    additional order line, not a replacement. Raises ValueError on bad data.
    """
    def aggregate(lines):
        amounts = defaultdict(int)
        prices = {}
        for product_id, unit_price, quantity in lines:
            if product_id is None or not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
                raise ValueError('Invalid product or quantity')
            try:
                price = Decimal(str(unit_price))
            except (InvalidOperation, ValueError, TypeError) as exc:
                raise ValueError('Invalid unit price') from exc
            if not price.is_finite() or price < 0:
                raise ValueError('Invalid unit price')
            if product_id in prices and prices[product_id] != price:
                raise ValueError('Conflicting prices for same product')
            prices[product_id] = price
            amounts[product_id] += quantity
        return amounts, prices

    existing_orders, order_prices = aggregate(order_lines)
    votes, vote_prices = aggregate(vote_lines)
    for pid, price in vote_prices.items():
        if pid in order_prices and order_prices[pid] != price:
            raise ValueError('Conflicting prices across sources')
    prices = {**vote_prices, **order_prices}
    if additional is not None:
        pid, price, qty = additional
        add_amounts, add_prices = aggregate([(pid, price, qty)])
        if pid in prices and prices[pid] != add_prices[pid]:
            raise ValueError('Conflicting additional price')
        prices.update(add_prices)
        existing_orders[pid] += add_amounts[pid]
    return sum((price * max(existing_orders[pid], votes[pid]) for pid, price in prices.items()), Decimal('0'))


# Final selection is a boundary between voting promises and actual orders.
# Keep rejected votes in the database for traceability, but ignore them in
# the active monetary commitment. Selection is never inferred from vote count.
def effective_commitment(order_lines, vote_lines, *, phase, selected_product_ids=None, additional=None):
    """Calculate the active monetary commitment for a specific campaign phase.

    ``order_lines`` and ``vote_lines`` contain (product_id, price, quantity).
    During voting all votes are binding. From the confirmed selection onward,
    only votes/orders for selected references are financially active.
    This function does not delete historical votes or alter their quantities.
    """
    if phase not in {'first', 'second', 'final', 'order'}:
        raise ValueError('Unknown campaign phase')
    if phase in {'first', 'second'}:
        return committed_total(order_lines, vote_lines, additional=additional)
    if selected_product_ids is None:
        raise ValueError('Confirmed selection required after voting')
    # Validate the confirmed selection before using it as a financial filter.
    # Invalid identifiers must not silently release binding commitments.
    try:
        selected = set(selected_product_ids)
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid confirmed selection') from exc
    if any(not isinstance(i, int) or isinstance(i, bool) or i <= 0 for i in selected):
        raise ValueError('Invalid selected product id')
    if additional is not None and additional[0] not in selected:
        raise ValueError('Cannot order a rejected reference')
    active_orders = [line for line in order_lines if line[0] in selected]
    active_votes = [line for line in vote_lines if line[0] in selected]
    # An added quantity increases the binding selected-reference floor even
    # when only a vote (and no Order row) existed previously.
    if additional is not None:
        pid, price, qty = additional
        order_qty = sum(row[2] for row in active_orders if row[0] == pid)
        vote_qty = sum(row[2] for row in active_votes if row[0] == pid)
        if vote_qty > order_qty:
            active_orders.append((pid, price, vote_qty - order_qty))
    return committed_total(active_orders, active_votes, additional=additional)


def materialized_order_quantity(order_lines, vote_lines, *, product_id, additional_quantity):
    """Amount to persist for an additive order operation after the cutoff.

    The first actual order must include any selected voting commitment not
    already represented by stored Order rows. This prevents the export from
    showing less than the voted floor while avoiding duplicated amounts.
    """
    if not isinstance(product_id, int) or isinstance(product_id, bool):
        raise ValueError("Invalid product")
    if (not isinstance(additional_quantity, int) or isinstance(additional_quantity, bool)
            or additional_quantity <= 0):
        raise ValueError("Invalid additional quantity")
    def quantity_for(lines):
        total = 0
        for pid, _price, quantity in lines:
            if pid != product_id:
                continue
            if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
                raise ValueError("Invalid existing quantity")
            total += quantity
        return total
    existing = quantity_for(order_lines)
    floor = quantity_for(vote_lines)
    return additional_quantity + max(floor - existing, 0)
