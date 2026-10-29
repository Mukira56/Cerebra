"""Money center: the owner's quotes and invoices, and what the business has earned and is owed.

Cerebra drafts quotes and invoices, numbers them when the owner issues them (so numbers have no gaps), lays them
out for printing or saving as PDF, and records payments the owner confirms or a connected payment service reports.
It never takes or moves money and never sends anything to a client by itself: the owner sends each document.
Amounts are the owner's own; Cerebra invents no prices, discounts or terms.
"""
from __future__ import annotations

import html
import re
from datetime import date, timedelta

from sqlalchemy import select

from .models import BusinessJob, Metadata, MoneyDocument, now, uid

KEY = "money_settings"
KINDS = {"quote", "invoice"}
DEFAULTS = {"business_name": "", "email": "", "phone": "", "address": "", "tax_id": "", "payment_terms_days": 14, "quote_valid_days": 30,
            "payment_instructions": "", "quote_prefix": "Q-", "invoice_prefix": "INV-", "next_quote": 1, "next_invoice": 1, "services": []}
MAX_SERVICES = 40
TEXT_FIELDS = {"business_name": 120, "email": 120, "phone": 40, "address": 300, "tax_id": 60, "payment_instructions": 600, "quote_prefix": 10, "invoice_prefix": 10}
EMAIL = re.compile(r"^[^@\s<>\"']+@[^@\s<>\"']+\.[^@\s<>\"']+$")
MAX_ITEMS = 50


def _clean(value, size):
    return " ".join(str(value or "").split())[:size]


def settings(session):
    row = session.get(Metadata, KEY)
    return {**DEFAULTS, **(row.value if row else {})}


def save_settings(session, changes):
    value = settings(session)
    for key, size in TEXT_FIELDS.items():
        if key in changes:
            value[key] = str(changes[key] or "").strip()[:size] if key in {"address", "payment_instructions"} else _clean(changes[key], size)
    if value["email"] and not EMAIL.match(value["email"]):
        raise ValueError("Enter a valid email address for your business")
    if "services" in changes:
        value["services"] = _services(changes["services"])
    for key, low, high in (("payment_terms_days", 0, 365), ("quote_valid_days", 1, 365)):
        if key in changes:
            number = int(changes[key])
            if not low <= number <= high:
                raise ValueError(f"{key.replace('_', ' ').capitalize()} must be between {low} and {high}")
            value[key] = number
    row = session.get(Metadata, KEY)
    if row:
        row.value = value
    else:
        session.add(Metadata(key=KEY, value=value))
    return value


def _services(raw):
    """The owner's usual services and prices, for one-click quote lines: [{"name", "price"}]."""
    if not isinstance(raw, list) or len(raw) > MAX_SERVICES:
        raise ValueError(f"Save at most {MAX_SERVICES} services")
    services = []
    for item in raw:
        name = _clean((item or {}).get("name"), 120)
        try:
            price = round(float(item.get("price") or 0), 2)
        except (TypeError, ValueError):
            raise ValueError("Each service needs a number as its price") from None
        if not name or not 0 <= price <= 10_000_000:
            raise ValueError("Each service needs a name and a price that isn't negative")
        services.append({"name": name, "price": price})
    return services


def _currency(session):
    from . import business
    return business.load(session)["currency"]


def _items(raw):
    if not isinstance(raw, list) or not raw:
        raise ValueError("Add at least one line: what you'll do and its price")
    if len(raw) > MAX_ITEMS:
        raise ValueError(f"At most {MAX_ITEMS} lines")
    items = []
    for line in raw:
        description = _clean((line or {}).get("description"), 300)
        try:
            quantity, price = float(line.get("quantity", 1)), float(line.get("unit_price", 0))
        except (TypeError, ValueError):
            raise ValueError("Quantities and prices must be numbers") from None
        if not description:
            raise ValueError("Every line needs a description")
        if not 0 < quantity <= 100_000 or not 0 <= price <= 10_000_000:
            raise ValueError("Quantities must be above 0 and prices can't be negative")
        items.append({"description": description, "quantity": round(quantity, 2), "unit_price": round(price, 2)})
    return items


def totals(doc):
    total = round(sum(item["quantity"] * item["unit_price"] for item in doc.items or []), 2)
    paid = round(sum(payment["amount"] for payment in doc.payments or []), 2)
    return {"total": total, "paid": paid, "balance": round(max(0.0, total - paid), 2)}


def _today():
    return date.today().isoformat()


def overdue(doc, today=None):
    return doc.kind == "invoice" and doc.status == "sent" and bool(doc.due_date) and doc.due_date < (today or _today())


def public(doc, today=None):
    return {"id": doc.id, "kind": doc.kind, "number": doc.number, "status": doc.status, "client": doc.client, "client_email": doc.client_email,
            "job_id": doc.job_id, "source_id": doc.source_id, "items": doc.items or [], "currency": doc.currency, "notes": doc.notes,
            "issued_at": doc.issued_at, "due_date": doc.due_date, "payment_url": doc.payment_url, "payments": doc.payments or [],
            "provider": {key: value for key, value in (doc.provider or {}).items() if key != "secret"}, "overdue": overdue(doc, today),
            "created_at": doc.created_at, "updated_at": doc.updated_at, **totals(doc)}


def _get(session, doc_id):
    doc = session.get(MoneyDocument, doc_id)
    if doc is None:
        raise LookupError("Quote or invoice not found")
    return doc


def _apply(session, doc, fields):
    if "client" in fields:
        doc.client = _clean(fields["client"], 120)
    if "client_email" in fields:
        email = _clean(fields["client_email"], 120)
        if email and not EMAIL.match(email):
            raise ValueError("Enter a valid email address for the client")
        doc.client_email = email
    if "items" in fields:
        doc.items = _items(fields["items"])
    if "notes" in fields:
        doc.notes = str(fields["notes"] or "").strip()[:2000]
    if "currency" in fields:
        currency = str(fields["currency"] or "").upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("Use a 3-letter currency code such as USD or KES")
        doc.currency = currency
    if "job_id" in fields:
        if fields["job_id"] and session.get(BusinessJob, fields["job_id"]) is None:
            raise ValueError("That business job doesn't exist")
        doc.job_id = fields["job_id"] or None
    if "payment_url" in fields:
        url = str(fields["payment_url"] or "").strip()
        if url and (not url.startswith("https://") or len(url) > 500 or any(c in url for c in " <>\"'")):
            raise ValueError("The payment link must be a full https:// address, for example a Stripe payment link")
        doc.payment_url = url
    if not doc.client:
        raise ValueError("Who is it for? Enter the client's name")
    doc.updated_at = now()


def create(session, kind, fields):
    if kind not in KINDS:
        raise ValueError("Choose a quote or an invoice")
    doc = MoneyDocument(id=uid(), kind=kind, currency=_currency(session), items=[], payments=[], provider={})
    _apply(session, doc, {**fields, "items": fields.get("items")})
    session.add(doc)
    session.flush()
    return doc


def update(session, doc_id, fields):
    doc = _get(session, doc_id)
    if doc.status != "draft":
        if set(fields) - {"payment_url"}:
            raise ValueError("Only drafts can be changed. Void it and make a new one, or record a payment.")
    _apply(session, doc, fields)
    return doc


def issue(session, doc_id, today=None):
    """Draft -> sent: give it the next number and its dates. The owner sends it to the client themselves."""
    doc = _get(session, doc_id)
    if doc.status != "draft":
        raise ValueError("It was already issued")
    if not doc.items:
        raise ValueError("Add at least one line first")
    config, day = settings(session), date.fromisoformat(today or _today())
    counter = "next_quote" if doc.kind == "quote" else "next_invoice"
    doc.number = f"{config['quote_prefix'] if doc.kind == 'quote' else config['invoice_prefix']}{config[counter]:04d}"
    while session.scalars(select(MoneyDocument).where(MoneyDocument.number == doc.number, MoneyDocument.kind == doc.kind, MoneyDocument.id != doc.id)).first():
        config[counter] += 1  # an older numbering, or a prefix changed back: never reuse a number
        doc.number = f"{config['quote_prefix'] if doc.kind == 'quote' else config['invoice_prefix']}{config[counter]:04d}"
    save_settings(session, {})  # makes sure the row exists
    session.flush()
    row = session.get(Metadata, KEY)
    row.value = {**row.value, counter: config[counter] + 1}
    doc.issued_at = day.isoformat()
    doc.due_date = (day + timedelta(days=config["quote_valid_days"] if doc.kind == "quote" else config["payment_terms_days"])).isoformat()
    doc.status = "sent"
    doc.updated_at = now()
    return doc


def accept(session, quote_id, deposit_percent=0):
    """The client accepted a quote: mark it, and draft the invoice (the whole amount, or a deposit) for the owner."""
    quote = _get(session, quote_id)
    if quote.kind != "quote" or quote.status != "sent":
        raise ValueError("Only an issued quote can be accepted")
    deposit = float(deposit_percent or 0)
    if not 0 <= deposit <= 100:
        raise ValueError("The deposit must be between 0 and 100 percent")
    quote.status, quote.updated_at = "accepted", now()
    if deposit and deposit < 100:
        total = totals(quote)["total"]
        items = [{"description": f"Deposit ({deposit:g}%) for quote {quote.number}", "quantity": 1, "unit_price": round(total * deposit / 100, 2)}]
    else:
        items = [dict(item) for item in quote.items]
    invoice = MoneyDocument(id=uid(), kind="invoice", client=quote.client, client_email=quote.client_email, job_id=quote.job_id, source_id=quote.id,
                            items=items, currency=quote.currency, notes=quote.notes, payments=[], provider={})
    session.add(invoice)
    session.flush()
    return invoice


def balance_invoice(session, quote_id):
    """After a deposit: draft the invoice for what the quote still has to be paid."""
    quote = _get(session, quote_id)
    if quote.kind != "quote" or quote.status != "accepted":
        raise ValueError("Only an accepted quote has a balance to invoice")
    invoiced = sum(totals(doc)["total"] for doc in session.scalars(select(MoneyDocument).where(MoneyDocument.source_id == quote.id, MoneyDocument.status != "void")))
    rest = round(totals(quote)["total"] - invoiced, 2)
    if rest <= 0:
        raise ValueError("Everything on this quote is already invoiced")
    invoice = MoneyDocument(id=uid(), kind="invoice", client=quote.client, client_email=quote.client_email, job_id=quote.job_id, source_id=quote.id,
                            items=[{"description": f"Balance for quote {quote.number}", "quantity": 1, "unit_price": rest}], currency=quote.currency,
                            notes=quote.notes, payments=[], provider={})
    session.add(invoice)
    session.flush()
    return invoice


def decline(session, quote_id):
    quote = _get(session, quote_id)
    if quote.kind != "quote" or quote.status != "sent":
        raise ValueError("Only an issued quote can be marked declined")
    quote.status, quote.updated_at = "declined", now()
    return quote


def record_payment(session, doc_id, amount, day=None, method="", reference="", source="owner"):
    """A payment the owner received (or a payment service confirmed). The linked business job's ledger gets it too."""
    doc = _get(session, doc_id)
    if doc.kind != "invoice" or doc.status not in {"sent", "paid"}:
        raise ValueError("Issue the invoice before recording payments")
    amount = round(float(amount), 2)
    if not 0 < amount <= 10_000_000:
        raise ValueError("Enter the amount received")
    reference = _clean(reference, 120)
    if reference and any(payment.get("reference") == reference for payment in doc.payments or []):
        return doc  # already recorded (a payment service reporting the same payment again)
    day = str(day or _today())[:10]
    payment = {"id": uid()[:12], "amount": amount, "date": day, "method": _clean(method, 40), "reference": reference, "source": source}
    doc.payments = list(doc.payments or []) + [payment]
    if totals(doc)["balance"] <= 0:
        doc.status = "paid"
    doc.updated_at = now()
    if doc.job_id:
        from . import business
        business.add_ledger(session, doc.job_id, {"kind": "payment", "amount": amount, "date": day, "note": f"Invoice {doc.number}" + (f" ({payment['method']})" if payment["method"] else "")})
    return doc


def void(session, doc_id):
    """Drafts are deleted; issued documents are voided and keep their number, so the sequence stays complete."""
    doc = _get(session, doc_id)
    if doc.status == "draft":
        session.delete(doc)
        return None
    if doc.payments:
        raise ValueError("It has payments recorded. Refund them in your payment service first.")
    doc.status, doc.updated_at = "void", now()
    return doc


def quote_from_job(session, job_id):
    """A draft quote prefilled from a business job's agreed scope (its price, pages and features)."""
    from . import business
    job, row = business.record(session, job_id)
    scope = row.scope or {}
    price = float(scope.get("price") or 0)
    pieces = [part for part in (", ".join(scope.get("pages") or []), ", ".join(scope.get("features") or [])) if part]
    items = [{"description": f"{job.title}" + (f": {'; '.join(pieces)}" if pieces else ""), "quantity": 1, "unit_price": price}]
    if scope.get("revisions_included"):
        items[0]["description"] = (items[0]["description"] + f". Includes {scope['revisions_included']} round(s) of changes")[:300]
    notes = ("Not included: " + ", ".join(scope["exclusions"])) if scope.get("exclusions") else ""
    return create(session, "quote", {"client": scope.get("client") or job.client or job.title, "items": items, "job_id": job.id, "notes": notes,
                                     **({"currency": scope["currency"]} if re.fullmatch(r"[A-Z]{3}", str(scope.get("currency") or "")) else {})})


def documents(session, today=None):
    rows = session.scalars(select(MoneyDocument).order_by(MoneyDocument.created_at.desc()).limit(500)).all()
    return [public(doc, today) for doc in rows]


def summary(session, today=None):
    """Earned, owed and coming, per currency, from the owner's own documents and business job ledgers."""
    from .models import BusinessRecord
    today = today or _today()
    month, year = today[:7], today[:4]
    main = _currency(session)
    sums = {}

    def bucket(currency):
        return sums.setdefault(currency, {"earned_month": 0.0, "earned_year": 0.0, "spent_month": 0.0, "spent_year": 0.0, "owed": 0.0, "overdue": 0.0, "overdue_count": 0, "pipeline": 0.0, "won_unbilled": 0.0})

    docs = session.scalars(select(MoneyDocument)).all()
    for doc in docs:
        figures, entry = totals(doc), bucket(doc.currency)
        if doc.kind == "invoice" and doc.status in {"sent", "paid"}:
            if not doc.job_id:  # a job's payments are counted from its ledger below
                for payment in doc.payments or []:
                    entry["earned_month"] += payment["amount"] if payment["date"][:7] == month else 0
                    entry["earned_year"] += payment["amount"] if payment["date"][:4] == year else 0
            if doc.status == "sent":
                entry["owed"] += figures["balance"]
                if overdue(doc, today):
                    entry["overdue"] += figures["balance"]
                    entry["overdue_count"] += 1
        elif doc.kind == "quote" and doc.status == "sent":
            entry["pipeline"] += figures["total"]
        elif doc.kind == "quote" and doc.status == "accepted":
            invoiced = sum(totals(other)["total"] for other in docs if other.source_id == doc.id and other.status != "void")
            entry["won_unbilled"] += max(0.0, figures["total"] - invoiced)
    from .models import ChannelEntry, Product
    for row in session.scalars(select(ChannelEntry)).all():
        entry, prefix = bucket(row.currency), "earned" if row.kind == "sale" else "spent"
        entry[prefix + "_month"] += row.amount if row.date[:7] == month else 0
        entry[prefix + "_year"] += row.amount if row.date[:4] == year else 0
    for product in session.scalars(select(Product)).all():
        entry = bucket(product.currency)
        for sale in product.sales or []:
            entry["earned_month"] += sale["amount"] if sale["date"][:7] == month else 0
            entry["earned_year"] += sale["amount"] if sale["date"][:4] == year else 0
    for record in session.scalars(select(BusinessRecord)).all():
        for item in record.ledger or []:
            if item.get("kind") in {"payment", "expense"}:
                entry, prefix = bucket(main), "earned" if item["kind"] == "payment" else "spent"
                entry[prefix + "_month"] += item["amount"] if str(item.get("date", ""))[:7] == month else 0
                entry[prefix + "_year"] += item["amount"] if str(item.get("date", ""))[:4] == year else 0
    bucket(main)
    return {"currency": main, "today": today, "by_currency": {currency: {key: round(value, 2) if isinstance(value, float) else value for key, value in entry.items()}
                                                              for currency, entry in sums.items()},
            "note": "From your own quotes, invoices and recorded payments, product sales Stripe reported, and Etsy and Printify orders you imported. Etsy sales are before Etsy's fees. Nothing is estimated."}


def _money(amount, currency):
    return f"{currency} {amount:,.2f}"


def render(doc, config):
    """A clean, printable page for the quote or invoice (print it, or save it as PDF from the browser)."""
    e = lambda value: html.escape(str(value or ""))  # noqa: E731
    figures = totals(doc)
    title = ("Quote" if doc.kind == "quote" else "Invoice") + (f" {doc.number}" if doc.number else " (draft)")
    rows = "".join(f"<tr><td>{e(item['description'])}</td><td class=n>{item['quantity']:g}</td><td class=n>{e(_money(item['unit_price'], doc.currency))}</td>"
                   f"<td class=n>{e(_money(item['quantity'] * item['unit_price'], doc.currency))}</td></tr>" for item in doc.items or [])
    paid = "".join(f"<tr><td colspan=3>Paid {e(payment['date'])}{' · ' + e(payment['method']) if payment.get('method') else ''}</td><td class=n>-{e(_money(payment['amount'], doc.currency))}</td></tr>"
                   for payment in doc.payments or [])
    dates = (f"<p>Date: {e(doc.issued_at)}<br>{'Valid until' if doc.kind == 'quote' else 'Due'}: {e(doc.due_date)}</p>" if doc.issued_at else "<p><strong>DRAFT</strong> — not issued yet</p>")
    pay = ""
    if doc.kind == "invoice":
        link = f"<p><a href=\"{e(doc.payment_url)}\">Pay online</a>: {e(doc.payment_url)}</p>" if doc.payment_url else ""
        how = f"<p>{e(config['payment_instructions']).replace(chr(10), '<br>')}</p>" if config.get("payment_instructions") else ""
        pay = f"<section><h2>How to pay</h2>{link}{how}</section>" if link or how else ""
    business_lines = "<br>".join(e(part) for part in (config.get("business_name"), config.get("address"), config.get("email"), config.get("phone"),
                                                      f"Tax ID: {config['tax_id']}" if config.get("tax_id") else "") if part).replace("\n", "<br>")
    notes = f"<section><h2>Notes</h2><p>{e(doc.notes).replace(chr(10), '<br>')}</p></section>" if doc.notes else ""
    status = "<p class=stamp>PAID</p>" if doc.status == "paid" else "<p class=stamp>VOID</p>" if doc.status == "void" else ""
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>{e(title)}</title>
<style>body{{font:15px/1.5 system-ui,Segoe UI,sans-serif;color:#111;max-width:780px;margin:32px auto;padding:0 20px}}header{{display:flex;justify-content:space-between;gap:24px}}
h1{{margin:0;font-size:28px}}h2{{font-size:15px;margin:24px 0 6px;text-transform:uppercase;letter-spacing:.05em;color:#555}}table{{width:100%;border-collapse:collapse;margin-top:16px}}
th,td{{padding:8px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}}.n{{text-align:right;white-space:nowrap}}tfoot td{{font-weight:600}}
.stamp{{display:inline-block;border:3px solid #b00;color:#b00;padding:2px 12px;font-weight:700;transform:rotate(-6deg)}}@media print{{body{{margin:0}}a{{color:#111}}}}</style></head>
<body><header><div><h1>{e(title)}</h1>{dates}{status}</div><div>{business_lines or '<em>Add your business details in Money → Your business</em>'}</div></header>
<section><h2>For</h2><p>{e(doc.client)}{'<br>' + e(doc.client_email) if doc.client_email else ''}</p></section>
<table><thead><tr><th>Description</th><th class=n>Qty</th><th class=n>Price</th><th class=n>Amount</th></tr></thead><tbody>{rows}{paid}</tbody>
<tfoot><tr><td colspan=3>{'Total' if doc.kind == 'quote' else 'Balance due' if doc.payments else 'Total due'}</td><td class=n>{e(_money(figures['total'] if doc.kind == 'quote' else figures['balance'], doc.currency))}</td></tr></tfoot></table>
{pay}{notes}</body></html>"""


def reminder(doc, config, today=None):
    """Ready-to-send wording asking the client to pay an issued invoice: friendly, then firm, then final, by how
    late it is. Written from the invoice's own facts (no AI, no invented terms); the owner sends it themselves."""
    from urllib.parse import quote
    if doc.kind != "invoice" or doc.status != "sent":
        raise ValueError("Only an issued, unpaid invoice needs a reminder")
    figures, today = totals(doc), today or _today()
    late = (date.fromisoformat(today) - date.fromisoformat(doc.due_date)).days if doc.due_date else 0
    owed, sender = _money(figures["balance"], doc.currency), config.get("business_name") or ""
    pay = []
    if doc.payment_url:
        pay.append(f"You can pay online here: {doc.payment_url}")
    if config.get("payment_instructions"):
        pay.append("Payment details:\n" + config["payment_instructions"].strip())
    how = ("\n\n" + "\n\n".join(pay)) if pay else ""
    if late <= 7:
        tone = "friendly"
        subject = f"Invoice {doc.number}: {owed} " + ("due " + doc.due_date if late <= 0 else "now due")
        opening = (f"I hope all is well. This is a quick reminder that invoice {doc.number} for {owed} is due on {doc.due_date}."
                   if late <= 0 else f"I hope all is well. Invoice {doc.number} for {owed} was due on {doc.due_date}; perhaps it slipped through.")
        closing = "If you've already paid, thank you, and please ignore this message."
    elif late <= 30:
        tone = "firm"
        subject = f"Overdue: invoice {doc.number} ({owed})"
        opening = f"Invoice {doc.number} for {owed} was due on {doc.due_date} and is now {late} days overdue. Please arrange payment this week."
        closing = "If something is holding up payment, reply and let me know, and we can sort it out."
    else:
        tone = "final"
        subject = f"Final reminder: invoice {doc.number} ({owed}) is {late} days overdue"
        opening = (f"Invoice {doc.number} for {owed} was due on {doc.due_date} and is now {late} days overdue. "
                   "I've sent earlier reminders and haven't received payment yet. Please pay the outstanding amount or contact me within 7 days.")
        closing = "If you've already paid, please send me the payment reference so I can match it."
    greeting = f"Hello {doc.client}," if doc.client else "Hello,"
    body = f"{greeting}\n\n{opening}{how}\n\n{closing}\n\nThank you," + (f"\n{sender}" if sender else "")
    link = "mailto:" + quote(doc.client_email or "", safe="@") + "?subject=" + quote(subject) + "&body=" + quote(body)
    return {"tone": tone, "days_late": late, "subject": subject, "body": body, "to": doc.client_email, "mailto": link,
            "sent": list((doc.provider or {}).get("reminders", []))}


def mark_reminded(session, doc_id, tone, today=None):
    doc = _get(session, doc_id)
    if doc.kind != "invoice" or doc.status != "sent":
        raise ValueError("Only an issued, unpaid invoice needs a reminder")
    provider = dict(doc.provider or {})
    provider["reminders"] = list(provider.get("reminders", [])) + [{"date": today or _today(), "tone": _clean(tone, 20)}]
    doc.provider, doc.updated_at = provider, now()
    return doc


# ---- recurring plans: care plans and retainers billed on a schedule ----
EVERY = {"month": 1, "quarter": 3, "year": 12}


def _add_months(day, months):
    """The same day `months` later, kept at most on the 28th so every month has it."""
    total = day.month - 1 + months
    return date(day.year + total // 12, total % 12 + 1, min(day.day, 28))


def plan_public(plan):
    from .models import RecurringPlan  # noqa: F401
    total = round(sum(item["quantity"] * item["unit_price"] for item in plan.items or []), 2)
    return {"id": plan.id, "client": plan.client, "client_email": plan.client_email, "job_id": plan.job_id, "items": plan.items or [], "currency": plan.currency,
            "notes": plan.notes, "every": plan.every, "next_date": plan.next_date, "auto_issue": plan.auto_issue, "active": plan.active, "made": plan.made or [],
            "total": total, "monthly": round(total / EVERY.get(plan.every, 1), 2)}


def save_plan(session, plan_id, fields):
    from .models import RecurringPlan
    plan = session.get(RecurringPlan, plan_id) if plan_id else RecurringPlan(id=uid(), items=[], made=[], currency=_currency(session))
    if plan is None:
        raise LookupError("Recurring plan not found")
    holder = MoneyDocument(kind="invoice", client=plan.client, client_email=plan.client_email, items=plan.items, currency=plan.currency,
                           notes=plan.notes, job_id=plan.job_id)
    _apply(session, holder, fields)  # the same checks as an invoice
    plan.client, plan.client_email, plan.items, plan.currency, plan.notes, plan.job_id = holder.client, holder.client_email, holder.items, holder.currency, holder.notes, holder.job_id
    if not plan.items:
        raise ValueError("Add at least one line: what you'll do each period and its price")
    if "every" in fields:
        if fields["every"] not in EVERY:
            raise ValueError("Bill every month, quarter or year")
        plan.every = fields["every"]
    if "next_date" in fields or not plan.next_date:
        try:
            plan.next_date = date.fromisoformat(str(fields.get("next_date") or _today())[:10]).isoformat()
        except ValueError:
            raise ValueError("Choose the date of the first invoice") from None
    if "auto_issue" in fields:
        plan.auto_issue = bool(fields["auto_issue"])
    if "active" in fields:
        plan.active = bool(fields["active"])
    plan.updated_at = now()
    if not plan_id:
        session.add(plan)
    session.flush()
    return plan


def delete_plan(session, plan_id):
    from .models import RecurringPlan
    plan = session.get(RecurringPlan, plan_id)
    if plan is None:
        raise LookupError("Recurring plan not found")
    session.delete(plan)  # the invoices it made stay


def plans(session):
    from .models import RecurringPlan
    return [plan_public(plan) for plan in session.scalars(select(RecurringPlan).order_by(RecurringPlan.created_at.desc()))]


def run_plans(session, today=None):
    """Make every invoice that is due: one per missed period (a laptop that was off for two months catches up), each
    dated on its own period. Returns the new documents. Safe to call often: a period is billed once."""
    from .models import RecurringPlan
    today = today or _today()
    made = []
    for plan in session.scalars(select(RecurringPlan).where(RecurringPlan.active.is_(True))).all():
        for _ in range(24):  # at most two years of catching up at once
            if not plan.next_date or plan.next_date > today:
                break
            period = plan.next_date
            doc = MoneyDocument(id=uid(), kind="invoice", client=plan.client, client_email=plan.client_email, job_id=plan.job_id, items=[dict(item) for item in plan.items],
                                currency=plan.currency, notes=(plan.notes + ("\n" if plan.notes else "") + f"For the period starting {period}.").strip(), payments=[], provider={"plan": plan.id})
            session.add(doc)
            session.flush()
            if plan.auto_issue:
                issue(session, doc.id, today=period)
            plan.made = list(plan.made or []) + [{"date": period, "document": doc.id}]
            plan.next_date = _add_months(date.fromisoformat(period), EVERY[plan.every]).isoformat()
            plan.updated_at = now()
            made.append(doc)
    return made


def year_rows(session, year):
    """Every payment, sale and cost of a calendar year, one row each, counted exactly like summary() (a business
    job's invoice payments come from its ledger, so nothing is listed twice)."""
    from .models import BusinessJob, BusinessRecord, ChannelEntry, Product
    year, main, rows = str(year), _currency(session), []
    for doc in session.scalars(select(MoneyDocument).where(MoneyDocument.kind == "invoice")).all():
        if doc.job_id:
            continue
        for payment in doc.payments or []:
            if payment["date"][:4] == year:
                rows.append([payment["date"], "income", "invoice payment", doc.client, doc.number, payment.get("method", ""), payment["amount"], doc.currency])
    for record in session.scalars(select(BusinessRecord)).all():
        job = session.get(BusinessJob, record.job_id)
        for item in record.ledger or []:
            if item.get("kind") in {"payment", "expense"} and str(item.get("date", ""))[:4] == year:
                rows.append([item["date"], "income" if item["kind"] == "payment" else "cost", "business job " + item["kind"], job.client if job else "",
                             job.title if job else "", item.get("note", ""), item["amount"], main])
    for product in session.scalars(select(Product)).all():
        for sale in product.sales or []:
            if sale["date"][:4] == year:
                rows.append([sale["date"], "income", "product sale (Stripe)", sale.get("email", ""), product.name, sale["id"], sale["amount"], product.currency])
    for entry in session.scalars(select(ChannelEntry)).all():
        if entry.date[:4] == year:
            rows.append([entry.date, "income" if entry.kind == "sale" else "cost", f"{entry.source} order", "", entry.note, entry.id.split(":", 1)[-1], entry.amount, entry.currency])
    return sorted(rows, key=lambda row: (row[0], row[1]))


def export_year(session, year, folder):
    """Write the year's rows as a CSV for the owner's accountant or tax return. Never overwrites: a new name each time."""
    import csv
    from pathlib import Path
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target, counter = folder / f"Cerebra money {year}.csv", 1
    while target.exists():
        target, counter = folder / f"Cerebra money {year} ({counter}).csv", counter + 1
    rows = year_rows(session, year)
    with target.open("x", newline="", encoding="utf-8-sig") as handle:  # Excel opens UTF-8 with a BOM correctly
        writer = csv.writer(handle)
        writer.writerow(["Date", "Type", "What", "Client or buyer", "Item", "Reference", "Amount", "Currency"])
        for row in rows:
            writer.writerow([_safe_cell(value) for value in row])
    return {"path": str(target), "rows": len(rows)}


def _safe_cell(value):
    """Spreadsheets run cells that start with = + - @ as formulas; client names are never formulas."""
    text = value if isinstance(value, (int, float)) else str(value or "")
    return "'" + text if isinstance(text, str) and text[:1] in ("=", "+", "-", "@", "\t", "\r") else text
