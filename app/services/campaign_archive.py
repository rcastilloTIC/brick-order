"""One-way archival of the single operational campaign, retaining older years.

Does not activate a new campaign: legacy route scoping is incomplete.
"""
from app.time_utils import utc_now
from pathlib import Path
from zipfile import BadZipFile, ZipFile
from decimal import Decimal, InvalidOperation
from openpyxl import load_workbook
from app import db
from app.models import Campaign
from app.services.campaign_phase import get_campaign_phase
from app.services.campaign_settings import get_annual_setting


class CampaignArchiveError(ValueError):
    pass


def valid_final_workbook(path: Path) -> bool:
    """Require a readable XLSX workbook, not just a non-empty renamed file."""
    try:
        with ZipFile(path) as workbook:
            names = set(workbook.namelist())
            required = {'[Content_Types].xml', '_rels/.rels', 'xl/workbook.xml'}
            if not required.issubset(names):
                return False
            # Check compressed payload integrity, including the workbook XML.
            if workbook.testzip() is not None:
                return False
            return bool(workbook.read('xl/workbook.xml').strip())
    except (OSError, BadZipFile, ValueError, RuntimeError, EOFError):
        return False



def _finite_decimal(value):
    """Reject booleans, Excel formulas, non-numeric and non-finite values."""
    if isinstance(value, bool) or value is None or not isinstance(value, (int, float, Decimal)):
        raise ValueError('Invalid numeric cell')
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError('Non-finite numeric cell')
    return number


def final_workbook_matches_order(path: Path, summary: dict) -> bool:
    """Compare the final XLSX against current campaign's authoritative order.

    Reject duplicate/missing/foreign references, edited quantities/prices and
    totals. Excel formulas are not accepted as numeric order values.
    """
    book = None
    try:
        book = load_workbook(path, read_only=True, data_only=False)
        if book.sheetnames != ['Pedido']:
            return False
        rows = book['Pedido'].iter_rows(values_only=True)
        header = next(rows, None)
        if header != ('Referencia', 'Nombre', 'Color', 'Precio unitario', 'Cantidad total', 'Importe total'):
            return False
        expected = {}
        for item in summary['products']:
            product = item['product']
            reference = str(product.reference)
            if reference in expected:
                return False
            expected[reference] = (
                str(product.name or ''),
                str(product.colour_id or ''),
                _finite_decimal(product.price or 0),
                int(item['total_quantity']),
                _finite_decimal(item['total_amount']),
            )
        if not expected:
            return False
        seen = set()
        total_found = False
        for row in rows:
            values = tuple(row[:6]) + (None,) * max(0, 6 - len(row))
            if len(row) > 6 and any(cell is not None for cell in row[6:]):
                return False
            ref, name, colour, price, quantity, amount = values[:6]
            if ref in (None, '') and name in (None, '') and colour in (None, '') and price in (None, '') and quantity == 'Total':
                if total_found or seen != set(expected):
                    return False
                if _finite_decimal(amount) != _finite_decimal(summary['base_total']):
                    return False
                total_found = True
                continue
            if total_found or ref is None:
                return False
            key = str(ref)
            if key not in expected or key in seen:
                return False
            want_name, want_colour, want_price, want_quantity, want_amount = expected[key]
            if (str(name or '') != want_name or str(colour or '') != want_colour
                    or isinstance(quantity, bool) or not isinstance(quantity, int)
                    or quantity != want_quantity or _finite_decimal(price) != want_price
                    or _finite_decimal(amount) != want_amount):
                return False
            seen.add(key)
        return total_found and seen == set(expected)
    except (OSError, ValueError, TypeError, KeyError, InvalidOperation, BadZipFile, StopIteration):
        return False
    finally:
        if book is not None:
            book.close()

def archive_completed_campaign(*, year: int, export_folder: str, actor_id: int):
    """Fail closed unless a finished order and its XLSX are present.

    This transition is atomic with its audit record, and is idempotently
    rejected on repeat. Existing orders/votes are never deleted.
    """
    from app.services.activity_log import log_user_action
    # Archived/closed years must never prevent archiving the current year.
    # A draft is also forbidden here: an operational year must be finished
    # before its successor is prepared. Reject unknown status values.
    campaigns = Campaign.query.all()
    active = [c for c in campaigns if c.status == 'legacy_active']
    if len(active) != 1:
        raise CampaignArchiveError('Debe existir exactamente una campaña activa.')
    if any(c.status not in ('legacy_active', 'archived', 'closed') for c in campaigns):
        raise CampaignArchiveError('Hay campañas en un estado incompatible con el archivado.')
    campaign = active[0]
    if campaign.year != year:
        raise CampaignArchiveError('La campaña indicada no está activa.')
    if get_campaign_phase() not in ('order'):
        raise CampaignArchiveError('Solo se puede archivar una campaña en fase de pedidos.')
    if not get_annual_setting('final_order_generated_at'):
        raise CampaignArchiveError('Primero hay que generar el pedido definitivo.')
    filename = get_annual_setting('final_order_excel')
    # Only the application-generated basename is accepted.
    if not filename or Path(filename).name != filename or not filename.lower().endswith('.xlsx'):
        raise CampaignArchiveError('Falta el Excel definitivo válido.')
    destination = Path(export_folder) / filename
    # Never trust a symlinked export: it could point outside the export folder
    # or to an unrelated file, even when the basename is valid.
    try:
        valid_export = (
            not destination.is_symlink()
            and destination.resolve().parent == Path(export_folder).resolve()
            and destination.is_file()
            and destination.stat().st_size > 0
            and valid_final_workbook(destination)
        )
    except (OSError, RuntimeError, ValueError):
        valid_export = False
    if not valid_export:
        raise CampaignArchiveError('No se encuentra el Excel definitivo válido en el servidor.')
    from app.services.order_exports import build_final_order_context
    if not final_workbook_matches_order(destination, build_final_order_context()):
        raise CampaignArchiveError('El Excel definitivo no coincide con los pedidos de la campaña.')
    try:
        campaign.status = 'archived'
        campaign.archived_at = utc_now()
        log_user_action(actor_id, 'admin_campaign_archive',
                        f'Campaña {campaign.year} (id={campaign.id}) archivada.')
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return campaign
