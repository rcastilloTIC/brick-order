"""Transactional, campaign-isolated import of a future year's catalog."""
from math import isfinite
from app import db
from app.models import Campaign, Product, ActionLog


ALLOWED_CATALOG_FIELDS = frozenset({
    'name', 'price', 'image_url', 'colour_id', 'main_group_top',
    'main_group', 'main_group_sub', 'is_locked', 'present_in_2024',
    'present_in_2025',
})


def validate_draft_catalog_rows(rows: dict) -> None:
    """Reject malformed Excel payloads before any database write."""
    if not isinstance(rows, dict) or not rows:
        raise ValueError('El catálogo está vacío o tiene un formato incorrecto.')
    if len(rows) > 100000:
        raise ValueError('El catálogo supera el máximo de 100000 referencias.')
    normalized = set()
    for reference, fields in rows.items():
        if not isinstance(reference, str) or not reference.strip() or len(reference) > 100:
            raise ValueError('Referencia inválida.')
        clean = reference.strip().casefold()
        if clean in normalized or reference != reference.strip():
            raise ValueError(f'Referencia duplicada o con espacios: {reference}.')
        normalized.add(clean)
        if not isinstance(fields, dict) or not isinstance(fields.get('name'), str) or not fields['name'].strip():
            raise ValueError(f'Descripción inválida para {reference}.')
        if 'reference' in fields and fields['reference'] != reference:
            raise ValueError(f'Referencia inconsistente para {reference}.')
        unknown = fields.keys() - ALLOWED_CATALOG_FIELDS - {'reference'}
        if unknown:
            raise ValueError(f'Columnas no admitidas para {reference}: {sorted(unknown)}.')
        # Enforce the actual Product column limits before opening a transaction.
        text_limits = {
            'name': 255, 'image_url': 255, 'colour_id': 50,
            'main_group_top': 100, 'main_group': 100, 'main_group_sub': 100,
        }
        for field, limit in text_limits.items():
            if field in fields:
                value = fields[field]
                if value is not None and (not isinstance(value, str) or len(value) > limit):
                    raise ValueError(f'Campo {field} inválido para {reference}.')
        for field in ('is_locked', 'present_in_2024', 'present_in_2025'):
            if field in fields and not isinstance(fields[field], bool):
                raise ValueError(f'Indicador {field} inválido para {reference}.')
        if 'price' in fields:
            price = fields['price']
            if isinstance(price, bool) or not isinstance(price, (int, float)) or not isfinite(price) or price < 0:
                raise ValueError(f'Precio inválido para {reference}.')


def import_draft_catalog(campaign_id: int, rows: dict, *, actor_id: int) -> dict:
    """Upsert by (campaign, reference), never copy or modify archived products.

    Validate the entire file before making any writes. Caller must hold admin access.
    """
    validate_draft_catalog_rows(rows)
    try:
        draft = Campaign.query.filter_by(id=campaign_id, status='draft').one_or_none()
        if draft is None:
            raise ValueError('La campaña ya no está en borrador.')
        # Recheck before writing: a draft must not coexist with an operating year.
        if Campaign.query.filter_by(status='legacy_active').first() is not None:
            raise ValueError('Archiva la campaña operativa antes de preparar el borrador.')
        existing = Product.query.filter_by(campaign_id=campaign_id).all()
        by_ref = {p.reference: p for p in existing}
        existing_normalized = [p.reference.strip().casefold() for p in existing]
        if len(set(existing_normalized)) != len(existing) or len(by_ref) != len(existing):
            raise ValueError('El borrador tiene referencias duplicadas; revisa su integridad.')
        incoming_normalized = {reference.casefold(): reference for reference in rows}
        for product in existing:
            matched = incoming_normalized.get(product.reference.strip().casefold())
            if matched is not None and matched != product.reference:
                raise ValueError(
                    f'La referencia {matched} ya existe como {product.reference}; '
                    'corrige las mayúsculas antes de importar.')
        created = updated = 0
        for reference, fields in rows.items():
            product = by_ref.get(reference)
            if product is None:
                product = Product(campaign_id=campaign_id, reference=reference)
                db.session.add(product)
                created += 1
            else:
                updated += 1
            for key in ALLOWED_CATALOG_FIELDS.intersection(fields):
                setattr(product, key, fields[key])
            product.present_in_2025 = True
        for reference, product in by_ref.items():
            if reference not in rows:
                product.present_in_2025 = False
        db.session.add(ActionLog(user_id=actor_id, action='draft_catalog_import',
                                 detail=f'Campaña {draft.year}: {created} nuevas, {updated} actualizadas'))
        db.session.commit()
        return {'created': created, 'updated': updated, 'missing': len(by_ref.keys() - rows.keys())}
    except Exception:
        db.session.rollback()
        raise
