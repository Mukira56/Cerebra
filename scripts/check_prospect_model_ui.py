"""Run Prospects model switching against isolated records and fixture providers only."""
import importlib.util
from pathlib import Path

root = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('customer_ui_fixture', root / 'scripts/check_customer_ui.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
setup = '''
import json,sys
sys.path.insert(0,str(Path.cwd()/"tests"))
from fakes import FixtureRegistry
from ai_hq.agents import AgentResult
from ai_hq.models import Prospect
calls=[]
class ProspectModel(FixtureRegistry):
    def chat(self,name,prompt,workdir,model="",cancel_event=None):
        calls.append(name)
        if name=="claude": return AgentResult(False,"",error="Claude usage limit reached")
        return AgentResult(True,json.dumps({"subject":"Fixture proposal","body":"Codex fixture draft about online booking."}))
app.state.supervisor.registry=ProspectModel()
app.state.prospect_writer.settings.live_enabled=True
app.state.prospect_writer.settings.cli_confinement_accepted=True
with app.state.db.Session.begin() as session:
    session.add(Prospect(id="fixture-dental",name="Fixture Dental",kind="dentists",city="Austin",state="Texas",status="kept",facts=[{"key":"no_booking","text":"No online booking","seen":"https://fixture.example"}]))
@app.get("/fixture-provider-calls")
def fixture_calls(): return calls
'''
fixture.SERVER = fixture.SERVER.replace('uvicorn.run(app,', setup + '\nuvicorn.run(app,')
original_run = fixture.subprocess.run
def run(args, **kwargs):
    args = [str(root / 'scripts/test_prospect_model_ui.cjs') if str(arg).endswith('test_customer_ui.cjs') else arg for arg in args]
    return original_run(args, **kwargs)
fixture.subprocess.run = run
if __name__ == '__main__':
    fixture.main()
