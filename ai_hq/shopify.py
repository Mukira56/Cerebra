"""Shopify stores, up to MAX_STORES, through each store's own Dev Dashboard app (the client credentials grant).

Since 1 January 2026 a store can't make new custom apps in its admin: the owner creates an app in Shopify's Dev Dashboard,
gives it the scopes write_products and read_orders, releases a version, installs it on the store and copies its Client ID
and secret here. The grant only works for stores in the same Shopify organization as the app. Its token lasts 24 hours and
is asked for again when it runs out. Cerebra creates draft products (never published) after the owner's confirmation and
reads orders as sales; it never changes an order, a price that's live, or a theme.
"""
from __future__ import annotations

import re
import secrets
import time

import httpx

from . import commerce, vault
from .models import Event, now
from .network import LazyClient

KEY = "shopify_stores"
MAX_STORES = 5
API_VERSION = "2026-10"
SKIPPED = {"REFUNDED", "VOIDED", "EXPIRED", "PENDING", "AUTHORIZED"}
ORDERS = """query($after: String) { orders(first: 100, after: $after, sortKey: CREATED_AT) {
  nodes { id name createdAt cancelledAt displayFinancialStatus
          currentTotalPriceSet { shopMoney { amount currencyCode } } currentTotalTaxSet { shopMoney { amount currencyCode } } }
  pageInfo { hasNextPage endCursor } } }"""
CREATE = """mutation($product: ProductCreateInput!) { productCreate(product: $product) {
  product { id handle variants(first: 1) { nodes { id } } } userErrors { field message } } }"""
PRICE = """mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) { productVariantsBulkUpdate(productId: $productId, variants: $variants) {
  userErrors { field message } } }"""


def domain(text):
    """The store's myshopify.com address: "my-store", "my-store.myshopify.com" or its admin URL."""
    text = str(text or "").strip().lower()
    text = re.sub(r"^https?://", "", text).split("/", 1)[0]
    if "." not in text: text += ".myshopify.com"
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,60}\.myshopify\.com", text):
        raise ValueError("Type the store's myshopify.com address, for example my-store.myshopify.com (Settings › Domains shows it)")
    return text


def sale(order):
    """What the buyer paid now (after edits, discounts and refunds), tax left out; None when it doesn't count."""
    if order.get("cancelledAt") or str(order.get("displayFinancialStatus") or "").upper() in SKIPPED:
        return None
    total = (order.get("currentTotalPriceSet") or {}).get("shopMoney") or {}
    tax = (order.get("currentTotalTaxSet") or {}).get("shopMoney") or {}
    try: amount = round(float(total.get("amount") or 0) - float(tax.get("amount") or 0), 2)
    except (TypeError, ValueError): return None
    if amount <= 0 or not total.get("currencyCode"):
        return None
    return {"amount": amount, "currency": str(total["currencyCode"]).upper(), "date": str(order.get("createdAt") or now())[:10],
            "note": f"Shopify order {order.get('name') or ''}".strip()}


class Shopify:
    def __init__(self, db, service, client=None):
        self.db, self.service = db, service  # service: the Commerce object (confirmed, write-once drafts)
        self.client = client or LazyClient(timeout=30)

    def close(self): self.client.close()

    # ---- the stores ----
    def stores(self):
        with self.db.Session() as session: return [dict(item) for item in commerce.load(session).get(KEY) or []]

    def _save(self, listed):
        with self.db.Session.begin() as session:
            value = commerce.load(session)
            if listed: value[KEY] = listed
            else: value.pop(KEY, None)
            commerce.store(session, value)

    def _store(self, store_id):
        found = next((item for item in self.stores() if item["id"] == store_id), None) if store_id else (self.stores() or [None])[0]
        if found is None: raise ValueError("That Shopify store isn't connected")
        return found

    def status(self):
        return {"max": MAX_STORES, "stores": [{"id": item["id"], "domain": item["domain"], "name": item.get("name", ""), "currency": item.get("currency", ""),
                                               "connected": bool(item.get("checked_at")), "checked_at": item.get("checked_at", "")} for item in self.stores()]}

    def add(self, address, client_id, client_secret):
        address = domain(address)
        client_id, client_secret = str(client_id or "").strip(), str(client_secret or "").strip()
        if not (8 <= len(client_id) <= 200 and 8 <= len(client_secret) <= 400 and (client_id + client_secret).isascii() and " " not in client_id + client_secret):
            raise ValueError("Paste the app's Client ID and Client secret from the Dev Dashboard (your app › Settings)")
        listed = self.stores()
        if any(item["domain"] == address for item in listed): raise ValueError(f"{address} is already connected")
        if len(listed) >= MAX_STORES: raise ValueError(f"Up to {MAX_STORES} Shopify stores can be connected; disconnect one first")
        store_id = secrets.token_hex(4)
        self._save([*listed, {"id": store_id, "domain": address, "client_id": vault.protect(client_id), "client_secret": vault.protect(client_secret), "added_at": now()}])
        try:
            return self.check(store_id)
        except ValueError:
            self._save([item for item in self.stores() if item["id"] != store_id])  # a store Shopify refuses isn't kept
            raise

    def remove(self, store_id):
        self._store(store_id)
        self._save([item for item in self.stores() if item["id"] != store_id])
        return {"message": "Store disconnected from this computer. Uninstall the app in that store's Shopify admin too if you no longer use it."}

    def _update(self, store_id, **fields):
        self._save([{**item, **fields} if item["id"] == store_id else item for item in self.stores()])

    # ---- talking to Shopify ----
    def _token(self, item):
        if item.get("token") and time.time() < item.get("expires_at", 0): return vault.unprotect(item["token"])
        try:
            response = self.client.post(f"https://{item['domain']}/admin/oauth/access_token", data={"grant_type": "client_credentials",
                                        "client_id": vault.unprotect(item["client_id"]), "client_secret": vault.unprotect(item["client_secret"])})
        except httpx.HTTPError: raise ValueError("Shopify could not be reached. Check your connection and try again.") from None
        try: body = response.json()
        except ValueError: body = {}
        if not response.is_success or not body.get("access_token"):
            if "shop_not_permitted" in str(body.get("error", "")):
                raise commerce.Rejected("Shopify refused: the app and this store must be in the same Shopify organization (Dev Dashboard). Create the app from the store owner's organization.")
            raise commerce.Rejected(f"Shopify refused the app's Client ID or secret (HTTP {response.status_code}). Check them, and that the app is released and installed on this store.")
        self._update(item["id"], token=vault.protect(body["access_token"]), expires_at=time.time() + int(body.get("expires_in") or 86399) - 120,
                     scope=str(body.get("scope") or ""))
        return body["access_token"]

    def graphql(self, store_id, query, variables=None):
        item = self._store(store_id)
        token = self._token(item)
        try:
            response = self.client.post(f"https://{item['domain']}/admin/api/{API_VERSION}/graphql.json", headers={"X-Shopify-Access-Token": token},
                                        json={"query": query, "variables": variables or {}})
        except httpx.HTTPError: raise ValueError("Shopify could not be reached. Nothing was changed; try again.") from None
        try: body = response.json()
        except ValueError: body = {}
        if response.status_code in {401, 403}:
            raise commerce.Rejected("Shopify didn't allow it. In the Dev Dashboard give the app the scopes write_products and read_orders, release a new version and install it again.")
        if not response.is_success: raise ValueError(f"Shopify returned HTTP {response.status_code}. Check the store in Shopify before trying again.")
        if body.get("errors"):
            message = "; ".join(str(error.get("message", "")) for error in body["errors"] if isinstance(error, dict))[:300]
            raise commerce.Rejected("Shopify refused it" + (f": {message}" if message else ""))
        return body.get("data") or {}

    def check(self, store_id):
        item = self._store(store_id)
        shop = self.graphql(item["id"], "{ shop { name currencyCode } }").get("shop") or {}
        self._update(item["id"], name=str(shop.get("name", "")), currency=str(shop.get("currencyCode", "")), checked_at=now())
        return {**self.status(), "message": f"Connected to Shopify: {shop.get('name') or item['domain']}. Cerebra creates draft products only after you confirm each one, and reads orders as sales."}

    # ---- a draft product (never published) ----
    def draft(self, job_id, fields, confirmed, store_id=None):
        if confirmed is not True: raise ValueError("Confirm this exact Shopify draft first")
        if set(fields) - {"title", "description", "price", "tags", "product_type"} or not {"title", "description", "price"} <= set(fields):
            raise ValueError("Use the draft template's fields: title, description, price, tags, product_type")
        title, description = str(fields["title"] or "").strip(), str(fields["description"] or "").strip()
        if not 1 <= len(title) <= 255 or not description: raise ValueError("Give the product a title (up to 255 characters) and a description")
        try: price = round(float(fields["price"]), 2)
        except (TypeError, ValueError): price = 0
        if not 0 < price <= 100000: raise ValueError("Set a price above zero")
        tags = [str(tag).strip()[:255] for tag in fields.get("tags") or [] if str(tag).strip()][:250]
        item = self._store(store_id)
        paragraphs = "".join(f"<p>{line}</p>" for line in (description.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")).split("\n") if line.strip())
        product = {"title": title, "descriptionHtml": paragraphs, "status": "DRAFT", "tags": tags}
        if fields.get("product_type"): product["productType"] = str(fields["product_type"])[:255]

        def perform(folder):
            created = (self.graphql(item["id"], CREATE, {"product": product}).get("productCreate") or {})
            if created.get("userErrors"): raise commerce.Rejected("Shopify refused the product: " + "; ".join(str(error.get("message", "")) for error in created["userErrors"])[:300])
            made = created.get("product") or {}
            variants = ((made.get("variants") or {}).get("nodes") or [])
            note = ""
            if variants:
                priced = (self.graphql(item["id"], PRICE, {"productId": made["id"], "variants": [{"id": variants[0]["id"], "price": f"{price:.2f}"}]})
                          .get("productVariantsBulkUpdate") or {})
                if priced.get("userErrors"): note = " Set its price in Shopify: the price wasn't accepted."
            return {"product_id": made.get("id"), "message": f"Draft product created in {item.get('name') or item['domain']}. It isn't published: add its images "
                    f"or files and review it in Shopify, then set it Active yourself.{note}"}
        return self.service.write_once(job_id, "shopify_draft", {"store": item["domain"], "fields": fields}, confirmed, perform, extra={"shop": item["domain"], "title": title})

    # ---- orders, as sales ----
    def import_orders(self, _service=None):
        from . import channels
        stores = [item for item in self.stores() if item.get("checked_at")]
        if not stores: raise ValueError("Connect a Shopify store in Business connections first")
        counts = {"added": 0, "changed": 0, "removed": 0}
        for item in stores:
            after = None
            for _ in range(channels.MAX_PAGES):
                page = (self.graphql(item["id"], ORDERS, {"after": after}).get("orders") or {})
                with self.db.Session.begin() as session:
                    for order in page.get("nodes") or []:
                        outcome = channels._store(session, f"shopify:{item['domain']}:{str(order.get('id')).rsplit('/', 1)[-1]}", "shopify", "sale", sale(order))
                        if outcome: counts[outcome] += 1
                info = page.get("pageInfo") or {}
                if not info.get("hasNextPage"): break
                after = info.get("endCursor")
        with self.db.Session.begin() as session:
            channels._remember(session, "shopify", counts)
            if any(counts.values()):
                session.add(Event(kind="money", message=f"Imported Shopify orders: {counts['added']} new, {counts['changed']} updated, {counts['removed']} cancelled or refunded"))
        return counts
