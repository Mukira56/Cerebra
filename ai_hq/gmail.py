"""Gmail access with the user's own Google OAuth client (installed-app flow with PKCE).

The user creates a free "Desktop app" OAuth client in their Google Cloud project and pastes its ID and
secret. Sign-in happens in their normal browser on Google's own page. Google redirects back to this local
server, and Cerebra keeps only the refresh token, encrypted with DPAPI. Two scopes are requested:
gmail.readonly, to see wins and replies, and gmail.send, used only by automatic outreach when the owner
switches it on (ai_hq/outreach.py). Cerebra can never delete or change mail. An account connected before
sending existed keeps working read-only until the owner connects again.
"""
from __future__ import annotations

import base64
import hashlib
import html
import re
import secrets
import time
from urllib.parse import urlencode

import httpx

from .models import Metadata, now
from . import vault
from .network import LazyClient

KEY = "gmail_oauth"
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SEND = "https://www.googleapis.com/auth/gmail.send"
AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
CLIENT_ID = re.compile(r"^[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com$")


def load(session):
    row = session.get(Metadata, KEY)
    return dict(row.value) if row else {}


def public(value):
    return {"configured": bool(value.get("client_id")), "client_id": value.get("client_id", ""),
            "connected": bool(value.get("refresh_token")), "email": value.get("email", ""), "connected_at": value.get("connected_at", ""),
            "can_send": bool(value.get("refresh_token") and value.get("can_send"))}


def _store(session, value):
    row = session.get(Metadata, KEY)
    if row:
        row.value = value
    else:
        session.add(Metadata(key=KEY, value=value))


def configure(session, client_id, client_secret):
    client_id = (client_id or "").strip()
    if not CLIENT_ID.fullmatch(client_id):
        raise ValueError("The client ID should end in .apps.googleusercontent.com (Google Cloud › Credentials › OAuth client › Desktop app)")
    if not 10 <= len((client_secret or "").strip()) <= 200:
        raise ValueError("Paste the client secret shown next to the client ID")
    _store(session, {"client_id": client_id, "client_secret": vault.protect(client_secret.strip())})


def disconnect(session):
    value = load(session)
    _store(session, {key: value[key] for key in ("client_id", "client_secret") if key in value})


class Gmail:
    def __init__(self, db, redirect_uri, client=None):
        self.db, self.redirect_uri = db, redirect_uri
        self.client = client or LazyClient(timeout=30)
        self._pending = {}  # state -> (verifier, created)
        self._access = (None, 0.0)

    def authorization_url(self):
        with self.db.Session() as session:
            value = load(session)
        if not value.get("client_id"):
            raise ValueError("Save your Google OAuth client ID and secret first")
        state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
        self._pending = {key: item for key, item in self._pending.items() if time.monotonic() - item[1] < 900}
        self._pending[state] = (verifier, time.monotonic())
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        return AUTH + "?" + urlencode({"client_id": value["client_id"], "redirect_uri": self.redirect_uri, "response_type": "code", "scope": f"{SCOPE} {SEND}",
                                       "access_type": "offline", "prompt": "consent", "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})

    def finish(self, state, code):
        pending = self._pending.pop(state or "", None)
        if not pending or time.monotonic() - pending[1] > 900:
            raise ValueError("This sign-in link expired or was not started here. Press Connect Gmail again.")
        with self.db.Session() as session:
            value = load(session)
        response = self.client.post(TOKEN, data={"code": code, "client_id": value["client_id"], "client_secret": vault.unprotect(value["client_secret"]),
                                                 "redirect_uri": self.redirect_uri, "grant_type": "authorization_code", "code_verifier": pending[0]})
        if response.status_code != 200:
            raise ValueError("Google refused the sign-in. Check your OAuth app's credentials, consent screen and test users.")
        tokens = response.json()
        if SCOPE not in tokens.get("scope", "").split() or not tokens.get("refresh_token"):
            raise ValueError("Google did not grant read-only Gmail access. Try again and allow access.")
        self._access = (tokens["access_token"], time.monotonic() + int(tokens.get("expires_in", 3600)) - 120)
        email = self.get("profile").get("emailAddress", "")
        with self.db.Session.begin() as session:
            stored = load(session)
            stored.update(refresh_token=vault.protect(tokens["refresh_token"]), email=email, connected_at=now(),
                          can_send=SEND in tokens.get("scope", "").split())  # the owner may allow reading only
            _store(session, stored)
        return email

    def _token(self):
        token, expires = self._access
        if token and time.monotonic() < expires:
            return token
        with self.db.Session() as session:
            value = load(session)
        if not value.get("refresh_token"):
            raise ValueError("Gmail is not connected")
        response = self.client.post(TOKEN, data={"client_id": value["client_id"], "client_secret": vault.unprotect(value["client_secret"]),
                                                 "refresh_token": vault.unprotect(value["refresh_token"]), "grant_type": "refresh_token"})
        if response.status_code != 200:
            raise ValueError("Gmail access was revoked or expired. Connect Gmail again.")
        data = response.json()
        self._access = (data["access_token"], time.monotonic() + int(data.get("expires_in", 3600)) - 120)
        return data["access_token"]

    def get(self, path, **params):
        response = self.client.get(f"{API}/{path}", params=params, headers={"Authorization": f"Bearer {self._token()}"})
        if response.status_code != 200:
            raise ValueError(f"Gmail returned {response.status_code}")
        return response.json()

    def send(self, to, subject, body, thread_id=None, reply_to_message_id=None):
        """Send one plain-text email from the connected address. A follow-up goes into the same thread."""
        from email.message import EmailMessage
        with self.db.Session() as session:
            value = load(session)
        if not value.get("can_send"):
            raise ValueError("Gmail can't send yet: connect Gmail again and allow sending email")
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = value.get("email", ""), to, subject
        if reply_to_message_id:
            message["In-Reply-To"] = message["References"] = reply_to_message_id
        message.set_content(body)
        payload = {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}
        if thread_id:
            payload["threadId"] = thread_id
        response = self.client.post(f"{API}/messages/send", json=payload, headers={"Authorization": f"Bearer {self._token()}"})
        if response.status_code != 200:
            raise ValueError(f"Gmail didn't send it ({response.status_code})")
        sent = response.json()
        try:  # the email is already sent: a failed look-up only costs the follow-up its In-Reply-To header, never a second copy
            headers = self.get(f"messages/{sent['id']}", format="metadata", metadataHeaders="Message-ID").get("payload", {}).get("headers", [])
        except (ValueError, httpx.HTTPError):
            headers = []
        message_id = next((item["value"] for item in headers if item["name"].lower() == "message-id"), "")
        return {"id": sent["id"], "thread_id": sent.get("threadId", ""), "message_id": message_id}

    def thread(self, thread_id):
        """The messages in a thread, oldest first: who sent each, its subject and the start of its text."""
        data = self.get(f"threads/{thread_id}", format="metadata", metadataHeaders=["From", "Subject", "Date", "Message-ID"])
        result = []
        for item in data.get("messages", []):
            headers = {header["name"].lower(): header["value"] for header in item.get("payload", {}).get("headers", [])}
            result.append({"id": item["id"], "from": headers.get("from", ""), "subject": headers.get("subject", ""), "date": headers.get("date", ""),
                           "message_id": headers.get("message-id", ""),
                           "snippet": html.unescape(item.get("snippet", "")), "labels": item.get("labelIds", [])})
        return result

    def search(self, query, limit=20):
        return [item["id"] for item in self.get("messages", q=query, maxResults=limit).get("messages", [])]

    def message(self, identifier):
        data = self.get(f"messages/{identifier}", format="full")
        headers = {item["name"].lower(): item["value"] for item in data.get("payload", {}).get("headers", [])}
        return {"id": data["id"], "thread_id": data.get("threadId", ""), "from": headers.get("from", ""), "subject": headers.get("subject", ""),
                "date": headers.get("date", ""), "snippet": html.unescape(data.get("snippet", "")), "body": body_text(data.get("payload", {}))[:20000]}


def _decode(part):
    raw = part.get("body", {}).get("data", "")
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8", "replace") if raw else ""


def body_text(payload):
    """Plain text of a message: text/plain parts, or text/html with tags removed."""
    plain, rich = [], []
    stack = [payload]
    while stack:
        part = stack.pop()
        stack.extend(reversed(part.get("parts", []) or []))
        kind = part.get("mimeType", "")
        if kind == "text/plain":
            plain.append(_decode(part))
        elif kind == "text/html":
            rich.append(_decode(part))
    if plain:
        return "\n".join(plain).strip()
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", "\n".join(rich))
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", text)
    return html.unescape(re.sub(r"<[^>]+>", " ", text)).strip()
