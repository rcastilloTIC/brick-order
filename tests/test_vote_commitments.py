"""Runtime checks and route wiring for irrevocable voting commitments."""
from pathlib import Path
import pytest
import importlib.util
import sys
import types

class BadRequest(Exception):
    pass

class Conflict(Exception):
    pass

if 'werkzeug.exceptions' not in sys.modules:
    werkzeug = types.ModuleType('werkzeug')
    exceptions = types.ModuleType('werkzeug.exceptions')
    exceptions.BadRequest = BadRequest
    exceptions.Conflict = Conflict
    sys.modules.setdefault('werkzeug', werkzeug)
    sys.modules['werkzeug.exceptions'] = exceptions
else:
    from werkzeug.exceptions import BadRequest, Conflict

path = Path(__file__).resolve().parents[1] / 'app/services/vote_commitments.py'
spec = importlib.util.spec_from_file_location('vote_commitments_under_test', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert_nondecreasing_vote = module.assert_nondecreasing_vote

@pytest.mark.parametrize("old,new", [(0,25),(25,25),(25,50),(50,75)])
def test_allowed(old,new):
    assert_nondecreasing_vote(old,new)

@pytest.mark.parametrize("old,new", [(25,0),(50,25),(75,50)])
def test_reduction_rejected(old,new):
    with pytest.raises(Conflict):
        assert_nondecreasing_vote(old,new)

@pytest.mark.parametrize("old,new", [(-1,10),(25,-1),(1,1.5),(True,2)])
def test_invalid_rejected(old,new):
    with pytest.raises(BadRequest):
        assert_nondecreasing_vote(old,new)

def test_all_mutation_routes_guarded():
    code = (Path(__file__).resolve().parents[1] / 'app/main/routes.py').read_text()
    for name, end in [('def submit_vote():','@main_bp.route("/favorite"'),
                      ('def admin_update_order():','def admin_add_order():'),
                      ('def admin_add_order():', '\n@main_bp.route')]:
        segment = code.split(name,1)[1].split(end,1)[0]
        assert 'assert_nondecreasing_vote(' in segment, name
    segment = code.split('def delete_vote():',1)[1].split('@main_bp.route',1)[0]
    assert 'db.session.delete(vote)' not in segment
