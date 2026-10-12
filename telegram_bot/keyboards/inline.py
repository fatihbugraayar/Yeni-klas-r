from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu(t):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("emoji_button"), callback_data="menu:emoji"),
                InlineKeyboardButton(text=t("photo_button"), callback_data="menu:photo"),
            ],
            [InlineKeyboardButton(text=t("studio_button"), callback_data="menu:studio")],
            [
                InlineKeyboardButton(text=t("language_button"), callback_data="menu:language"),
                InlineKeyboardButton(text=t("quota_button"), callback_data="menu:quota"),
            ],
            [InlineKeyboardButton(text=t("terms_button"), callback_data="menu:terms")],
        ]
    )


def grids():
    builder = InlineKeyboardBuilder()
    for grid in range(2, 9):
        builder.button(text=f"{grid}×{grid}", callback_data=f"grid:{grid}")
    builder.adjust(3, 3, 1)
    return builder.as_markup()


def languages():
    builder = InlineKeyboardBuilder()
    for code, label in [("tr", "🇹🇷 Türkçe"), ("en", "🇬🇧 English"), ("de", "🇩🇪 Deutsch")]:
        builder.button(text=label, callback_data=f"lang:{code}")
    builder.adjust(3)
    return builder.as_markup()


def studio_grids():
    builder = InlineKeyboardBuilder()
    for grid in range(1, 10):
        builder.button(text=f"{grid}×{grid}", callback_data=f"studio_grid:{grid}")
    builder.adjust(3)
    return builder.as_markup()


def studio_formats(t, token: str):
    builder = InlineKeyboardBuilder()
    for kind in ("custom_emoji", "regular"):
        builder.button(text=t("studio_" + kind), callback_data=f"studio_format:{token}:{kind}")
    builder.adjust(1)
    return builder.as_markup()


def photo_modes(t):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("pixelate_button"), callback_data="mode:pixelate"),
                InlineKeyboardButton(text=t("blur_button"), callback_data="mode:blur"),
            ]
        ]
    )


def terms(t, job_id: str | None = None):
    buttons = [[InlineKeyboardButton(text=t("accept_terms"), callback_data="terms:accept")]]
    if job_id:
        buttons.append([InlineKeyboardButton(text=t("pay_button"), callback_data=f"pay:{job_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
