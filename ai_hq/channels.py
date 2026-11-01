"""Marketplace money in one place: Etsy and Shopify orders as sales and Printify orders as costs, read from the owner's accounts.

Read-only: Cerebra lists the shop's receipts (Etsy, scope transactions_r) and orders (Printify) and records each
once under the service's own ID, updating it when a refund or cancellation changes it. An Etsy sale counts what
the buyer paid for items and shipping, after discounts and refunds; tax is left out (Etsy collects and pays it in
most places), and so are Etsy's fees, which the owner sees in Etsy's own payment account. A Printify order counts
what Printify charges the owner (production, shipping and tax). Nothing is created, changed or bought.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from . import commerce as connections, vault
from .models import ChannelEntry, EtsySaleLine, Event, Metadata, now

KEY = "channel_imports"
MAX_PAGES = 20
SKIPPED_ETSY = {"canceled", "fully refunded"}


def _money(value):
    """Etsy's {"amount": 1234, "divisor": 100, "currency_code": "USD"}."""
    if not isinstance(value, dict) or not value.get("divisor"):
        return 0.0, ""
    return round(int(value.get("amount") or 0) / int(value["divisor"]), 2), str(value.get("currency_code") or "")


def _day(seconds):
    return datetime.fromtimestamp(int(seconds or 0), timezone.utc).date().isoformat()


def etsy_sale(receipt):
    """The owner's takings from one Etsy receipt, or None when it doesn't count (unpaid, cancelled, refunded)."""
    status = str(receipt.get("status") or "").lower()
    if status in SKIPPED_ETSY or receipt.get("is_paid") is False:
        return None
    subtotal, currency = _money(receipt.get("subtotal"))
    shipping, _ = _money(receipt.get("total_shipping_cost"))
    refunded = sum(_money(refund.get("amount"))[0] for refund in receipt.get("refunds") or [] if isinstance(refund, dict))
    amount = round(subtotal + shipping - refunded, 2)
    if amount <= 0 or not currency:
        return None
    return {"amount": amount, "currency": currency.upper(), "date": _day(receipt.get("created_timestamp") or receipt.get("create_timestamp")),
            "note": f"Etsy order {receipt.get('receipt_id')}" + (" (partly refunded)" if refunded else "")}


def store_lines(session, receipt, shop):
    """The order's items, replaced each import: none when the order no longer counts (cancelled, refunded, unpaid)."""
    receipt_id = str(receipt.get("receipt_id"))
    for row in session.scalars(select(EtsySaleLine).where(EtsySaleLine.receipt_id == receipt_id)).all():
        session.delete(row)
    sale = etsy_sale(receipt)
    if sale is None:
        return
    for item in receipt.get("transactions") or []:
        if not isinstance(item, dict) or not item.get("transaction_id"):
            continue
        price, currency = _money(item.get("price"))
        quantity = max(1, int(item.get("quantity") or 1))
        session.merge(EtsySaleLine(id=str(item["transaction_id"]), receipt_id=receipt_id, listing_id=str(item.get("listing_id") or ""), shop_id=str(shop),
                                   title=str(item.get("title") or "")[:200], quantity=quantity, amount=round(price * quantity, 2),
                                   currency=(currency or sale["currency"]).upper(), date=sale["date"]))


def printify_cost(order):
    if str(order.get("status") or "").lower() in {"canceled", "cancelled"}:
        return None
    cents = sum(int(order.get(key) or 0) for key in ("total_price", "total_shipping", "total_tax"))
    if cents <= 0:
        return None
    created = str(order.get("created_at") or "")[:10]
    return {"amount": round(cents / 100, 2), "currency": "USD", "date": created or now()[:10], "note": f"Printify order {str(order.get('id'))[:24]}"}


def _store(session, identifier, source, kind, entry):
    row = session.get(ChannelEntry, identifier)
    if entry is None:
        if row is not None:
            session.delete(row)  # cancelled or refunded since the last import
            return "removed"
        return None
    if row is None:
        session.add(ChannelEntry(id=identifier, source=source, kind=kind, **entry))
        return "added"
    if (row.amount, row.currency, row.date, row.note) != (entry["amount"], entry["currency"], entry["date"], entry["note"]):
        row.amount, row.currency, row.date, row.note, row.updated_at = entry["amount"], entry["currency"], entry["date"], entry["note"], now()
        return "changed"
    return None


def _remember(session, source, result):
    row = session.get(Metadata, KEY)
    value = dict(row.value) if row else {}
    value[source] = {**result, "at": now()}
    if row:
        row.value = value
    else:
        session.add(Metadata(key=KEY, value=value))


def import_etsy(service):
    """service: the Commerce connection object (Etsy sign-in, token refresh, safe errors). Orders come from every connected shop."""
    try:
        service.etsy_headers()
    except ValueError:
        raise ValueError("Connect and authorize Etsy in Business connections first") from None
    if not service.config("etsy").get("shop_id"):
        raise ValueError("Check the Etsy connection once so Cerebra knows your shop")
    counts = {"added": 0, "changed": 0, "removed": 0}
    for connected in service.etsy_shops():
        if connected["shop_id"]:
            _import_shop(service, service.etsy_headers(connected["id"]), connected["shop_id"], counts)
    with service.db.Session.begin() as session:
        _remember(session, "etsy", counts)
        if any(counts.values()):
            session.add(Event(kind="money", message=f"Imported Etsy orders: {counts['added']} new, {counts['changed']} updated, {counts['removed']} cancelled or refunded"))
    return counts


def _import_shop(service, headers, shop, counts):
    offset = 0
    for _ in range(MAX_PAGES):
        try:
            page = service.request("GET", f"https://api.etsy.com/v3/application/shops/{shop}/receipts", headers=headers, params={"limit": 100, "offset": offset})
        except connections.Rejected:
            raise ValueError("Etsy didn't allow reading your orders. Authorize Etsy again in Business connections (Cerebra now also asks to read transactions).") from None
        results = page.get("results") or []
        with service.db.Session.begin() as session:
            for receipt in results:
                outcome = _store(session, f"etsy:{receipt.get('receipt_id')}", "etsy", "sale", etsy_sale(receipt))
                if outcome:
                    counts[outcome] += 1
                store_lines(session, receipt, shop)
        offset += len(results)
        if len(results) < 100 or offset >= int(page.get("count") or 0):
            break


def import_printify(service):
    item = service.config("printify")
    if not item.get("shop_id"):
        raise ValueError("Check the Printify connection once so Cerebra knows your store")
    headers = {"Authorization": "Bearer " + vault.unprotect(item["api_key"])}
    counts = {"added": 0, "changed": 0, "removed": 0}
    for number in range(1, MAX_PAGES + 1):
        page = service.request("GET", f"https://api.printify.com/v1/shops/{item['shop_id']}/orders.json", headers=headers, params={"page": number, "limit": 50})
        orders = page.get("data") or []
        with service.db.Session.begin() as session:
            for order in orders:
                outcome = _store(session, f"printify:{order.get('id')}", "printify", "cost", printify_cost(order))
                if outcome:
                    counts[outcome] += 1
        if not orders or number >= int(page.get("last_page") or number):
            break
    with service.db.Session.begin() as session:
        _remember(session, "printify", counts)
        if any(counts.values()):
            session.add(Event(kind="money", message=f"Imported Printify orders: {counts['added']} new, {counts['changed']} updated, {counts['removed']} cancelled"))
    return counts


def status(session):
    imports = (session.get(Metadata, KEY).value if session.get(Metadata, KEY) else {})
    linked = connections.public(session)
    result = {}
    for source, kind in (("etsy", "sale"), ("printify", "cost")):
        rows = session.scalars(select(ChannelEntry).where(ChannelEntry.source == source)).all()
        ready = linked[source]["authorized"] if source == "etsy" else linked[source]["configured"]
        result[source] = {"connected": bool(ready and linked[source].get("shop_id")), "kind": kind, "count": len(rows),
                          "last_import": (imports.get(source) or {}).get("at", ""), "totals": _totals(rows)}
    rows = session.scalars(select(ChannelEntry).where(ChannelEntry.source == "shopify")).all()
    stores = connections.load(session).get("shopify_stores") or []
    result["shopify"] = {"connected": any(item.get("checked_at") for item in stores), "kind": "sale", "count": len(rows),
                         "last_import": (imports.get("shopify") or {}).get("at", ""), "totals": _totals(rows)}
    result["recent"] = [{"id": row.id, "source": row.source, "kind": row.kind, "amount": row.amount, "currency": row.currency, "date": row.date, "note": row.note}
                        for row in session.scalars(select(ChannelEntry).order_by(ChannelEntry.date.desc()).limit(25))]
    return result


def _totals(rows):
    totals = {}
    for row in rows:
        totals[row.currency] = round(totals.get(row.currency, 0.0) + row.amount, 2)
    return totals
