from datetime import date, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from telegram_bot.database.base import Database
from telegram_bot.database.models import Job, PaymentInbox, Transaction, User, utcdate, utcnow

PRICES = {"emoji_pack": 50, "face_censor": 20, "ai_studio_pack": 100}
CREDIT_POOLS = {
    "emoji_pack": ["free_emoji_credits"],
    "face_censor": ["daily_photo_credits", "initial_photo_credits"],
    "ai_studio_pack": ["free_ai_studio_credits"],
}


class Repository:
    def __init__(self, db: Database):
        self.db = db

    async def ensure_user(self, telegram_id: int, username: str | None, language: str) -> User:
        async with self.db.sessions.begin() as session:
            insert = sqlite_insert if self.db.engine.dialect.name == "sqlite" else pg_insert
            await session.execute(
                insert(User)
                .values(telegram_id=telegram_id, username=username, language_code=language)
                .on_conflict_do_nothing(index_elements=[User.telegram_id])
            )
            await session.execute(
                update(User).where(User.telegram_id == telegram_id).values(username=username)
            )
            await self._refresh_daily(session, telegram_id, utcdate())
            return await session.get(User, telegram_id)

    @staticmethod
    async def _refresh_daily(session, telegram_id: int, today: date):
        await session.execute(
            update(User)
            .where(User.telegram_id == telegram_id, User.last_daily_photo_date < today)
            .values(daily_photo_credits=1, last_daily_photo_date=today)
        )

    async def get_user(self, telegram_id: int) -> User:
        async with self.db.sessions() as session:
            user = await session.get(User, telegram_id)
            if user is None:
                raise ValueError("Unknown user")
            return user

    async def set_language(self, telegram_id: int, language: str):
        if language not in {"tr", "en", "de"}:
            raise ValueError("Unsupported language")
        async with self.db.sessions.begin() as session:
            await session.execute(
                update(User).where(User.telegram_id == telegram_id).values(language_code=language)
            )

    async def accept_terms(self, telegram_id: int):
        async with self.db.sessions.begin() as session:
            await session.execute(
                update(User).where(User.telegram_id == telegram_id).values(terms_accepted=True)
            )

    async def create_job(self, job: Job) -> Job:
        try:
            return await self._create_job(job)
        except IntegrityError:
            async with self.db.sessions() as session:
                existing = await session.scalar(select(Job).where(Job.source_key == job.source_key))
                if existing is None:
                    raise
                return existing

    async def _create_job(self, job: Job) -> Job:
        if job.service_type not in PRICES:
            raise ValueError("Unknown service")
        async with self.db.sessions.begin() as session:
            existing = await session.scalar(select(Job).where(Job.source_key == job.source_key))
            if existing:
                return existing
            today = utcdate()
            await self._refresh_daily(session, job.telegram_id, today)
            columns = CREDIT_POOLS[job.service_type]
            job.reserved_credit = None
            for name in columns:
                column = getattr(User, name)
                result = await session.execute(
                    update(User)
                    .where(User.telegram_id == job.telegram_id, column > 0)
                    .values({name: column - 1})
                )
                if result.rowcount:
                    job.reserved_credit = name
                    job.reserved_date = today
                    break
            job.stars_amount = 0 if job.reserved_credit else PRICES[job.service_type]
            job.status = "queued" if job.reserved_credit else "awaiting_payment"
            session.add(job)
            await session.flush()
            return job

    async def get_job(self, job_id: str) -> Job | None:
        async with self.db.sessions() as session:
            return await session.get(Job, job_id)

    async def recent_jobs(self, user_id: int) -> list[Job]:
        async with self.db.sessions() as session:
            return list(
                await session.scalars(
                    select(Job)
                    .where(Job.telegram_id == user_id)
                    .order_by(Job.created_at.desc())
                    .limit(5)
                )
            )

    async def patch_job(self, job_id: str, **values):
        async with self.db.sessions.begin() as session:
            await session.execute(update(Job).where(Job.id == job_id).values(**values))

    async def approve_checkout(self, job_id: str, user_id: int, currency: str, amount: int) -> bool:
        if currency != "XTR":
            return False
        async with self.db.sessions.begin() as session:
            result = await session.execute(
                update(Job)
                .where(
                    Job.id == job_id,
                    Job.telegram_id == user_id,
                    Job.status.in_(["awaiting_payment", "approved"]),
                    Job.stars_amount == amount,
                    Job.stars_amount > 0,
                    Job.expires_at > utcnow(),
                    select(User.terms_accepted)
                    .where(User.telegram_id == user_id)
                    .scalar_subquery(),
                )
                .values(status="approved")
            )
            return bool(result.rowcount)

    async def record_payment(
        self, user_id: int, job_id: str | None, currency: str, amount: int, charge: str
    ) -> Transaction:
        try:
            return await self._record_payment(user_id, job_id, currency, amount, charge)
        except IntegrityError:
            async with self.db.sessions() as session:
                existing = await session.scalar(
                    select(Transaction).where(Transaction.telegram_charge_id == charge)
                )
                if existing is None:
                    raise
                return existing

    async def _record_payment(
        self, user_id: int, job_id: str | None, currency: str, amount: int, charge: str
    ) -> Transaction:
        async with self.db.sessions.begin() as session:
            existing = await session.scalar(
                select(Transaction).where(Transaction.telegram_charge_id == charge)
            )
            if existing:
                return existing
            # Conditional update elects one charge even if an old invoice is paid twice.
            result = (
                await session.execute(
                    update(Job)
                    .where(
                        Job.id == job_id,
                        Job.telegram_id == user_id,
                        Job.status == "approved",
                        Job.stars_amount == amount,
                        Job.stars_amount > 0,
                        Job.payment_charge_id.is_(None),
                    )
                    .values(status="queued", payment_charge_id=charge)
                )
                if currency == "XTR"
                else None
            )
            accepted = result is not None and bool(result.rowcount)
            job = await session.get(Job, job_id) if accepted else None
            transaction = Transaction(
                telegram_id=user_id,
                job_id=job.id if job else None,
                service_type=job.service_type if job else "invalid_payment",
                stars_amount=amount,
                telegram_charge_id=charge,
                status="paid" if accepted else "refund_pending",
            )
            session.add(transaction)
            await session.flush()
            return transaction

    async def fail_job(self, job_id: str):
        async with self.db.sessions.begin() as session:
            job = await session.get(Job, job_id, with_for_update=True)
            if not job or job.status in {"failed", "completed", "refund_pending", "refunded"}:
                return
            new_status = "refund_pending" if job.payment_charge_id else "failed"
            result = await session.execute(
                update(Job)
                .where(Job.id == job.id, Job.status == job.status)
                .values(status=new_status, reserved_credit=None)
                .execution_options(synchronize_session=False)
            )
            if not result.rowcount:
                return
            if job.reserved_credit:
                column = getattr(User, job.reserved_credit)
                conditions = [User.telegram_id == job.telegram_id]
                if job.reserved_credit == "daily_photo_credits":
                    conditions += [User.last_daily_photo_date == job.reserved_date, column < 1]
                await session.execute(
                    update(User).where(*conditions).values({job.reserved_credit: column + 1})
                )
            if job.payment_charge_id:
                await session.execute(
                    update(Transaction)
                    .where(Transaction.telegram_charge_id == job.payment_charge_id)
                    .values(status="refund_pending")
                )

    async def pending_jobs(self) -> list[Job]:
        async with self.db.sessions() as session:
            return list(
                await session.scalars(
                    select(Job)
                    .where(
                        Job.status.in_(["queued", "processing"]), Job.next_attempt_at <= utcnow()
                    )
                    .order_by(Job.created_at)
                    .limit(50)
                )
            )

    async def pending_refunds(self) -> list[Transaction]:
        async with self.db.sessions() as session:
            return list(
                await session.scalars(
                    select(Transaction)
                    .where(
                        Transaction.status == "refund_pending",
                        Transaction.refund_retry_at <= utcnow(),
                    )
                    .limit(50)
                )
            )

    async def get_transaction(self, charge: str) -> Transaction | None:
        async with self.db.sessions() as session:
            return await session.scalar(
                select(Transaction).where(Transaction.telegram_charge_id == charge)
            )

    async def defer_refund(self, charge: str, delay: int):
        async with self.db.sessions.begin() as session:
            await session.execute(
                update(Transaction)
                .where(
                    Transaction.telegram_charge_id == charge, Transaction.status == "refund_pending"
                )
                .values(
                    refund_retry_at=utcnow() + timedelta(seconds=delay),
                    refund_attempts=Transaction.refund_attempts + 1,
                )
            )

    async def save_payment_update(self, update_id: int, payload: dict):
        async with self.db.sessions.begin() as session:
            insert = sqlite_insert if self.db.engine.dialect.name == "sqlite" else pg_insert
            await session.execute(
                insert(PaymentInbox)
                .values(update_id=update_id, payload=payload)
                .on_conflict_do_nothing(index_elements=[PaymentInbox.update_id])
            )

    async def pending_payment_updates(self) -> list[PaymentInbox]:
        async with self.db.sessions() as session:
            return list(
                await session.scalars(
                    select(PaymentInbox).order_by(PaymentInbox.update_id).limit(100)
                )
            )

    async def ack_payment_update(self, update_id: int):
        async with self.db.sessions.begin() as session:
            await session.execute(delete(PaymentInbox).where(PaymentInbox.update_id == update_id))

    async def mark_refunded(self, charge: str):
        async with self.db.sessions.begin() as session:
            tx = await session.scalar(
                select(Transaction).where(Transaction.telegram_charge_id == charge)
            )
            if not tx:
                return
            tx.status = "refunded"
            if tx.job_id:
                await session.execute(
                    update(Job).where(Job.id == tx.job_id).values(status="refunded")
                )

    async def expire_jobs(self) -> list[Job]:
        async with self.db.sessions.begin() as session:
            # Approved invoices retain media for 24h, matching Telegram's update retention.
            jobs = list(
                await session.scalars(
                    update(Job)
                    .where(
                        ((Job.status == "awaiting_payment") & (Job.expires_at < utcnow()))
                        | (
                            (Job.status == "approved")
                            & (Job.expires_at < utcnow() - timedelta(days=1))
                        )
                    )
                    .values(status="expired")
                    .returning(Job)
                )
            )
            return jobs
