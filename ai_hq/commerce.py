"""Opt-in business connections. Fixed origins, protected secrets, drafts only, no order endpoints.

Every external write requires a dashboard confirmation and a persisted operation reservation.
Uncertain writes are never retried automatically. Model actions cannot invoke this service.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from . import business, vault
from .models import BusinessJob, Event, Metadata, Task, now
from .network import LazyClient

KEY = "business_connections"
PROVIDERS = {"etsy", "printify", "images"}
IMAGE_MODEL = "gpt-image-2.5-flare"
SECRET_FIELDS = {"api_key", "shared_secret", "access_token", "refresh_token"}
FIELDS = {"etsy": {"api_key", "shared_secret", "redirect_uri", "shop_id"},
          "printify": {"api_key", "shop_id"}, "images": {"api_key", "model"}}


class Rejected(ValueError):
    """The write certainly did not happen: Cerebra's own checks stopped it, or the service refused it (4xx).
    Such an operation may be retried after the problem is fixed. Timeouts, network errors and 5xx stay uncertain."""


def load(session):
    row = session.get(Metadata, KEY)
    return dict(row.value) if row else {}


def store(session, value):
    row = session.get(Metadata, KEY)
    if row: row.value = value
    else: session.add(Metadata(key=KEY, value=value))


def public(session):
    value = load(session)
    result = {}
    for provider in sorted(PROVIDERS):
        item = value.get(provider, {})
        result[provider] = {key: field for key, field in item.items() if key not in SECRET_FIELDS}
        result[provider].update(configured=bool(item.get("api_key")), connected=bool(item.get("checked_at")),
                                authorized=bool(item.get("access_token")), key_saved=bool(item.get("api_key")))
    result["images"].setdefault("model", IMAGE_MODEL)
    return result


def save(session, provider, changes):
    if provider not in PROVIDERS: raise ValueError("Unknown connection")
    if set(changes) - FIELDS[provider]: raise ValueError("Unknown connection setting")
    value = load(session)
    item = dict(value.get(provider, {}))
    changed = False
    for key, raw in changes.items():
        text = str(raw or "").strip()
        if not text: continue  # blank secrets keep the protected value
        if len(text) > 4096 or any(c in text for c in "\r\n"): raise ValueError("Invalid connection setting")
        if key in SECRET_FIELDS and (not text.isascii() or any(ord(c) < 32 for c in text)):
            raise ValueError("API credentials must contain ordinary ASCII characters without control characters")
        if key == "shop_id" and not text.isdigit(): raise ValueError("Shop ID must contain digits only")
        if key == "redirect_uri":
            parsed = urlparse(text)
            if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment or parsed.username:
                raise ValueError("Etsy needs your exact registered HTTPS callback URL, without a query or fragment")
        if key == "model" and not re.fullmatch(r"gpt-image-[a-z0-9.-]+", text):
            raise ValueError("Choose a GPT image model supported by your API account")
        item[key] = vault.protect(text) if key in SECRET_FIELDS else text
        changed = True
    if changed:
        item.pop("checked_at", None)
        if provider == "etsy":
            for key in ("access_token", "refresh_token", "expires_at"): item.pop(key, None)
    value[provider] = item
    store(session, value)
    return public(session)[provider]


class Commerce:
    def __init__(self, db, client=None):
        self.db = db
        self.client = client or LazyClient(timeout=30)
        self.lock = Lock()
        self.pending = {}

    def close(self): self.client.close()

    def config(self, provider):
        with self.db.Session() as session: item = dict(load(session).get(provider, {}))
        if not item.get("api_key"): raise ValueError("Save this connection's API key in Business Studio first")
        return item

    def request(self, method, url, **kwargs):
        # Never include HTTP exception text/response bodies: either can expose a token or client data.
        try: response = self.client.request(method, url, **kwargs)
        except httpx.HTTPError: raise ValueError("The service could not be reached. Check your connection; an external write may need checking in the provider dashboard.") from None
        if not response.is_success:
            message = f"The service returned HTTP {response.status_code}. Check the account's key, scopes, quota and provider dashboard."
            # A 4xx (except 408 request timeout) means the service refused the request, so nothing was created.
            raise (Rejected if 400 <= response.status_code < 500 and response.status_code != 408 else ValueError)(message)
        try: return response.json()
        except ValueError: raise ValueError("The service returned an unreadable response. Check its dashboard before retrying a write.") from None

    def update(self, provider, **fields):
        with self.db.Session.begin() as session:
            value = load(session); value[provider] = {**value.get(provider, {}), **fields}; store(session, value)

    def etsy_headers(self):
        item = self.config("etsy")
        if not item.get("access_token"): raise ValueError("Authorize Etsy first")
        if time.time() >= item.get("expires_at", 0):
            data = self.request("POST", "https://api.etsy.com/v3/public/oauth/token", data={"grant_type": "refresh_token",
                                "client_id": vault.unprotect(item["api_key"]), "refresh_token": vault.unprotect(item["refresh_token"])})
            self.update("etsy", access_token=vault.protect(data["access_token"]), refresh_token=vault.protect(data["refresh_token"]),
                        expires_at=time.time() + int(data["expires_in"]) - 60)
            item = self.config("etsy")
        if not item.get("shared_secret"): raise ValueError("Save the Etsy app's shared secret")
        return {"Authorization": "Bearer " + vault.unprotect(item["access_token"]),
                "x-api-key": vault.unprotect(item["api_key"]) + ":" + vault.unprotect(item["shared_secret"])}

    def authorize_etsy(self):
        item = self.config("etsy")
        if not item.get("redirect_uri") or not item.get("shared_secret"): raise ValueError("Save the registered HTTPS callback URL and shared secret first")
        state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
        with self.lock:
            self.pending = {key: data for key, data in self.pending.items() if time.monotonic() - data[1] < 600}
            self.pending[state] = (verifier, time.monotonic(), item["redirect_uri"], item["api_key"])
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        return "https://www.etsy.com/oauth/connect?" + urlencode({"response_type": "code", "client_id": vault.unprotect(item["api_key"]),
                   "redirect_uri": item["redirect_uri"], "scope": "shops_r listings_r listings_w transactions_r", "state": state,
                   "code_challenge": challenge, "code_challenge_method": "S256"})

    def finish_etsy(self, redirected_url):
        parsed = urlparse(redirected_url); query = parse_qs(parsed.query)
        state = query.get("state", [""])[0]
        with self.lock: pending = self.pending.pop(state, None)
        if not pending or time.monotonic() - pending[1] > 600: raise ValueError("Etsy sign-in expired or did not start here. Start again.")
        callback = urlparse(pending[2])
        if (parsed.scheme, parsed.netloc, parsed.path) != (callback.scheme, callback.netloc, callback.path):
            raise ValueError("Paste the exact redirected callback URL from your Etsy authorization")
        item = self.config("etsy")
        if pending[3] != item["api_key"]: raise ValueError("Etsy settings changed. Start sign-in again.")
        code = query.get("code", [""])[0]
        if not code: raise ValueError("Etsy did not provide an authorization code")
        data = self.request("POST", "https://api.etsy.com/v3/public/oauth/token", data={"grant_type": "authorization_code",
                            "client_id": vault.unprotect(item["api_key"]), "redirect_uri": pending[2], "code": code, "code_verifier": pending[0]})
        self.update("etsy", access_token=vault.protect(data["access_token"]), refresh_token=vault.protect(data["refresh_token"]),
                    expires_at=time.time() + int(data["expires_in"]) - 60)
        return {"message": "Etsy authorized. Press Check connection to verify your shop."}

    def check(self, provider):
        item = self.config(provider)
        self.update(provider, checked_at="")
        if provider == "printify":
            shops = self.request("GET", "https://api.printify.com/v1/shops.json", headers={"Authorization": "Bearer " + vault.unprotect(item["api_key"])})
            shops = [{"id": str(shop["id"]), "title": shop.get("title", "")} for shop in shops]
            if not shops: raise Rejected("Your Printify account has no store yet. In Printify open My stores › Add new store, then check again.")
            if item.get("shop_id") and item["shop_id"] not in [shop["id"] for shop in shops]: raise ValueError("This Printify key cannot access that shop ID")
            if not item.get("shop_id") and len(shops) == 1:
                self.update("printify", shop_id=shops[0]["id"])
                result = {"shops": shops, "shop_id": shops[0]["id"], "message": f"Printify verified. Using your store “{shops[0]['title']}” (ID {shops[0]['id']}). Order creation and production are blocked."}
            else:
                result = {"shops": shops, "message": "Printify key verified." + ("" if item.get("shop_id") else " You have several stores: type the ID of the one to use in Shop ID and save.") + " Order creation and production are blocked."}
        elif provider == "etsy":
            headers = self.etsy_headers()
            if not item.get("shop_id"):
                # Etsy access tokens begin with the numeric user ID of the person who authorized the app.
                user_id = headers["Authorization"].split(" ", 1)[1].split(".", 1)[0]
                if not user_id.isdigit(): raise ValueError("Type your Etsy shop ID and save, then check again")
                try: owned = self.request("GET", f"https://api.etsy.com/v3/application/users/{user_id}/shops", headers=headers)
                except Rejected: raise Rejected("This Etsy account has no shop yet. Open one at etsy.com/sell, then check again.") from None
                if not owned.get("shop_id"): raise Rejected("This Etsy account has no shop yet. Open one at etsy.com/sell, then check again.")
                self.update("etsy", shop_id=str(owned["shop_id"]))
                item = self.config("etsy")
            shop = self.request("GET", f"https://api.etsy.com/v3/application/shops/{item['shop_id']}", headers=headers)
            result = {"shop_id": str(shop["shop_id"]), "message": "Etsy shop verified: " + str(shop.get("shop_name", ""))}
        elif provider == "images":
            model = item.get("model", IMAGE_MODEL)
            self.request("GET", "https://api.openai.com/v1/models/" + model, headers={"Authorization": "Bearer " + vault.unprotect(item["api_key"])})
            result = {"message": f"API key can access {model}. Generating an image is a separate paid action."}
        else: raise ValueError("Unknown connection")
        self.update(provider, checked_at=now())
        return result

    def disconnect(self, provider):
        if provider not in PROVIDERS: raise ValueError("Unknown connection")
        with self.db.Session.begin() as session:
            value = load(session); value.pop(provider, None); store(session, value)
        return {"message": "Connection removed from this computer. Revoke its token in the provider dashboard if needed."}

    def write_once(self, job_id, action, payload, confirmed, perform):
        if confirmed is not True: raise ValueError("Confirm this exact external action first")
        with self.db.Session() as session:
            job = session.get(BusinessJob, job_id)
            if not job: raise ValueError("Business job not found")
            task = session.get(Task, job.task_id)
            if business.stage(job, task) not in {"ready", "completed"}: raise ValueError("Finish the job's review and approvals first")
            folder = Path(job.output_dir)
        signature = hashlib.sha256(json.dumps([job_id, action, payload], sort_keys=True).encode()).hexdigest()
        key = "business_operation_" + signature
        with self.lock, self.db.Session.begin() as session:
            previous = session.get(Metadata, key)
            if previous and previous.value.get("status") == "succeeded": return previous.value["result"]
            if previous and previous.value.get("status") != "rejected":
                raise ValueError("This action is pending or its outcome is uncertain. Check the provider dashboard; Cerebra will not repeat it automatically.")
            reservation = {"job_id": job_id, "action": action, "status": "pending", "at": now()}
            if previous: previous.value = reservation
            else: session.add(Metadata(key=key, value=reservation))
        try:
            result = perform(folder)
        except Rejected:
            with self.db.Session.begin() as session:
                row = session.get(Metadata, key); row.value = {**row.value, "status": "rejected"}
            raise
        except Exception:
            with self.db.Session.begin() as session:
                row = session.get(Metadata, key); row.value = {**row.value, "status": "uncertain"}
            raise
        with self.db.Session.begin() as session:
            row = session.get(Metadata, key); row.value = {**row.value, "status": "succeeded", "result": result}
            session.add(Event(task_id=job.task_id, kind="business", message=f"Business Studio: {action} completed", data={"job_id": job_id}))
        return result

    def image(self, job_id, prompt, confirmed):
        if confirmed is not True: raise ValueError("Confirm this paid image generation first")
        prompt = prompt.strip()
        if not 20 <= len(prompt) <= 12000: raise ValueError("Write your own image instructions (20–12000 characters)")
        item = self.config("images"); model = item.get("model", IMAGE_MODEL)
        def perform(folder):
            data = self.request("POST", "https://api.openai.com/v1/images/generations", timeout=180,
                                headers={"Authorization": "Bearer " + vault.unprotect(item["api_key"])},
                                json={"model": model, "prompt": prompt, "n": 1, "size": "1024x1024", "output_format": "png"})
            encoded = data.get("data", [{}])[0].get("b64_json", "")
            if len(encoded) > 40 * 1024 * 1024: raise ValueError("The image response was too large")
            try: raw = base64.b64decode(encoded, validate=True)
            except ValueError: raise ValueError("The service did not return a valid image") from None
            if not raw.startswith(b"\x89PNG\r\n\x1a\n"): raise ValueError("The service did not return a PNG image")
            target = business._within(folder / "generated", folder); target.mkdir(exist_ok=True)
            name = "image-" + secrets.token_hex(6) + ".png"; path = target / name
            with path.open("xb") as stream: stream.write(raw)
            (target / (name + ".json")).write_text(json.dumps({"model": model, "prompt": prompt, "usage": data.get("usage"), "at": now(),
                "note": "Generated after job review. Inspect this image before publishing; it has not been independently reviewed."}, indent=2), encoding="utf-8")
            return {"path": str(path), "message": "Image saved locally. Inspect it, then export again to include it. This image has not been independently reviewed.", "usage": data.get("usage")}
        return self.write_once(job_id, "generate_image", {"prompt": prompt, "model": model}, confirmed, perform)

    def etsy_draft(self, job_id, fields, confirmed, original_confirmed):
        if confirmed is not True: raise ValueError("Confirm this exact Etsy draft first")
        if original_confirmed is not True: raise ValueError("Confirm your original creative input and required AI/production-partner disclosures")
        required = {"quantity", "title", "description", "price", "who_made", "when_made", "taxonomy_id", "type"}
        allowed = required | {"tags", "shipping_profile_id", "readiness_state_id", "production_partner_ids"}
        if not required <= set(fields) or set(fields) - allowed: raise ValueError("Use the draft template's fields; publishing/state changes are not supported")
        if not isinstance(fields["title"], str) or not isinstance(fields["description"], str) or not fields["description"].strip():
            raise ValueError("Provide a text title and description")
        if fields["who_made"] not in {"i_did", "collective", "someone_else"} or not isinstance(fields["when_made"], str):
            raise ValueError("Check who_made and when_made against Etsy's listing requirements")
        if fields["type"] not in {"physical", "download"}: raise ValueError("Listing type must be physical or download")
        if fields["type"] == "physical" and not {"shipping_profile_id", "readiness_state_id"} <= set(fields): raise ValueError("Physical listings need shipping_profile_id and readiness_state_id")
        try:
            valid_numbers = 1 <= int(fields["quantity"]) <= 999 and 0 < float(fields["price"]) <= 100000 and int(fields["taxonomy_id"]) > 0
        except (ValueError, TypeError): valid_numbers = False
        if not valid_numbers: raise ValueError("Check quantity, price and a real positive taxonomy ID")
        if not fields["title"].strip() or len(fields["title"]) > 140: raise ValueError("Etsy title must be 1–140 characters")
        item = self.config("etsy")
        if not item.get("shop_id"): raise ValueError("Save your Etsy shop ID first")
        headers = self.etsy_headers()
        def perform(folder):
            data = self.request("POST", f"https://api.etsy.com/v3/application/shops/{item['shop_id']}/listings", headers=headers, data=fields)
            return {"listing_id": data["listing_id"], "message": "Draft created on Etsy. Review its images, files, AI disclosures and production partners in Etsy. It has not been published."}
        return self.write_once(job_id, "etsy_draft", {"shop": item["shop_id"], "fields": fields}, confirmed, perform)

    def printify_product(self, job_id, fields, confirmed):
        if confirmed is not True: raise ValueError("Confirm this exact Printify draft first")
        required = {"title", "description", "blueprint_id", "print_provider_id", "variants", "print_areas"}
        if set(fields) != required: raise ValueError("Use the Printify draft template's fields. Orders and publishing are not supported.")
        if not isinstance(fields["title"], str) or not fields["title"].strip() or not isinstance(fields["description"], str):
            raise ValueError("Provide a text title and description")
        try:
            valid = int(fields["blueprint_id"]) > 0 and int(fields["print_provider_id"]) > 0 and bool(fields["print_areas"]) and bool(fields["variants"])
            valid = valid and all(int(variant["id"]) > 0 and int(variant["price"]) > 0 for variant in fields["variants"])
        except (ValueError, TypeError, KeyError): valid = False
        if not valid: raise ValueError("Choose real positive blueprint, provider and variant IDs, prices and print areas first")
        item = self.config("printify")
        if not item.get("shop_id"): raise ValueError("Save the Printify shop ID first")
        def perform(folder):
            data = self.request("POST", f"https://api.printify.com/v1/shops/{item['shop_id']}/products.json",
                                headers={"Authorization": "Bearer " + vault.unprotect(item["api_key"])}, json=fields)
            return {"product_id": data["id"], "message": "Draft product created in Printify. It is not published and no order was created. Review placement and pricing in Printify."}
        return self.write_once(job_id, "printify_draft", {"shop": item["shop_id"], "fields": fields}, confirmed, perform)

    def printify_upload(self, job_id, relative_path, confirmed):
        if confirmed is not True: raise ValueError("Confirm this exact image upload first")
        item = self.config("printify")
        def perform(folder):
            try: path = business._within(folder / relative_path, folder)
            except ValueError as exc: raise Rejected(str(exc)) from None
            if path.suffix.lower() not in {".png", ".jpg", ".jpeg"} or not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
                raise Rejected("Choose a PNG/JPEG inside this job, up to 20 MB")
            data = self.request("POST", "https://api.printify.com/v1/uploads/images.json",
                                headers={"Authorization": "Bearer " + vault.unprotect(item["api_key"])},
                                json={"file_name": path.name, "contents": base64.b64encode(path.read_bytes()).decode()})
            return {"image_id": data["id"], "message": "Image uploaded to your Printify library. Use this image ID in the product draft's print areas."}
        return self.write_once(job_id, "printify_upload", {"path": relative_path}, confirmed, perform)

    def operations(self, job_id):
        with self.db.Session() as session:
            rows = session.query(Metadata).filter(Metadata.key.like("business_operation_%")).all()
            return [{"action": row.value["action"], "status": row.value["status"], "at": row.value["at"], "result": row.value.get("result", {})}
                    for row in rows if row.value.get("job_id") == job_id][-50:]
