import asyncio
import io
from datetime import UTC, datetime

import numpy as np
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Chat, File, Message, Sticker, StickerSet, Update, User
from PIL import Image
from sqlalchemy import update

from telegram_bot.config import Settings
from telegram_bot.database.models import User as DbUser
from telegram_bot.i18n import Translator
from telegram_bot.main import configure_dispatcher
from telegram_bot.services.face_censor import FaceCensor
from telegram_bot.services.image_service import ImageService, MediaStore
from telegram_bot.services.payment_service import PaymentService, payload_for
from telegram_bot.services.sticker_service import StickerService
from telegram_bot.services.template_service import TemplateService
from telegram_bot.services.worker import Worker


class TelegramSession(BaseSession):
    def __init__(self, image):
        super().__init__()
        self.calls = []
        self.image = image
        self.sets = {}
        self.counter = 1000
        self.updates = []

    async def close(self):
        pass

    async def stream_content(self, url, **kwargs):
        yield self.image

    async def make_request(self, bot, method, timeout=None):  # noqa: ASYNC109
        self.calls.append(method)
        name = method.__api_method__
        self.counter += 1
        if name == "getUpdates":
            updates, self.updates = self.updates, []
            return updates
        if name == "getFile":
            return File(
                file_id="image",
                file_unique_id="image",
                file_size=len(self.image),
                file_path="photos/image.png",
            )
        if name == "uploadStickerFile":
            return File(file_id=f"tile{self.counter}", file_unique_id=f"unique{self.counter}")
        if name == "getStickerSet":
            if method.name not in self.sets:
                raise TelegramBadRequest(method, "STICKERSET_INVALID")
            title, stickers, kind = self.sets[method.name]
            return StickerSet(
                name=method.name,
                title=title,
                sticker_type=kind,
                stickers=[
                    Sticker(
                        file_id=s.sticker,
                        file_unique_id=s.sticker,
                        width=100 if kind == "custom_emoji" else 512,
                        height=100 if kind == "custom_emoji" else 512,
                        type=kind,
                        is_animated=False,
                        is_video=False,
                    )
                    for s in stickers
                ],
            )
        if name == "createNewStickerSet":
            self.sets[method.name] = (method.title, list(method.stickers), method.sticker_type)
            return True
        if name == "addStickerToSet":
            self.sets[method.name][1].append(method.sticker)
            return True
        if name in {"answerCallbackQuery", "answerPreCheckoutQuery", "refundStarPayment"}:
            return True
        if name in {"sendMessage", "sendInvoice", "sendDocument"}:
            return Message(
                message_id=self.counter,
                date=datetime.now(UTC),
                chat=Chat(id=method.chat_id, type="private"),
                text=getattr(method, "text", None),
            )
        raise AssertionError(f"Unexpected Telegram method: {name}")


def image_bytes(blank=False):
    array = (
        np.full((800, 1000, 3), 255, dtype=np.uint8)
        if blank
        else np.random.default_rng(7).integers(0, 256, (800, 1000, 3), dtype=np.uint8)
    )
    with Image.fromarray(array) as image, io.BytesIO() as buffer:
        image.save(buffer, "PNG")
        return buffer.getvalue()


async def test_complete_telegram_routing_free_pack_no_faces_and_paid_recovery(repo, tmp_path):
    session = TelegramSession(image_bytes())
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", session=session)
    translator = Translator()
    store = MediaStore(tmp_path / "media")
    settings = Settings(bot_token=bot.token, support_contact="@testsupport", _env_file=None)
    images = ImageService(store, settings.max_image_pixels, 2)
    stickers = StickerService(bot, repo, store, "ExampleBot")
    payments = PaymentService(bot, repo, translator, store)
    worker = Worker(bot, repo, store, stickers, translator)
    dispatcher = configure_dispatcher(
        repo,
        translator,
        settings=settings,
        images=images,
        templates=TemplateService(images.slots),
        censor=FaceCensor(),
        payments=payments,
        worker=worker,
        input_slots=asyncio.Semaphore(2),
    )
    actor = User(id=202, is_bot=False, first_name="Test", language_code="de-DE")
    counter = 0

    async def feed(text=None, callback=None, photo=False, checkout=None):
        nonlocal counter
        counter += 1
        message = dict(
            message_id=counter,
            date=datetime.now(UTC),
            chat={"id": 202, "type": "private"},
            from_user=actor,
        )
        if text:
            message["text"] = text
        if photo:
            message["document"] = {
                "file_id": "image",
                "file_unique_id": "image",
                "mime_type": "image/png",
                "file_name": "source.png",
                "file_size": len(session.image),
            }
        if callback:
            event = Update(
                update_id=counter,
                callback_query={
                    "id": str(counter),
                    "from_user": actor,
                    "chat_instance": "test",
                    "data": callback,
                    "message": message,
                },
            )
        elif checkout:
            event = Update(
                update_id=counter,
                pre_checkout_query={
                    "id": str(counter),
                    "from_user": actor,
                    "currency": "XTR",
                    **checkout,
                },
            )
        else:
            event = Update(update_id=counter, message=message)
        await dispatcher.feed_update(bot, event)

    await feed("/start")
    assert "Willkommen" in session.calls[-1].text
    await feed(callback="lang:tr")
    assert (await repo.get_user(202)).language_code == "tr"
    await feed("/emoji_pack")
    await feed(callback="grid:8")
    await feed(photo=True)
    job = (await repo.recent_jobs(202))[0]
    assert job.status == "completed" and job.params["grid"] == 8
    assert len(next(iter(session.sets.values()))[1]) == 64
    assert (await repo.get_user(202)).free_emoji_credits == 2

    session.image = image_bytes(blank=True)
    await feed("/photo_edit")
    await feed(callback="mode:blur")
    await feed(photo=True)
    assert "Yüz algılanamadı" in session.calls[-1].text
    assert (await repo.get_user(202)).initial_photo_credits == 5
    assert (await repo.get_user(202)).daily_photo_credits == 1

    async with repo.db.sessions.begin() as db_session:
        await db_session.execute(
            update(DbUser).where(DbUser.telegram_id == 202).values(free_emoji_credits=0)
        )
    session.image = image_bytes()
    await feed("/emoji_pack")
    await feed(callback="grid:2")
    await feed(photo=True)
    job = (await repo.recent_jobs(202))[0]
    assert job.status == "awaiting_payment"
    await feed(callback="terms:accept")
    await feed(callback=f"pay:{job.id}")
    invoice = next(call for call in reversed(session.calls) if call.__api_method__ == "sendInvoice")
    assert invoice.currency == "XTR" and invoice.prices[0].amount == 50
    await feed(checkout={"invoice_payload": invoice.payload, "total_amount": 49})
    assert session.calls[-1].ok is False
    await feed(checkout={"invoice_payload": invoice.payload, "total_amount": 50})
    assert session.calls[-1].ok is True

    # Payment is persisted by the polling reader BEFORE Telegram can acknowledge its offset.
    counter += 1
    payment_update = Update(
        update_id=counter,
        message={
            "message_id": counter,
            "date": datetime.now(UTC),
            "chat": {"id": 202, "type": "private"},
            "from_user": actor,
            "successful_payment": {
                "currency": "XTR",
                "total_amount": 50,
                "invoice_payload": payload_for(job.id),
                "telegram_payment_charge_id": "integration-paid",
                "provider_payment_charge_id": "",
            },
        },
    )
    session.updates = [payment_update]
    reader = dispatcher._listen_updates(bot, polling_timeout=1)
    captured = await anext(reader)
    assert len(await repo.pending_payment_updates()) == 1
    await reader.aclose()
    # Simulate a lost FSM after restart, then replay the durable payment.
    dispatcher.storage.storage.clear()
    await dispatcher.feed_update(bot, captured)
    assert not await repo.pending_payment_updates()
    assert (await repo.get_job(job.id)).status == "completed"
    assert len(session.sets) == 2
    uploaded_before = sum(call.__api_method__ == "uploadStickerFile" for call in session.calls)
    await dispatcher.feed_update(bot, payment_update)
    assert (
        sum(call.__api_method__ == "uploadStickerFile" for call in session.calls) == uploaded_before
    )
    await feed("/status")
    assert "Tamamlandı" in session.calls[-1].text

    # Studio templates are free; an upload asks for a format before reserving a credit.
    await feed("/ai_studio")
    await feed(callback="studio_grid:9")
    blueprint = next(
        call for call in reversed(session.calls) if call.__api_method__ == "sendDocument"
    )
    with Image.open(io.BytesIO(blueprint.document.data)) as image:
        assert image.size == (1024, 1024)
    assert any(
        "[KONU" in getattr(call, "text", "")
        for call in session.calls
        if call.__api_method__ == "sendMessage"
    )
    session.image = b"not an image"
    await feed(photo=True)
    invalid_button = session.calls[-1].reply_markup.inline_keyboard[0][0].callback_data
    await feed(callback=invalid_button)
    assert "Görsel okunamadı" in session.calls[-1].text
    assert (await repo.get_user(202)).free_ai_studio_credits == 1
    session.image = image_bytes()
    await feed(photo=True)
    assert (await repo.get_user(202)).free_ai_studio_credits == 1
    old_button = session.calls[-1].reply_markup.inline_keyboard[1][0].callback_data
    await feed(photo=True)  # Replacing the input makes the first image's buttons stale.
    format_button = session.calls[-1].reply_markup.inline_keyboard[1][0].callback_data
    await feed(callback=old_button)
    assert session.calls[-1].show_alert
    assert (await repo.get_user(202)).free_ai_studio_credits == 1
    await feed(callback=format_button)
    studio = (await repo.recent_jobs(202))[0]
    assert studio.status == "completed" and studio.service_type == "ai_studio_pack"
    assert studio.result_url.startswith("https://t.me/addstickers/")
    assert studio.params["grid"] == 9 and studio.params["output_type"] == "regular"
    pack = session.sets[studio.result_url.rsplit("/", 1)[1]]
    assert len(pack[1]) == 81 and pack[2] == "regular"
    assert pack[0].endswith(" • by @ExampleBot")
    assert (await repo.get_user(202)).free_ai_studio_credits == 0
    assert (await repo.get_user(202)).initial_photo_credits == 5
    before = len(session.sets)
    await feed(callback=format_button)
    assert len(session.sets) == before

    # Both Studio output types share one lifetime credit; a second pack costs 100 XTR.
    await feed(callback="menu:studio")
    await feed(callback="studio_grid:1")
    await feed(photo=True)
    format_button = session.calls[-1].reply_markup.inline_keyboard[0][0].callback_data
    await feed(callback=format_button)
    paid_studio = (await repo.recent_jobs(202))[0]
    assert paid_studio.status == "awaiting_payment" and paid_studio.stars_amount == 100
    invoice = next(call for call in reversed(session.calls) if call.__api_method__ == "sendInvoice")
    assert invoice.prices[0].amount == 100 and "Stüdyo" in invoice.title
    await feed(checkout={"invoice_payload": invoice.payload, "total_amount": 50})
    assert session.calls[-1].ok is False
    await feed(checkout={"invoice_payload": invoice.payload, "total_amount": 100})
    assert session.calls[-1].ok is True
    counter += 1
    studio_payment = Update(
        update_id=counter,
        message={
            "message_id": counter,
            "date": datetime.now(UTC),
            "chat": {"id": 202, "type": "private"},
            "from_user": actor,
            "successful_payment": {
                "currency": "XTR",
                "total_amount": 100,
                "invoice_payload": invoice.payload,
                "telegram_payment_charge_id": "studio-integration-paid",
                "provider_payment_charge_id": "",
            },
        },
    )
    await dispatcher.feed_update(bot, studio_payment)
    completed = await repo.get_job(paid_studio.id)
    assert completed.status == "completed" and completed.result_url.startswith(
        "https://t.me/addemoji/"
    )
    assert (await repo.get_transaction("studio-integration-paid")).service_type == "ai_studio_pack"
    uploaded = sum(call.__api_method__ == "uploadStickerFile" for call in session.calls)
    await dispatcher.feed_update(bot, studio_payment)
    assert sum(call.__api_method__ == "uploadStickerFile" for call in session.calls) == uploaded
    await feed("/quota")
    assert "AI Stüdyo paketleri: 0" in session.calls[-1].text
    await bot.session.close()
