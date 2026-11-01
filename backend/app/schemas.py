from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import BaseModel, Field, field_validator, model_validator


class EventDetails(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    start: datetime | None = None
    end: datetime | None = None
    timezone: str = "Asia/Kolkata"
    all_day: bool = False
    venue: str = Field(default="", max_length=300)
    category: Literal[
        "Assignment", "Exam", "Quiz", "Submission", "Seminar", "Deadline"
    ] = "Deadline"
    description: str = Field(default="", max_length=2000)
    confidence: float = Field(default=0.5, ge=0, le=1)
    warnings: list[str] = []
    source: str = "Outlook"
    source_url: str = ""

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except Exception:
            raise ValueError("Use a valid IANA timezone")
        return value

    @model_validator(mode="after")
    def valid_range(self):
        for value in [self.start, self.end]:
            if value and value.tzinfo is None:
                raise ValueError("Dates must include a UTC offset")
        if self.start and self.end and self.end <= self.start:
            raise ValueError("End must follow start")
        return self
