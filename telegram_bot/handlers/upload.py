import asyncio
import logging
from datetime import timedelta
from uuid import uuid4

from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from telegram_bot.database.models import Job, utcnow
from telegram_bot.handlers.states import Flow
from telegram_bot.keyboards.inline import terms
from telegram_bot.services.image_service import InvalidImage, download_image

logger = logging.getLogger(__name__)


async def submit(
    message: Message,
    state: FSMContext,
    service: str,
    t,
    settings,
    repo,
    images,
    censor,
    payments,
    worker,
    input_slots,
):
    if not message.photo and not message.document:
        await message.answer(t("expected_image"))
        return
    job_id = uuid4().hex
    state_data = await state.get_data()
    durable = False
    try:
        await message.answer(t("processing"))
        async with input_slots:
            raw = await download_image(message.bot, message, settings.max_upload_bytes)
            if service == "emoji_pack":
                params = await images.emoji(raw, state_data["grid"], job_id)
                params["title"] = (message.caption or "Emoji Grid")[:128]
            elif service == "ai_studio_pack":
                params = await images.studio(
                    raw, state_data["grid"], state_data["output_type"], job_id
                )
                params["title"] = (message.caption or "AI Studio")[:128]
            else:
                params = await images.photo(raw, state_data["mode"], job_id, censor)
            del raw
        if params is None:
            await message.answer(t("no_faces"))
            return
        job = await repo.create_job(
            Job(
                id=job_id,
                source_key=f"{message.chat.id}:{message.message_id}",
                telegram_id=message.from_user.id,
                chat_id=message.chat.id,
                service_type=service,
                params=params,
                expires_at=utcnow() + timedelta(minutes=settings.invoice_ttl_minutes),
            )
        )
        if job.id != job_id:
            await asyncio.to_thread(images.store.remove, job_id)
            await message.answer(t("already_submitted"))
            return
        durable = True
        await state.clear()
        if job.stars_amount:
            await state.set_state(Flow.payment)
            await state.update_data(job_id=job.id)
            user = await repo.get_user(job.telegram_id)
            if not user.terms_accepted:
                await message.answer(
                    t("terms", support=settings.support_contact), reply_markup=terms(t, job.id)
                )
                await message.answer(t("terms_required"))
            else:
                await message.answer(t("payment_prompt", stars=job.stars_amount))
                if not await payments.invoice(job.id, job.telegram_id):
                    await message.answer(t("payment_invalid"))
        else:
            await worker.fulfill(job.id)
    except InvalidImage:
        if service == "ai_studio_pack":
            await state.set_state(Flow.studio_image)
            await state.update_data(studio_source=None, format_token=None)
        await message.answer(
            t(
                "invalid_image",
                mb=settings.max_upload_bytes // 1_000_000,
                pixels=settings.max_image_pixels / 1_000_000,
            )
        )
    except TelegramAPIError:
        # A durable job is recoverable through /status or the worker, even if a reply fails.
        logger.warning("Upload API interaction failed for user %s", message.from_user.id)
        await worker.notify(
            message.from_user.id, t("failed") if not durable else t("already_submitted")
        )
    except Exception as exc:
        logger.error("Upload preparation failed (%s)", type(exc).__name__)
        await worker.notify(message.from_user.id, t("failed"))
    finally:
        if not durable:
            await asyncio.to_thread(images.store.remove, job_id)
