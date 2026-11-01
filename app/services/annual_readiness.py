"""Read-only database readiness checks before enabling another campaign.

This report is deliberately NOT an activation permission: unscoped legacy routes
must also be refactored and integration tested before a year can be activated.
"""
from sqlalchemy import text
from app import db

TABLES = ('product', 'user_vote', 'user_favorite', 'order')
LINKED = ('user_vote', 'user_favorite', 'order')


def inspect_annual_readiness():
    """Return diagnostic findings without modifying the session or database."""
    findings = []
    campaigns = db.session.execute(text('SELECT id, year, status FROM campaign ORDER BY year')).all()
    active = [c for c in campaigns if c.status == 'legacy_active']
    drafts = [c for c in campaigns if c.status == 'draft']
    if len(active) > 1:
        findings.append('Hay varias campañas activas.')
    if len(drafts) > 1:
        findings.append('Hay varios borradores simultáneos.')
    if not drafts:
        findings.append('No hay una campaña en borrador.')
    if active and drafts:
        findings.append('Debe archivarse la campaña activa antes de activar un borrador.')

    for table in TABLES:
        # Names are fixed constants, never request parameters.
        unassigned = db.session.execute(text(
            f'SELECT COUNT(*) FROM "{table}" WHERE campaign_id IS NULL'
        )).scalar_one()
        if unassigned:
            findings.append(f'{table}: {unassigned} registros sin campaña.')
        dangling = db.session.execute(text(
            f'SELECT COUNT(*) FROM "{table}" t LEFT JOIN campaign c ON c.id = t.campaign_id '
            'WHERE t.campaign_id IS NOT NULL AND c.id IS NULL'
        )).scalar_one()
        if dangling:
            findings.append(f'{table}: {dangling} registros de una campaña inexistente.')

    for table in LINKED:
        mismatches = db.session.execute(text(
            f'SELECT COUNT(*) FROM "{table}" t LEFT JOIN product p ON p.id = t.product_id '
            'WHERE p.id IS NULL OR p.campaign_id IS NULL OR '
            't.campaign_id IS NULL OR p.campaign_id != t.campaign_id'
        )).scalar_one()
        if mismatches:
            findings.append(f'{table}: {mismatches} relaciones con productos de otra campaña o inexistentes.')
        missing_members = db.session.execute(text(
            f'SELECT COUNT(*) FROM "{table}" t LEFT JOIN campaign_participation cp '
            'ON cp.campaign_id = t.campaign_id AND cp.user_id = t.user_id '
            'WHERE cp.id IS NULL'
        )).scalar_one()
        if missing_members:
            findings.append(f'{table}: {missing_members} registros sin inscripción anual.')

    # A draft is a preparation workspace: its catalogue and annual roster are
    # expected and must not be classified as corruption. Operational records
    # (votes, orders, favourites) are forbidden until explicit activation.
    draft_preparation = {}
    for campaign in drafts:
        counts = {}
        for table in ('product', 'campaign_participation', *LINKED):
            counts[table] = db.session.execute(text(
                f'SELECT COUNT(*) FROM "{table}" WHERE campaign_id = :campaign_id'
            ), {'campaign_id': campaign.id}).scalar_one()
        # Annual consent is stored on the participation, not on the durable
        # User account. An approval from a previous year cannot count here.
        consent = db.session.execute(text('''
            SELECT
              SUM(CASE WHEN status = 'approved' AND
                       signed_document IS NOT NULL AND
                       TRIM(signed_document) != '' THEN 1 ELSE 0 END),
              SUM(CASE WHEN status = 'approved' AND
                       (signed_document IS NULL OR
                        TRIM(signed_document) = '') THEN 1 ELSE 0 END)
            FROM campaign_participation WHERE campaign_id = :campaign_id
        '''), {'campaign_id': campaign.id}).one()
        counts['approved_with_document'] = int(consent[0] or 0)
        counts['approved_without_document'] = int(consent[1] or 0)
        draft_preparation[campaign.year] = counts
        if counts['approved_without_document']:
            findings.append(
                f"Borrador {campaign.year}: {counts['approved_without_document']} "
                'inscripciones aprobadas sin documento anual firmado.'
            )
        for table in LINKED:
            if counts[table]:
                findings.append(
                    f'Borrador {campaign.year}: {counts[table]} registros operativos en {table}; '
                    'no se permiten pedidos, votos ni favoritos antes de la activación.'
                )

    # Audit every campaign-owned table, not just the four original operational
    # tables. A forgotten annual table must never silently pass the preflight.
    from sqlalchemy import inspect as sa_inspect
    inspector = sa_inspect(db.engine)
    existing = set(inspector.get_table_names())
    for table in sorted(existing):
        if table in TABLES or table == 'campaign':
            continue
        columns = {column['name'] for column in inspector.get_columns(table)}
        if 'campaign_id' not in columns:
            continue
        # Table names originate from the database inspector, not HTTP input.
        quoted = db.engine.dialect.identifier_preparer.quote(table)
        orphaned = db.session.execute(text(
            f'SELECT COUNT(*) FROM {quoted} t LEFT JOIN campaign c '
            'ON c.id = t.campaign_id '
            'WHERE t.campaign_id IS NULL OR c.id IS NULL'
        )).scalar_one()
        if orphaned:
            findings.append(f'{table}: {orphaned} registros sin campaña válida.')

    # SQLite foreign keys may be disabled on older databases or connections.
    # Explicitly check them rather than trusting connection configuration.
    if db.engine.dialect.name == 'sqlite':
        violations = db.session.execute(text('PRAGMA foreign_key_check')).all()
        if violations:
            findings.append(f'SQLite: {len(violations)} violaciones de claves foráneas.')

    # Separate actionable draft-data prerequisites from the release-wide gate.
    # This never grants activation: routes and end-to-end tests remain pending.
    from app.services.draft_activation_preflight import evaluate_draft_activation
    archived_years = [c.year for c in campaigns if c.status in ('archived', 'closed')]
    draft_activation = {
        c.year: evaluate_draft_activation(
            year=c.year, counts=draft_preparation[c.year],
            database_findings=findings, archived_years=archived_years)
        for c in drafts
    }

    # Even a clean database cannot certify legacy routes or global configuration.
    return {'database_consistent': not findings, 'findings': findings,
            'draft_preparation': draft_preparation,
            'draft_activation': draft_activation,
            'activation_enabled': False,
            'caution': 'La activación continúa deshabilitada hasta aislar las rutas y probar Flask/Docker.'}
