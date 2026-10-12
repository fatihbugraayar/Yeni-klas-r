import asyncio

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery

from telegram_bot.i18n import detect_language
from telegram_bot.services.payment_service import job_from_payload

router = Router(name="payments")


@router.callback_query(F.data.startswith("pay:"))
async def open_invoice(query: CallbackQuery, payments, t):
    await query.answer()
    job_id = query.data.split(":", 1)[1]
    if not await payments.invoice(job_id, query.from_user.id):
        await query.message.answer(t("payment_invalid"))


@router.pre_checkout_query()
async def checkout(query: PreCheckoutQuery, repo, translator, images):
    language = detect_language(query.from_user.language_code)
    job_id = job_from_payload(query.invoice_payload)

    async def validate():
        job = await repo.get_job(job_id) if job_id else None
        if not job or not images.store.ready(job):
            return False
        return await repo.approve_checkout(
            job.id, query.from_user.id, query.currency, query.total_amount
        )

    try:
        valid = await asyncio.wait_for(validate(), timeout=7.5)
    except Exception:
        valid = False
    await query.answer(
        ok=valid, error_message=None if valid else translator.text(language, "payment_invalid")
    )


@router.message(F.successful_payment)
async def successful_payment(message: Message, state: FSMContext, repo, worker, t, event_update):
    payment = message.successful_payment
    tx = await repo.record_payment(
        message.from_user.id,
        job_from_payload(payment.invoice_payload),
        payment.currency,
        payment.total_amount,
        payment.telegram_payment_charge_id,
    )
    # Queued jobs/refunds are now durable; the raw payment update can be discarded.
    await repo.ack_payment_update(event_update.update_id)
    if tx.status == "refund_pending":
        await worker.refund(tx)
        return
    if tx.status != "paid" or not tx.job_id:
        return
    job = await repo.get_job(tx.job_id)
    if job is None or job.status in {"completed", "failed", "refunded", "refund_pending"}:
        return
    if (await state.get_data()).get("job_id") == tx.job_id:
        await state.clear()
    await worker.notify(message.from_user.id, t("payment_received"))
    # The durable job is independent of MemoryStorage and survives /start or restarts.
    await worker.fulfill(tx.job_id)
