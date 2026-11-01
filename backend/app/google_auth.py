"""Google server-side authorization code flow with PKCE and encrypted tokens.

Identity is fetched from Google's authenticated userinfo endpoint. We do not
trust unverified JWT claims or identity fields supplied by the browser.
"""

import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from . import auth
from .config import settings

API_SCOPES = {
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events.owned",
}
SCOPES = ["openid", "email", "profile", *sorted(API_SCOPES)]
TOKEN_URL = "https://oauth2.googleapis.com/token"


def configured():
    s = settings()
    if not all([s.google_client_id, s.google_client_secret, s.credential_key]):
        raise HTTPException(
            503,
            "Gmail needs server setup: add GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and CREDENTIAL_KEY to backend/.env, then restart the backend.",
        )
    try:
        auth.cipher()
    except (ValueError, TypeError):
        raise HTTPException(
            503,
            "CREDENTIAL_KEY is invalid. Generate a Fernet key using the setup instructions.",
        )


def begin():
    configured()
    s = settings()
    verifier = secrets.token_urlsafe(64)
    flow = {
        "provider": "google",
        "state": secrets.token_urlsafe(32),
        "verifier": verifier,
    }
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": s.google_client_id,
            "redirect_uri": s.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "state": flow["state"],
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent select_account",
        }
    )
    return flow, url


def token_request(data):
    try:
        response = httpx.post(
            TOKEN_URL,
            data={
                "client_id": settings().google_client_id,
                "client_secret": settings().google_client_secret,
                **data,
            },
            timeout=20,
        )
    except httpx.RequestError:
        raise HTTPException(502, "Google could not be reached. Please try again.")
    if response.is_error:
        # Never echo Google responses containing codes or token information.
        if response.status_code == 400:
            raise HTTPException(
                401,
                "Google authorization expired or was revoked. Reconnect Gmail and grant both requested permissions.",
            )
        raise HTTPException(
            502,
            "Google sign-in could not be completed. Check your Google client settings and try again.",
        )
    result = response.json()
    if not result.get("access_token"):
        raise HTTPException(502, "Google did not return a usable access token.")
    result["expires_at"] = time.time() + int(result.get("expires_in", 3600))
    return result


def exchange(flow, code):
    result = token_request(
        {
            "code": code,
            "code_verifier": flow["verifier"],
            "redirect_uri": settings().google_redirect_uri,
            "grant_type": "authorization_code",
        }
    )
    if not API_SCOPES.issubset(set(result.get("scope", "").split())):
        raise HTTPException(
            403,
            "Allow Gmail read access and Google Calendar event access, then reconnect.",
        )
    return result


def profile(token):
    try:
        response = httpx.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
    except httpx.RequestError:
        raise HTTPException(
            502, "Google profile could not be retrieved. Try connecting again."
        )
    if response.is_error:
        raise HTTPException(
            401, "Google could not verify this account. Reconnect Gmail."
        )
    data = response.json()
    if (
        not data.get("sub")
        or not data.get("email")
        or data.get("email_verified") is not True
    ):
        raise HTTPException(401, "A verified Google email account is required.")
    return data


def store_tokens(result, previous=None):
    # Store only what refresh needs, not the ID token or authorization response.
    refresh = result.get("refresh_token") or (previous or {}).get("refresh_token")
    if not refresh:
        raise HTTPException(
            409,
            "Google did not grant offline access. Remove AcadSync in Google account permissions, then reconnect.",
        )
    return auth.encrypt(
        json.dumps(
            {
                "access_token": result["access_token"],
                "refresh_token": refresh,
                "expires_at": result["expires_at"],
                "scope": result.get("scope", (previous or {}).get("scope", "")),
            }
        )
    )


def access_token(user, db):
    if not user.cache:
        raise HTTPException(409, "Connect Gmail to continue.")
    credentials = json.loads(auth.decrypt(user.cache))
    if credentials.get("expires_at", 0) <= time.time() + 60:
        if not credentials.get("refresh_token"):
            raise HTTPException(401, "Reconnect Gmail to renew access.")
        result = token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": credentials["refresh_token"],
            }
        )
        if "scope" in result and not API_SCOPES.issubset(set(result["scope"].split())):
            raise HTTPException(
                403,
                "Google permissions changed. Reconnect Gmail and grant both permissions.",
            )
        user.cache = store_tokens(result, credentials)
        db.commit()
        return result["access_token"]
    return credentials["access_token"]
