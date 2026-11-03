from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_has_no_private_order_feature():
    # The public shortage flow may use "ampliacion publica".
    forbidden = ("extension_interest", "final_extension", "allow_extensions", "extension_start_date", "extension_end_date", "ampliacion voluntaria", "ampliación voluntaria")
    for folder in ("app", "templates"):
        for path in (ROOT / folder).rglob("*"):
            if path.suffix not in {".py", ".html", ".json", ".js"}:
                continue
            content = path.read_text(encoding="utf-8").lower()
            assert not any(token in content for token in forbidden), path


def test_only_public_phases_are_supported():
    tree = ast.parse((ROOT / "app/services/campaign_phase.py").read_text())
    phases = next(node.value for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PHASES" for t in node.targets))
    assert set(ast.literal_eval(phases.args[0])) == {"first", "second", "final", "order"}
