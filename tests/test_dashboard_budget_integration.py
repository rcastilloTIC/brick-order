from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_dashboard_budget_uses_selection_aware_ledger():
    source = (ROOT / "app/main/routes.py").read_text()
    assert "active_commitment = effective_commitment(" in source
    assert "selected_ids_for_budget" in source
    assert "available_budget = max(" in source
    assert "historical_votes = votes_query().filter_by(user_id=current_user.id).all()" in source

def test_dashboard_displays_released_budget():
    template = (ROOT / "templates/user_dashboard.html").read_text()
    assert "{{ \"%.2f\"|format(released_budget) }}" in template
    assert "{{ \"%.2f\"|format(available_budget) }}" in template
