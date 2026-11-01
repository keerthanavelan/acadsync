"""Google login routes; only opaque session IDs are sent to the browser."""

import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from . import auth, google_auth
from .config import settings
from .db import Session, User, db

router = APIRouter(prefix="/api/auth/google")


@router.get("/status")
def status():
    google_auth.configured()
    return {"configured": True}


@router.get("/login")
def login(db: DBSession = Depends(db)):
    flow, url = google_auth.begin()
    response = RedirectResponse(url)
    auth.new_session(db, response, flow=flow)
    return response


def failed(reason):
    return RedirectResponse(
        settings().frontend_url + "/sources?auth=" + reason + "&provider=google"
    )


@router.get("/callback")
def callback(request: Request, db: DBSession = Depends(db)):
    try:
        session = auth.get_session(request, db)
    except HTTPException:
        return failed("expired")
    if not session.flow:
        return failed("invalid")
    flow = json.loads(auth.decrypt(session.flow))
    if flow.get("provider") != "google":
        return failed("invalid")
    # Atomic consume prevents parallel callbacks from exchanging the same code.
    consumed = db.execute(delete(Session).where(Session.id == session.id))
    db.commit()
    if not consumed.rowcount or not secrets.compare_digest(
        flow["state"], request.query_params.get("state", "")
    ):
        return failed("invalid")
    if request.query_params.get("error"):
        return failed("denied")
    code = request.query_params.get("code")
    if not code:
        return failed("invalid")
    try:
        tokens = google_auth.exchange(flow, code)
        identity = google_auth.profile(tokens["access_token"])
        subject = "google:" + identity["sub"]
        user = db.scalar(select(User).where(User.subject == subject))
        previous = json.loads(auth.decrypt(user.cache)) if user and user.cache else None
        encrypted = google_auth.store_tokens(tokens, previous)
    except HTTPException as exc:
        return failed("permissions" if exc.status_code in (403, 409) else "exchange")
    if not user:
        user = User(subject=subject, timezone=settings().default_timezone)
        db.add(user)
    user.name = identity.get("name") or "Student"
    user.email = identity["email"]
    user.cache = encrypted
    db.flush()
    response = RedirectResponse(settings().frontend_url + "/dashboard")
    auth.new_session(db, response, user.id)
    return response
