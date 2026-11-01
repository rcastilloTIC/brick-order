"""Install SQLite write guards on annual catalog, votes, favorites and orders.

This is an opt-in, offline hardening operation. It does NOT enable multiple
campaigns; all application routes must be scoped before that is safe.
Use only with the service stopped and a verified independent backup.
"""
import argparse
import sqlite3
from pathlib import Path
from urllib.parse import quote

TABLES = ('order', 'user_vote', 'user_favorite')


class GuardError(RuntimeError):
    pass


def install(database, *, apply=False):
    path = Path(database).resolve()
    if not path.is_file():
        raise GuardError('Database file does not exist')
    mode = 'rw' if apply else 'ro'
    uri = 'file:' + quote(str(path), safe='/') + '?mode=' + mode
    con = sqlite3.connect(uri, uri=True, timeout=10)
    try:
        con.execute('PRAGMA foreign_keys=ON')
        required = ('campaign', 'campaign_participation', 'product', *TABLES)
        existing = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if set(required) - existing:
            raise GuardError('Campaign tables missing: ' + ', '.join(sorted(set(required) - existing)))
        if con.execute('SELECT COUNT(*) FROM campaign').fetchone()[0] != 1:
            raise GuardError('Requires exactly one registered campaign during transition')
        for table in ('product', *TABLES):
            cols = {r[1] for r in con.execute(f'PRAGMA table_info("{table}")')}
            needed = {'campaign_id'} | ({'user_id', 'product_id'} if table in TABLES else set())
            if not needed <= cols:
                raise GuardError(f'{table}: missing columns {sorted(needed - cols)}')
            bad = con.execute(f'''SELECT COUNT(*) FROM "{table}" t
                 LEFT JOIN campaign c ON c.id=t.campaign_id
                 WHERE t.campaign_id IS NULL OR c.id IS NULL''').fetchone()[0]
            if bad:
                raise GuardError(f'{table}: {bad} records not assigned to a valid campaign')
        for table in TABLES:
            bad = con.execute(f'''SELECT COUNT(*) FROM "{table}" t
               LEFT JOIN product p ON p.id=t.product_id
               WHERE p.id IS NULL OR p.campaign_id != t.campaign_id''').fetchone()[0]
            if bad:
                raise GuardError(f'{table}: {bad} cross-campaign or missing products')
            bad = con.execute(f'''SELECT COUNT(*) FROM "{table}" t WHERE NOT EXISTS
               (SELECT 1 FROM campaign_participation cp
                WHERE cp.user_id=t.user_id AND cp.campaign_id=t.campaign_id)''').fetchone()[0]
            if bad:
                raise GuardError(f'{table}: {bad} records of unenrolled users')
        names = []
        if not apply:
            return {'applied': False, 'tables': list(TABLES)}
        # START IMMEDIATE for a consistent check with write protection. The
        # service must still be stopped: this is not an online migration.
        con.execute('BEGIN IMMEDIATE')
        for table in TABLES:
            for verb in ('INSERT', 'UPDATE'):
                name = f'guard_{table}_{verb.lower()}_campaign'
                names.append(name)
                con.execute(f'''CREATE TRIGGER IF NOT EXISTS "{name}"
                   BEFORE {verb} ON "{table}" BEGIN
                     SELECT RAISE(ABORT, 'invalid campaign assignment')
                     WHERE NEW.campaign_id IS NULL OR NOT EXISTS
                        (SELECT 1 FROM campaign c WHERE c.id=NEW.campaign_id);
                     SELECT RAISE(ABORT, 'product belongs to another campaign')
                     WHERE NOT EXISTS (SELECT 1 FROM product p
                        WHERE p.id=NEW.product_id AND p.campaign_id=NEW.campaign_id);
                     SELECT RAISE(ABORT, 'user not enrolled in campaign')
                     WHERE NOT EXISTS (SELECT 1 FROM campaign_participation cp
                        WHERE cp.user_id=NEW.user_id AND cp.campaign_id=NEW.campaign_id);
                   END''')
        for verb in ('INSERT', 'UPDATE'):
            name = f'guard_product_{verb.lower()}_campaign'
            names.append(name)
            change_condition = 'OLD.campaign_id IS NOT NEW.campaign_id' if verb == 'UPDATE' else '0'
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS "{name}"
                BEFORE {verb} ON product BEGIN
                   SELECT RAISE(ABORT, 'invalid product campaign')
                   WHERE NEW.campaign_id IS NULL OR NOT EXISTS
                     (SELECT 1 FROM campaign c WHERE c.id=NEW.campaign_id);
                   SELECT RAISE(ABORT, 'cannot move product with existing orders or votes')
                   WHERE {change_condition}
                     AND (EXISTS (SELECT 1 FROM "order" o WHERE o.product_id=NEW.id)
                       OR EXISTS (SELECT 1 FROM user_vote v WHERE v.product_id=NEW.id)
                       OR EXISTS (SELECT 1 FROM user_favorite f WHERE f.product_id=NEW.id));
                END''')
        con.commit()
        return {'applied': True, 'triggers': len(names)}
    finally:
        con.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('database')
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    try:
        print(install(args.database, apply=args.apply))
    except (GuardError, sqlite3.Error) as exc:
        p.exit(1, f'ERROR: {exc}\n')


if __name__ == '__main__':
    main()
