import hashlib
from sqlalchemy import select
from .db import Event, Notice
from .extraction import extract, fingerprint, normalized_title


def ingest(db, user, messages):
    added = 0
    for message in messages:
        if "@removed" in message or "receivedDateTime" not in message:
            continue
        digest = hashlib.sha256(
            (
                message.get("subject", "") + message.get("body", {}).get("content", "")
            ).encode()
        ).hexdigest()
        notice = db.scalar(
            select(Notice).where(
                Notice.user_id == user.id, Notice.message_id == message["id"]
            )
        )
        if notice and notice.digest == digest:
            continue
        suggestions = extract(message, user.timezone)
        # Store metadata only for relevant notices; raw bodies are transient.
        if not suggestions:
            continue
        if not notice:
            notice = Notice(
                user_id=user.id,
                message_id=message["id"],
                digest=digest,
                title=message.get("subject", "")[:500],
                received_at=message["receivedDateTime"],
                result="Detected",
            )
            db.add(notice)
        notice.digest = digest
        for suggestion in suggestions:
            data = suggestion.model_dump(mode="json")
            data["source"] = message.get("source", "Outlook")
            key = fingerprint(data["title"], data["start"])
            existing = db.scalar(
                select(Event).where(Event.user_id == user.id, Event.fingerprint == key)
            )
            if existing:
                continue
            candidates = db.scalars(select(Event).where(Event.user_id == user.id)).all()
            prior = next((e for e in candidates if e.source_id == message["id"]), None)
            if not prior and any(
                "deadline change" in warning for warning in data["warnings"]
            ):
                same_title = [
                    e
                    for e in candidates
                    if normalized_title(e.data["title"])
                    == normalized_title(data["title"])
                ]
                if len(same_title) == 1:
                    prior = same_title[0]
            if prior:
                data["warnings"] = list(
                    dict.fromkeys(
                        data["warnings"]
                        + ["Updated notice. Review the new details before approval."]
                    )
                )
                prior.data = data
                prior.fingerprint = key
                prior.status = "pending"
                prior.source_id = message["id"]
                notice.result = "Change detected"
            else:
                db.add(
                    Event(
                        user_id=user.id,
                        source_id=message["id"],
                        fingerprint=key,
                        data=data,
                    )
                )
                added += 1
        db.flush()
    return added
