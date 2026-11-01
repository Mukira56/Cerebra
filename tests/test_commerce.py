"""External connections use fixture HTTP transports. No real account, message or paid call."""
import base64
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from ai_hq import commerce, gmail, vault
from ai_hq.api import create_app
from ai_hq.config import Settings
from ai_hq.models import BusinessJob, Project, Task
from test_product_api import KEY


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data"), bootstrap_key=KEY, start_worker=False)
    folder = tmp_path / "job"; folder.mkdir()
    with app.state.db.Session.begin() as session:
        session.add(Project(id="project", name="Fixture business", path=str(folder), default_branch="main")); session.flush()
        session.add(Task(id="task", project_id="project", description="Original artwork", state="COMPLETED")); session.flush()
        session.add(BusinessJob(id="job", title="Original artwork", kind="svg", brief="Original artwork for this client.", output_dir=str(folder), project_id="project", task_id="task"))
    with TestClient(app) as result:
        result.headers["X-CSRF-Token"] = result.post("/api/session", json={"key":KEY}).json()["csrf_token"]
        yield result


def transport(client, handler):
    client.app.state.commerce.client.close()
    client.app.state.commerce.client = httpx.Client(transport=httpx.MockTransport(handler))


def configure(client, provider, **values):
    response = client.put("/api/business/connections/" + provider, json={"values":values})
    assert response.status_code == 200, response.text


def external(client, **payload): return client.post("/api/business/jobs/job/external", json=payload)


def test_secret_storage_and_settings_validation(client):
    configure(client, "images", api_key="fixture-secret-not-a-real-key")
    view = client.get("/api/business/connections").json()
    assert view["images"]["configured"] and not view["images"]["connected"]
    assert "fixture-secret" not in json.dumps(view) and "api_key" not in view["images"]
    with client.app.state.db.Session() as session:
        stored = commerce.load(session)["images"]["api_key"]
        assert stored.startswith((vault.PREFIX, vault.KEYCHAIN)) and vault.unprotect(stored) == "fixture-secret-not-a-real-key"  # DPAPI, or the system keychain
    configure(client, "images", api_key="")
    assert client.get("/api/business/connections").json()["images"]["configured"]
    assert client.put("/api/business/connections/etsy", json={"values":{"redirect_uri":"http://example.com/callback"}}).status_code == 400
    assert client.put("/api/business/connections/printify", json={"values":{"shop_id":"../orders"}}).status_code == 400
    assert client.put("/api/business/connections/images", json={"values":{"endpoint":"http://evil.invalid"}}).status_code == 400
    assert client.delete("/api/business/connections/images").status_code == 200
    assert not client.get("/api/business/connections").json()["images"]["configured"]


def test_printify_check_lists_real_response_shops(client):
    configure(client, "printify", api_key="fixture-printify", shop_id="123")
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=[{"id":123,"title":"My studio"}])
    transport(client, handle)
    response = client.post("/api/business/connections/printify/check")
    assert response.json()["shops"] == [{"id":"123","title":"My studio"}]
    assert requests[0].url == "https://api.printify.com/v1/shops.json"
    assert client.get("/api/business/connections").json()["printify"]["connected"]


def test_image_confirmation_persistence_and_restart_duplicate_protection(client):
    configure(client, "images", api_key="fixture-image-key")
    calls=[]
    def handle(request):
        calls.append(request)
        return httpx.Response(200,json={"data":[{"b64_json":base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()}],"usage":{"total_tokens":12}})
    transport(client, handle)
    payload={"action":"image","prompt":"My original blue bird with geometric wings.","confirmed":False}
    assert external(client,**payload).status_code == 400 and not calls
    payload["confirmed"]=True
    result=external(client,**payload)
    assert result.status_code == 200 and result.json()["usage"]["total_tokens"] == 12
    from pathlib import Path
    assert Path(result.json()["path"]).is_file()
    # A fresh service instance reads the durable reservation, rather than relying on a browser cache.
    recovered=commerce.Commerce(client.app.state.db,client.app.state.commerce.client)
    assert recovered.image("job",payload["prompt"],True)==result.json() and len(calls)==1
    assert json.loads(calls[0].content)["model"]==commerce.IMAGE_MODEL
    assert client.get("/api/business/jobs/job/operations").json()[0]["status"]=="succeeded"


def test_uncertain_image_write_is_not_repeated_and_errors_hide_secrets(client):
    configure(client,"images",api_key="fixture-key-do-not-display")
    calls=[]
    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout("fixture-key-do-not-display",request=request)
    transport(client,handle)
    payload={"action":"image","prompt":"An original green kite over a blue lake.","confirmed":True}
    response=external(client,**payload)
    assert response.status_code==400 and "fixture-key-do-not-display" not in response.text
    assert external(client,**payload).status_code==400 and len(calls)==1
    assert client.get("/api/business/jobs/job/operations").json()[0]["status"]=="uncertain"


def test_external_actions_require_review_and_reject_order_or_publish_payloads(client):
    configure(client,"images",api_key="fixture-image-key")
    with client.app.state.db.Session.begin() as session: session.get(Task,"task").state="RUNNING"
    transport(client,lambda request: pytest.fail("No external HTTP before review"))
    assert external(client,action="image",prompt="An original blue bird with geometric wings.",confirmed=True).status_code==400
    assert external(client,action="production",confirmed=True).status_code==422
    assert external(client,action="printify_draft",confirmed=True,fields={"orders":[]}).status_code==400


def test_printify_draft_never_calls_orders_or_publish(client):
    configure(client,"printify",api_key="fixture-key",shop_id="123")
    calls=[]
    def handle(request):
        calls.append(request); return httpx.Response(200,json={"id":"real-response-product-id"})
    transport(client,handle)
    fields={"title":"Original artwork","description":"Client-specific","blueprint_id":5,"print_provider_id":9,
            "variants":[{"id":12,"price":2000,"is_enabled":True}],"print_areas":[{"variant_ids":[12],"placeholders":[]}]}
    result=external(client,action="printify_draft",fields=fields,confirmed=True)
    assert result.status_code==200 and result.json()["product_id"]=="real-response-product-id"
    assert len(calls)==1 and calls[0].url.path=="/v1/shops/123/products.json"
    assert external(client,action="printify_draft",fields={**fields,"visible":True},confirmed=True).status_code==400
    assert external(client,action="printify_upload",path="../outside.png",confirmed=True).status_code==400


def test_etsy_pkce_state_binding_and_draft_fields(client):
    configure(client,"etsy",api_key="fixture-etsy-key",shared_secret="fixture-shared",shop_id="12",redirect_uri="https://my-site.invalid/callback")
    service=client.app.state.commerce
    parameters=parse_qs(urlparse(service.authorize_etsy()).query)
    assert parameters["code_challenge_method"]==["S256"]
    assert parameters["scope"]==["shops_r listings_r listings_w transactions_r"]
    calls=[]
    def handle(request):
        calls.append(request)
        if request.url.path.endswith("/oauth/token"):
            assert "code_verifier" in parse_qs(request.content.decode())
            return httpx.Response(200,json={"access_token":"fixture-access","refresh_token":"fixture-refresh","expires_in":3600})
        assert request.headers["x-api-key"]=="fixture-etsy-key:fixture-shared"
        return httpx.Response(200,json={"listing_id":789,"state":"draft"})
    transport(client,handle)
    redirected="https://my-site.invalid/callback?code=fixture-code&state="+parameters["state"][0]
    assert client.post("/api/business/connections/etsy/finish",json={"redirected_url":redirected}).status_code==200
    assert client.post("/api/business/connections/etsy/finish",json={"redirected_url":redirected}).status_code==400
    fields={"quantity":1,"title":"Original blue bird","description":"Original artwork","price":10,"who_made":"i_did","when_made":"made_to_order","taxonomy_id":1,"type":"download"}
    assert external(client,action="etsy_draft",fields=fields,confirmed=True).status_code==400
    result=external(client,action="etsy_draft",fields=fields,confirmed=True,original_confirmed=True)
    assert result.json()["listing_id"]==789 and len(calls)==2
    assert calls[-1].url.path=="/v3/application/shops/12/listings"
    assert external(client,action="etsy_draft",fields={**fields,"state":"active"},confirmed=True,original_confirmed=True).status_code==400


def test_gmail_state_scope_body_and_disconnect(client):
    assert client.put("/api/business/gmail",json={"client_id":"123-abc.apps.googleusercontent.com","client_secret":"fixture-google-secret"}).status_code==200
    mailbox=client.app.state.mailbox
    params=parse_qs(urlparse(mailbox.authorization_url()).query)
    assert params["scope"]==[f"{gmail.SCOPE} {gmail.SEND}"] and params["code_challenge_method"]==["S256"]
    assert client.get("/oauth/gmail/callback?state=invalid&code=invalid",headers={"Sec-Fetch-Site":"cross-site"}).status_code==400
    def handle(request):
        if request.url.host=="oauth2.googleapis.com":
            return httpx.Response(200,json={"access_token":"fixture-google-access","refresh_token":"fixture-google-refresh","scope":gmail.SCOPE,"expires_in":3600})
        return httpx.Response(200,json={"emailAddress":"fixture@example.invalid"})
    mailbox.client.close(); mailbox.client=httpx.Client(transport=httpx.MockTransport(handle))
    response=client.get("/oauth/gmail/callback",params={"state":params["state"][0],"code":"fixture-code"},headers={"Sec-Fetch-Site":"cross-site"})
    assert response.status_code==200 and client.get("/api/business/gmail").json()["connected"]
    assert client.delete("/api/business/gmail").status_code==200 and mailbox._access==(None,0.0)
    assert not client.get("/api/business/gmail").json()["connected"]
    html=base64.urlsafe_b64encode(b"<script>bad()</script><p>Client brief</p>").decode()
    assert "bad()" not in gmail.body_text({"mimeType":"text/html","body":{"data":html}})


def test_notifications_are_opt_in_and_test_delivery_is_explicit(client):
    settings=client.get("/api/business/notifications").json()
    assert not settings["ntfy_enabled"] and not settings["telegram_enabled"]
    assert len(settings["ntfy_topic"])>20
    calls=[]
    client.app.state.notifier.client.close()
    client.app.state.notifier.client=httpx.Client(transport=httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(200,json={})))
    assert client.post("/api/business/notifications/test").json()["sent"]==[] and not calls
    assert client.put("/api/business/notifications",json={"ntfy_enabled":True}).status_code==200
    assert client.post("/api/business/notifications/test").json()["sent"]==["ntfy"] and len(calls)==1
    assert client.put("/api/business/notifications",json={"ntfy_server":"http://insecure.invalid"}).status_code==400


def test_refused_or_locally_rejected_writes_can_be_retried(client):
    """A 4xx refusal or a local check failure created nothing, so it must not block a corrected retry."""
    configure(client,"printify",api_key="fixture-printify-key",shop_id="42")
    from pathlib import Path
    folder=Path(client.app.state.commerce.db.Session().get(BusinessJob,"job").output_dir)
    calls=[]; replies=[httpx.Response(422,json={"error":"bad image"}),httpx.Response(200,json={"id":"uploaded-image-id"})]
    def handle(request):
        calls.append(request); return replies.pop(0)
    transport(client,handle)
    payload={"action":"printify_upload","path":"art.png","confirmed":True}
    assert external(client,**payload).status_code==400 and not calls  # missing file: rejected locally, nothing sent
    assert client.get("/api/business/jobs/job/operations").json()[0]["status"]=="rejected"
    (folder/"art.png").write_bytes(b"\x89PNG\r\n\x1a\n"+b"0"*32)
    assert external(client,**payload).status_code==400 and len(calls)==1  # the service refused it (422)
    result=external(client,**payload)
    assert result.status_code==200 and result.json()["image_id"]=="uploaded-image-id" and len(calls)==2
    assert external(client,**payload).json()["image_id"]=="uploaded-image-id" and len(calls)==2  # success is never repeated
