"""Regression checks for campaign boundaries in selection and exports."""
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "app" / "services"

def test_selection_uses_campaign_products():
    text = (BASE / "final_selection.py").read_text()
    assert "Product.query" not in text
    assert "products_query()" in text
    assert "UserVote.campaign_id == active_campaign_id()" in text
    assert "Product.campaign_id == active_campaign_id()" in text

def test_export_uses_campaign_data():
    text = (BASE / "order_exports.py").read_text()
    assert "products_query().filter(Product.final_selected.is_(True))" in text
    assert "quantity_model = Order if use_orders else UserVote" in text
    assert "quantity_model.campaign_id == active_campaign_id()" in text
    assert "quantity_model.product_id.in_(product_map.keys())" in text
