"""Exercise the actual service functions with isolated database doubles."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'app/services/campaign_participation.py'


class ArchivedParticipationGuardTests(unittest.TestCase):
    def setUp(self):
        source = ast.parse(SOURCE.read_text())
        names = {'_require_active_membership_campaign', 'enroll_existing_user',
                 'submit_signed_document', 'review_signed_document'}
        functions = [node for node in source.body if isinstance(node, ast.FunctionDef)
                     and node.name in names]
        self.campaigns = {}
        campaigns = self.campaigns

        class Query:
            def filter_by(self, **kwargs):
                self.id = kwargs['id']
                return self
            def first(self):
                return campaigns.get(self.id)

        db = SimpleNamespace(session=SimpleNamespace(add=lambda entry: None, flush=lambda: None))
        scope = {'Campaign': SimpleNamespace(query=Query()), 'db': db,
                 'User': SimpleNamespace(query=Query()), 'CampaignParticipation': object,
                 'IntegrityError': RuntimeError, 'datetime': SimpleNamespace(utcnow=lambda: None), 'utc_now': lambda: None,
                 'participation_for': lambda *args: None,
                 'VALID_STATUSES': {'pending_commitment', 'pending_review', 'approved', 'rejected'}}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), 'exec'), scope)
        self.scope = scope

    def test_archived_and_closed_enrolment_rejected_before_user_lookup(self):
        for status in ('archived', 'closed', 'invalid'):
            with self.subTest(status=status):
                self.campaigns[9] = SimpleNamespace(status=status)
                with self.assertRaisesRegex(ValueError, 'Cannot enrol'):
                    self.scope['enroll_existing_user'](9, 7)

    def test_archived_document_submission_does_not_mutate(self):
        self.campaigns[9] = SimpleNamespace(status='archived')
        entry = SimpleNamespace(campaign_id=9, status='approved', signed_document='old.pdf')
        with self.assertRaisesRegex(ValueError, 'non-active'):
            self.scope['submit_signed_document'](entry, 'new.pdf')
        self.assertEqual(entry.signed_document, 'old.pdf')
        self.assertEqual(entry.status, 'approved')

    def test_archived_approval_does_not_mutate(self):
        self.campaigns[9] = SimpleNamespace(status='closed')
        entry = SimpleNamespace(campaign_id=9, status='pending_review', signed_document='old.pdf')
        with self.assertRaisesRegex(ValueError, 'non-active'):
            self.scope['review_signed_document'](entry, SimpleNamespace(is_admin=True), True)
        self.assertEqual(entry.status, 'pending_review')

    def test_active_document_update_remains_available(self):
        self.campaigns[9] = SimpleNamespace(status='legacy_active')
        entry = SimpleNamespace(campaign_id=9, status='approved', signed_document='old.pdf')
        self.scope['submit_signed_document'](entry, 'new.pdf')
        self.assertEqual((entry.status, entry.signed_document), ('pending_review', 'new.pdf'))


if __name__ == '__main__':
    unittest.main()
