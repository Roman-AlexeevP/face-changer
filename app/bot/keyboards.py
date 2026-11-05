"""Инлайн-клавиатуры бота: только кнопки и callback_data."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot import texts

CONSENT_CALLBACK = "consent:accept"
CHECKOUT_CALLBACK = "checkout:start"


def consent_keyboard() -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(text=texts.CONSENT_BUTTON, callback_data=CONSENT_CALLBACK)
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


def checkout_keyboard(price_kopecks: int) -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(
        text=texts.pay_button_text(price_kopecks),
        callback_data=CHECKOUT_CALLBACK,
    )
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


def again_keyboard() -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(text=texts.AGAIN_BUTTON, callback_data=CHECKOUT_CALLBACK)
    return InlineKeyboardMarkup(inline_keyboard=[[button]])
