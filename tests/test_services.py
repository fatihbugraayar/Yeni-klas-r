import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.methods import GetStickerSet, SendDocument
from sqlalchemy import update

from telegram_bot.database.models import User, utcnow
from telegram_bot.i18n import Translator, detect_language
from telegram_bot.services.image_service import MediaStore
from telegram_bot.services.payment_service import PaymentService, job_from_payload, payload_for
from telegram_bot.services.sticker_service import StickerService, pack_identity
from telegram_bot.services.worker import Worker

from .conftest import new_job
from .test_repository import paid_job


def test_language_detection_and_translation_consistency():
    translator = Translator()
    assert [detect_language(code) for code in [None, "en-US", "DE_de", "fr", "tr"]] == [
        "tr",
        "en",
        "de",
        "tr",
        "tr",
    ]
    assert "Welcome" in translator.text("en", "welcome")
    assert "Willkommen" in translator.text("de", "welcome")


def test_pack_identity_limits_and_payload_validation():
    name, title = pack_identity("a" * 32, "x" * 29 + "bot", "y" * 200)
    assert len(name) <= 64 and len(title) <= 64
    assert name[0].isalpha() and name.endswith("_by_" + "x" * 29 + "bot")
    assert title.endswith(" • by @" + "x" * 29 + "bot")
    assert job_from_payload(payload_for("a" * 32)) == "a" * 32
    assert job_from_payload("job:../../escape") is None


async def test_8x8_creates_50_then_appends_14_and_resumes_partial_pack(repo, tmp_path):
    store = MediaStore(tmp_path / "media")
    job = await repo.create_job(
        new_job(
            params={
                "files": [f"tile_{i:02d}.webp" for i in range(64)],
                "uploaded": [],
                "title": "My pack",
            }
        )
    )
    bot = SimpleNamespace(
        upload_sticker_file=AsyncMock(
            side_effect=[SimpleNamespace(file_id=f"file{i}") for i in range(64)]
        ),
        get_sticker_set=AsyncMock(
            side_effect=TelegramBadRequest(GetStickerSet(name="x"), "STICKERSET_INVALID")
        ),
        create_new_sticker_set=AsyncMock(),
        add_sticker_to_set=AsyncMock(),
    )
    service = StickerService(bot, repo, store, "ExampleBot")
    url = await service.create(job)
    assert url.endswith("_by_ExampleBot")
    assert len(bot.create_new_sticker_set.call_args.kwargs["stickers"]) == 50
    assert bot.create_new_sticker_set.call_args.kwargs["sticker_type"] == "custom_emoji"
    assert bot.add_sticker_to_set.call_count == 14
    bot.get_sticker_set.side_effect = None
    bot.get_sticker_set.return_value = SimpleNamespace(stickers=[None] * 60)
    bot.add_sticker_to_set.reset_mock()
    await service.create(await repo.get_job(job.id))
    assert bot.upload_sticker_file.call_count == 64
    assert bot.create_new_sticker_set.call_count == 1
    assert bot.add_sticker_to_set.call_count == 4


async def test_invoice_native_stars_one_price_and_owner_binding(repo, tmp_path):
    job = await paid_job(repo)
    store = MediaStore(tmp_path / "media")
    store.write(job.id, {"tile_00.webp": b"image"})
    await repo.patch_job(job.id, params={"files": ["tile_00.webp"]})
    bot = SimpleNamespace(send_invoice=AsyncMock())
    payments = PaymentService(bot, repo, Translator(), store)
    assert await payments.invoice(job.id, 101)
    values = bot.send_invoice.call_args.kwargs
    assert values["currency"] == "XTR" and values["provider_token"] == ""
    assert len(values["prices"]) == 1 and values["prices"][0].amount == 50
    assert values["payload"] == payload_for(job.id)
    await repo.ensure_user(202, None, "en")
    assert not await payments.invoice(job.id, 202)


def worker_for(repo, store, bot=None, stickers=None):
    bot = bot or SimpleNamespace(
        send_document=AsyncMock(), send_message=AsyncMock(), refund_star_payment=AsyncMock()
    )
    return Worker(bot, repo, store, stickers or SimpleNamespace(create=AsyncMock()), Translator())


async def test_worker_replay_delivers_once_and_deletes_media(repo, tmp_path):
    store = MediaStore(tmp_path / "media")
    job = await repo.create_job(
        new_job("face_censor", params={"files": ["result.png"], "faces": 2})
    )
    store.write(job.id, {"result.png": b"prepared"})
    worker = worker_for(repo, store)
    await asyncio.gather(worker.fulfill(job.id), worker.fulfill(job.id))
    assert worker.bot.send_document.call_count == 1
    assert (await repo.get_job(job.id)).status == "completed"
    assert not store.directory(job.id).exists()


async def test_free_api_failure_restores_credit_and_paid_failure_refunds(repo, tmp_path):
    store = MediaStore(tmp_path / "media")
    free = await repo.create_job(
        new_job("face_censor", params={"files": ["result.png"], "faces": 1})
    )
    store.write(free.id, {"result.png": b"prepared"})
    bot = SimpleNamespace(
        send_document=AsyncMock(
            side_effect=TelegramBadRequest(SendDocument(chat_id=101, document="file"), "blocked")
        ),
        send_message=AsyncMock(),
        refund_star_payment=AsyncMock(),
    )
    worker = worker_for(repo, store, bot)
    await worker.fulfill(free.id)
    assert (await repo.get_user(101)).daily_photo_credits == 1
    paid = await paid_job(repo)
    assert await repo.approve_checkout(paid.id, 101, "XTR", 50)
    await repo.record_payment(101, paid.id, "XTR", 50, "paid-failure")
    # Simulate missing disk assets after payment; the original charge must be refunded.
    await worker.fulfill(paid.id)
    assert (await repo.get_job(paid.id)).status == "refund_pending"
    await worker.refund((await repo.pending_refunds())[0])
    assert bot.refund_star_payment.call_args.kwargs["telegram_payment_charge_id"] == "paid-failure"
    assert (await repo.get_job(paid.id)).status == "refunded"


async def test_rate_limit_preserves_media_and_quota_for_retry(repo, tmp_path):
    store = MediaStore(tmp_path / "media")
    job = await repo.create_job(
        new_job("face_censor", params={"files": ["result.png"], "faces": 1})
    )
    store.write(job.id, {"result.png": b"prepared"})
    worker = worker_for(repo, store)
    worker.bot.send_document.side_effect = TelegramRetryAfter(
        SendDocument(chat_id=101, document="file"), "slow down", retry_after=5
    )
    await worker.fulfill(job.id)
    saved = await repo.get_job(job.id)
    assert saved.status == "queued" and saved.next_attempt_at > utcnow()
    assert store.ready(saved)
    assert (await repo.get_user(101)).daily_photo_credits == 0


async def test_refund_api_failure_remains_durable_for_retry(repo, tmp_path):
    tx = await repo.record_payment(101, None, "XTR", 20, "retry-refund")
    worker = worker_for(repo, MediaStore(tmp_path / "media"))
    worker.bot.refund_star_payment.side_effect = TelegramBadRequest(
        GetStickerSet(name="x"), "temporarily unavailable"
    )
    await worker.refund(tx)
    saved = await repo.get_transaction("retry-refund")
    assert saved.status == "refund_pending" and saved.refund_retry_at > utcnow()
    assert not await repo.pending_refunds()
    from telegram_bot.database.models import Transaction

    async with repo.db.sessions.begin() as session:
        await session.execute(
            update(Transaction).where(Transaction.id == tx.id).values(refund_retry_at=utcnow())
        )
    worker.bot.refund_star_payment.side_effect = None
    await worker.refund(tx)
    assert not await repo.pending_refunds()


async def test_photo_price_is_twenty_stars(repo):
    async with repo.db.sessions.begin() as session:
        await session.execute(
            update(User)
            .where(User.telegram_id == 101)
            .values(initial_photo_credits=0, daily_photo_credits=0)
        )
    assert (await repo.create_job(new_job("face_censor"))).stars_amount == 20


async def test_refund_honors_telegram_retry_after(repo, tmp_path):
    tx = await repo.record_payment(101, None, "XTR", 20, "limited-refund")
    worker = worker_for(repo, MediaStore(tmp_path / "media"))
    worker.bot.refund_star_payment.side_effect = TelegramRetryAfter(
        GetStickerSet(name="x"), "slow down", retry_after=120
    )
    await worker.refund(tx)
    saved = await repo.get_transaction("limited-refund")
    assert (saved.refund_retry_at - utcnow()).total_seconds() > 119
    await worker.refund(tx)
    assert worker.bot.refund_star_payment.call_count == 1


async def test_new_process_repository_recovers_persisted_processing_job(repo, tmp_path):
    from telegram_bot.database.base import Database
    from telegram_bot.database.repository import Repository

    store = MediaStore(tmp_path / "media")
    job = await repo.create_job(
        new_job("face_censor", params={"files": ["result.png"], "faces": 1})
    )
    store.write(job.id, {"result.png": b"prepared"})
    await repo.patch_job(job.id, status="processing")
    url = str(repo.db.engine.url)
    await repo.db.close()
    fresh_db = Database(url)
    try:
        await fresh_db.initialize()
        fresh_repo = Repository(fresh_db)
        assert (await fresh_repo.pending_jobs())[0].id == job.id
        worker = worker_for(fresh_repo, store)
        await worker.fulfill(job.id)
        assert (await fresh_repo.get_job(job.id)).status == "completed"
        assert (await fresh_repo.get_user(101)).daily_photo_credits == 0
    finally:
        await fresh_db.close()
