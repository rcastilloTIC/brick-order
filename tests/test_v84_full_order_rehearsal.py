"""V84: isolated real-service rehearsal; inherits V83 cross-year fixtures.

Not a substitute for the unimplemented shortage-notice/cancellation workflow.
"""
import unittest
from decimal import Decimal
from werkzeug.exceptions import Conflict
from app import db
from app.models import Campaign, Config, Order, Product, UserVote
from app.services.campaign_phase import get_campaign_phase, set_campaign_phase
from app.services.campaign_settings import get_annual_setting, set_annual_setting, annual_key
from app.services.order_materialization import materialize_selected_commitments, assert_selected_commitments_materialized
from app.services.commitment_ledger import effective_commitment, materialized_order_quantity
from app.services.vote_commitments import assert_nondecreasing_vote
from app.services.campaign_registry import create_next_campaign_draft
from test_v83_multi_campaign_auto import MultiCampaignAutomaticTests

class FullOrderAutomaticTests(MultiCampaignAutomaticTests):
    def test_real_selected_cutoff_85_and_no_rejected_orders(self):
        selected = Product.query.filter_by(campaign_id=2, final_selected=True, final_disabled=False).all()
        self.assertEqual(len(selected),85)
        rejected = {p.id for p in Product.query.filter_by(campaign_id=2, final_selected=False).all()}
        self.assertEqual(len(rejected),15)
        materialize_selected_commitments()
        assert_selected_commitments_materialized()
        self.assertEqual(Order.query.filter_by(campaign_id=2).count(),16*85)
        self.assertFalse({o.product_id for o in Order.query.filter_by(campaign_id=2).all()} & rejected)

    def test_selected_commitment_is_binding_and_rejected_vote_is_released(self):
        votes = [(1001,Decimal('0.20'),10),(1090,Decimal('0.20'),15)]
        self.assertEqual(effective_commitment([],votes,phase='second'),Decimal('5.00'))
        self.assertEqual(effective_commitment([],votes,phase='final',selected_product_ids={1001}),Decimal('2.00'))
        with self.assertRaises(ValueError):
            effective_commitment([],votes,phase='order',selected_product_ids={1001},
                                 additional=(1090,Decimal('0.20'),1))

    def test_voting_cannot_decrease_pledged_quantity(self):
        assert_nondecreasing_vote(10,10)
        assert_nondecreasing_vote(10,11)
        with self.assertRaises(Conflict):
            assert_nondecreasing_vote(10,9)
        with self.assertRaises(Conflict):
            assert_nondecreasing_vote(10,0)

    def test_additive_order_respects_floor_and_materialization_idempotence(self):
        self.assertEqual(materialized_order_quantity([],[(1001,0.2,10)],product_id=1001,additional_quantity=5),15)
        self.assertEqual(materialized_order_quantity([(1001,0.2,10)],[(1001,0.2,10)],product_id=1001,additional_quantity=5),5)
        first=materialize_selected_commitments()
        self.assertEqual(first[0],16*85)
        self.assertEqual(materialize_selected_commitments(),(0,0))
        assert_selected_commitments_materialized()

    def test_campaign_minimum_below_then_above_with_real_stored_orders(self):
        set_annual_setting('limit_minimum_total','4800')
        self.assertEqual(Decimal(get_annual_setting('limit_minimum_total')),Decimal('4800'))
        materialize_selected_commitments()
        def total():
            rows=db.session.query(Order.quantity,Product.price).join(Product,Product.id==Order.product_id).filter(Order.campaign_id==2).all()
            return sum((Decimal(str(q))*Decimal(str(p)) for q,p in rows),Decimal('0'))
        self.assertLess(total(),Decimal('4800'))
        db.session.add(Order(campaign_id=2,user_id=15,product_id=1001,quantity=25000))
        db.session.flush()
        self.assertGreaterEqual(total(),Decimal('4800'))
        assert_selected_commitments_materialized()

    def test_annual_minimum_and_phase_do_not_pass_to_next_year(self):
        set_annual_setting('limit_minimum_total','4800')
        set_campaign_phase('order')
        self.assertEqual(get_campaign_phase(),'order')
        db.session.query(Campaign).filter(Campaign.id==2).update({'status':'archived'})
        db.session.add(Campaign(id=3,year=2027,title='Fictional 2027',status='legacy_active'))
        db.session.flush()
        self.assertEqual(get_campaign_phase(),'first')
        self.assertIsNone(get_annual_setting('limit_minimum_total'))
        self.assertEqual(Config.get(annual_key('limit_minimum_total',2)),'4800')
        self.assertEqual(Order.query.filter_by(campaign_id=3).count(),0)
        self.assertEqual(UserVote.query.filter_by(campaign_id=3).count(),0)

    def test_next_draft_cannot_open_before_archival(self):
        with self.assertRaises(ValueError):
            create_next_campaign_draft(year=2027,title='Fictional 2027',actor_id=1)
        self.assertEqual(Campaign.query.count(),2)

    def test_next_draft_after_archival_has_no_inherited_users(self):
        for c in Campaign.query.all(): c.status='archived'
        db.session.flush()
        draft=create_next_campaign_draft(year=2027,title='Fictional 2027',actor_id=1)
        self.assertEqual(draft.status,'draft')
        self.assertFalse(draft.participations)
        self.assertEqual(Product.query.filter_by(campaign_id=draft.id).count(),0)
        self.assertEqual(Order.query.filter_by(campaign_id=draft.id).count(),0)
        self.assertEqual(UserVote.query.filter_by(campaign_id=draft.id).count(),0)
        self.assertEqual(get_campaign_phase(),'first')

if __name__=='__main__': unittest.main()
