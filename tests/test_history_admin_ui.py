from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_admin_route():
    source = (ROOT / 'app/main/routes.py').read_text()
    section = source.split('def campaign_history():', 1)[1].split('@main_bp.route', 1)[0]
    assert '_ensure_admin()' in section
    assert 'render_template(' in section
    assert 'db.session.commit' not in section

def test_scoped_aggregations():
    source = (ROOT / 'app/services/history_summary.py').read_text()
    for model in ('CampaignParticipation', 'Product', 'UserVote', 'Order'):
        assert f'{model}.query.filter_by(campaign_id=campaign_id)' in source
    assert 'Product.campaign_id == campaign_id' in source
    assert 'Order.campaign_id == campaign_id' in source
    assert "['archived', 'closed']" in source

def test_navigation():
    assert "url_for('main.campaign_history')" in (ROOT / 'templates/base.html').read_text()
