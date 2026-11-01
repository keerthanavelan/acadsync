"""Conservative rule-based extraction; replace behind extract() for an LLM provider."""

import hashlib
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import dateparser
from bs4 import BeautifulSoup
from .schemas import EventDetails

CATEGORIES = [
    ("Exam", r"\b(exam|examination|midterm|finals)\b"),
    ("Quiz", r"\bquiz\b"),
    ("Assignment", r"\b(assignment|homework|problem set)\b"),
    ("Submission", r"\b(submission|submit|project report)\b"),
    ("Seminar", r"\b(seminar|workshop|lecture|colloquium)\b"),
    ("Deadline", r"\b(deadline|due date|due by)\b"),
]
DATE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?|\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)(?:\s+\d{4})?|tomorrow|today|next\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday))\b",
    re.I,
)
TIME = re.compile(
    r"\b(?:at\s+)?(\d{1,2}:\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm))\b", re.I
)


def normalized_title(title):
    title = re.sub(
        r"^(?:(?:re|fw|fwd|updated|update|reminder|deadline extended|rescheduled)\s*[:\-]\s*)+",
        "",
        title,
        flags=re.I,
    )
    return re.sub(r"\W+", " ", title.lower()).strip()


def fingerprint(title, start):
    if start:
        start = (
            datetime.fromisoformat(str(start).replace("Z", "+00:00"))
            .astimezone(timezone.utc)
            .isoformat()
        )
    return hashlib.sha256(
        f'{normalized_title(title)}|{start or "unknown"}'.encode()
    ).hexdigest()


def extract(message: dict, timezone: str) -> list[EventDetails]:
    title = message.get("subject", "")[:300]
    body = BeautifulSoup(
        message.get("body", {}).get("content", ""), "html.parser"
    ).get_text(" ", strip=True)
    text = f"{title}\n{body}"
    category = next(
        (name for name, pattern in CATEGORIES if re.search(pattern, text, re.I)), None
    )
    if not category:
        return []
    if re.search(r"\b(unsubscribe|discount|buy now|promo code)\b", text, re.I):
        return []
    base = datetime.fromisoformat(
        message["receivedDateTime"].replace("Z", "+00:00")
    ).astimezone(ZoneInfo(timezone))
    matches = list(DATE.finditer(text))
    changed = bool(
        re.search(r"\b(extended|rescheduled|postponed|changed|moved)\b", text, re.I)
    )
    warnings = []
    start = None
    all_day = True
    if len(matches) > 1:
        warnings.append("Multiple dates found. Verify the intended event date.")
    if matches:
        selected = matches[-1] if changed else matches[0]
        date_text = selected.group()
        if re.match(r"\d{1,2}/\d{1,2}/", date_text):
            warnings.append("Ambiguous numeric date. Enter the correct date manually.")
        else:
            nearby = text[selected.end() : selected.end() + 35]
            time = TIME.search(nearby)
            all_day = time is None
            parsed = dateparser.parse(
                date_text + (" " + time.group(1) if time else ""),
                settings={
                    "RELATIVE_BASE": base.replace(tzinfo=None),
                    "TIMEZONE": timezone,
                    "RETURN_AS_TIMEZONE_AWARE": True,
                    "PREFER_DATES_FROM": "future",
                },
            )
            if parsed:
                start = (
                    parsed
                    if time
                    else parsed.replace(hour=0, minute=0, second=0, microsecond=0)
                )
    if not start:
        warnings.append(
            "A definite date could not be extracted. Set a date before approval."
        )
    if changed:
        warnings.append(
            "Possible deadline change. Review before updating your calendar."
        )
    if re.search(r"\b(?:PST|PDT|EST|EDT|GMT|UTC|IST)\b", text):
        warnings.append(
            "Timezone mentioned in notice. Verify against your account timezone."
        )
    venue = re.search(r"(?:venue|location|room)\s*:\s*([^\n.;]{1,100})", text, re.I)
    return [
        EventDetails(
            title=title or category,
            start=start,
            end=(
                (start + (timedelta(days=1) if all_day else timedelta(hours=1)))
                if start
                else None
            ),
            timezone=timezone,
            all_day=all_day,
            venue=venue.group(1).strip() if venue else "",
            category=category,
            description="Detected from an academic email. Verify details before approval.",
            confidence=0.94 if start and not warnings else 0.55,
            warnings=warnings,
            source_url=message.get("webLink", ""),
        )
    ]
