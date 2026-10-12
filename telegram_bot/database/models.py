from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    # Store naive UTC consistently on SQLite and PostgreSQL.
    return datetime.now(UTC).replace(tzinfo=None)


def utcdate() -> date:
    return datetime.now(UTC).date()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("free_emoji_credits >= 0"),
        CheckConstraint("free_ai_studio_credits >= 0"),
        CheckConstraint("initial_photo_credits >= 0"),
        CheckConstraint("daily_photo_credits >= 0 AND daily_photo_credits <= 1"),
    )

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    language_code: Mapped[str] = mapped_column(String(5), default="tr")
    terms_accepted: Mapped[bool] = mapped_column(default=False)
    free_emoji_credits: Mapped[int] = mapped_column(default=3)
    free_ai_studio_credits: Mapped[int] = mapped_column(default=1, server_default="1")
    initial_photo_credits: Mapped[int] = mapped_column(default=5)
    daily_photo_credits: Mapped[int] = mapped_column(default=1)
    last_daily_photo_date: Mapped[date] = mapped_column(Date, default=utcdate)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(100), unique=True)
    telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    service_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    # awaiting_payment -> approved -> queued -> processing -> completed
    # failures -> failed (free), refund_pending -> refunded (paid)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    stars_amount: Mapped[int] = mapped_column(Integer)
    reserved_credit: Mapped[str | None] = mapped_column(String(32))
    reserved_date: Mapped[date | None] = mapped_column(Date)
    payment_charge_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    result_url: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), index=True)
    service_type: Mapped[str] = mapped_column(String(32))
    stars_amount: Mapped[int] = mapped_column(Integer)
    telegram_charge_id: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="paid", index=True)
    refund_attempts: Mapped[int] = mapped_column(default=0)
    refund_retry_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PaymentInbox(Base):
    __tablename__ = "payment_inbox"

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
