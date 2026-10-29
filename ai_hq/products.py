"""Digital products the owner sells: package finished work into a clean ZIP, price it, and track sales.

Selling works with Stripe alone, without a web host: the owner uploads the ZIP to storage they control (Google
Drive, Dropbox, OneDrive…) and pastes its share link; Cerebra creates a Stripe payment link whose thank-you page
gives the buyer that download link. Sales are read from Stripe's completed checkouts (payments.py). Packages
never include Git history, installed packages or settings files, so the owner's secrets can't be sold by accident.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

from sqlalchemy import select

from . import envfiles
from .models import BusinessJob, Product, Project, now, uid

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", ".cache", ".pytest_cache", ".turbo", "coverage", ".idea", ".vscode"}
SKIP_FILES = re.compile(r"^(\.env(\.[\w-]+)*|cerebra-brief\.json|.*\.(pem|key|p12|pfx|sqlite3?|db))$", re.I)
MAX_BYTES = 200 * 1024 * 1024
MAX_FILES = 5000


def _clean(value, size):
    return " ".join(str(value or "").split())[:size]


def public(product):
    revenue = round(sum(sale["amount"] for sale in product.sales or []), 2)
    return {"id": product.id, "name": product.name, "description": product.description, "price": product.price, "currency": product.currency,
            "download_url": product.download_url, "package": product.package or {}, "status": product.status, "sales": product.sales or [],
            "sold": len(product.sales or []), "revenue": revenue, "link": (product.stripe or {}).get("url", ""), "service": is_service(product),
            "selling": bool((product.stripe or {}).get("active")), "created_at": product.created_at, "updated_at": product.updated_at}


def _get(session, product_id):
    product = session.get(Product, product_id)
    if product is None:
        raise LookupError("Product not found")
    return product


def _apply(product, fields):
    if "name" in fields:
        product.name = _clean(fields["name"], 120)
    if "description" in fields:
        product.description = str(fields["description"] or "").strip()[:2000]
    if "price" in fields:
        price = round(float(fields["price"] or 0), 2)
        if not 0 < price <= 100_000:
            raise ValueError("Set a price above 0")
        product.price = price
    if "currency" in fields:
        currency = str(fields["currency"] or "").upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("Use a 3-letter currency code such as USD")
        product.currency = currency
    if "download_url" in fields:
        url = str(fields["download_url"] or "").strip()
        if url and (not url.startswith("https://") or len(url) > 400 or any(c in url for c in " <>\"'")):
            raise ValueError("The download link must be a full https:// share link, for example from Google Drive or Dropbox")
        product.download_url = url
    if not product.name:
        raise ValueError("Give the product a name")
    product.updated_at = now()


def create(session, fields):
    from . import business
    product = Product(id=uid(), name="", currency=business.load(session)["currency"], package={}, stripe={}, sales=[])
    _apply(product, {"price": fields.get("price") or 0, **fields})
    session.add(product)
    session.flush()
    return product


def update(session, product_id, fields):
    product = _get(session, product_id)
    if (product.stripe or {}).get("active") and {"price", "currency", "download_url"} & set(fields):
        raise ValueError("Pause selling first: the live Stripe link has the old price and download link. Then create a new link.")
    _apply(product, fields)
    return product


def delete(session, product_id):
    product = _get(session, product_id)
    if product.sales:
        raise ValueError("It has sales on record. Pause selling instead, so your sales history stays complete.")
    if (product.stripe or {}).get("active"):
        raise ValueError("Pause selling first")
    session.delete(product)


def products(session):
    return [public(product) for product in session.scalars(select(Product).order_by(Product.created_at.desc()).limit(300))]


def sources(session):
    """What a product can be packaged from: the owner's business jobs and registered projects."""
    jobs = [{"kind": "job", "id": job.id, "label": f"Business job: {job.title}"} for job in session.scalars(select(BusinessJob).order_by(BusinessJob.created_at.desc()).limit(100))]
    projects = [{"kind": "project", "id": project.id, "label": f"Project: {project.name}"} for project in session.scalars(select(Project).order_by(Project.created_at.desc()).limit(100))]
    return jobs + projects


def _source_folder(session, kind, identifier):
    if kind == "job":
        job = session.get(BusinessJob, identifier)
        if job is None:
            raise LookupError("Business job not found")
        exported = (job.export or {}).get("folder")
        return Path(exported if exported and Path(exported).is_dir() else job.output_dir)
    if kind == "project":
        project = session.get(Project, identifier)
        if project is None:
            raise LookupError("Project not found")
        return Path(project.path)
    raise ValueError("Package from a business job or a project")


def _included(root):
    files, total = [], 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts[:-1]) or path.is_dir() or path.is_symlink():
            continue
        if SKIP_FILES.match(path.name) and not envfiles.EXAMPLES.search(path.name):
            continue
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        total += path.stat().st_size
        files.append(path)
        if total > MAX_BYTES or len(files) > MAX_FILES:
            raise ValueError("That folder is too big to sell as one download (over 200 MB or 5,000 files). Package a smaller folder.")
    if not files:
        raise ValueError("There are no files to package in that folder")
    return files


def package(session_factory, product_id, kind, identifier):
    """Zip the source's files into the business folder's Products folder. Never overwrites an earlier package."""
    from . import business
    with session_factory() as session:
        product = _get(session, product_id)
        root = _source_folder(session, kind, identifier).resolve()
        name, folder = product.name, Path(business.load(session)["output_root"]) / "Products"
    if not root.is_dir():
        raise ValueError("That folder no longer exists")
    files = _included(root)
    folder.mkdir(parents=True, exist_ok=True)
    archive, counter = folder / f"{business.slug(name)}-{now()[:10]}.zip", 1
    while archive.exists():
        archive, counter = folder / f"{business.slug(name)}-{now()[:10]}-{counter}.zip", counter + 1
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            bundle.write(path, path.relative_to(root))
    info = {"zip": str(archive), "files": len(files), "bytes": archive.stat().st_size, "from": str(root), "at": now()}
    with session_factory.begin() as session:
        product = _get(session, product_id)
        product.package, product.updated_at = info, now()
    return info


def record_sale(session, product_id, checkout):
    """One completed Stripe checkout. Returns True when it is new."""
    from datetime import datetime, timezone
    from .payments import major
    product = _get(session, product_id)
    if any(sale["id"] == checkout["id"] for sale in product.sales or []):
        return False
    details = checkout.get("customer_details") or {}
    email, phone = _clean(details.get("email"), 120), _clean(details.get("phone"), 40)
    day = datetime.fromtimestamp(int(checkout.get("created") or 0), timezone.utc).date().isoformat()
    product.sales = list(product.sales or []) + [{"id": checkout["id"], "amount": major(int(checkout.get("amount_total") or 0), product.currency),
                                                   "date": day, "email": email, **({"phone": phone} if phone else {})}]
    product.updated_at = now()
    return True


def is_service(product):
    """A product without a download link is a service the owner delivers (a website deposit, an hour of support)."""
    return not product.download_url


def thank_you(product):
    """Stripe's thank-you page text (at most 500 characters): where the buyer downloads what they paid for, or, for a
    service, that the owner will be in touch (Stripe collects the buyer's email and phone number for that)."""
    if is_service(product):
        return (f"Thank you for booking {product.name}! Your payment is confirmed. I'll contact you by email or phone, "
                "using the details you just gave, to get started.")[:500]
    text = f"Thank you for buying {product.name}! Download your files here: {product.download_url} (save or bookmark this link)."
    return text[:500]
