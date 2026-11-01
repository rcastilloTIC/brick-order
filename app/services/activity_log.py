from app.time_utils import utc_now

from app import db
from app.models import ActionLog

ACTION_LABELS = {
    "login": "Login",
    "password_change": "Cambio de contraseña",
    "password_reset": "Reset de contraseña",
    "vote_added": "Voto registrado",
    "vote_updated": "Voto actualizado",
    "vote_deleted": "Voto eliminado",
    "admin_clean_data": "Limpieza de datos",
    "admin_toggle_test_mode": "Modo de pruebas",
    "admin_order_add": "Pedido admin: alta",
    "admin_order_update": "Pedido admin: edicion",
    "admin_order_delete": "Pedido admin: eliminacion",
    "excel_import": "Carga de piezas",
    "admin_campaign_activate": "Activa la campaña",
    "admin_campaign_archive": "Archiva la campaña",
    "admin_campaign_draft": "Crea el borrador del año siguiente",
    "campaign_calendar_changed": "Cambia el calendario",
    "commitment_changed": "Cambia el documento de compromiso",
    "document_approved": "Aprueba una declaración",
    "document_rejected": "Rechaza una declaración",
    "document_uploaded": "Sube su declaración firmada",
    "draft_catalog_import": "Importa el catálogo del borrador",
    "limits_changed": "Cambia los límites",
    "shortage_open": "Abre el plazo de pedido insuficiente",
    "shortage_close": "Cierra el plazo de pedido insuficiente",
    "shortage_order_increase": "Amplía su pedido en el plazo extraordinario",
    "campaign_closed": "Cierra la campaña cancelada",
}


def log_user_action(user_id: int, action: str, detail: str | None = None, commit: bool = False) -> ActionLog:
    entry = ActionLog(
        user_id=user_id,
        action=action,
        detail=detail,
        created_at=utc_now(),
    )
    db.session.add(entry)
    if commit:
        db.session.commit()
    return entry
