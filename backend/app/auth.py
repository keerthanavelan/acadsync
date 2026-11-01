import hashlib
import json
import secrets
from datetime import timedelta
from cryptography.fernet import Fernet
from fastapi import HTTPException, Request
import msal
from .config import settings
from .db import Session, User, now

SCOPES = ["User.Read", "Mail.Read", "Calendars.ReadWrite"]
COOKIE = "academicflow_session"


def cipher():
    key = settings().credential_key
    if not key:
        raise HTTPException(
            503, "Set CREDENTIAL_KEY on the backend before connecting an account."
        )
    return Fernet(key.encode())


def encrypt(value):
    return cipher().encrypt(value.encode()).decode()


def decrypt(value):
    return cipher().decrypt(value.encode()).decode()


def client(cache=None):
    s = settings()
    if not s.microsoft_client_id or not s.microsoft_client_secret:
        raise HTTPException(
            503,
            "Outlook setup is incomplete. Configure MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET on the server.",
        )
    return msal.ConfidentialClientApplication(
        s.microsoft_client_id,
        authority=f"https://login.microsoftonline.com/{s.microsoft_tenant_id}",
        client_credential=s.microsoft_client_secret,
        token_cache=cache,
    )


def session_key(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def new_session(db, response, user_id=None, flow=None):
    raw = secrets.token_urlsafe(32)
    db.add(
        Session(
            id=session_key(raw),
            user_id=user_id,
            flow=encrypt(json.dumps(flow)) if flow else None,
            expires=(
                now() + timedelta(hours=12)
                if user_id
                else now() + timedelta(minutes=10)
            ),
        )
    )
    db.commit()
    response.set_cookie(
        COOKIE,
        raw,
        httponly=True,
        secure=settings().cookie_secure,
        samesite="lax",
        max_age=43200 if user_id else 600,
        path="/",
    )


def get_session(request, db):
    raw = request.cookies.get(COOKIE, "")
    session = db.get(Session, session_key(raw)) if raw else None
    if not session or session.expires.replace(tzinfo=now().tzinfo) < now():
        raise HTTPException(401, "Please sign in to continue.")
    return session


def current_user(request: Request, db):
    session = get_session(request, db)
    user = db.get(User, session.user_id) if session.user_id else None
    if not user:
        raise HTTPException(401, "Please sign in to continue.")
    return user


def access_token(user, db):
    if not user.cache:
        raise HTTPException(409, "Connect Outlook to continue.")
    cache = msal.SerializableTokenCache()
    cache.deserialize(decrypt(user.cache))
    app = client(cache)
    accounts = app.get_accounts()
    result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
    if not result or "access_token" not in result:
        raise HTTPException(
            401, "Your Microsoft session expired or needs consent. Reconnect Outlook."
        )
    if cache.has_state_changed:
        user.cache = encrypt(cache.serialize())
        db.commit()
    return result["access_token"]
