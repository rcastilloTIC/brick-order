"""Regression checks for the annual CSV enrolment boundary."""
import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "app/main/routes.py"

def _function():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_handle_users_csv_upload")

def test_import_uses_active_campaign_and_not_campaign_count():
    text = ast.get_source_segment(SOURCE.read_text(encoding="utf-8"), _function())
    assert "current_campaign()" in text
    assert "len(campaigns) > 1" not in text
    assert "Activate a campaign before importing participants" in text

def test_existing_identity_is_not_overwritten():
    text = ast.get_source_segment(SOURCE.read_text(encoding="utf-8"), _function())
    assert "if is_new:" in text
    assert "setattr(user, model_attr, value)" in text
    assert "accepted_usernames.add(username.casefold())" in text
    assert "for username in accepted_usernames:" in text
    assert "enroll_existing_user(registered_campaign.id, user.id)" in text
