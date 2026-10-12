import asyncio
import logging
from datetime import timedelta
from weakref import WeakValueDictionary

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import FSInputFile

from telegram_bot.database.models import utcnow
from telegram_bot.keyboards.inline import main_menu

logger = logging.getLogger(__name__)


class Worker:
    """Single-process durable job worker; selected FSM steps are intentionally ephemeral."""

    def __init__(self, bot, repo, store, stickers, translator, concurrency=2):
        self.bot, self.repo, self.store = bot, repo, store
        self.stickers, self.translator = stickers, translator
        self.slots = asyncio.Semaphore(concurrency)
        self.locks = WeakValueDictionary()
        self.tasks: dict[str, asyncio.Task] = {}

    async def notify(self, user_id: int, text: str, **kwargs):
        try:
            await self.bot.send_message(chat_id=user_id, text=text, **kwargs)
        except TelegramAPIError:
            logger.warning("Notification unavailable for user %s", user_id)

    async def fulfill(self, job_id: str):
        lock = self.locks.setdefault(job_id, asyncio.Lock())
        async with lock, self.slots:
            job = await self.repo.get_job(job_id)
            if not job or job.status not in {"queued", "processing"}:
                return
            if job.next_attempt_at > utcnow():
                return
            user = await self.repo.get_user(job.telegram_id)
            t = self.translator.for_language(user.language_code)
            await self.repo.patch_job(job.id, status="processing")
            try:
                if not self.store.ready(job):
                    raise FileNotFoundError("Prepared media missing")
                if job.service_type in {"emoji_pack", "ai_studio_pack"}:
                    url = job.result_url or await self.stickers.create(job)
                    await self.repo.patch_job(job.id, result_url=url)
                    done_key = (
                        "sticker_done"
                        if job.params.get("output_type") == "regular"
                        else "pack_done"
                    )
                    await self.bot.send_message(
                        chat_id=job.chat_id, text=t(done_key, url=url), reply_markup=main_menu(t)
                    )
                else:
                    await self.bot.send_document(
                        chat_id=job.chat_id,
                        document=FSInputFile(self.store.path(job.id, "result.png")),
                        caption=t("photo_done", count=job.params["faces"]),
                        reply_markup=main_menu(t),
                    )
                await self.repo.patch_job(job.id, status="completed")
            except TelegramRetryAfter as exc:
                await self.repo.patch_job(
                    job.id,
                    status="queued",
                    next_attempt_at=utcnow() + timedelta(seconds=exc.retry_after + 1),
                )
                return
            except (TelegramNetworkError, TelegramServerError):
                if job.attempts < 3:
                    await self.repo.patch_job(
                        job.id,
                        status="queued",
                        attempts=job.attempts + 1,
                        next_attempt_at=utcnow() + timedelta(seconds=15 * 2**job.attempts),
                    )
                    return
                await self.repo.fail_job(job.id)
                await self.notify(job.telegram_id, t("failed"), reply_markup=main_menu(t))
            except Exception as exc:
                logger.error("Job %s failed (%s)", job.id, type(exc).__name__)
                await self.repo.fail_job(job.id)
                await self.notify(job.telegram_id, t("failed"), reply_markup=main_menu(t))
            await asyncio.to_thread(self.store.remove, job.id)

    async def refund(self, transaction):
        lock = self.locks.setdefault("refund:" + transaction.telegram_charge_id, asyncio.Lock())
        async with lock:
            current = await self.repo.get_transaction(transaction.telegram_charge_id)
            if (
                current is None
                or current.status != "refund_pending"
                or current.refund_retry_at > utcnow()
            ):
                return
            await self._refund(current)

    async def _refund(self, transaction):
        delay = min(3600, 15 * 2 ** min(transaction.refund_attempts, 8))
        try:
            await self.bot.refund_star_payment(
                user_id=transaction.telegram_id,
                telegram_payment_charge_id=transaction.telegram_charge_id,
            )
        except TelegramRetryAfter as exc:
            await self.repo.defer_refund(transaction.telegram_charge_id, exc.retry_after + 1)
            return
        except TelegramBadRequest as exc:
            if "CHARGE_ALREADY_REFUNDED" not in exc.message.upper():
                logger.error("Refund needs retry for transaction %s", transaction.id)
                await self.repo.defer_refund(transaction.telegram_charge_id, delay)
                return
        except TelegramAPIError:
            logger.warning("Refund temporarily unavailable for transaction %s", transaction.id)
            await self.repo.defer_refund(transaction.telegram_charge_id, delay)
            return
        await self.repo.mark_refunded(transaction.telegram_charge_id)
        if transaction.job_id:
            await asyncio.to_thread(self.store.remove, transaction.job_id)
        user = await self.repo.get_user(transaction.telegram_id)
        await self.notify(
            transaction.telegram_id,
            self.translator.text(user.language_code, "refunded", stars=transaction.stars_amount),
        )

    async def sweep_media(self):
        for job_id in await asyncio.to_thread(self.store.aged_directories):
            job = await self.repo.get_job(job_id)
            if job is None or job.status in {"completed", "failed", "refunded", "expired"}:
                await asyncio.to_thread(self.store.remove, job_id)

    async def run(self):
        try:
            while True:
                try:
                    for key, task in list(self.tasks.items()):
                        if task.done():
                            try:
                                task.result()
                            except Exception as exc:
                                logger.error(
                                    "Worker task %s interrupted (%s)", key, type(exc).__name__
                                )
                            del self.tasks[key]
                    for job in await self.repo.pending_jobs():
                        if job.id not in self.tasks:
                            self.tasks[job.id] = asyncio.create_task(self.fulfill(job.id))
                    for transaction in await self.repo.pending_refunds():
                        await self.refund(transaction)
                    for job in await self.repo.expire_jobs():
                        await asyncio.to_thread(self.store.remove, job.id)
                    await self.sweep_media()
                except Exception as exc:
                    logger.error("Recovery loop interrupted (%s)", type(exc).__name__)
                await asyncio.sleep(5)
        finally:
            for task in self.tasks.values():
                task.cancel()
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
