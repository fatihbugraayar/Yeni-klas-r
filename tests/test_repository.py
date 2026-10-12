import asyncio
from datetime import timedelta

from sqlalchemy import select, update

from telegram_bot.database.models import Job, Transaction, User, utcdate, utcnow

from .conftest import new_job


async def test_concurrent_emoji_quota_cannot_be_overspent(repo):
    jobs = await asyncio.gather(*(repo.create_job(new_job()) for _ in range(10)))
    assert sum(job.stars_amount == 0 for job in jobs) == 3
    assert sum(job.stars_amount == 50 for job in jobs) == 7
    assert (await repo.get_user(101)).free_emoji_credits == 0


async def test_photo_uses_daily_first_then_five_lifetime_uses(repo):
    jobs = [await repo.create_job(new_job("face_censor")) for _ in range(7)]
    assert jobs[0].reserved_credit == "daily_photo_credits"
    assert all(job.reserved_credit == "initial_photo_credits" for job in jobs[1:6])
    assert jobs[6].stars_amount == 20
    async with repo.db.sessions.begin() as session:
        await session.execute(
            update(User)
            .where(User.telegram_id == 101)
            .values(last_daily_photo_date=utcdate() - timedelta(days=5))
        )
    user = await repo.ensure_user(101, None, "de")
    assert user.daily_photo_credits == 1
    assert user.initial_photo_credits == 0
    assert user.language_code == "en"  # Stored preferences survive client language changes.
    assert (await repo.create_job(new_job("face_censor"))).stars_amount == 0
    assert (await repo.create_job(new_job("face_censor"))).stars_amount == 20


async def test_duplicate_upload_reserves_once(repo):
    jobs = await asyncio.gather(
        *(repo.create_job(new_job(source_key="same-message")) for _ in range(4))
    )
    assert len({job.id for job in jobs}) == 1
    assert (await repo.get_user(101)).free_emoji_credits == 2


async def test_failure_restores_credit_once_even_concurrently(repo):
    job = await repo.create_job(new_job())
    await asyncio.gather(repo.fail_job(job.id), repo.fail_job(job.id))
    assert (await repo.get_user(101)).free_emoji_credits == 3
    assert (await repo.get_job(job.id)).status == "failed"


async def test_old_daily_reservation_does_not_stack_on_next_day(repo):
    job = await repo.create_job(new_job("face_censor"))
    async with repo.db.sessions.begin() as session:
        await session.execute(
            update(User)
            .where(User.telegram_id == 101)
            .values(daily_photo_credits=0, last_daily_photo_date=utcdate() + timedelta(days=1))
        )
    await repo.fail_job(job.id)
    assert (await repo.get_user(101)).daily_photo_credits == 0


async def paid_job(repo):
    async with repo.db.sessions.begin() as session:
        await session.execute(
            update(User).where(User.telegram_id == 101).values(free_emoji_credits=0)
        )
    job = await repo.create_job(new_job())
    await repo.accept_terms(101)
    return job


async def test_checkout_validates_owner_amount_currency_terms_and_expiry(repo):
    job = await paid_job(repo)
    assert not await repo.approve_checkout(job.id, 999, "XTR", 50)
    assert not await repo.approve_checkout(job.id, 101, "USD", 50)
    assert not await repo.approve_checkout(job.id, 101, "XTR", 49)
    async with repo.db.sessions.begin() as session:
        await session.execute(
            update(User).where(User.telegram_id == 101).values(terms_accepted=False)
        )
    assert not await repo.approve_checkout(job.id, 101, "XTR", 50)
    await repo.accept_terms(101)
    await repo.patch_job(job.id, expires_at=utcnow() - timedelta(seconds=1))
    assert not await repo.approve_checkout(job.id, 101, "XTR", 50)


async def test_payment_replay_is_idempotent_and_second_charge_is_refunded(repo):
    job = await paid_job(repo)
    assert await repo.approve_checkout(job.id, 101, "XTR", 50)
    txs = await asyncio.gather(
        *(repo.record_payment(101, job.id, "XTR", 50, "charge-a") for _ in range(3))
    )
    assert len({tx.id for tx in txs}) == 1
    assert txs[0].status == "paid"
    extra = await repo.record_payment(101, job.id, "XTR", 50, "charge-b")
    assert extra.status == "refund_pending"
    assert extra.job_id is None
    assert (await repo.get_job(job.id)).payment_charge_id == "charge-a"
    await repo.fail_job(job.id)
    assert len(await repo.pending_refunds()) == 2
    await repo.mark_refunded("charge-a")
    assert (await repo.get_job(job.id)).status == "refunded"


async def test_malformed_or_unapproved_payment_is_durable_refund(repo):
    tx = await repo.record_payment(101, None, "XTR", 50, "unknown")
    assert tx.status == "refund_pending"
    async with repo.db.sessions() as session:
        assert await session.scalar(
            select(Transaction).where(Transaction.telegram_charge_id == "unknown")
        )


async def test_approved_payment_survives_invoice_expiry_but_unpaid_job_expires(repo):
    approved = await paid_job(repo)
    pending = await repo.create_job(new_job())
    assert await repo.approve_checkout(approved.id, 101, "XTR", 50)
    for job in (approved, pending):
        await repo.patch_job(job.id, expires_at=utcnow() - timedelta(minutes=5))
    expired = await repo.expire_jobs()
    assert [job.id for job in expired] == [pending.id]
    tx = await repo.record_payment(101, approved.id, "XTR", 50, "late-charge")
    assert tx.status == "paid"
    assert (await repo.get_job(approved.id)).status == "queued"
    async with repo.db.sessions() as session:
        assert await session.scalar(
            select(Job).where(Job.id == pending.id, Job.status == "expired")
        )
