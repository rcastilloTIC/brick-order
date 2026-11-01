"""Pure preflight for the next annual campaign; never changes campaign state.

This checks data prerequisites, not application-wide route isolation. A green
preflight is not permission to activate while the release gate is disabled.
"""


def evaluate_draft_activation(*, year, counts, database_findings, archived_years):
    """Return actionable blockers for a draft; inputs are read-only snapshots."""
    blockers = []
    if not archived_years:
        blockers.append('No existe una campaña anterior archivada o cerrada.')
    elif year <= max(archived_years):
        blockers.append('El borrador debe ser posterior a todas las campañas archivadas.')
    if database_findings:
        blockers.append('El diagnóstico global de integridad tiene incidencias pendientes.')
    if counts.get('product', 0) <= 0:
        blockers.append('Falta importar el catálogo anual.')
    if counts.get('campaign_participation', 0) <= 0:
        blockers.append('Falta importar la lista anual de participantes.')
    if counts.get('approved_with_document', 0) <= 0:
        blockers.append('Debe existir al menos un participante aprobado con documento firmado de esta campaña.')
    if counts.get('approved_without_document', 0):
        blockers.append('Existen aprobaciones sin documento firmado para este año.')
    for table, label in (('user_vote', 'votaciones'),
                         ('user_favorite', 'favoritos'), ('order', 'pedidos')):
        if counts.get(table, 0):
            blockers.append(f'El borrador ya contiene {label}; debe revisarse.')
    return {'data_prepared': not blockers, 'blockers': blockers,
            'activation_enabled': False}
