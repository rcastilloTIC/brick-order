from pathlib import Path


def test_admin_order_creation_has_recipient_and_limits():
    root = Path(__file__).resolve().parents[1]
    code = (root / "orders/routes.py").read_text()
    form = (root / "templates/orders/create.html").read_text()
    assert 'user_id=current_user.id' not in code
    assert 'require_campaign_participant(target_user_id)' in code
    assert 'validate_quantity(product.price, quantity)' in code
    assert 'Config.get("final_order_generated_at")' in code
    # Aggregating max(grand totals) across orders and votes is unsafe:
    # per-product effective_commitment must be used to avoid undercounting.
    assert 'effective_commitment(current_orders, current_votes,' in code
    assert 'additional=(product.id, price, quantity)' in code
    assert 'if projected > limit:' in code
    assert 'max(current_orders, current_votes)' not in code
    assert 'get_limit_configuration()["phase_one_order_limit"]' in code
    assert 'name="user_id"' in form
