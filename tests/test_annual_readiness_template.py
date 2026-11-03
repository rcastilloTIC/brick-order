"""Render the actual admin readiness template without starting Flask."""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, DictLoader, ChoiceLoader


def render(report):
    templates = Path(__file__).resolve().parents[1] / 'templates'
    env = Environment(loader=ChoiceLoader([
        DictLoader({'base.html': '{% block title %}{% endblock %}{% block content %}{% endblock %}'}),
        FileSystemLoader(str(templates)),
    ]), autoescape=True)
    env.globals['url_for'] = lambda endpoint: '/admin/campaign-history'
    return env.get_template('admin_campaign_readiness.html').render(report=report)


def test_draft_preparation_is_visible_and_read_only():
    html = render({'database_consistent': True, 'findings': [],
                   'draft_preparation': {2027: {'product': 15, 'campaign_participation': 4,
                                                'user_vote': 0, 'user_favorite': 0, 'order': 0}},
                   'activation_enabled': False, 'caution': 'Activación deshabilitada'})
    assert 'Preparación de las próximas campañas' in html
    assert '2027' in html and '15' in html
    assert 'Preparación registrada' in html
    assert '<form' not in html
    assert 'Activación no disponible' in html


def test_draft_with_orders_is_flagged_and_empty_draft_is_incomplete():
    html = render({'database_consistent': False, 'findings': ['Pedido prematuro'],
                   'draft_preparation': {
                       2027: {'product': 0, 'campaign_participation': 0,
                              'user_vote': 0, 'user_favorite': 0, 'order': 0},
                       2028: {'product': 2, 'campaign_participation': 1,
                              'user_vote': 0, 'user_favorite': 0, 'order': 1}},
                   'activation_enabled': False, 'caution': 'No disponible'})
    assert 'Preparación incompleta' in html
    assert 'Revisión necesaria' in html
    assert html.index('2027') < html.index('2028')


def test_without_draft_does_not_render_empty_table():
    html = render({'database_consistent': True, 'findings': [],
                   'draft_preparation': {}, 'activation_enabled': False,
                   'caution': 'No disponible'})
    assert 'Preparación de las próximas campañas' not in html
    assert 'Activación no disponible' in html


def test_draft_annual_approval_without_document_is_visible():
    html = render({'database_consistent': False, 'findings': ['Aprobación sin documento'],
                   'draft_preparation': {2027: {'product': 3, 'campaign_participation': 2,
                      'approved_with_document': 1, 'approved_without_document': 1,
                      'user_vote': 0, 'user_favorite': 0, 'order': 0}},
                   'activation_enabled': False, 'caution': 'No disponible'})
    assert 'Aprobadas con documento' in html
    assert 'Aprobadas sin documento' in html
    assert 'Revisión necesaria' in html
    assert '<form' not in html
