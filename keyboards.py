"""
keyboards.py
============
لوحات المفاتيح InlineKeyboard للبوت.

يحتوي على:
- لوحة اختيار الجودة (240p, 360p, 480p, 720p, 1080p, Best)
- لوحة نعم/لا
- لوحة القائمة الرئيسية
- لوحة إلغاء العملية
"""

from __future__ import annotations

from typing import List

from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from config import QUALITY_OPTIONS


# ============================================================
# بادئات Callback Data
# ============================================================
CALLBACK_QUALITY_PREFIX = "q:"           # اختيار الجودة
CALLBACK_YES = "yes"                      # نعم
CALLBACK_NO = "no"                        # لا
CALLBACK_CANCEL = "cancel"                # إلغاء
CALLBACK_START = "start"                  # البدء
CALLBACK_TRANSCRIBE = "transcribe"        # استخراج الكلام
CALLBACK_TRANSLATE = "translate"          # الترجمة
CALLBACK_BURN_SUBS = "burn_subs"          # دمج الترجمة بالفيديو
CALLBACK_NEW_VIDEO = "new_video"          # فيديو جديد
CALLBACK_HELP = "help"                    # مساعدة


def quality_keyboard() -> InlineKeyboardMarkup:
    """
    لوحة اختيار الجودة.

    تعرض أزرار: 240p, 360p, 480p, 720p, 1080p, Best
    مرتبة في صفين (3 أزرار لكل صف).
    """
    buttons: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []

    for opt in QUALITY_OPTIONS:
        label = opt["label"]
        row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=f"{CALLBACK_QUALITY_PREFIX}{label}",
            )
        )
        if len(row) == 3:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    # زر الإلغاء في صف منفصل
    buttons.append(
        [
            InlineKeyboardButton(
                text="❌ إلغاء",
                callback_data=CALLBACK_CANCEL,
            )
        ]
    )

    return InlineKeyboardMarkup(buttons)


def yes_no_keyboard(
    yes_callback: str = CALLBACK_YES,
    no_callback: str = CALLBACK_NO,
    yes_text: str = "✅ نعم",
    no_text: str = "❌ لا",
) -> InlineKeyboardMarkup:
    """
    لوحة نعم/لا القياسية.

    Args:
        yes_callback: بيانات callback لزر "نعم".
        no_callback: بيانات callback لزر "لا".
        yes_text: نص زر "نعم".
        no_text: نص زر "لا".
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(text=yes_text, callback_data=yes_callback),
                InlineKeyboardButton(text=no_text, callback_data=no_callback),
            ]
        ]
    )


def transcribe_keyboard() -> InlineKeyboardMarkup:
    """لوحة سؤال استخراج الكلام التركي."""
    return yes_no_keyboard(
        yes_callback=CALLBACK_TRANSCRIBE,
        no_callback=CALLBACK_NO,
        yes_text="✅ نعم، استخرج الكلام",
        no_text="❌ لا، شكراً",
    )


def translate_keyboard() -> InlineKeyboardMarkup:
    """لوحة سؤال الترجمة إلى العربية."""
    return yes_no_keyboard(
        yes_callback=CALLBACK_TRANSLATE,
        no_callback=CALLBACK_NO,
        yes_text="✅ نعم، ترجم إلى العربية",
        no_text="❌ لا، شكراً",
    )


def burn_subs_keyboard() -> InlineKeyboardMarkup:
    """لوحة سؤال دمج الترجمة في الفيديو."""
    return yes_no_keyboard(
        yes_callback=CALLBACK_BURN_SUBS,
        no_callback=CALLBACK_NO,
        yes_text="✅ نعم، ادمج الترجمة",
        no_text="❌ لا، شكراً",
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """لوحة القائمة الرئيسية بعد انتهاء العملية."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="🎬 فيديو جديد",
                    callback_data=CALLBACK_NEW_VIDEO,
                ),
                InlineKeyboardButton(
                    text="❓ مساعدة",
                    callback_data=CALLBACK_HELP,
                ),
            ]
        ]
    )


def cancel_keyboard() -> InlineKeyboardMarkup:
    """لوحة تحتوي على زر إلغاء فقط."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="❌ إلغاء العملية",
                    callback_data=CALLBACK_CANCEL,
                )
            ]
        ]
    )


def start_keyboard() -> InlineKeyboardMarkup:
    """لوحة البدء الابتدائية."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="🎬 ابدأ الآن",
                    callback_data=CALLBACK_START,
                ),
                InlineKeyboardButton(
                    text="❓ تعليمات",
                    callback_data=CALLBACK_HELP,
                ),
            ]
        ]
    )


def parse_quality_callback(callback_data: str) -> str | None:
    """
    يستخرج اسم الجودة من callback_data.

    Args:
        callback_data: نص callback_data.

    Returns:
        اسم الجودة (مثل "720p") أو None.
    """
    if callback_data.startswith(CALLBACK_QUALITY_PREFIX):
        return callback_data[len(CALLBACK_QUALITY_PREFIX) :]
    return None
