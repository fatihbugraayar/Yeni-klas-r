import asyncio
import io

import numpy as np
import pytest
from PIL import Image
from sqlalchemy import text, update

from telegram_bot.database.base import Database
from telegram_bot.database.models import Base, Transaction, User
from telegram_bot.database.repository import Repository
from telegram_bot.i18n import Translator
from telegram_bot.services.image_service import InvalidImage, split_studio_grid
from telegram_bot.services.template_service import TemplateService, draw_blueprint

from .conftest import new_job
from .test_images import png


@pytest.mark.parametrize("grid", range(1, 10))
def test_blueprint_is_deterministic_1024_png(grid):
    blueprint = draw_blueprint(grid)
    assert blueprint == draw_blueprint(grid)
    with Image.open(io.BytesIO(blueprint)) as image:
        assert image.format == "PNG" and image.size == (1024, 1024)
        assert len(image.getcolors(maxcolors=4096)) > 3


async def test_blueprint_uses_shared_processing_limit():
    slots = asyncio.Semaphore(1)
    service = TemplateService(slots)
    async with slots:
        pending = asyncio.create_task(service.generate(9))
        await asyncio.sleep(0)
        assert not pending.done()
    assert await pending == draw_blueprint(9)
    with pytest.raises(ValueError):
        await service.generate(10)


@pytest.mark.parametrize("kind,size", [("custom_emoji", 100), ("regular", 512)])
@pytest.mark.parametrize("grid", [1, 3, 9])
def test_studio_outputs_ordered_png_tiles_with_alpha(kind, size, grid):
    side = grid * 20
    array = np.zeros((side, side + 40, 4), dtype=np.uint8)
    array[:, :20] = array[:, -20:] = (255, 255, 255, 255)
    for row in range(grid):
        for col in range(grid):
            array[row * 20 : (row + 1) * 20, 20 + col * 20 : 20 + (col + 1) * 20] = (
                row * 28,
                col * 28,
                120,
                128,
            )
    tiles = split_studio_grid(png(array), grid, kind)
    assert len(tiles) == grid * grid
    for index, data in enumerate(tiles):
        assert len(data) <= 512 * 1024
        with Image.open(io.BytesIO(data)) as image:
            assert image.format == "PNG" and image.size == (size, size)
            with image.convert("RGBA") as rgba:
                expected = (
                    index // grid * 28,
                    index % grid * 28,
                    120,
                    128,
                )
                actual = rgba.getpixel((size // 2, size // 2))
                # Pillow resizes RGBA with premultiplied-alpha rounding in RGB.
                assert actual[3] == expected[3]
                assert all(abs(a - b) <= 1 for a, b in zip(actual[:3], expected[:3], strict=True))


def test_detailed_sticker_stays_within_upload_limit_and_keeps_transparent_region():
    array = np.random.default_rng(12).integers(0, 256, (512, 512, 4), dtype=np.uint8)
    array[:, :, 3] = 255
    array[:64, :64] = (0, 0, 0, 0)
    output = split_studio_grid(png(array), 1, "regular")[0]
    assert len(output) <= 512 * 1024
    with Image.open(io.BytesIO(output)) as image, image.convert("RGBA") as rgba:
        assert rgba.getpixel((10, 10))[3] == 0
        assert rgba.getpixel((300, 300))[3] == 255
    for grid, kind in [(0, "regular"), (10, "regular"), (1, "mask")]:
        with pytest.raises(InvalidImage):
            split_studio_grid(png(array), grid, kind)


def test_studio_prompts_have_localized_fill_in_slots_and_chosen_dimensions():
    translator = Translator()
    for language, subject in [("tr", "KONU"), ("en", "SUBJECT"), ("de", "MOTIV")]:
        prompt = translator.text(language, "studio_ai_prompt", grid=9)
        assert "9x9" in prompt and f"[{subject}" in prompt and "--ar 1:1" in prompt
        assert len(prompt) < 4096
        assert "100" in translator.text(language, "studio_grid_prompt")


async def test_studio_credit_is_atomic_separate_and_failure_restores_once(repo):
    jobs = await asyncio.gather(*[repo.create_job(new_job("ai_studio_pack")) for _ in range(8)])
    free = [job for job in jobs if job.stars_amount == 0]
    assert len(free) == 1
    assert all(job.stars_amount == 100 for job in jobs if job not in free)
    user = await repo.get_user(101)
    assert user.free_ai_studio_credits == 0
    assert (user.free_emoji_credits, user.initial_photo_credits, user.daily_photo_credits) == (
        3,
        5,
        1,
    )
    await asyncio.gather(repo.fail_job(free[0].id), repo.fail_job(free[0].id))
    assert (await repo.get_user(101)).free_ai_studio_credits == 1
    assert (await repo.create_job(new_job("ai_studio_pack"))).stars_amount == 0
    paid = await repo.create_job(new_job("ai_studio_pack"))
    await repo.accept_terms(101)
    assert not await repo.approve_checkout(paid.id, 101, "XTR", 50)
    assert await repo.approve_checkout(paid.id, 101, "XTR", 100)
    receipts = await asyncio.gather(
        *[repo.record_payment(101, paid.id, "XTR", 100, "studio-charge") for _ in range(3)]
    )
    assert len({receipt.id for receipt in receipts}) == 1
    assert receipts[0].service_type == "ai_studio_pack"
    assert receipts[0].stars_amount == 100


async def test_upgrade_preserves_existing_users_jobs_and_receipts(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    try:
        async with database.engine.begin() as connection:
            await connection.execute(
                text("""
                CREATE TABLE users (
                    telegram_id BIGINT PRIMARY KEY, username VARCHAR(64),
                    language_code VARCHAR(5) NOT NULL, terms_accepted BOOLEAN NOT NULL,
                    free_emoji_credits INTEGER NOT NULL, initial_photo_credits INTEGER NOT NULL,
                    daily_photo_credits INTEGER NOT NULL, last_daily_photo_date DATE NOT NULL,
                    created_at DATETIME NOT NULL
                )
            """)
            )
            await connection.execute(
                text("""
                INSERT INTO users VALUES
                (101, 'legacy', 'de', 1, 0, 2, 0, CURRENT_DATE, CURRENT_TIMESTAMP)
            """)
            )
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(
                    sync,
                    tables=[
                        table for table in Base.metadata.sorted_tables if table.name != "users"
                    ],
                )
            )
        job = new_job(stars_amount=50, status="completed", payment_charge_id="legacy-charge")
        async with database.sessions.begin() as session:
            session.add(job)
            await session.flush()
            session.add(
                Transaction(
                    telegram_id=101,
                    job_id=job.id,
                    service_type="emoji_pack",
                    stars_amount=50,
                    telegram_charge_id="legacy-charge",
                    status="paid",
                )
            )
        await database.initialize()
        repository = Repository(database)
        user = await repository.get_user(101)
        assert user.language_code == "de" and user.terms_accepted
        assert user.free_ai_studio_credits == 1
        assert (user.free_emoji_credits, user.initial_photo_credits, user.daily_photo_credits) == (
            0,
            2,
            0,
        )
        assert (await repository.get_job(job.id)).status == "completed"
        assert (await repository.get_transaction("legacy-charge")).stars_amount == 50
        async with database.sessions.begin() as session:
            await session.execute(update(User).values(free_ai_studio_credits=0))
        await database.initialize()
        assert (await repository.get_user(101)).free_ai_studio_credits == 0
    finally:
        await database.close()
