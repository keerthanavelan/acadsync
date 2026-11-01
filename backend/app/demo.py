from datetime import timedelta
from .db import now


def messages():
    today = now()
    fixtures = [
        (
            "CS301 · Database design assignment",
            "Assignment due",
            2,
            "11:59 pm",
            "Online submission",
        ),
        (
            "Linear Algebra · Midterm exam",
            "Exam scheduled for",
            5,
            "10:00 am",
            "Room 204, Science Block",
        ),
        (
            "Designing for a sustainable future",
            "Seminar on",
            3,
            "2:00 pm",
            "Main auditorium",
        ),
        ("CS204 · Algorithms quiz", "Quiz on", 1, "9:00 am", "Lab 3"),
        (
            "Research methods · Project proposal",
            "Submission deadline",
            8,
            "5:00 pm",
            "Student portal",
        ),
        ("Data science · Guest lecture", "Seminar on", 7, "11:00 am", "Innovation Hub"),
    ]
    return [
        {
            "id": f"demo-{i}",
            "subject": title,
            "body": {
                "content": f'{kind} {(today+timedelta(days=days)).strftime("%B %d, %Y")} at {time}. Venue: {venue}.'
            },
            "receivedDateTime": today.isoformat(),
            "webLink": "",
        }
        for i, (title, kind, days, time, venue) in enumerate(fixtures)
    ]
