"""Gmail message normalization and Google Calendar adapter."""

import base64
import hashlib
import html
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.message import Message
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException


def text_body(part):
    """Prefer text/plain in multipart alternatives; never retrieve attachments."""
    if part.get("filename") or part.get("mimeType", "").startswith("message/"):
        return ""
    children = part.get("parts", [])
    if children:
        if part.get("mimeType") == "multipart/alternative":
            children = sorted(
                children, key=lambda child: child.get("mimeType") != "text/plain"
            )
            return next((body for child in children if (body := text_body(child))), "")
        return "\n".join(filter(None, (text_body(child) for child in children)))
    kind = part.get("mimeType", "")
    data = part.get("body", {}).get("data", "")
    if kind not in ("text/plain", "text/html") or not data:
        return ""
    mime = Message()
    for header in part.get("headers", []):
        if header["name"].lower() == "content-type":
            mime["Content-Type"] = header["value"]
    try:
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
        text = raw.decode(mime.get_content_charset() or "utf-8", errors="replace")
    except (ValueError, LookupError):
        return ""
    return html.escape(text) if kind == "text/plain" else text


def normalize(message):
    headers = {
        h["name"].lower(): h["value"]
        for h in message.get("payload", {}).get("headers", [])
    }
    return {
        "id": message["id"],
        "subject": headers.get("subject", ""),
        "body": {"content": text_body(message.get("payload", {}))},
        "receivedDateTime": datetime.fromtimestamp(
            int(message["internalDate"]) / 1000, timezone.utc
        ).isoformat(),
        "webLink": "https://mail.google.com/mail/u/0/#inbox/"
        + quote(message.get("threadId", message["id"]), safe=""),
        "source": "Gmail",
    }


class Google:
    def __init__(self, token):
        self.token = token

    def request(self, method, service, path, *, allowed=(), **kwargs):
        roots = {
            "gmail": "https://gmail.googleapis.com/gmail/v1/users/me",
            "calendar": "https://www.googleapis.com/calendar/v3/calendars/primary",
        }
        url = roots[service] + path
        for attempt in range(3):
            try:
                response = httpx.request(
                    method,
                    url,
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=15,
                    **kwargs,
                )
            except httpx.RequestError:
                if attempt < 2:
                    continue
                raise HTTPException(
                    502,
                    "Google could not be reached. Retry; approved calendar writes are safe to retry.",
                )
            if response.status_code not in (429, 500, 502, 503, 504):
                break
            if attempt < 2:
                retry = response.headers.get("Retry-After", "1")
                time.sleep(min(int(retry) if retry.isdigit() else 1, 3))
        if response.status_code in allowed:
            return {"_status": response.status_code}
        if response.status_code == 401:
            raise HTTPException(
                401, "Google access expired or was revoked. Reconnect Gmail."
            )
        if response.status_code == 403:
            raise HTTPException(
                403,
                "Google denied access. Enable Gmail API and Google Calendar API, add your account as a test user, and reconnect with both permissions.",
            )
        if response.status_code == 400:
            raise HTTPException(
                409,
                "Google rejected this request. For sync errors, use Reset sync in Settings; for calendar errors, check the event dates.",
            )
        if response.is_error:
            raise HTTPException(
                502, "Google could not complete the request. Please retry."
            )
        return response.json() if response.content else {}

    def messages(self, cursor=None):
        state = json.loads(cursor) if cursor else {}
        upper = int(state.get("until", time.time()))
        lower = int(state.get("since", upper - 30 * 86400))
        params = {"q": f"in:inbox after:{lower} before:{upper + 1}", "maxResults": 50}
        if state.get("page"):
            params["pageToken"] = state["page"]
        page = self.request("GET", "gmail", "/messages", params=params)

        def fetch(item):
            data = self.request(
                "GET",
                "gmail",
                "/messages/" + quote(item["id"], safe=""),
                params={"format": "full"},
                allowed=(404,),
            )
            return None if data.get("_status") == 404 else normalize(data)

        # A bounded page and a small worker pool avoid an unbounded mailbox scan.
        with ThreadPoolExecutor(max_workers=5) as pool:
            messages = list(filter(None, pool.map(fetch, page.get("messages", []))))
        messages.sort(key=lambda row: row["receivedDateTime"])
        next_state = (
            {"since": lower, "until": upper, "page": page["nextPageToken"]}
            if page.get("nextPageToken")
            else {"since": upper - 120}
        )
        return messages, json.dumps(next_state)

    def save_event(self, event, transaction_id, graph_id=None):
        data = event.data
        zone = ZoneInfo(data["timezone"])
        payload = {
            "summary": data["title"],
            "description": data["description"],
            "location": data["venue"],
            "extendedProperties": {"private": {"acadsync_event": event.id}},
        }
        for key in ("start", "end"):
            value = datetime.fromisoformat(data[key]).astimezone(zone)
            payload[key] = (
                {"date": value.date().isoformat()}
                if data["all_day"]
                else {"dateTime": value.isoformat(), "timeZone": data["timezone"]}
            )
        if graph_id:
            return self.request(
                "PATCH",
                "calendar",
                "/events/" + quote(graph_id, safe=""),
                json=payload,
                params={"sendUpdates": "none"},
            )
        # Deterministic Google-compatible ID makes retries safe even if DB commit fails.
        remote_id = hashlib.sha256(transaction_id.encode()).hexdigest()
        created = self.request(
            "POST",
            "calendar",
            "/events",
            json={"id": remote_id, **payload},
            params={"sendUpdates": "none"},
            allowed=(409,),
        )
        if created.get("_status") == 409:
            existing = self.request("GET", "calendar", "/events/" + remote_id)
            if (
                existing.get("extendedProperties", {})
                .get("private", {})
                .get("acadsync_event")
                != event.id
            ):
                raise HTTPException(
                    409, "Calendar ID conflict. No existing event was changed."
                )
            return self.request(
                "PATCH",
                "calendar",
                "/events/" + remote_id,
                json=payload,
                params={"sendUpdates": "none"},
            )
        return created
