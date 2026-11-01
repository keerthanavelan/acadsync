from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import (
    create_engine,
    String,
    Text,
    JSON,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import settings


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings().database_url,
    connect_args=(
        {"check_same_thread": False}
        if settings().database_url.startswith("sqlite")
        else {}
    ),
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=uid)
    subject: Mapped[str] = mapped_column(String(300), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="Student")
    email: Mapped[str] = mapped_column(String(300), default="")
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Kolkata")
    demo: Mapped[bool] = mapped_column(default=False)
    cache: Mapped[str | None] = mapped_column(Text, nullable=True)
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def provider(self):
        # Identity namespaces keep Google and Microsoft workspaces separate.
        # Existing Microsoft rows need no destructive database migration.
        return "google" if self.subject.startswith("google:") else "outlook"


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    flow: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("user_id", "fingerprint"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    graph_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Notice(Base):
    __tablename__ = "notices"
    __table_args__ = (UniqueConstraint("user_id", "message_id"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    message_id: Mapped[str] = mapped_column(Text)
    digest: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(500))
    received_at: Mapped[str] = mapped_column(String(80))
    result: Mapped[str] = mapped_column(String(100))


def db():
    with SessionLocal() as session:
        yield session
