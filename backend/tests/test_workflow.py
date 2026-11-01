from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import SessionLocal, User, Event, Notice
from app.extraction import extract
from app.pipeline import ingest
from app import auth
from app.graph import Outlook
import pytest

HEADERS = {"Origin": "http://localhost:3000"}


def message(body, subject="CS301 Assignment", id="test-1"):
    return {
        "id": id,
        "subject": subject,
        "body": {"content": body},
        "receivedDateTime": "2026-10-31T09:00:00Z",
    }


def test_extraction_dates_and_noise():
    event = extract(
        message("Due November 5, 2026 at 5:00 pm. Venue: Room 201."), "Asia/Kolkata"
    )[0]
    assert event.start.day == 5 and event.start.hour == 17 and event.venue == "Room 201"
    assert event.confidence > 0.9
    ambiguous = extract(message("Due 05/11/2026."), "Asia/Kolkata")[0]
    assert ambiguous.start is None and ambiguous.warnings
    missing = extract(message("Assignment due soon."), "UTC")[0]
    assert missing.start is None
    assert (
        extract(message("Buy now discount assignment planner. Unsubscribe"), "UTC")
        == []
    )
    assert extract(message("Lunch today", subject="Lunch plans"), "UTC") == []


def test_deadline_changes_and_duplicates():
    with TestClient(app), SessionLocal() as db:
        user = User(subject="pipeline-user", timezone="UTC")
        db.add(user)
        db.flush()
        original = message("Due November 5, 2026 at 5 pm.")
        assert ingest(db, user, [original]) == 1
        assert ingest(db, user, [original]) == 0
        assert (
            ingest(db, user, [message("Due November 5, 2026 at 5 pm.", id="duplicate")])
            == 0
        )
        event = db.scalar(select(Event).where(Event.user_id == user.id))
        event.status = "approved"
        event.graph_id = "outlook-id"
        ingest(
            db,
            user,
            [
                message(
                    "Deadline extended from November 5, 2026 to November 8, 2026 at 5 pm.",
                    subject="Updated: CS301 Assignment",
                    id="updated",
                )
            ],
        )
        db.flush()
        rows = db.scalars(select(Event).where(Event.user_id == user.id)).all()
        assert len(rows) == 1 and rows[0].status == "pending"
        assert rows[0].data["start"].startswith("2026-11-08")
        assert rows[0].graph_id == "outlook-id"
        db.rollback()


def test_demo_review_isolation_deletion():
    with TestClient(app) as c:
        assert c.get("/api/events").status_code == 401
        assert c.post("/api/demo").status_code == 403
        assert c.post("/api/demo", headers=HEADERS).status_code == 200
        items = c.get("/api/events").json()
        assert len(items) == 6
        event = next(e for e in items if e["status"] == "pending")
        assert (
            c.post(
                "/api/events/" + event["id"] + "/approve", headers=HEADERS
            ).status_code
            == 200
        )
        assert (
            c.post(
                "/api/events/" + event["id"] + "/approve", headers=HEADERS
            ).status_code
            == 200
        )
        with TestClient(app) as other:
            other.post("/api/demo", headers=HEADERS)
            assert (
                other.post(
                    "/api/events/" + event["id"] + "/reject", headers=HEADERS
                ).status_code
                == 404
            )
        assert c.delete("/api/account", headers=HEADERS).status_code == 200
        assert c.get("/api/me").json()["authenticated"] is False
        assert c.get("/api/events").status_code == 401


def test_live_approval_failure_retry_and_update(monkeypatch):
    calls = []
    with TestClient(app) as c:
        c.post("/api/demo", headers=HEADERS)
        items = c.get("/api/events").json()
        e = next(e for e in items if e["status"] == "pending")
        with SessionLocal() as db:
            event = db.get(Event, e["id"])
            user = db.get(User, event.user_id)
            user.demo = False
            user.cache = "fake"
            db.commit()
        monkeypatch.setattr(auth, "access_token", lambda *args: "fake-token")
        from fastapi import HTTPException

        def failed(*args):
            raise HTTPException(502, "retry")

        monkeypatch.setattr(Outlook, "save_event", failed)
        assert (
            c.post("/api/events/" + e["id"] + "/approve", headers=HEADERS).status_code
            == 502
        )
        assert (
            next(x for x in c.get("/api/events").json() if x["id"] == e["id"])["status"]
            == "pending"
        )

        def save(self, event, transaction_id, graph_id):
            calls.append((transaction_id, graph_id))
            return {"id": "remote-event"}

        monkeypatch.setattr(Outlook, "save_event", save)
        assert (
            c.post("/api/events/" + e["id"] + "/approve", headers=HEADERS).status_code
            == 200
        )
        assert (
            c.post("/api/events/" + e["id"] + "/approve", headers=HEADERS).status_code
            == 200
        )
        assert calls == [(e["id"], None)]
        with SessionLocal() as db:
            event = db.get(Event, e["id"])
            event.status = "pending"
            db.commit()
        assert (
            c.post("/api/events/" + e["id"] + "/approve", headers=HEADERS).status_code
            == 200
        )
        assert calls[-1] == (e["id"], "remote-event")


def test_missing_date_and_bad_edit():
    with TestClient(app) as c:
        c.post("/api/demo", headers=HEADERS)
        e = next(e for e in c.get("/api/events").json() if e["status"] == "pending")
        e.update(start=None, end=None)
        assert (
            c.patch("/api/events/" + e["id"], json=e, headers=HEADERS).status_code
            == 200
        )
        assert (
            c.post("/api/events/" + e["id"] + "/approve", headers=HEADERS).status_code
            == 422
        )
        e.update(start="2026-11-05T12:00:00", end="2026-11-05T13:00:00")
        assert (
            c.patch("/api/events/" + e["id"], json=e, headers=HEADERS).status_code
            == 422
        )
        assert (
            c.patch(
                "/api/settings", json={"timezone": "Invalid/Zone"}, headers=HEADERS
            ).status_code
            == 422
        )


def test_oauth_cookie_encryption_and_callback_replay(monkeypatch):
    from cryptography.fernet import Fernet
    from app.config import settings

    monkeypatch.setattr(settings(), "credential_key", Fernet.generate_key().decode())

    class FakeMSAL:
        def initiate_auth_code_flow(self, *args, **kwargs):
            return {
                "auth_uri": "https://login.microsoftonline.com/authorize",
                "state": "expected-state",
                "code_verifier": "secret-verifier",
            }

        def acquire_token_by_auth_code_flow(self, flow, response):
            assert flow["code_verifier"] == "secret-verifier"
            if response.get("state") != flow["state"]:
                raise ValueError("state mismatch")
            return {
                "access_token": "secret-access-token",
                "id_token_claims": {"tid": "tenant", "oid": "user", "sub": "subject"},
            }

    monkeypatch.setattr(auth, "client", lambda *args: FakeMSAL())
    monkeypatch.setattr(
        Outlook,
        "profile",
        lambda self: {"displayName": "Test Student", "mail": "student@example.edu"},
    )
    with TestClient(app) as c:
        response = c.get("/api/auth/login", follow_redirects=False)
        assert response.status_code == 307
        assert "httponly" in response.headers["set-cookie"].lower()
        assert "secret-verifier" not in response.headers["set-cookie"]
        denied = c.get(
            "/api/auth/callback?state=wrong&code=code", follow_redirects=False
        )
        assert "auth=invalid" in denied.headers["location"]
        assert (
            c.get("/api/auth/callback?state=expected-state&code=code").status_code
            == 401
        )
        c.get("/api/auth/login", follow_redirects=False)
        success = c.get(
            "/api/auth/callback?state=expected-state&code=code", follow_redirects=False
        )
        assert success.headers["location"].endswith("/dashboard")
        assert c.get("/api/me").json()["connected"] is True
        assert (
            c.get("/api/auth/callback?state=expected-state&code=code").status_code
            == 400
        )
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.subject == "tenant:user"))
            assert user.cache and not user.cache.startswith("{")


def test_graph_pagination_and_safe_urls(monkeypatch):
    import httpx
    from fastapi import HTTPException

    calls = []

    def request(method, url, **kwargs):
        calls.append(url)
        return httpx.Response(
            200,
            json={
                "value": [{"id": str(len(calls))}],
                **(
                    {"@odata.nextLink": "https://graph.microsoft.com/v1.0/next"}
                    if len(calls) == 1
                    else {"@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta"}
                ),
            },
        )

    monkeypatch.setattr(httpx, "request", request)
    rows, cursor = Outlook("private-token").messages()
    assert len(rows) == 2 and cursor.endswith("/delta")
    with pytest.raises(HTTPException):
        Outlook("private-token").messages("https://attacker.example/collect")
    assert len(calls) == 2


def test_same_instant_duplicate_key():
    from app.extraction import fingerprint

    assert fingerprint("CS assignment", "2026-11-05T17:00:00+05:30") == fingerprint(
        "Reminder: CS assignment", "2026-11-05T11:30:00Z"
    )
