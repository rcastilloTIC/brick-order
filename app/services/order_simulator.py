"""Deterministic demonstration of a collective order. NO database imports or writes.

All products, participants and financial amounts are synthetic. This service is
not a source of live campaign analytics and cannot modify business data.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from decimal import Decimal
import random

MAX_PRODUCTS = 180
MAX_USERS = 120
CUTOFF = 85


def _eur(cents: int) -> str:
    return f"{Decimal(cents) / 100:,.2f}"


def build_demo(seed: int = 2026, users: int = 36, products: int = 110,
               *, limits: dict | None = None, minimum_total: float = 4800,
               boost_ref: int = 0, boost_units: int = 0) -> dict:
    """Build reproducible fictitious end-to-end journey (no I/O)."""
    if not (1 <= seed <= 999999 and 5 <= users <= MAX_USERS and 90 <= products <= MAX_PRODUCTS):
        raise ValueError('Simulation input outside safe bounds')
    limits = limits or {}
    individual_cap = int(round(float(limits.get('phase_one_order_limit', 235)) * 100))
    first_refs = int(limits.get('max_refs_phase_one', 10))
    second_refs = int(limits.get('max_refs_phase_two', 20))
    cutoff = int(limits.get('final_selection_limit', CUTOFF))
    if not (100 <= individual_cap <= 100_000_000 and 1 <= first_refs <= 1000
            and first_refs <= second_refs <= 1000 and 1 <= cutoff <= products
            and 0 <= boost_ref <= products and 0 <= boost_units <= 10000
            and (boost_ref or not boost_units) and minimum_total >= 0):
        raise ValueError('Invalid simulation limits or intervention')
    rng = random.Random(seed)
    palette = ('Rojo', 'Azul', 'Negro', 'Blanco', 'Gris', 'Amarillo', 'Verde')
    groups = ('Placas', 'Ladrillos', 'Tiles', 'Ejes', 'Conectores', 'Accesorios')
    catalog = []
    for i in range(products):
        catalog.append(dict(id=i+1, reference=f'SIM-{i+1:04d}',
                            name=f'{groups[i % len(groups)]} · modelo {i+1}',
                            group=groups[i % len(groups)], color=palette[i % len(palette)],
                            price_cents=rng.randint(40, 300)))
    people = [dict(id=i+1, name=f'Participante de prueba {i+1:03d}',
                   budget_cents=rng.randint(max(100, individual_cap * 65 // 100), individual_cap)) for i in range(users)]
    # Phase 1 respects its reference cap. Phase 2 can reach its own cap.
    votes = defaultdict(int)
    budgets = {p['id']: p['budget_cents'] for p in people}
    product_votes = Counter()
    voted_by = defaultdict(set)
    for person in people:
        available = budgets[person['id']]
        picks = rng.sample(catalog, k=min(len(catalog), rng.randint(first_refs, second_refs)))
        for pos, product in enumerate(picks):
            qty = rng.randint(1, 6) if pos < first_refs else rng.randint(1, 4)
            qty = min(qty, available // product['price_cents'])
            if qty:
                votes[(person['id'], product['id'])] += qty
                product_votes[product['id']] += qty
                voted_by[product['id']].add(person['id'])
                available -= qty * product['price_cents']
    base_rank = sorted(catalog, key=lambda p: (-product_votes[p['id']], p['id']))
    base_positions = {p['id']: n for n, p in enumerate(base_rank, 1)}
    intervention_applied = 0
    intervention_person = None
    # Editing a hypothetical participant's vote is an *increase only*. The
    # reference cap and unspent budget are applied as they would be in voting.
    if boost_ref and boost_units:
        product = catalog[boost_ref - 1]
        for person in people:
            uid = person['id']
            current_refs = {pid for u, pid in votes if u == uid}
            if boost_ref not in current_refs and len(current_refs) >= second_refs:
                continue
            used = sum(q * catalog[pid - 1]['price_cents'] for (u, pid), q in votes.items() if u == uid)
            increment = min(boost_units, (budgets[uid] - used) // product['price_cents'])
            if increment:
                votes[(uid, boost_ref)] += increment
                product_votes[boost_ref] += increment
                voted_by[boost_ref].add(uid)
                intervention_applied = increment
                intervention_person = person['name']
                break
    # Stable ranking with reference ID as tie breaker.
    rank = sorted(catalog, key=lambda p: (-product_votes[p['id']], p['id']))
    selected = {p['id'] for p in rank[:cutoff]}
    commitments_before = sum(q * catalog[pid-1]['price_cents'] for (_, pid),q in votes.items())
    retained = {(uid,pid):q for (uid,pid),q in votes.items() if pid in selected}
    commitments_after = sum(q * catalog[pid-1]['price_cents'] for (_,pid),q in retained.items())
    released = commitments_before-commitments_after
    assert released >= 0
    # Final orders respect retained commitments as an immutable floor.
    orders = dict(retained)
    remaining = {p['id']:p['budget_cents'] for p in people}
    for (uid,pid),qty in retained.items():
        remaining[uid] -= qty * catalog[pid-1]['price_cents']
    for uid in remaining:
        for product in rng.sample([p for p in catalog if p['id'] in selected], k=min(35, cutoff)):
            if rng.random() < .27:
                qty = min(rng.randint(1, 3), remaining[uid] // product['price_cents'])
                if qty:
                    orders[(uid,product['id'])] = orders.get((uid,product['id']),0)+qty
                    remaining[uid] -= qty * product['price_cents']
    assert all(orders.get(k,0) >= q for k,q in retained.items())
    assert all(v >= 0 for v in remaining.values())
    final_amount = sum(q * catalog[pid-1]['price_cents'] for (_,pid),q in orders.items())
    assert final_amount <= sum(p['budget_cents'] for p in people)
    # Fictional fulfillment numbers, expressly NOT actual payments/deliveries.
    fulfilled = {uid for uid in remaining if rng.random() > .13}
    paid = {uid for uid in fulfilled if rng.random() > .08}
    units_by_product = Counter()
    total_by_group = Counter()
    for (uid,pid), qty in orders.items():
        p = catalog[pid-1]
        units_by_product[pid] += qty
        total_by_group[p['group']] += qty * p['price_cents']
    top = sorted((p for p in catalog if p['id'] in selected),
                 key=lambda p: (-units_by_product[p['id']],p['id']))[:10]
    peaks = max((units_by_product[p['id']] for p in top), default=1)
    stage_info = [
        ('Configuración', 'Crear una campaña ficticia, un presupuesto por participante y un catálogo de prueba.',
         {'Máximo individual (€)': _eur(individual_cap), 'Participantes': str(users), 'Referencias de catálogo': str(products), 'Presupuesto total (€)': _eur(sum(budgets.values()))}),
        ('Catálogo', 'Simular piezas y colores con precios completamente inventados.',
         {'Referencias': str(products), 'Colores': str(len(palette)), 'Grupos': str(len(groups))}),
        ('Votaciones', 'Cada participante vota sin sobrepasar su presupuesto ficticio.',
         {'Máx. refs. fase 1 / fase 2': f'{first_refs} / {second_refs}', 'Referencias votadas': str(len(product_votes)), 'Piezas comprometidas': str(sum(votes.values())), 'Compromiso inicial (€)': _eur(commitments_before)}),
        ('Corte de referencias', 'Se conservan las referencias del corte configurado y se liberan las descartadas.',
         {'Límite de seleccionadas': str(cutoff), 'Seleccionadas': str(len(selected)), 'Descartadas': str(products-len(selected)), 'Importe liberado (€)': _eur(released)}),
        ('Reconciliación', 'Los compromisos seleccionados son mínimos obligatorios, nunca se reducen.',
         {'Compromiso retenido (€)': _eur(commitments_after), 'Saldo recuperado (€)': _eur(released), 'Referencias con compromiso': str(len({pid for _,pid in retained}))}),
        ('Pedidos finales', 'Se añaden cantidades voluntarias respetando compromisos y límites individuales.',
         {'Total del pedido (€)': _eur(final_amount), 'Unidades totales': str(sum(orders.values())), 'Referencias pedidas': str(len(units_by_product))}),
        ('Preparación y pagos', 'Ejemplo de recepción y pago simulados; no genera transacciones ni facturas.',
         {'Pedidos preparados (simulados)': str(len(fulfilled)), 'Pagos registrados (simulados)': str(len(paid)), 'Pendientes de pago (simulados)': str(users-len(paid))}),
        ('Cierre y auditoría', 'Verificar que la suma coincide y que no hay pedidos inferiores a los compromisos.',
         {'Total final (€)': _eur(final_amount), 'Presupuesto sin usar (€)': _eur(sum(remaining.values())), 'Mínimo colectivo (€)': f'{minimum_total:,.2f}', 'Mínimo alcanzado': 'Sí' if final_amount >= round(minimum_total * 100) else 'No', 'Invariantes verificadas': '4/4'}),
    ]
    stages=[dict(number=i+1,title=title,detail=detail,stats=stats) for i,(title,detail,stats) in enumerate(stage_info)]
    return dict(seed=seed, users=users, products=products, stages=stages,
                total_budget=_eur(sum(budgets.values())), initial=_eur(commitments_before),
                retained=_eur(commitments_after), released=_eur(released), final=_eur(final_amount),
                top=[dict(reference=p['reference'], name=p['name'], units=units_by_product[p['id']],
                          percent=round(100*units_by_product[p['id']]/peaks,1)) for p in top],
                categories=[dict(name=name, amount=_eur(value)) for name,value in total_by_group.most_common()],
                selected_refs=len(selected), discarded_refs=products-len(selected),
                limits=dict(personal=_eur(individual_cap), first_refs=first_refs,
                            second_refs=second_refs, cutoff=cutoff,
                            minimum=f'{minimum_total:,.2f}'),
                threshold_met=final_amount >= round(minimum_total * 100),
                intervention=dict(reference=f'SIM-{boost_ref:04d}' if boost_ref else '',
                                  asked=boost_units, applied=intervention_applied,
                                  participant=intervention_person or '',
                                  previous=base_positions.get(boost_ref, 0),
                                  current=next((n for n,p in enumerate(rank,1) if p['id']==boost_ref),0),
                                  selected=(boost_ref in selected) if boost_ref else False),
                boundary=[dict(reference=p['reference'], units=product_votes[p['id']],
                               voters=len(voted_by[p['id']]), position=n,
                               selected=n <= cutoff)
                          for n,p in enumerate(rank,1)
                          if max(1,cutoff-5) <= n <= min(products,cutoff+5)],
                active_voters=len({uid for uid,_ in votes}), order_users=len({uid for uid,_ in orders}),
                orders_above_floor=sum(orders[k]-retained.get(k,0) for k in orders),
                result_checks=('Los datos simulados nunca se guardan.',
                               'Las cantidades finales respetan los compromisos retenidos.',
                               'Ningún participante rebasa su presupuesto ficticio.',
                               'La simulación utiliza los límites configurados como referencia y no modifica su valor.'))
