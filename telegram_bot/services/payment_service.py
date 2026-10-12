import re

from aiogram import Bot
from aiogram.types import LabeledPrice

from telegram_bot.database.models import utcnow


def payload_for(job_id: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ValueError("Invalid job ID")
    return f"job:{job_id}"


def job_from_payload(payload: str) -> str | None:
    return payload[4:] if re.fullmatch(r"job:[a-f0-9]{32}", payload) else None


class PaymentService:
    def __init__(self, bot: Bot, repo, translator, store):
        self.bot, self.repo, self.translator, self.store = bot, repo, translator, store

    async def invoice(self, job_id: str, user_id: int) -> bool:
        job = await self.repo.get_job(job_id)
        user = await self.repo.get_user(user_id)
        if (
            job is None
            or job.telegram_id != user_id
            or not user.terms_accepted
            or job.status not in {"awaiting_payment", "approved"}
            or job.expires_at <= utcnow()
            or not self.store.ready(job)
        ):
            return False
        t = self.translator.for_language(user.language_code)
        title = t(
            {
                "emoji_pack": "invoice_emoji_title",
                "face_censor": "invoice_photo_title",
                "ai_studio_pack": "invoice_studio_title",
            }[job.service_type]
        )
        await self.bot.send_invoice(
            chat_id=job.chat_id,
            title=title,
            description=t("invoice_description", stars=job.stars_amount),
            payload=payload_for(job.id),
            provider_token="",
            currency="XTR",
            prices=[
                LabeledPrice(label=f"{title} ({job.stars_amount} Stars)", amount=job.stars_amount)
            ],
            start_parameter=f"job_{job.id}",
        )
        return True
