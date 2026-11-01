"""One-time metadata registration; does NOT create or reset operational data.

Usage: python register_existing_campaign.py 2026 "Campaña 2026"
Run only after backing up the database.
"""
import sys
from run import app
from app import db
from app.services.campaign_registry import register_current_campaign


def main(argv):
    if len(argv) != 3:
        raise SystemExit('Usage: python register_existing_campaign.py YEAR TITLE')
    with app.app_context():
        db.create_all()
        campaign = register_current_campaign(int(argv[1]), argv[2])
        print(f'Registered campaign {campaign.year}: {campaign.title}')


if __name__ == '__main__':
    main(sys.argv)
