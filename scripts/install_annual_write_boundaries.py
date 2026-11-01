"""Opt-in SQLite annual cross-campaign write integrity checks."""
import argparse
import sqlite3
from pathlib import Path
from urllib.parse import quote

TABLES = ('order', 'user_vote', 'user_favorite')
REQUIRED = {'campaign': {'id'}, 'product': {'id', 'campaign_id'},
            'campaign_participation': {'campaign_id', 'user_id'},
            **{t: {'id', 'campaign_id', 'product_id', 'user_id'} for t in TABLES}}


class BoundaryError(RuntimeError):
    pass


def install(database, *, apply=False):
    path = Path(database).resolve()
    if not path.is_file():
        raise BoundaryError('Database does not exist')
    mode = 'rw' if apply else 'ro'
    con = sqlite3.connect('file:' + quote(str(path), safe='/') + '?mode=' + mode, uri=True)
    try:
        if apply:
            con.execute('BEGIN IMMEDIATE')
        for table, columns in REQUIRED.items():
            actual = {row[1] for row in con.execute(f'PRAGMA table_info("{table}")')}
            if not columns <= actual:
                raise BoundaryError(f'Missing schema for {table}: {sorted(columns - actual)}')
        for table in TABLES:
            invalid = con.execute(f'''SELECT COUNT(*) FROM "{table}" x
              LEFT JOIN product p ON p.id=x.product_id
              LEFT JOIN campaign c ON c.id=x.campaign_id
              WHERE x.campaign_id IS NULL OR c.id IS NULL OR p.id IS NULL
                OR p.campaign_id IS NULL OR p.campaign_id != x.campaign_id
                OR NOT EXISTS(SELECT 1 FROM campaign_participation m
                  WHERE m.campaign_id=x.campaign_id AND m.user_id=x.user_id)''').fetchone()[0]
            if invalid:
                raise BoundaryError(f'{table}: {invalid} incompatible historical rows')
        if not apply:
            return {'applied': False, 'incompatible_rows': 0}
        names = []
        for table in TABLES:
            for action in ('INSERT', 'UPDATE'):
                name = f'annual_boundary_{table}_{action.lower()}'
                names.append(name)
                con.execute(f'''CREATE TRIGGER IF NOT EXISTS "{name}"
                  BEFORE {action} ON "{table}" BEGIN
                    SELECT RAISE(ABORT, 'invalid annual product or membership')
                    WHERE NEW.campaign_id IS NULL
                      OR NOT EXISTS(SELECT 1 FROM campaign WHERE id=NEW.campaign_id)
                      OR NOT EXISTS(SELECT 1 FROM product p WHERE p.id=NEW.product_id
                                     AND p.campaign_id=NEW.campaign_id)
                      OR NOT EXISTS(SELECT 1 FROM campaign_participation m
                           WHERE m.campaign_id=NEW.campaign_id AND m.user_id=NEW.user_id);
                  END''')
        names.append('annual_boundary_product_update')
        con.execute('''CREATE TRIGGER IF NOT EXISTS annual_boundary_product_update
            BEFORE UPDATE OF campaign_id ON product BEGIN
            SELECT RAISE(ABORT, 'product has annual references')
            WHERE NEW.campaign_id IS NOT OLD.campaign_id
              AND (EXISTS(SELECT 1 FROM "order" WHERE product_id=OLD.id)
                OR EXISTS(SELECT 1 FROM user_vote WHERE product_id=OLD.id)
                OR EXISTS(SELECT 1 FROM user_favorite WHERE product_id=OLD.id));
            END''')
        for action in ('DELETE', 'UPDATE OF campaign_id, user_id'):
            name = 'annual_boundary_membership_' + ('delete' if action == 'DELETE' else 'update')
            names.append(name)
            changed = '1' if action == 'DELETE' else '(NEW.campaign_id IS NOT OLD.campaign_id OR NEW.user_id IS NOT OLD.user_id)'
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS "{name}"
              BEFORE {action} ON campaign_participation BEGIN
              SELECT RAISE(ABORT, 'membership has annual references') WHERE {changed}
                AND (EXISTS(SELECT 1 FROM "order" WHERE campaign_id=OLD.campaign_id AND user_id=OLD.user_id)
                  OR EXISTS(SELECT 1 FROM user_vote WHERE campaign_id=OLD.campaign_id AND user_id=OLD.user_id)
                  OR EXISTS(SELECT 1 FROM user_favorite WHERE campaign_id=OLD.campaign_id AND user_id=OLD.user_id));
              END''')
        con.commit()
        return {'applied': True, 'triggers': len(names)}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('database')
    group = p.add_mutually_exclusive_group()
    group.add_argument('--check', action='store_true')
    group.add_argument('--apply', action='store_true')
    args = p.parse_args()
    try:
        print(install(args.database, apply=args.apply))
    except (BoundaryError, sqlite3.Error) as exc:
        p.exit(1, f'ERROR: {exc}\n')
