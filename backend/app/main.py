import json
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.orm import Session as DBSession
import msal
from .config import settings
from .db import Base, engine, db, User, Session, Event, Notice, now, uid
from . import auth, google_auth
from .google import Google
from .google_routes import router as google_router
from .graph import Outlook
from .pipeline import ingest
from .schemas import EventDetails
from .extraction import fingerprint
from .demo import messages


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="AcadSync API", lifespan=lifespan)
app.include_router(google_router)


def account_token(user, db):
    return (
        google_auth.access_token(user, db)
        if user.provider == "google"
        else auth.access_token(user, db)
    )


def account_adapter(user, token):
    return Google(token) if user.provider == "google" else Outlook(token)


@app.middleware("http")
async def security(request: Request, call_next):
    if request.method in ("POST", "PATCH", "DELETE", "PUT") and request.headers.get(
        "origin"
    ) != settings().frontend_url.rstrip("/"):
        return JSONResponse(
            {"detail": "Request origin is not allowed."}, status_code=403
        )
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/auth/status")
def auth_status():
    s = settings()
    if not all([s.microsoft_client_id, s.microsoft_client_secret, s.credential_key]):
        raise HTTPException(
            503,
            "Outlook needs server setup first: add your Microsoft app ID, client secret and encryption key to backend/.env. You can explore the demo now.",
        )
    return {"configured": True}


@app.get("/api/me")
def me(request: Request, db: DBSession = Depends(db)):
    try:
        user = auth.current_user(request, db)
    except HTTPException as e:
        if e.status_code != 401:
            raise
        return {"authenticated": False, "demo_enabled": settings().demo_enabled}
    return {
        "authenticated": True,
        "name": user.name,
        "email": user.email,
        "demo": user.demo,
        "provider": user.provider,
        "timezone": user.timezone,
        "connected": bool(user.cache),
        "last_sync": user.last_sync,
        "demo_enabled": settings().demo_enabled,
    }


@app.post("/api/demo")
def demo(request: Request, db: DBSession = Depends(db)):
    if not settings().demo_enabled:
        raise HTTPException(404, "Demo mode is disabled.")
    try:
        old = auth.get_session(request, db)
        if old.user_id:
            existing = db.get(User, old.user_id)
            if existing and not existing.demo:
                raise HTTPException(409, "Sign out before entering demo mode.")
            if existing:
                return {"ok": True}
    except HTTPException as e:
        if e.status_code != 401:
            raise
    user = User(
        subject="demo-" + uid(),
        name="Alex Morgan",
        email="alex.morgan@university.edu",
        demo=True,
        timezone=settings().default_timezone,
    )
    db.add(user)
    db.flush()
    ingest(db, user, messages())
    events = db.scalars(select(Event).where(Event.user_id == user.id)).all()
    for event in events[:3]:
        event.status = "approved"
    user.last_sync = now()
    response = JSONResponse({"ok": True})
    auth.new_session(db, response, user.id)
    return response


@app.get("/api/auth/login")
def login(request: Request, db: DBSession = Depends(db)):
    flow = auth.client().initiate_auth_code_flow(
        auth.SCOPES, redirect_uri=settings().redirect_uri, prompt="select_account"
    )
    response = RedirectResponse(flow["auth_uri"])
    auth.new_session(db, response, flow=flow)
    return response


@app.get("/api/auth/callback")
def callback(request: Request, db: DBSession = Depends(db)):
    session = auth.get_session(request, db)
    if not session.flow:
        raise HTTPException(400, "This sign-in attempt has already been used.")
    flow = json.loads(auth.decrypt(session.flow))
    if flow.get("provider") == "google":
        raise HTTPException(
            400, "This sign-in attempt belongs to Google. Start sign-in again."
        )
    db.delete(session)
    db.commit()  # single use, including denied consent
    cache = msal.SerializableTokenCache()
    try:
        result = auth.client(cache).acquire_token_by_auth_code_flow(
            flow, dict(request.query_params)
        )
    except ValueError:
        return RedirectResponse(settings().frontend_url + "/sources?auth=invalid")
    if "access_token" not in result:
        return RedirectResponse(settings().frontend_url + "/sources?auth=denied")
    claims = result.get("id_token_claims", {})
    subject = f"{claims.get('tid')}:{claims.get('oid') or claims.get('sub')}"
    if not claims.get("sub"):
        raise HTTPException(400, "Microsoft did not return a valid identity.")
    profile = Outlook(result["access_token"]).profile()
    user = db.scalar(select(User).where(User.subject == subject))
    if not user:
        user = User(subject=subject, timezone=settings().default_timezone)
        db.add(user)
    user.name = profile.get("displayName") or "Student"
    user.email = profile.get("mail") or profile.get("userPrincipalName", "")
    user.cache = auth.encrypt(cache.serialize())
    db.flush()
    response = RedirectResponse(settings().frontend_url + "/dashboard")
    auth.new_session(db, response, user.id)
    return response


@app.get("/api/events")
def events(request: Request, db: DBSession = Depends(db)):
    user = auth.current_user(request, db)
    return [
        {"id": e.id, "status": e.status, **e.data, "calendar_synced": bool(e.graph_id)}
        for e in db.scalars(
            select(Event)
            .where(Event.user_id == user.id)
            .order_by(Event.created_at.desc())
        )
    ]


@app.get("/api/notices")
def notices(request: Request, db: DBSession = Depends(db)):
    user = auth.current_user(request, db)
    return [
        {
            "id": n.id,
            "title": n.title,
            "received_at": n.received_at,
            "result": n.result,
            "source": "Gmail" if user.provider == "google" else "Outlook",
        }
        for n in db.scalars(
            select(Notice)
            .where(Notice.user_id == user.id)
            .order_by(Notice.received_at.desc())
            .limit(30)
        )
    ]


@app.post("/api/sync")
def sync(request: Request, db: DBSession = Depends(db)):
    user = auth.current_user(request, db)
    # Serialize per-account sync and approval on PostgreSQL.
    token = None if user.demo else account_token(user, db)
    user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    if (
        user.last_sync
        and (now() - user.last_sync.replace(tzinfo=now().tzinfo)).total_seconds() < 5
    ):
        return {"added": 0, "message": "Already up to date."}
    rows, cursor = (
        (messages(), None)
        if user.demo
        else account_adapter(user, token).messages(user.cursor)
    )
    added = ingest(db, user, rows)
    user.cursor = cursor
    user.last_sync = now()
    db.commit()
    more = (
        not user.demo
        and user.provider == "google"
        and bool(json.loads(cursor or "{}").get("page"))
    )
    return {
        "added": added,
        "more": more,
        "message": f"Sync complete. {added} new suggestions."
        + (" More emails remain; click Sync now again." if more else ""),
    }


def owned_event(request, db, id):
    user = auth.current_user(request, db)
    event = db.scalar(
        select(Event).where(Event.id == id, Event.user_id == user.id).with_for_update()
    )
    if not event:
        raise HTTPException(404, "Event not found.")
    return user, event


@app.patch("/api/events/{id}")
def edit(id: str, data: EventDetails, request: Request, db: DBSession = Depends(db)):
    user, event = owned_event(request, db, id)
    if event.status != "pending":
        raise HTTPException(409, "Only pending suggestions can be edited.")
    key = fingerprint(data.title, data.start.isoformat() if data.start else None)
    duplicate = db.scalar(
        select(Event).where(
            Event.user_id == user.id, Event.fingerprint == key, Event.id != id
        )
    )
    if duplicate:
        raise HTTPException(409, "This event already exists.")
    updated = data.model_dump(mode="json")
    updated["source"] = event.data.get("source", "Outlook")
    updated["source_url"] = event.data.get("source_url", "")
    event.data = updated
    event.fingerprint = key
    db.commit()
    return {"ok": True}


@app.post("/api/events/{id}/approve")
def approve(id: str, request: Request, db: DBSession = Depends(db)):
    user = auth.current_user(request, db)
    token = None if user.demo else account_token(user, db)
    user, event = owned_event(request, db, id)
    if event.status == "approved":
        return {"ok": True}
    if event.status == "rejected":
        raise HTTPException(409, "Rejected suggestions cannot be approved.")
    data = EventDetails(**event.data)
    if not data.start or not data.end:
        raise HTTPException(422, "Set a start and end date before approving.")
    if data.all_day:
        start = data.start.astimezone(ZoneInfo(data.timezone))
        end = data.end.astimezone(ZoneInfo(data.timezone))
        if any(
            [start.hour, start.minute, start.second, end.hour, end.minute, end.second]
        ):
            raise HTTPException(
                422,
                "All-day events must start and end at midnight in the selected timezone.",
            )
    if not user.demo:
        result = account_adapter(user, token).save_event(
            event, event.id, event.graph_id
        )
        event.graph_id = result.get("id") or event.graph_id
    event.status = "approved"
    db.commit()
    return {"ok": True}


@app.post("/api/events/{id}/reject")
def reject(id: str, request: Request, db: DBSession = Depends(db)):
    _, event = owned_event(request, db, id)
    if event.status != "pending":
        raise HTTPException(409, "Only pending suggestions can be rejected.")
    event.status = "rejected"
    db.commit()
    return {"ok": True}


class Preferences(BaseModel):
    timezone: str


@app.patch("/api/settings")
def preferences(data: Preferences, request: Request, db: DBSession = Depends(db)):
    try:
        ZoneInfo(data.timezone)
    except Exception:
        raise HTTPException(422, "Enter a valid IANA timezone.")
    user = auth.current_user(request, db)
    user.timezone = data.timezone
    db.commit()
    return {"ok": True}


@app.post("/api/reset-sync")
def reset_sync(request: Request, db: DBSession = Depends(db)):
    user = auth.current_user(request, db)
    user.cursor = None
    user.last_sync = None
    db.commit()
    return {"ok": True}


@app.post("/api/disconnect")
def disconnect(request: Request, db: DBSession = Depends(db)):
    user = auth.current_user(request, db)
    user.cache = None
    user.cursor = None
    db.commit()
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request, db: DBSession = Depends(db)):
    session = auth.get_session(request, db)
    db.delete(session)
    db.commit()
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.COOKIE)
    return response


@app.delete("/api/account")
def delete_account(request: Request, db: DBSession = Depends(db)):
    user = auth.current_user(request, db)
    for model in [Event, Notice, Session]:
        db.execute(delete(model).where(model.user_id == user.id))
    db.delete(user)
    db.commit()
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.COOKIE)
    return response
