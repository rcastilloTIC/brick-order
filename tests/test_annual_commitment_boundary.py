import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class AnnualCommitmentBoundary(unittest.TestCase):
    def test_template_campaign_scoped(self):
        cfg = (ROOT / 'app/services/campaign_settings.py').read_text()
        self.assertIn('"commitment_pdf"', cfg)
        main = (ROOT / 'app/main/routes.py').read_text()
        self.assertIn("set_annual_setting('commitment_pdf', filename)", main)
        self.assertNotIn("Config.set('commitment_pdf'", main)

    def test_no_global_approval_reset(self):
        main = (ROOT / 'app/main/routes.py').read_text()
        self.assertNotIn('User.query.filter_by(is_admin=False).update', main)
        self.assertIn("CampaignParticipation.query.filter_by(campaign_id=active_campaign_id())", main)

    def test_documents_are_annual(self):
        main = (ROOT / 'app/main/routes.py').read_text()
        self.assertIn('membership.signed_document', main)
        self.assertIn("membership.status = 'rejected'", main)
        template = (ROOT / 'templates/admin_commitment.html').read_text()
        self.assertIn('documents.get(user.id)', template)

    def test_login_not_using_lifetime_validation(self):
        auth = (ROOT / 'app/auth/routes.py').read_text()
        login_section = auth.split('def _next_destination_after_login(',1)[1].split('def _allowed_pdf',1)[0]
        self.assertNotIn('user.declaration_validated', login_section)
        self.assertIn("membership.status != 'approved'", login_section)

if __name__ == '__main__': unittest.main()
