"""Un participante NUEVO (contraseña provisional, sin declaración) debe poder cambiar su contraseña."""
from app import db
from app.models import CampaignParticipation, User
from tests._v92_campaign_fixture import _V92CampaignFixture

class NewParticipantOnboarding(_V92CampaignFixture):
    def test_new_participant_can_change_initial_password(self):
        user = db.session.get(User, 2)
        user.must_change_password = True
        membership = CampaignParticipation.query.filter_by(campaign_id=self.ACTIVE_CAMPAIGN_ID, user_id=2).one()
        membership.status, membership.signed_document = 'pending_commitment', None
        db.session.commit()
        self.login_as(2)
        r = self.client.post('/change-password', data={'new_password': 'Nueva-clave-ensayo-1',
                                                       'confirm_password': 'Nueva-clave-ensayo-1'})
        db.session.expire_all()
        print('\n  HTTP', r.status_code, '->', r.headers.get('Location'),
              '| must_change_password:', db.session.get(User, 2).must_change_password)
        self.assertFalse(db.session.get(User, 2).must_change_password)
        # Then the participant is sent to upload the signed document, not back again.
        self.assertTrue(r.headers['Location'].endswith('/upload-declaration'))
