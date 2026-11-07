"""Regresión (ronda 4): previsualización e importación aplican las mismas reglas al catálogo."""
import io
from openpyxl import Workbook
from app.models import Product
from tests._v92_campaign_fixture import _V92CampaignFixture


def _xlsx(rows):
    wb = Workbook(); ws = wb.active
    ws.append(["Material", "Description", "price"])
    for row in rows:
        ws.append(list(row))
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


class CatalogImportRegression(_V92CampaignFixture):
    ROWS = [(9900101, "Primera", 0.5), (9900101, "DUPLICADA", 0.75), (9900102, "Sin precio", None),
            (9900103, "Texto", "gratis"), (9900104, "NaN", "nan"), (9900105, "Infinito", "inf"),
            (9900106, "Negativo", -1), (9900107, "Cero", 0), (9900108, "Coma decimal", "1,20")]

    def _import(self, rows):
        self.login_as(self.ADMIN_ID)
        first = self.client.post('/admin/upload-data', data={'excel_file': (io.BytesIO(_xlsx(rows)), 'c.xlsx')},
                                 content_type='multipart/form-data')
        preview = first.get_data(as_text=True)
        self.client.post('/admin/upload-data', data={'confirm_upload': '1'})  # existing catalogue -> preview + confirm
        return preview

    def _get(self, ref):
        return Product.query.filter_by(campaign_id=self.ACTIVE_CAMPAIGN_ID, reference=str(ref)).one_or_none()

    def test_duplicates_and_invalid_prices_behave_as_previewed(self):
        preview = self._import(self.ROWS)
        self.assertIn('referencia duplicada 9900101', preview)
        self.assertEqual(self._get(9900101).name, 'Primera')        # first row wins, not overwritten
        self.assertEqual(self._get(9900101).price, 0.5)
        for ref in (9900103, 9900104, 9900105, 9900106, 9900107):
            self.assertIsNone(self._get(ref), ref)                   # unusable price: row skipped
        self.assertIsNotNone(self._get(9900102))                     # empty price: imported, flagged
        self.assertIsNone(self._get(9900102).price)
        self.assertAlmostEqual(self._get(9900108).price, 1.20)       # Spanish decimal comma accepted

    def test_invalid_price_never_overwrites_existing_price(self):
        before = self._get('LADRILLO-ROJO').price
        self._import([('LADRILLO-ROJO', "Roja", "nan")])
        self.assertEqual(self._get('LADRILLO-ROJO').price, before)
