"""Executable tests for the archive service with realistic historical registry."""
import importlib.util
import tempfile
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from openpyxl import Workbook

SRC = Path(__file__).resolve().parents[1] / 'app/services/campaign_archive.py'

class Campaign:
    def __init__(self, year, status, id):
        self.year, self.status, self.id = year, status, id
        self.archived_at = None

class Query:
    def __init__(self, rows): self.rows = rows
    def all(self): return self.rows

class ArchiveTests(unittest.TestCase):
    def run_archive(self, rows, year=2027, phase='order', generated='2027-10-10', file=True):
        logs=[]
        session=types.SimpleNamespace(commit=lambda: logs.append('commit'))
        fake_app=types.ModuleType('app')
        fake_app.db=types.SimpleNamespace(session=session)
        fake_models=types.ModuleType('app.models')
        fake_models.Campaign=type('CampaignModel', (), {'query':Query(rows)})
        fake_phase=types.ModuleType('app.services.campaign_phase')
        fake_phase.get_campaign_phase=lambda: phase
        fake_settings=types.ModuleType('app.services.campaign_settings')
        fake_settings.get_annual_setting=lambda key: {'final_order_generated_at':generated,'final_order_excel':'order.xlsx'}[key]
        fake_log=types.ModuleType('app.services.activity_log')
        fake_log.log_user_action=lambda *args:logs.append(args)
        fake_services=types.ModuleType('app.services')
        fake_exports=types.ModuleType('app.services.order_exports')
        fake_exports.build_final_order_context=lambda: {
            'products': [{'product': types.SimpleNamespace(reference='3001', name='Brick', colour_id=1, price=0.1),
                          'total_quantity': 10, 'total_amount': 1.0}], 'base_total': 1.0}

        modules={'app':fake_app,'app.models':fake_models,'app.services':fake_services,
                 'app.services.campaign_phase':fake_phase,'app.services.campaign_settings':fake_settings,
                 'app.services.activity_log':fake_log,
                 'app.services.order_exports':fake_exports}
        with tempfile.TemporaryDirectory() as folder,patch.dict(sys.modules, modules):
            if file:
                workbook=Workbook()
                sheet=workbook.active
                sheet.title='Pedido'
                sheet.append(['Referencia','Nombre','Color','Precio unitario','Cantidad total','Importe total'])
                sheet.append(['3001','Brick',1,0.1,10,1.0])
                sheet.append(['','','','','Total',1.0])
                workbook.save(Path(folder)/'order.xlsx')
            spec=importlib.util.spec_from_file_location('archive_under_test',SRC)
            mod=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            try:
                result=mod.archive_completed_campaign(year=year,export_folder=folder,actor_id=9)
                return result,logs,None
            except mod.CampaignArchiveError as exc:
                return None,logs,str(exc)

    def test_multiple_archived_years_are_allowed(self):
        rows=[Campaign(2025,'archived',1),Campaign(2026,'closed',2),Campaign(2027,'legacy_active',3)]
        result,logs,error=self.run_archive(rows)
        self.assertIsNone(error)
        self.assertIs(result,rows[-1])
        self.assertEqual(result.status,'archived')
        self.assertIsNotNone(result.archived_at)
        self.assertEqual([r.status for r in rows[:2]],['archived','closed'])
        self.assertEqual(logs[-1],'commit')
        self.assertEqual(len(logs),2)

    def test_draft_blocks_archive(self):
        rows=[Campaign(2026,'archived',1),Campaign(2027,'legacy_active',2),Campaign(2028,'draft',3)]
        result,logs,error=self.run_archive(rows)
        self.assertIsNone(result)
        self.assertIn('incompatible',error)
        self.assertEqual(logs,[])

    def test_two_active_campaigns_block_archive(self):
        rows=[Campaign(2026,'legacy_active',1),Campaign(2027,'legacy_active',2)]
        self.assertIn('exactamente una',self.run_archive(rows)[2])

    def test_wrong_year_blocks_archive(self):
        rows=[Campaign(2026,'archived',1),Campaign(2027,'legacy_active',2)]
        self.assertIn('no está activa',self.run_archive(rows,year=2026)[2])
        self.assertEqual(rows[1].status,'legacy_active')

    def test_no_excel_blocks_archive(self):
        rows=[Campaign(2027,'legacy_active',1)]
        self.assertIn('No se encuentra',self.run_archive(rows,file=False)[2])
        self.assertEqual(rows[0].status,'legacy_active')

    def test_wrong_phase_blocks_archive(self):
        rows=[Campaign(2027,'legacy_active',1)]
        self.assertIn('fase de pedidos',self.run_archive(rows,phase='first')[2])

if __name__=='__main__': unittest.main()
