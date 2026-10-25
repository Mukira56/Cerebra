"""Client delivery workspace: scope gate, website checks, ledger, customer results, change requests, form check."""
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_hq import business_check
from ai_hq.agents import AgentResult
from test_business import DeliverableAgent, client, drive  # noqa: F401  (client is a fixture)
from test_product_api import enable_agents

ENDPOINT = "https://formspree.io/f/abcdwxyz"
NAV = '<nav><a href="index.html">Home</a> <a href="services.html">Services</a> <a href="quote.html">Get a quote</a></nav>'
HEAD = '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title><link rel="stylesheet" href="styles.css"></head>'


def site_files(endpoint=ENDPOINT, quote_extra="", index_extra=""):
    page = lambda title, body: f"<!doctype html><html>{HEAD.format(title=title)}<body>{NAV}{body}</body></html>"
    return {
        "index.html": page("Sparkle Cleaning", f"<h1>House cleaning in Austin</h1><p>Call <a href='tel:+15125550100'>(512) 555-0100</a></p><img src='assets/team.svg' alt='Our team'>{index_extra}"),
        "services.html": page("Services", "<h2>Deep cleaning</h2><h2>Move-out cleaning</h2><p>Serving Austin and Round Rock.</p>"),
        "quote.html": page("Request a quote", f"<form method='post' action='{endpoint}'><input name='name' required><input name='phone' type='tel' required>"
                                              f"<input name='email' type='email'><select name='service'><option>Deep cleaning</option></select><input name='zip'>"
                                              f"<textarea name='message'></textarea>{quote_extra}<button type='submit'>Send</button></form>"),
        "thank-you.html": page("Thank you", "<p>We'll call you within one business day.</p>"),
        "styles.css": "body{font-family:sans-serif}", "README.md": "How to edit and publish this site.", "assets/team.svg": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1 1'><rect/><rect/></svg>"}


def write_site(folder, files):
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")


BRIEF = {"required_files": ["index.html", "services.html", "quote.html", "thank-you.html", "styles.css", "README.md"],
         "must_mention": ["Deep cleaning", "Move-out cleaning", "Austin", "Round Rock"], "site": {"quote_page": "quote.html", "form_endpoint": ENDPOINT, "phone": "(512) 555-0100"}}


@pytest.mark.parametrize("change,problem", [
    (None, None),
    (dict(index_extra="<a href='about.html'>About</a>"), "broken link to about.html"),
    (dict(index_extra="<img src='assets/x.png'>"), "no alt text"),
    (dict(endpoint="https://formspree.io/f/other"), "must send to the agreed address"),
    (dict(index_extra="<a href='http://insecure.example'>x</a>"), "not secure"),
])
def test_site_checks(tmp_path, change, problem, capsys):
    write_site(tmp_path, site_files(**(change or {})))
    (tmp_path / "cerebra-brief.json").write_text(json.dumps(BRIEF), encoding="utf-8")
    result = business_check.main(str(tmp_path)); output = capsys.readouterr().out
    assert (result == 0) is (problem is None), output
    if problem: assert problem in output


def test_site_checks_require_real_form_and_content(tmp_path, capsys):
    files = site_files()
    files["quote.html"] = files["quote.html"].replace("<input name='phone' type='tel' required>", "<input name='phone' type='tel'>")
    files["services.html"] = files["services.html"].replace("Round Rock", "")
    write_site(tmp_path, files)
    (tmp_path / "cerebra-brief.json").write_text(json.dumps({**BRIEF, "site": {**BRIEF["site"], "form_endpoint": ""}}), encoding="utf-8")
    files["quote.html"] = files["quote.html"].replace(ENDPOINT, "https://formspree.io/f/your-form-id")
    write_site(tmp_path, files)
    assert business_check.main(str(tmp_path)) == 1
    output = capsys.readouterr().out
    assert "no real https:// delivery address" in output and "must be required" in output and "Round Rock" in output


class SiteAgent(DeliverableAgent):
    def execute(self, name, request, cancel_event=None):
        if request.role == "implement":
            self.requests.append((name, request))
            write_site(Path(request.workdir), site_files())
            return AgentResult(True, "Fixture: wrote the site")
        return super().execute(name, request, cancel_event)


JOB = {"title": "Sparkle Cleaning website", "kind": "service_site", "client": "Sparkle Cleaning", "brief": "A website for a house cleaning company in Austin, Texas that gets quote requests."}
SCOPE = {"services": ["Deep cleaning", "Move-out cleaning"], "service_areas": ["Austin", "Round Rock"], "form_endpoint": ENDPOINT, "phone": "(512) 555-0100", "price": 750, "revisions_included": 1}


def test_scope_gate_then_full_delivery(client):
    enable_agents(client)
    client.app.state.supervisor.registry = SiteAgent()
    job = client.post("/api/business/jobs", json=JOB).json()
    assert job["stage"] == "scope" and job["task_id"] is None
    assert "Add at least one service" in client.post(f"/api/business/jobs/{job['id']}/scope/approve").json()["detail"]
    assert client.put(f"/api/business/jobs/{job['id']}/scope", json={"form_endpoint": "http://insecure"}).status_code == 400
    assert client.put(f"/api/business/jobs/{job['id']}/scope", json=SCOPE).json()["services"] == SCOPE["services"]
    approved = client.post(f"/api/business/jobs/{job['id']}/scope/approve").json()
    assert approved["task_id"] and approved["stage"] == "waiting"
    folder = Path(job["output_dir"])
    brief = json.loads((folder / "cerebra-brief.json").read_text(encoding="utf-8"))
    assert brief["site"]["form_endpoint"] == ENDPOINT and "Round Rock" in brief["must_mention"]
    assert "Approved scope" in subprocess.run(["git", "-C", str(folder), "log", "--format=%s"], capture_output=True, text=True).stdout
    assert client.put(f"/api/business/jobs/{job['id']}/scope", json={"price": 1}).status_code == 400  # frozen after approval
    task = client.get(f"/api/tasks/{approved['task_id']}").json()
    assert "AGREED SCOPE" in task["description"] and "Round Rock" in task["description"]
    finished = drive(client, job["id"])
    assert finished["stage"] == "ready" and any("passed the deliverable checks" in line for line in finished["passed"]), finished
    assert client.post(f"/api/business/jobs/{job['id']}/export", json={"zip": True}).json()["stage"] == "completed"


def test_money_results_and_change_requests(client, monkeypatch):
    enable_agents(client)
    job = client.post("/api/business/jobs", json=JOB).json()
    jid = job["id"]
    assert client.put("/api/business/settings", json={"hourly_rate": 25}).status_code == 200
    assert client.get("/api/business").json()["settings"]["output_root"]  # saving the rate keeps the folder
    for entry in ({"kind": "payment", "amount": 750}, {"kind": "expense", "amount": 100, "note": "hosting + tools"}, {"kind": "time", "hours": 8}):
        assert client.post(f"/api/business/jobs/{jid}/ledger", json=entry).status_code == 201
    assert client.post(f"/api/business/jobs/{jid}/ledger", json={"kind": "payment"}).status_code == 400
    assert client.post(f"/api/business/jobs/{jid}/ledger", json={"kind": "refund", "amount": 5}).status_code == 400
    money = client.get(f"/api/business/jobs/{jid}/delivery").json()["money"]
    assert (money["collected"], money["expenses"], money["hours"], money["profit_before_tax"]) == (750, 100, 8, 450)
    first = client.post(f"/api/business/jobs/{jid}/enquiries", json={"source": "website form", "status": "quoted"}).json()
    client.post(f"/api/business/jobs/{jid}/enquiries", json={"status": "booked", "value": 180, "confirmed": True})
    client.patch(f"/api/business/jobs/{jid}/enquiries/{first['id']}", json={"status": "booked", "value": 120})
    outcomes = client.get(f"/api/business/jobs/{jid}/delivery").json()["outcomes"]
    assert (outcomes["enquiries"], outcomes["booked"], outcomes["booked_value"], outcomes["confirmed_booked_value"]) == (2, 2, 300, 180)
    assert client.delete(f"/api/business/jobs/{jid}/enquiries/{first['id']}").status_code == 200
    # Change requests need an approved scope; the second one is beyond the one revision included.
    assert client.post(f"/api/business/jobs/{jid}/changes", json={"request": "Make the buttons larger"}).status_code == 400
    client.put(f"/api/business/jobs/{jid}/scope", json=SCOPE); client.post(f"/api/business/jobs/{jid}/scope/approve")
    assert client.post(f"/api/business/jobs/{jid}/changes", json={"request": "Make the buttons larger"}).json()["extra"] is False
    assert client.post(f"/api/business/jobs/{jid}/changes", json={"request": "Add a Spanish version of the home page"}).json()["extra"] is True
    revisions = client.get(f"/api/business/jobs/{jid}/delivery").json()["revisions"]
    assert len(revisions) == 2 and revisions[0]["state"] == "AWAITING_APPROVAL"


def test_test_enquiry_goes_to_the_agreed_form_only_when_confirmed(client, monkeypatch):
    job = client.post("/api/business/jobs", json=JOB).json(); jid = job["id"]
    sent = []
    monkeypatch.setattr("httpx.post", lambda url, data, headers, timeout, follow_redirects: sent.append((url, data)) or SimpleNamespace(status_code=200))
    assert client.post(f"/api/business/jobs/{jid}/test-enquiry", json={"confirmed": True}).status_code == 400  # no approved scope yet
    enable_agents(client)
    client.put(f"/api/business/jobs/{jid}/scope", json=SCOPE); client.post(f"/api/business/jobs/{jid}/scope/approve")
    assert client.post(f"/api/business/jobs/{jid}/test-enquiry", json={}).status_code == 400
    result = client.post(f"/api/business/jobs/{jid}/test-enquiry", json={"confirmed": True}).json()
    assert result["sent"] and sent[0][0] == ENDPOINT and "TEST from Cerebra" in sent[0][1]["message"]
    assert client.post(f"/api/business/jobs/{jid}/test-enquiry/received", json={"received": True}).json()["received"] is True
