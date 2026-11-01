from datetime import datetime

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
}


def log_user_action(user_id: int, action: str, detail: str | None = None, commit: bool = False) -> ActionLog:
    entry = ActionLog(
        user_id=user_id,
        action=action,
        detail=detail,
        created_at=datetime.utcnow(),
    )
    db.session.add(entry)
    if commit:
        db.session.commit()
    return entry
