import base64
import hashlib
import json
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import auth, google_auth
from app.config import settings
from app.db import SessionLocal, User, Event
from app.google import Google, normalize, text_body
from app.main import app

HEADERS = {"Origin": "http://localhost:3000"}


@pytest.fixture
def google_config(monkeypatch):
    monkeypatch.setattr(settings(), "credential_key", Fernet.generate_key().decode())
    monkeypatch.setattr(
        settings(), "google_client_id", "test-client.apps.googleusercontent.com"
    )
    monkeypatch.setattr(settings(), "google_client_secret", "test-client-secret")


def start(c):
    response = c.get("/api/auth/google/login", follow_redirects=False)
    assert response.status_code == 307
    return parse_qs(urlparse(response.headers["location"]).query)


def token_result(**changes):
    return {
        "access_token": "private-access-token",
        "refresh_token": "private-refresh-token",
        "expires_in": 3600,
        "scope": " ".join(google_auth.SCOPES),
        **changes,
    }


def mail(
    id="mail1",
    title="CS301 Assignment",
    text="Assignment due November 10, 2026 at 5:00 pm. Venue: Lab 3.",
):
    return {
        "id": id,
        "threadId": "thread1",
        "internalDate": "1793500000000",
        "payload": {
            "mimeType": "text/plain",
            "headers": [{"name": "Subject", "value": title}],
            "body": {
                "data": base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")
            },
        },
    }


def test_google_state_pkce_denial_and_replay(google_config, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid callback must not contact Google's token endpoint")

    monkeypatch.setattr(httpx, "post", unexpected)
    with TestClient(app) as c:
        query = start(c)
        assert query["redirect_uri"] == [
            "http://localhost:3000/api/auth/google/callback"
        ]
        assert query["code_challenge_method"] == ["S256"]
        assert query["access_type"] == ["offline"]
        assert "client_secret" not in query
        response = c.get(
            "/api/auth/google/callback?state=wrong&code=bad", follow_redirects=False
        )
        assert "auth=invalid" in response.headers["location"]
        replay = c.get(
            "/api/auth/google/callback",
            params={"state": query["state"][0], "code": "code"},
            follow_redirects=False,
        )
        assert "auth=expired" in replay.headers["location"]
        query = start(c)
        denied = c.get(
            "/api/auth/google/callback",
            params={"state": query["state"][0], "error": "access_denied"},
            follow_redirects=False,
        )
        assert "auth=denied" in denied.headers["location"]
        assert c.get("/api/me").json()["authenticated"] is False


def test_google_end_to_end_mocked(google_config, monkeypatch):
    calls = []
    challenge = []
    calendar_store = {}

    def post(url, data, **kwargs):
        assert url == google_auth.TOKEN_URL
        assert data["client_secret"] == "test-client-secret"
        actual = (
            base64.urlsafe_b64encode(
                hashlib.sha256(data["code_verifier"].encode()).digest()
            )
            .rstrip(b"=")
            .decode()
        )
        assert actual == challenge[0]
        return httpx.Response(200, json=token_result())

    def get(url, headers, **kwargs):
        assert url == "https://openidconnect.googleapis.com/v1/userinfo"
        return httpx.Response(
            200,
            json={
                "sub": "google-student",
                "email": "student@gmail.com",
                "email_verified": True,
                "name": "Student",
            },
        )

    def request(method, url, **kwargs):
        calls.append((method, url))
        assert kwargs["headers"]["Authorization"] == "Bearer private-access-token"
        if url.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "mail1"}]})
        if url.endswith("/messages/mail1"):
            return httpx.Response(200, json=mail())
        if method == "POST" and url.endswith("/events"):
            payload = kwargs["json"]
            assert payload["summary"] == "CS301 Assignment"
            assert payload["start"]["dateTime"].startswith("2026-11-10T17:00")
            assert "attendees" not in payload
            calendar_store[payload["id"]] = payload
            return httpx.Response(200, json={"id": payload["id"]})
        pytest.fail(f"Unexpected Google request: {method} {url}")

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(httpx, "get", get)
    monkeypatch.setattr(httpx, "request", request)
    with TestClient(app) as c:
        query = start(c)
        challenge.append(query["code_challenge"][0])
        response = c.get(
            "/api/auth/google/callback",
            params={"state": query["state"][0], "code": "valid-code"},
            follow_redirects=False,
        )
        assert response.headers["location"].endswith("/dashboard")
        profile = c.get("/api/me").json()
        assert profile["provider"] == "google" and profile["connected"]
        assert "token" not in json.dumps(profile)
        with SessionLocal() as db:
            user = db.scalar(
                select(User).where(User.subject == "google:google-student")
            )
            assert "private-" not in user.cache
            assert (
                json.loads(auth.decrypt(user.cache))["refresh_token"]
                == "private-refresh-token"
            )
        assert c.post("/api/sync", headers=HEADERS).json()["added"] == 1
        rows = c.get("/api/events").json()
        assert len(rows) == 1 and rows[0]["source"] == "Gmail"
        assert c.get("/api/notices").json()[0]["source"] == "Gmail"
        id = rows[0]["id"]
        assert c.post(f"/api/events/{id}/approve", headers=HEADERS).status_code == 200
        assert c.post(f"/api/events/{id}/approve", headers=HEADERS).status_code == 200
        assert len(calendar_store) == 1
        c.post("/api/reset-sync", headers=HEADERS)
        assert c.post("/api/sync", headers=HEADERS).json()["added"] == 0
        assert len(c.get("/api/events").json()) == 1
        assert c.post("/api/disconnect", headers=HEADERS).status_code == 200
        assert c.get("/api/me").json()["connected"] is False
        assert c.post("/api/sync", headers=HEADERS).status_code == 409
        assert c.delete("/api/account", headers=HEADERS).status_code == 200
        assert c.get("/api/me").json()["authenticated"] is False


def test_google_refresh_preserves_refresh_token(google_config, monkeypatch):
    user = SimpleNamespace(
        cache=auth.encrypt(
            json.dumps(
                {
                    "access_token": "old",
                    "refresh_token": "keep-me",
                    "expires_at": 0,
                    "scope": " ".join(google_auth.SCOPES),
                }
            )
        )
    )
    committed = []
    db = SimpleNamespace(commit=lambda: committed.append(True))

    def post(url, data, **kwargs):
        assert data["refresh_token"] == "keep-me"
        return httpx.Response(200, json={"access_token": "new", "expires_in": 3600})

    monkeypatch.setattr(httpx, "post", post)
    assert google_auth.access_token(user, db) == "new"
    assert json.loads(auth.decrypt(user.cache))["refresh_token"] == "keep-me"
    assert committed == [True]
    assert google_auth.access_token(user, db) == "new"
    assert committed == [True]


def test_missing_scopes_and_revoked_refresh(google_config, monkeypatch):
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **k: httpx.Response(200, json=token_result(scope="openid email")),
    )
    with pytest.raises(HTTPException) as exc:
        google_auth.exchange({"verifier": "v"}, "code")
    assert exc.value.status_code == 403
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **k: httpx.Response(400, json={"error": "invalid_grant"}),
    )
    with pytest.raises(HTTPException) as exc:
        google_auth.token_request(
            {"grant_type": "refresh_token", "refresh_token": "revoked"}
        )
    assert exc.value.status_code == 401


def test_gmail_mime_and_pagination(monkeypatch):
    part = mail()["payload"]
    message = mail()
    message["payload"] = {
        "mimeType": "multipart/alternative",
        "headers": part["headers"],
        "parts": [
            {
                "mimeType": "text/html",
                "body": {
                    "data": base64.urlsafe_b64encode(b"<p>HTML duplicate</p>").decode()
                },
            },
            part,
            {
                "mimeType": "text/plain",
                "filename": "private.txt",
                "body": {"data": base64.urlsafe_b64encode(b"attachment").decode()},
            },
        ],
    }
    assert "HTML duplicate" not in normalize(message)["body"]["content"]
    assert "attachment" not in text_body(message["payload"])
    seen = []

    def request(self, method, service, path, **kwargs):
        if path == "/messages":
            seen.append(kwargs["params"])
            return {
                "messages": [{"id": "mail1"}],
                **({"nextPageToken": "page2"} if len(seen) == 1 else {}),
            }
        return mail()

    monkeypatch.setattr(Google, "request", request)
    google = Google("token")
    rows, cursor = google.messages()
    assert rows[0]["source"] == "Gmail"
    assert json.loads(cursor)["page"] == "page2"
    rows, cursor = google.messages(cursor)
    assert seen[0]["q"] == seen[1]["q"]
    assert seen[1]["pageToken"] == "page2"
    assert "page" not in json.loads(cursor)


def test_calendar_all_day_conflict_recovery_and_update(monkeypatch):
    calls = []
    event = SimpleNamespace(
        id="local-event",
        data={
            "title": "Exam",
            "description": "Review",
            "venue": "Lab",
            "timezone": "Asia/Kolkata",
            "all_day": True,
            "start": "2026-11-10T00:00:00+05:30",
            "end": "2026-11-11T00:00:00+05:30",
        },
    )

    def request(self, method, service, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "POST":
            return {"_status": 409}
        if method == "GET":
            return {"extendedProperties": {"private": {"acadsync_event": event.id}}}
        return {"id": "saved"}

    monkeypatch.setattr(Google, "request", request)
    assert Google("t").save_event(event, event.id)["id"] == "saved"
    payload = calls[0][2]["json"]
    assert payload["start"] == {"date": "2026-11-10"} and payload["end"] == {
        "date": "2026-11-11"
    }
    assert len(payload["id"]) == 64
    assert [c[0] for c in calls] == ["POST", "GET", "PATCH"]
    calls.clear()
    Google("t").save_event(event, event.id, "existing-remote")
    assert calls[0][0] == "PATCH" and calls[0][1].endswith("/existing-remote")


def test_google_failure_leaves_suggestion_pending(google_config, monkeypatch):
    from app import google_auth

    with TestClient(app) as c:
        c.post("/api/demo", headers=HEADERS)
        event = next(e for e in c.get("/api/events").json() if e["status"] == "pending")
        with SessionLocal() as db:
            row = db.get(Event, event["id"])
            user = db.get(User, row.user_id)
            user.subject = "google:failure-test"
            user.demo = False
            user.cache = "fake"
            db.commit()
        monkeypatch.setattr(google_auth, "access_token", lambda *a: "token")

        def fail(*a, **k):
            raise HTTPException(502, "Google temporarily unavailable")

        monkeypatch.setattr(Google, "save_event", fail)
        assert (
            c.post(
                "/api/events/" + event["id"] + "/approve", headers=HEADERS
            ).status_code
            == 502
        )
        assert (
            next(e for e in c.get("/api/events").json() if e["id"] == event["id"])[
                "status"
            ]
            == "pending"
        )
