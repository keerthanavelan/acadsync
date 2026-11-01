"""Microsoft Graph adapter. Credentials never cross the backend boundary."""

from datetime import timedelta
from urllib.parse import urlparse, quote
import time
import httpx
from fastapi import HTTPException
from .db import now

ROOT = "https://graph.microsoft.com/v1.0"


class Outlook:
    def __init__(self, token):
        self.token = token

    def request(self, method, path, **kwargs):
        url = path if path.startswith("https://") else ROOT + path
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "graph.microsoft.com":
            raise HTTPException(502, "Invalid Graph continuation URL")
        for attempt in range(3):
            try:
                response = httpx.request(
                    method,
                    url,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Prefer": 'outlook.body-content-type="text", IdType="ImmutableId"',
                    },
                    timeout=30,
                    **kwargs,
                )
            except httpx.RequestError:
                raise HTTPException(
                    502, "Microsoft could not be reached. Please retry."
                )
            if response.status_code not in (429, 503):
                break
            if attempt < 2:
                retry = response.headers.get("Retry-After", "2")
                time.sleep(min(int(retry) if retry.isdigit() else 2, 5))
        if response.status_code == 410:
            raise HTTPException(
                409, "Sync cursor expired. Reset sync in Settings and try again."
            )
        if response.status_code in (401, 403):
            raise HTTPException(
                403,
                "Microsoft denied access. Reconnect or ask your institution administrator to approve delegated permissions.",
            )
        if response.is_error:
            raise HTTPException(
                502, "Microsoft could not complete the request. Please retry."
            )
        return response.json() if response.content else {}

    def profile(self):
        return self.request("GET", "/me?$select=id,displayName,mail,userPrincipalName")

    def messages(self, cursor=None):
        since = (now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        path = (
            cursor
            or f"/me/mailFolders/inbox/messages/delta?$select=id,subject,body,receivedDateTime,webLink&$filter=receivedDateTime ge {since}&$top=50"
        )
        # Bounded batches preserve nextLink for the next sync; no unbounded mailbox crawl.
        rows = []
        for _ in range(10):
            page = self.request("GET", path)
            rows.extend(page.get("value", []))
            path = page.get("@odata.nextLink") or page.get("@odata.deltaLink")
            if not page.get("@odata.nextLink"):
                break
        return rows, path

    def save_event(self, event, transaction_id, graph_id=None):
        data = event.data
        from datetime import datetime
        from zoneinfo import ZoneInfo

        zone = ZoneInfo(data["timezone"])

        def local(value):
            return (
                datetime.fromisoformat(value)
                .astimezone(zone)
                .replace(tzinfo=None)
                .isoformat()
            )

        payload = {
            "subject": data["title"],
            "body": {"contentType": "text", "content": data["description"]},
            "start": {"dateTime": local(data["start"]), "timeZone": data["timezone"]},
            "end": {"dateTime": local(data["end"]), "timeZone": data["timezone"]},
            "isAllDay": data["all_day"],
            "location": {"displayName": data["venue"]},
        }
        if graph_id:
            return self.request(
                "PATCH", "/me/events/" + quote(graph_id, safe=""), json=payload
            )
        payload["transactionId"] = transaction_id
        return self.request("POST", "/me/events", json=payload)
