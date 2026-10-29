"""Stripe for the owner's invoices: a payment link per invoice, and invoices marked paid when Stripe reports payment.

The owner's own Stripe account and key (a restricted key is recommended), kept with Windows DPAPI like the other
business connections. Creating a payment link is an action on the owner's account, so it needs the owner's
confirmation each time; Stripe's idempotency keys make a repeated request return the same link instead of a second
one. Cerebra only reads completed checkouts to learn what was paid: it never charges, refunds or moves money, and
the client pays Stripe directly. Error text from Stripe is shown (it explains a missing permission), never the key.
"""
from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timezone

import httpx

from . import commerce, money, vault
from .models import Event, MoneyDocument, now
from .network import LazyClient
from .security import redact

API = "https://api.stripe.com/v1"
# Currencies Stripe counts in whole units (no cents): https://docs.stripe.com/currencies#zero-decimal
ZERO_DECIMAL = {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}
SYNC_SECONDS = 600
SLOW_EVERY = 36  # every 6 hours
PERMISSIONS = "Products: Write, Prices: Write, Payment Links: Write, Checkout Sessions: Read"


def minor(amount, currency):
    return int(round(amount)) if currency.upper() in ZERO_DECIMAL else int(round(amount * 100))


def major(amount, currency):
    return float(amount) if currency.upper() in ZERO_DECIMAL else round(amount / 100, 2)


def mode(key):
    return "live" if "_live_" in key else "test"


def status(session):
    item = commerce.load(session).get("stripe", {})
    return {"configured": bool(item.get("api_key")), "connected": bool(item.get("checked_at")), "mode": item.get("mode", ""),
            "account": item.get("account", ""), "checked_at": item.get("checked_at", ""), "permissions": PERMISSIONS}


class Payments:
    def __init__(self, db, client=None):
        self.db = db
        self.client = client or LazyClient(timeout=30)
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self.slow_jobs = []  # run every SLOW_EVERY checks (marketplace imports), each failure recorded and skipped

    # ---- connection ----
    def save_key(self, key):
        key = str(key or "").strip()
        if not (key.startswith(("rk_live_", "rk_test_", "sk_live_", "sk_test_")) and key.isascii() and 20 <= len(key) <= 300 and " " not in key):
            raise ValueError("Paste a Stripe restricted key (rk_live_… or rk_test_…) from Stripe Dashboard › Developers › API keys")
        with self.db.Session.begin() as session:
            value = commerce.load(session)
            value["stripe"] = {"api_key": vault.protect(key), "mode": mode(key)}
            commerce.store(session, value)
            return status(session)

    def disconnect(self):
        with self.db.Session.begin() as session:
            value = commerce.load(session)
            value.pop("stripe", None)
            commerce.store(session, value)
        return {"message": "Stripe key removed from this computer. Existing payment links keep working; delete the key in your Stripe dashboard if you no longer use it."}

    def _key(self):
        with self.db.Session() as session:
            item = commerce.load(session).get("stripe", {})
        if not item.get("api_key"):
            raise ValueError("Connect Stripe first: paste your restricted key on the Money page")
        return vault.unprotect(item["api_key"])

    def request(self, method, path, data=None, idempotency=None, params=None):
        headers = {"Authorization": "Bearer " + self._key(), "Stripe-Version": "2024-06-20"}
        if idempotency:
            headers["Idempotency-Key"] = idempotency
        try:
            response = self.client.request(method, API + path, data=data, params=params, headers=headers)
        except httpx.HTTPError:
            raise ValueError("Stripe could not be reached. Check your internet connection and try again; nothing is created twice.") from None
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not response.is_success:
            detail = str((body.get("error") or {}).get("message") or "")[:300]
            raise ValueError(f"Stripe refused it (HTTP {response.status_code})" + (f": {redact(detail)}" if detail else "") + ". Check the key's permissions: " + PERMISSIONS)
        return body

    def check(self):
        self.request("GET", "/payment_links", params={"limit": 1})
        self.request("GET", "/checkout/sessions", params={"limit": 1})
        with self.db.Session.begin() as session:
            value = commerce.load(session)
            value["stripe"] = {**value.get("stripe", {}), "checked_at": now()}
            commerce.store(session, value)
            result = status(session)
        return {**result, "message": f"Stripe connected ({result['mode']} mode). Cerebra can create payment links and see completed payments."
                + (" Test mode: clients can't really pay; use a live key for real invoices." if result["mode"] == "test" else "")}

    # ---- payment links ----
    def create_link(self, doc_id, confirmed):
        if confirmed is not True:
            raise ValueError("Confirm creating this payment link in your Stripe account first")
        with self.db.Session() as session:
            doc = money._get(session, doc_id)
            if doc.kind != "invoice" or doc.status != "sent":
                raise ValueError("Issue the invoice first; paid and voided invoices don't need a link")
            figures, existing = money.totals(doc), (doc.provider or {}).get("stripe") or {}
            number, client, currency = doc.number, doc.client, doc.currency.upper()
        amount = minor(figures["balance"], currency)
        if amount <= 0:
            raise ValueError("Nothing is owed on this invoice")
        if existing.get("active") and existing.get("amount") == amount and existing.get("url"):
            return {"url": existing["url"], "message": "This invoice already has a Stripe payment link for that amount."}
        tag = f"cerebra-{doc_id}-{amount}"
        price = self.request("POST", "/prices", idempotency=tag + "-price", data={
            "currency": currency.lower(), "unit_amount": amount, "product_data[name]": f"Invoice {number} · {client}"[:250]})
        link = self.request("POST", "/payment_links", idempotency=tag + "-link", data={
            "line_items[0][price]": price["id"], "line_items[0][quantity]": 1, "metadata[cerebra_invoice]": doc_id, "metadata[invoice_number]": number,
            "payment_intent_data[metadata][invoice_number]": number, "payment_intent_data[description]": f"Invoice {number}",
            "after_completion[type]": "hosted_confirmation",
            "after_completion[hosted_confirmation][custom_message]": f"Thank you! Your payment for invoice {number} was received."})
        with self.db.Session.begin() as session:
            doc = money._get(session, doc_id)
            if existing.get("payment_link") and existing.get("payment_link") != link["id"]:
                previous = existing  # the amount changed (a part payment arrived): retire the old link below
            else:
                previous = None
            doc.payment_url = link["url"]
            doc.provider = {**(doc.provider or {}), "stripe": {"payment_link": link["id"], "price": price["id"], "url": link["url"], "amount": amount,
                                                               "active": True, "mode": "live" if link.get("livemode") else "test", "created_at": now(),
                                                               "retired": list(existing.get("retired", [])) + ([previous["payment_link"]] if previous else [])}}
            doc.updated_at = now()
            session.add(Event(kind="money", message=f"Stripe payment link created for invoice {number}", data={"document": doc_id}))
        if previous:
            self._deactivate(previous["payment_link"])
        return {"url": link["url"], "message": f"Payment link created. It's on invoice {number} as “Pay online”; send the invoice or the link to {client}."}

    # ---- digital products ----
    def create_product_link(self, product_id, confirmed):
        """A Stripe payment link that sells the product; the thank-you page gives the buyer the download link."""
        from . import products
        if confirmed is not True:
            raise ValueError("Confirm creating this payment link in your Stripe account first")
        with self.db.Session() as session:
            product = products._get(session, product_id)
            if not product.download_url:
                raise ValueError("Add the download link first: upload the package to Google Drive, Dropbox or OneDrive and paste its share link")
            existing, name, currency, amount, message = dict(product.stripe or {}), product.name, product.currency.upper(), minor(product.price, product.currency), products.thank_you(product)
        if existing.get("active"):
            return {"url": existing["url"], "message": "This product is already on sale."}
        tag = "cerebra-product-" + hashlib.sha256(f"{product_id}|{amount}|{currency}|{message}".encode()).hexdigest()[:32]
        price = self.request("POST", "/prices", idempotency=tag + "-price", data={"currency": currency.lower(), "unit_amount": amount, "product_data[name]": name[:250]})
        link = self.request("POST", "/payment_links", idempotency=tag + "-link", data={
            "line_items[0][price]": price["id"], "line_items[0][quantity]": 1, "metadata[cerebra_product]": product_id,
            "after_completion[type]": "hosted_confirmation", "after_completion[hosted_confirmation][custom_message]": message})
        if not link.get("active", True):  # Stripe returned an earlier, paused link for the same request
            self.request("POST", f"/payment_links/{link['id']}", data={"active": "true"})
        with self.db.Session.begin() as session:
            product = products._get(session, product_id)
            links = list(dict.fromkeys([*existing.get("links", []), link["id"]]))
            product.stripe = {"payment_link": link["id"], "price": price["id"], "url": link["url"], "active": True, "links": links,
                              "mode": "live" if link.get("livemode") else "test", "created_at": now()}
            product.status, product.updated_at = "selling", now()
            session.add(Event(kind="money", message=f"Stripe payment link created for product {name}", data={"product": product_id}))
        return {"url": link["url"], "message": f"{name} is on sale. Share the link anywhere: your site, social media, WhatsApp, a marketplace profile."}

    def set_selling(self, product_id, active):
        from . import products
        with self.db.Session() as session:
            stripe = dict(products._get(session, product_id).stripe or {})
        if not stripe.get("payment_link"):
            raise ValueError("Create its payment link first")
        self.request("POST", f"/payment_links/{stripe['payment_link']}", data={"active": "true" if active else "false"})
        with self.db.Session.begin() as session:
            product = products._get(session, product_id)
            product.stripe = {**product.stripe, "active": bool(active)}
            product.status, product.updated_at = ("selling" if active else "paused"), now()
            return products.public(product)

    def _deactivate(self, link_id):
        try:
            self.request("POST", f"/payment_links/{link_id}", data={"active": "false"})
            return True
        except ValueError:
            return False

    # ---- payments ----
    def sync(self, doc_id=None):
        """Record every completed, paid checkout on the owner's invoice links. Safe to repeat: each Stripe checkout
        is recorded once (its ID is the payment reference). A paid invoice's link is switched off."""
        with self._lock:
            with self.db.Session() as session:
                docs = [doc for doc in session.query(MoneyDocument).filter(MoneyDocument.kind == "invoice", MoneyDocument.status.in_(["sent", "paid"])).all()
                        if (doc.provider or {}).get("stripe") and (doc_id is None or doc.id == doc_id)]
                links = [(doc.id, doc.currency, [doc.provider["stripe"]["payment_link"], *doc.provider["stripe"].get("retired", [])], doc.provider["stripe"].get("active"))
                         for doc in docs]
            found = 0
            for identifier, currency, link_ids, active in links:
                for link_id in link_ids:
                    sessions = self.request("GET", "/checkout/sessions", params={"payment_link": link_id, "limit": 100}).get("data", [])
                    for checkout in sessions:
                        if checkout.get("status") != "complete" or checkout.get("payment_status") != "paid":
                            continue
                        with self.db.Session.begin() as session:
                            doc = money._get(session, identifier)
                            before = len(doc.payments or [])
                            day = datetime.fromtimestamp(int(checkout.get("created") or 0), timezone.utc).date().isoformat()
                            money.record_payment(session, identifier, major(int(checkout.get("amount_total") or 0), currency), day, "Stripe", checkout["id"], source="stripe")
                            if len(doc.payments or []) > before:
                                found += 1
                                session.add(Event(kind="money", message=f"Stripe payment received for invoice {doc.number}", data={"document": identifier}))
                with self.db.Session() as session:
                    paid = money._get(session, identifier).status == "paid"
                if paid and active and self._deactivate(link_ids[0]):
                    with self.db.Session.begin() as session:
                        doc = money._get(session, identifier)
                        doc.provider = {**doc.provider, "stripe": {**doc.provider["stripe"], "active": False}}
            sold = self._sync_products()
            words = [f"{found} invoice payment(s)" if found else "", f"{sold} product sale(s)" if sold else ""]
            return {"new_payments": found, "new_sales": sold, "message": ("Recorded " + " and ".join(word for word in words if word) + " from Stripe.") if found or sold else "No new Stripe payments."}

    def _sync_products(self):
        from . import products
        from .models import Product
        with self.db.Session() as session:
            listed = [(product.id, product.name, list((product.stripe or {}).get("links", []))) for product in session.query(Product).all() if (product.stripe or {}).get("links")]
        sold = 0
        for product_id, name, link_ids in listed:
            for link_id in link_ids:
                for checkout in self.request("GET", "/checkout/sessions", params={"payment_link": link_id, "limit": 100}).get("data", []):
                    if checkout.get("status") != "complete" or checkout.get("payment_status") != "paid":
                        continue
                    with self.db.Session.begin() as session:
                        if products.record_sale(session, product_id, checkout):
                            sold += 1
                            session.add(Event(kind="money", message=f"Sold {name} through Stripe", data={"product": product_id}))
        return sold

    # ---- background check ----
    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="cerebra-stripe", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        ticks = 0
        while not self._stop.wait(SYNC_SECONDS):
            ticks += 1
            if ticks % SLOW_EVERY == 1:
                for job in self.slow_jobs:
                    try:
                        job()
                    except Exception:  # not connected, or the service is down: the next round tries again
                        pass
            try:
                with self.db.Session() as session:
                    if not status(session)["connected"]:
                        continue
                self.sync()
            except Exception as exc:  # recorded, never fatal
                try:
                    with self.db.Session.begin() as session:
                        session.add(Event(kind="money", message=f"Couldn't check Stripe for payments: {redact(str(exc))[:300]}"))
                except Exception:
                    pass
