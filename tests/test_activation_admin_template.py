from pathlib import Path
from jinja2 import Environment, FileSystemLoader, DictLoader, ChoiceLoader
for edition in ('current',):
 root=Path(__file__).resolve().parents[1]
 env=Environment(loader=ChoiceLoader([DictLoader({'base.html':'{% block content %}{% endblock %}'}),FileSystemLoader(str(root/'templates'))]))
 env.globals.update(url_for=lambda endpoint, **kw: '/'+endpoint, csrf_token=lambda: 'token')
 template=env.get_template('admin_campaign_history.html')
 draft=type('Draft',(),{'year':2027,'id':2,'title':'Campaña 2027'})()
 def render(flag, prepared, blockers=[]):
  return template.render(active_campaign=None,can_create_draft=False,draft_campaigns=[draft],campaigns=[],draft_activation={2027:{'data_prepared':prepared,'blockers':blockers}},activation_flag_enabled=flag)
 assert 'name="confirmation"' not in render(False,True)
 assert 'name="confirmation"' not in render(True,False,['Falta catálogo'])
 assert 'Falta catálogo' in render(True,False,['Falta catálogo'])
 ok=render(True,True)
 assert 'name="confirmation"' in ok and 'name="csrf_token"' in ok and 'name="year"' in ok
 assert 'ACTIVAR 2027' in ok and 'main.campaign_activate' in ok
 print(edition, '4 template scenarios passed')
