"""Read-only integrity audit before enabling more than one annual campaign.

Usage: python scripts/audit_campaign_integrity.py --db /srv/data/app.db
Exit status 0 means the *checked data* is consistent, not that routes are ready.
The audit never modifies its database and does not enable annual campaigns.
"""
import argparse
import json
import sqlite3
from pathlib import Path

TABLES = ('product', 'order', 'user_vote', 'user_favorite')


def audit_database(filename):
    """Return a JSON-serialisable report; fail closed on incomplete schemas."""
    path = Path(filename)
    issues = []
    counts = {}
    if not path.is_file():
        return {'ok': False, 'issues': ['Database file does not exist'], 'counts': counts}
    # Read-only URI prevents sqlite from silently creating a missing database.
    from urllib.parse import quote
    uri = 'file:' + quote(str(path.resolve()), safe='/') + '?mode=ro'
    try:
        with sqlite3.connect(uri, uri=True) as con:
            con.row_factory = sqlite3.Row
            existing = {row[0] for row in con.execute('SELECT name FROM sqlite_master WHERE type = ?', ('table',))}
            required = {'campaign', 'campaign_participation', *TABLES, 'user'}
            missing = sorted(required - existing)
            if missing:
                issues.append('Missing tables: ' + ', '.join(missing))
            if 'campaign' in existing:
                counts['campaigns'] = con.execute('SELECT count(*) FROM campaign').fetchone()[0]
                campaign_cols = {row[1] for row in con.execute('PRAGMA table_info("campaign")')}
                if 'status' in campaign_cols:
                    active_count = con.execute("SELECT count(*) FROM campaign WHERE status='legacy_active'").fetchone()[0]
                    draft_count = con.execute("SELECT count(*) FROM campaign WHERE status='draft'").fetchone()[0]
                    counts['active_campaigns'] = active_count
                    counts['draft_campaigns'] = draft_count
                    unknown_statuses = con.execute("SELECT count(*) FROM campaign WHERE status IS NULL OR status NOT IN ('legacy_active', 'archived', 'closed', 'draft')").fetchone()[0]
                    if unknown_statuses:
                        issues.append(f'campaign: {unknown_statuses} unknown or null lifecycle statuses')
                    if active_count > 1:
                        issues.append('Multiple simultaneously active campaigns')
                    if draft_count > 1:
                        issues.append('Multiple simultaneous campaign drafts')
                    if active_count and draft_count:
                        issues.append('Active campaign must be archived before preparing next year')
                    for table in (*TABLES, 'campaign_participation'):
                        if table not in existing:
                            continue
                        columns = {row[1] for row in con.execute(f'PRAGMA table_info("{table}")')}
                        if 'campaign_id' not in columns:
                            continue
                        count = con.execute(f'''SELECT count(*) FROM "{table}" t
                            JOIN campaign c ON c.id=t.campaign_id WHERE c.status='draft' ''').fetchone()[0]
                        if count:
                            issues.append(f'{table}: {count} records already attached to draft campaigns')
                else:
                    # Even a one-year database cannot be classified as archived,
                    # draft or writable without an explicit status field.
                    issues.append('Campaign status column missing: lifecycle safety cannot be verified')
            for table in TABLES:
                if table not in existing:
                    continue
                cols = {row[1] for row in con.execute(f'PRAGMA table_info("{table}")')}
                counts[table] = con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                if 'campaign_id' not in cols:
                    issues.append(f'{table}: campaign_id column is missing')
                    continue
                if 'campaign' not in existing:
                    # The schema is incomplete: do not attempt joins against an
                    # absent table or silently mark these rows as validated.
                    issues.append(f'{table}: campaign ownership cannot be verified (campaign table missing)')
                else:
                    invalid = con.execute(f'''SELECT count(*) FROM "{table}" t
                      LEFT JOIN campaign c ON c.id = t.campaign_id
                      WHERE t.campaign_id IS NULL OR c.id IS NULL''').fetchone()[0]
                    if invalid:
                        issues.append(f'{table}: {invalid} rows without a valid campaign')
            if 'product' in existing:
                product_cols = {row[1] for row in con.execute('PRAGMA table_info("product")')}
                if 'campaign_id' in product_cols:
                    for table in ('order', 'user_vote', 'user_favorite'):
                        if table not in existing:
                            continue
                        cols = {row[1] for row in con.execute(f'PRAGMA table_info("{table}")')}
                        if not {'campaign_id', 'product_id'}.issubset(cols):
                            continue
                        bad = con.execute(f'''SELECT count(*) FROM "{table}" t
                            LEFT JOIN product p ON t.product_id = p.id
                            WHERE p.id IS NULL OR t.campaign_id IS NOT p.campaign_id''').fetchone()[0]
                        if bad:
                            issues.append(f'{table}: {bad} missing or cross-campaign products')
            # A user may have only one record for the same reference within a
            # campaign. Duplicates inflate totals and can bypass the order cap.
            # Check actual stored data, even when legacy DBs lack constraints.
            for table in ('user_vote', 'user_favorite'):
                if table not in existing:
                    continue
                cols = {row[1] for row in con.execute(f'PRAGMA table_info("{table}")')}
                if {'campaign_id', 'user_id', 'product_id'}.issubset(cols):
                    duplicate_groups = con.execute(f'''SELECT count(*) FROM (
                        SELECT 1 FROM "{table}"
                        GROUP BY campaign_id, user_id, product_id
                        HAVING count(*) > 1)''').fetchone()[0]
                    if duplicate_groups:
                        issues.append(f'{table}: {duplicate_groups} duplicate user/product/campaign groups')
            # Multiple order rows for the same user/product/year can evade
            # per-line validation and inflate the monetary total.
            if 'order' in existing:
                cols = {row[1] for row in con.execute('PRAGMA table_info("order")')}
                if {'campaign_id', 'user_id', 'product_id'}.issubset(cols):
                    duplicates = con.execute('''SELECT count(*) FROM (
                        SELECT 1 FROM "order" GROUP BY campaign_id, user_id, product_id
                        HAVING count(*) > 1)''').fetchone()[0]
                    if duplicates:
                        issues.append(f'order: {duplicates} duplicate user/product/campaign groups')
            # Monetary totals are not meaningful for absent, negative, NaN,
            # or infinite prices. Legacy catalogs may not have a price field.
            if 'product' in existing and 'price' in {row[1] for row in con.execute('PRAGMA table_info("product")')}:
                bad_prices = con.execute('''SELECT count(*) FROM product WHERE price IS NULL
                    OR typeof(price) NOT IN ('real', 'integer') OR price < 0
                    OR price > 1000000''').fetchone()[0]
                if bad_prices:
                    issues.append(f'product: {bad_prices} invalid or missing prices')
            # Nonpositive quantities are invalid for stored order lines; zero
            # quantities must be removed rather than retained as fake orders.
            for table in ('order', 'user_vote'):
                if table in existing:
                    cols = {row[1] for row in con.execute(f'PRAGMA table_info("{table}")')}
                    if 'quantity' in cols:
                        bad_quantities = con.execute(f'''SELECT count(*) FROM "{table}"
                            WHERE quantity IS NULL OR quantity <= 0''').fetchone()[0]
                        if bad_quantities:
                            issues.append(f'{table}: {bad_quantities} invalid quantities')
            # SQLite structural checks are read-only and catch corruption or
            # broken foreign keys independently of the application models.
            integrity = con.execute('PRAGMA quick_check').fetchall()
            if len(integrity) != 1 or integrity[0][0] != 'ok':
                issues.append('SQLite quick_check failed: ' + '; '.join(str(r[0]) for r in integrity[:5]))
            fk_violations = con.execute('PRAGMA foreign_key_check').fetchall()
            if fk_violations:
                issues.append(f'SQLite foreign_key_check: {len(fk_violations)} violations')

            # Orders/votes/favorites must belong to a user actually enrolled
            # in that same year. An account can exist without participation.
            if 'campaign_participation' in existing:
                membership_cols = {r[1] for r in con.execute('PRAGMA table_info("campaign_participation")')}
                if {'campaign_id', 'user_id'}.issubset(membership_cols):
                    for table in ('order', 'user_vote', 'user_favorite'):
                        if table not in existing:
                            continue
                        cols = {r[1] for r in con.execute(f'PRAGMA table_info("{table}")')}
                        if not {'campaign_id', 'user_id'}.issubset(cols):
                            issues.append(f'{table}: user_id or campaign_id column missing')
                            continue
                        unregistered = con.execute(f'''SELECT count(*) FROM "{table}" t
                            WHERE NOT EXISTS (
                              SELECT 1 FROM campaign_participation cp
                              WHERE cp.campaign_id = t.campaign_id AND cp.user_id = t.user_id
                            )''').fetchone()[0]
                        if unregistered:
                            issues.append(f'{table}: {unregistered} rows owned by users not enrolled in that campaign')

            if 'campaign_participation' in existing:
                cols = {row[1] for row in con.execute('PRAGMA table_info("campaign_participation")')}
                if not {'campaign_id', 'user_id'}.issubset(cols):
                    issues.append('campaign_participation: missing campaign_id or user_id column')
                if {'campaign_id', 'user_id'}.issubset(cols) and {'campaign', 'user'}.issubset(existing):
                    invalid = con.execute('''SELECT count(*) FROM campaign_participation cp
                        LEFT JOIN campaign c ON c.id = cp.campaign_id
                        LEFT JOIN user u ON u.id = cp.user_id
                        WHERE c.id IS NULL OR u.id IS NULL''').fetchone()[0]
                    if invalid:
                        issues.append(f'campaign_participation: {invalid} orphan records')
                    duplicates = con.execute('''SELECT count(*) FROM (
                        SELECT 1 FROM campaign_participation
                        GROUP BY campaign_id, user_id HAVING count(*) > 1)''').fetchone()[0]
                    if duplicates:
                        issues.append(f'campaign_participation: {duplicates} duplicate memberships')
    except sqlite3.DatabaseError as exc:
        issues.append('SQLite error: ' + str(exc))
    return {'ok': not issues, 'issues': issues, 'counts': counts,
            'note': 'Passing this audit does not prove that all application routes are campaign-scoped.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, help='Path to an existing SQLite database')
    args = parser.parse_args()
    result = audit_database(args.db)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
