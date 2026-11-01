"""Static release blockers audit; no dependencies and no database writes.

Run: python scripts/audit_release_readiness.py --json
Exit status 2 indicates public release blockers. This audit is intentionally
conservative: findings are review candidates, not verified vulnerabilities.
"""
import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODE = "public"
MODELS = {"Product", "Order", "UserVote", "UserFavorite"}


def scan():
    findings = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        relative = str(path.relative_to(ROOT))
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except SyntaxError as exc:
            findings.append({"kind": "syntax_error", "file": relative, "line": exc.lineno, "detail": str(exc)})
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "query" and isinstance(node.value, ast.Name) and node.value.id in MODELS:
                findings.append({"kind": "direct_annual_query_review", "file": relative, "line": node.lineno, "detail": node.value.id})
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = scan()
    counts = {kind: sum(item["kind"] == kind for item in findings) for kind in sorted({item["kind"] for item in findings})}
    report = {"edition": MODE, "ready_for_publication": not findings, "counts": counts, "findings": findings}
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"{MODE}: {len(findings)} review findings: {counts}")
        for finding in findings[:30]:
            print(f"{finding['file']}:{finding['line']}: {finding['kind']}: {finding['detail']}")
    return 2 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
