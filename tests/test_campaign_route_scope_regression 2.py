"""Regression checks for annual scoping of high-impact route operations."""
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'app' / 'main' / 'routes.py'

def _block(src, name):
    return src.split(f'def {name}(', 1)[1].split('\ndef ', 1)[0]

def test_totals_filter_vote_and_product_by_campaign():
    source = SOURCE.read_text()
    for name in ('_calculate_final_selected_total', '_calculate_user_total_final_selected', '_calculate_user_total', '_calculate_global_order_total'):
        block = _block(source, name)
        assert 'UserVote.campaign_id == active_campaign_id()' in block
        assert 'Product.campaign_id == active_campaign_id()' in block

def test_admin_mutation_requires_campaign_scoped_vote():
    block = _block(SOURCE.read_text(), 'admin_update_order')
    assert 'votes_query().filter(UserVote.id == vote_id).first_or_404()' in block
    assert 'validate_product_campaign(vote.product)' in block

def test_yearly_purge_fails_closed():
    block = _block(SOURCE.read_text(), '_purge_current_cycle_data')
    assert 'abort(409' in block
    assert '.delete(' not in block

def test_admin_catalog_is_scoped():
    source = SOURCE.read_text()
    assert 'query = products_query()' in _block(source, 'admin_dashboard')
    assert 'products_query().count()' in _block(source, 'upload_data')
