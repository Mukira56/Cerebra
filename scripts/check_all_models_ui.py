"""Catalog/key/model selection browser fixture; synthetic keys, no real provider calls."""
import importlib.util
from pathlib import Path

root = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('customer_ui_fixture', root / 'scripts/check_customer_ui.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
setup = '''
import json,httpx
from ai_hq import catalog
from ai_hq.models import Prospect
catalog.catalog=lambda: {"codex":[{"model":"gpt-cli-fixture","label":"Codex individual fixture"}],"claude":[{"model":"sonnet","label":"Claude Code Sonnet fixture"}]}
calls=[]
def provider(request):
    if request.method=="GET":
        if request.url.host=="api.anthropic.com": return httpx.Response(200,json={"data":[{"id":"claude-api-fixture","display_name":"Claude API fixture"}]})
        return httpx.Response(200,json={"data":[{"id":"gpt-api-fixture"},{"id":"gpt-image-fixture"}]})
    body=json.loads(request.content)
    calls.append({"host":request.url.host,"model":body["model"]})
    if request.url.host=="api.anthropic.com": return httpx.Response(429,json={"error":{"message":"Fixture Claude API quota reached"}})
    text=json.dumps({"subject":"OpenAI API fixture draft","body":"Helpful booking changes for your customers."})
    return httpx.Response(200,json={"status":"completed","output":[{"type":"message","content":[{"type":"output_text","text":text}]}]})
app.state.model_connections.client=httpx.Client(transport=httpx.MockTransport(provider))
with app.state.db.Session.begin() as session:
    session.add(Prospect(id="api-ui-fixture",name="API Fixture Dental",kind="dentists",city="Austin",state="Texas",status="kept",facts=[{"key":"no_booking","text":"No booking form","seen":"https://fixture.example"}]))
@app.get("/fixture-api-calls")
def provider_calls(): return calls
'''
fixture.SERVER = fixture.SERVER.replace('uvicorn.run(app,', setup + '\nuvicorn.run(app,')
original_run = fixture.subprocess.run
def run(args, **kwargs):
    args = [str(root / 'scripts/test_all_models_ui.cjs') if str(arg).endswith('test_customer_ui.cjs') else arg for arg in args]
    return original_run(args, **kwargs)
fixture.subprocess.run = run
if __name__ == '__main__':
    fixture.main()
