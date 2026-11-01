"""Export a consistent, read-only annual campaign snapshot as CSV files.

No password hashes, DNI, signed documents or other account secrets are exported.
This is an administrative backup/report, NOT an annual campaign activation tool.
"""
import argparse
import csv
import hashlib
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

DATASETS = {
    'participants': ('campaign_participation', ('id', 'campaign_id', 'user_id', 'status', 'enrolled_at', 'document_approved_at')),
    'products': ('product', ('id', 'campaign_id', 'reference', 'name', 'price', 'final_selected', 'final_disabled')),
    'votes': ('user_vote', ('id', 'campaign_id', 'user_id', 'product_id', 'quantity', 'initial_quantity', 'phase')),
    'favorites': ('user_favorite', ('id', 'campaign_id', 'user_id', 'product_id')),
    'orders': ('order', ('id', 'campaign_id', 'user_id', 'product_id', 'quantity', 'timestamp')),
}


def export_campaign(db_path, campaign_id, output_dir):
    db_path, output_dir = Path(db_path), Path(output_dir)
    if not db_path.is_file():
        raise ValueError('Database does not exist')
    uri = 'file:' + quote(str(db_path.resolve()), safe='/') + '?mode=ro'
    with sqlite3.connect(uri, uri=True) as con:
        con.row_factory = sqlite3.Row
        con.execute('BEGIN')  # stable snapshot across every exported table
        campaign = con.execute('SELECT id, year, title, status FROM campaign WHERE id = ?', (campaign_id,)).fetchone()
        if campaign is None:
            raise ValueError('Campaign does not exist')
        if campaign['status'] == 'legacy_active':
            raise ValueError('Refusing to export an active campaign as historical archive')
        batches = {}
        for filename, (table, desired_columns) in DATASETS.items():
            available = {r['name'] for r in con.execute('PRAGMA table_info("' + table + '")')}
            if not {'id', 'campaign_id'}.issubset(available):
                raise ValueError(table + ': missing required columns')
            columns = tuple(c for c in desired_columns if c in available)
            rows = con.execute('SELECT ' + ', '.join('"' + c + '"' for c in columns) +
                               ' FROM "' + table + '" WHERE campaign_id = ? ORDER BY id', (campaign_id,)).fetchall()
            batches[filename] = (columns, [tuple(r) for r in rows])
        # Reject data linked to a product belonging to a different campaign.
        for table in ('user_vote', 'user_favorite', 'order'):
            mismatches = con.execute('SELECT count(*) FROM "' + table + '" t '
                'LEFT JOIN product p ON p.id = t.product_id WHERE t.campaign_id = ? '
                'AND (p.id IS NULL OR p.campaign_id IS NOT t.campaign_id)', (campaign_id,)).fetchone()[0]
            if mismatches:
                raise ValueError(table + ': cross-campaign or missing product records')
        con.execute('COMMIT')
    if output_dir.exists():
        raise FileExistsError('Output directory already exists: ' + str(output_dir))
    output_dir.mkdir(parents=True)
    manifest = {'campaign': dict(campaign), 'files': {}}
    for filename, (columns, rows) in batches.items():
        target = output_dir / (filename + '.csv')
        with target.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(columns)
            writer.writerows(rows)
        manifest['files'][target.name] = {'rows': len(rows), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--campaign-id', type=int, required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(export_campaign(args.db, args.campaign_id, args.out), ensure_ascii=False, indent=2))
    except (ValueError, FileExistsError, sqlite3.Error) as exc:
        parser.exit(1, 'Export cancelled: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
