from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, InputSticker

from telegram_bot.database.repository import Repository
from telegram_bot.services.image_service import MediaStore


def pack_identity(job_id: str, username: str, title: str) -> tuple[str, str]:
    suffix = f"_by_{username}"
    name = ("e" + job_id)[: 64 - len(suffix)] + suffix
    branding = f" • by @{username}"
    title = " ".join(title.split()) or "Emoji Grid"
    return name, title[: 64 - len(branding)] + branding


class StickerService:
    def __init__(self, bot: Bot, repo: Repository, store: MediaStore, username: str):
        self.bot, self.repo, self.store, self.username = bot, repo, store, username

    async def create(self, job) -> str:
        name, title = pack_identity(job.id, self.username, job.params.get("title", "Emoji Grid"))
        params = dict(job.params)
        output_type = params.get("output_type", "custom_emoji")
        if output_type not in {"custom_emoji", "regular"}:
            raise ValueError("Unsupported sticker set type")
        uploaded = list(params.get("uploaded", []))
        # Persist Telegram file IDs after each upload so retries reuse the same stickers.
        for filename in params["files"][len(uploaded) :]:
            file = await self.bot.upload_sticker_file(
                user_id=job.telegram_id,
                sticker=FSInputFile(self.store.path(job.id, filename)),
                sticker_format="static",
            )
            uploaded.append(file.file_id)
            params["uploaded"] = list(uploaded)
            await self.repo.patch_job(job.id, params=params)
        stickers = [
            InputSticker(sticker=file_id, format="static", emoji_list=["🧩"])
            for file_id in uploaded
        ]
        try:
            existing = await self.bot.get_sticker_set(name)
        except TelegramBadRequest as exc:
            if not any(
                value in exc.message.upper() for value in ("STICKERSET_INVALID", "NOT FOUND")
            ):
                raise
            existing = None
        if existing is None:
            await self.bot.create_new_sticker_set(
                user_id=job.telegram_id,
                name=name,
                title=title,
                stickers=stickers[:50],
                sticker_type=output_type,
            )
            added = min(50, len(stickers))
        else:
            added = len(existing.stickers)
        # Both 8×8 and 9×9 exceed Telegram's 50-sticker initial request limit.
        for sticker in stickers[added:]:
            await self.bot.add_sticker_to_set(user_id=job.telegram_id, name=name, sticker=sticker)
        action = "addemoji" if output_type == "custom_emoji" else "addstickers"
        return f"https://t.me/{action}/{name}"
