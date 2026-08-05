"""
handlers.py
===========
معالجات الرسائل الواردة من تيليجرام.

يدعم:
- /start - بدء البوت
- /help - المساعدة
- /cancel - إلغاء العملية الحالية
- استقبال رابط الفيديو التركي وبدء العملية

كذلك يدير user_sessions (قاموس في الذاكرة، لا قاعدة بيانات).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, Optional

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
)

from config import (
    BOT_NAME,
    BOT_DESCRIPTION,
    STEP_IDLE,
    STEP_WAITING_QUALITY,
    STEP_DOWNLOADING,
    STEP_VIDEO_SENT,
    STEP_TRANSCRIBING,
    STEP_SRT_SENT,
    STEP_TRANSLATING,
    STEP_TRANSLATION_SENT,
)
from keyboards import (
    quality_keyboard,
    start_keyboard,
    cancel_keyboard,
    main_menu_keyboard,
)
from logger import get_child_logger, logger
from utils import get_file_size, format_file_size
from video_info import get_video_info

_handlers_logger = get_child_logger(logger.name, "handlers")


# ============================================================
# إدارة الحالة - user_sessions في الذاكرة فقط
# ============================================================
# لكل مستخدم: video_path, turkish_srt_path, arabic_srt_path, current_step
user_sessions: Dict[int, Dict[str, Any]] = {}


def get_user_session(user_id: int) -> Dict[str, Any]:
    """يجلب أو ينشئ جلسة مستخدم."""
    if user_id not in user_sessions:
        user_sessions[user_id] = create_new_session()
    return user_sessions[user_id]


def create_new_session() -> Dict[str, Any]:
    """ينشئ جلسة جديدة فارغة."""
    return {
        "video_path": None,
        "turkish_srt_path": None,
        "arabic_srt_path": None,
        "current_step": STEP_IDLE,
        "url": None,
        "quality": None,
        "video_message_id": None,
        "info_message_id": None,
        "video_info": None,
        "created_at": asyncio.get_event_loop().time(),
    }


def update_session(user_id: int, **kwargs) -> Dict[str, Any]:
    """يحدّث حقولاً في جلسة المستخدم."""
    session = get_user_session(user_id)
    session.update(kwargs)
    return session


def get_session_step(user_id: int) -> str:
    """يجلب الخطوة الحالية للمستخدم."""
    return get_user_session(user_id).get("current_step", STEP_IDLE)


def set_session_step(user_id: int, step: str) -> None:
    """يضبط الخطوة الحالية للمستخدم."""
    update_session(user_id, current_step=step)


def clear_session(user_id: int) -> None:
    """يمسح جلسة مستخدم وينشئ واحدة جديدة."""
    user_sessions[user_id] = create_new_session()


# ============================================================
# التحقق من الرابط
# ============================================================
URL_REGEX = re.compile(
    r"^https?://(www\.)?[a-zA-Z0-9\-._~:/?#\[\]@!$&'()*+,;=]+$",
    re.IGNORECASE,
)


def is_valid_video_url(url: str) -> bool:
    """يتحقق إذا كان النص رابطاً صالحاً."""
    if not url or not isinstance(url, str):
        return False
    return bool(URL_REGEX.match(url.strip()))


# ============================================================
# نصوص الرسائل
# ============================================================
WELCOME_TEXT = (
    f"👋 أهلاً بك في **{BOT_NAME}**\n\n"
    f"📋 {BOT_DESCRIPTION}\n\n"
    "🎯 **طريقة الاستخدام:**\n"
    "1️⃣ أرسل رابط فيديو تركي (YouTube, Instagram, TikTok...)\n"
    "2️⃣ اختر الجودة المناسبة\n"
    "3️⃣ انتظر تحميل الفيديو\n"
    "4️⃣ اختر استخراج الكلام التركي (Whisper)\n"
    "5️⃣ اختر ترجمة النص إلى العربية (Qwen2.5-3B)\n\n"
    "🚀 **أرسل الرابط الآن للبدء!**"
)

HELP_TEXT = (
    f"📚 **تعليمات {BOT_NAME}**\n\n"
    "🔹 **الأوامر المتاحة:**\n"
    "• /start - بدء استخدام البوت\n"
    "• /help - عرض هذه التعليمات\n"
    "• /cancel - إلغاء العملية الحالية\n"
    "• /status - عرض حالة جلستك\n\n"
    "🔹 **مراحل العمل:**\n"
    "1. أرسل رابط فيديو تركي.\n"
    "2. اختر الجودة (240p - 1080p أو Best).\n"
    "3. سيتم تحميل الفيديو وإرساله لك.\n"
    "4. اختر 'نعم' لاستخراج الكلام التركي عبر Whisper.\n"
    "5. ستحصل على ملف SRT بالنص التركي.\n"
    "6. اختر 'نعم' لترجمة النص إلى العربية عبر Qwen2.5-3B.\n"
    "7. ستحصل على ملف SRT عربي مع الحفاظ على التوقيت.\n\n"
    "⚠️ **ملاحظات:**\n"
    "• الحد الأقصى لحجم الفيديو 2000 ميجابايت.\n"
    "• يدعم البوت حتى دقة 1080p.\n"
    "• العمليات قد تستغرق وقتاً حسب طول الفيديو.\n"
    "• البوت يحفظ جلستك في الذاكرة فقط (لا قاعدة بيانات).\n"
)


# ============================================================
# معالجات الأوامر
# ============================================================
async def start_command(client: Client, message: Message) -> None:
    """معالج أمر /start."""
    user_id = message.from_user.id
    clear_session(user_id)

    await message.reply_text(
        WELCOME_TEXT,
        reply_markup=start_keyboard(),
    )
    _handlers_logger.info(f"المستخدم {user_id} بدأ البوت")


async def help_command(client: Client, message: Message) -> None:
    """معالج أمر /help."""
    await message.reply_text(HELP_TEXT)


async def cancel_command(client: Client, message: Message) -> None:
    """معالج أمر /cancel."""
    user_id = message.from_user.id
    step = get_session_step(user_id)

    if step == STEP_IDLE:
        await message.reply_text("لا توجد عملية جارية لإلغائها.")
        return

    clear_session(user_id)
    await message.reply_text(
        "❌ تم إلغاء العملية الحالية.\n\n"
        "أرسل رابطاً جديداً للبدء من جديد.",
        reply_markup=main_menu_keyboard(),
    )
    _handlers_logger.info(f"المستخدم {user_id} ألغى العملية (كان في: {step})")


async def status_command(client: Client, message: Message) -> None:
    """معالج أمر /status - يعرض حالة الجلسة."""
    user_id = message.from_user.id
    session = get_user_session(user_id)

    lines = [
        f"📊 **حالة جلستك**\n",
        f"• الخطوة الحالية: `{session.get('current_step', 'idle')}`",
        f"• الرابط: `{session.get('url', 'لا يوجد')}`",
        f"• الجودة: `{session.get('quality', 'لا يوجد')}`",
    ]
    if session.get("video_path"):
        lines.append(f"• الفيديو: `{session['video_path']}`")
    if session.get("turkish_srt_path"):
        lines.append(f"• SRT تركي: `{session['turkish_srt_path']}`")
    if session.get("arabic_srt_path"):
        lines.append(f"• SRT عربي: `{session['arabic_srt_path']}`")

    await message.reply_text("\n".join(lines))


# ============================================================
# معالجة الرسائل النصية (روابط الفيديو)
# ============================================================
async def handle_text_message(client: Client, message: Message) -> None:
    """يعالج الرسائل النصية الواردة (بشكل أساسي روابط الفيديو)."""
    user_id = message.from_user.id
    text = message.text or message.caption or ""

    if not text.strip():
        return

    # التحقق إذا كان نصاً عادياً (وليس رابطاً)
    text_stripped = text.strip()

    # إذا كان أمراً معروفاً، تجاهله (تتم معالجته في مكان آخر)
    if text_stripped.startswith("/"):
        return

    # التحقق إذا كان رابطاً
    if not is_valid_video_url(text_stripped):
        # نص عادي وليس رابطاً
        if get_session_step(user_id) == STEP_IDLE:
            await message.reply_text(
                "⚠️ الرجاء إرسال رابط فيديو صالح.\n\n"
                "أمثلة:\n"
                "• https://www.youtube.com/watch?v=...\n"
                "• https://youtu.be/...\n"
                "• https://www.instagram.com/reel/...\n"
            )
        return

    # رابط صالح - بدء العملية
    await _start_video_workflow(client, message, user_id, text_stripped)


# ============================================================
# بدء سير عمل الفيديو
# ============================================================
async def _start_video_workflow(
    client: Client,
    message: Message,
    user_id: int,
    url: str,
) -> None:
    """يبدأ سير عمل تحميل الفيديو."""
    _handlers_logger.info(f"المستخدم {user_id} أرسل رابطاً: {url}")

    # تحديث الجلسة
    update_session(
        user_id,
        url=url,
        current_step=STEP_WAITING_QUALITY,
    )

    # رسالة انتظار
    wait_msg = await message.reply_text(
        "⏳ جاري التحقق من الرابط وجلب معلومات الفيديو..."
    )

    # جلب معلومات الفيديو
    video_info = await get_video_info(url)

    if video_info is None:
        await wait_msg.edit_text(
            "❌ تعذر جلب معلومات الفيديو.\n"
            "تأكد من صحة الرابط وأن الفيديو متاح للعموم.\n\n"
            "أرسل رابطاً آخر للمحاولة مرة أخرى."
        )
        clear_session(user_id)
        return

    # حفظ معلومات الفيديو في الجلسة
    update_session(user_id, video_info=video_info)

    # بناء رسالة المعلومات
    info_text = (
        "✅ تم العثور على الفيديو!\n\n"
        f"{video_info.to_display()}\n\n"
        "📊 **اختر الجودة المطلوبة:**"
    )

    await wait_msg.edit_text(
        info_text,
        reply_markup=quality_keyboard(),
    )

    _handlers_logger.info(
        f"المستخدم {user_id}: تم عرض خيارات الجودة للفيديو '{video_info.title}'"
    )


# ============================================================
# تسجيل المعالجات
# ============================================================
def register_handlers(app: Client) -> None:
    """يسجل جميع المعالجات في تطبيق Pyrogram."""

    @app.on_message(filters.command("start"))
    async def _start(client: Client, message: Message) -> None:
        await start_command(client, message)

    @app.on_message(filters.command("help"))
    async def _help(client: Client, message: Message) -> None:
        await help_command(client, message)

    @app.on_message(filters.command("cancel"))
    async def _cancel(client: Client, message: Message) -> None:
        await cancel_command(client, message)

    @app.on_message(filters.command("status"))
    async def _status(client: Client, message: Message) -> None:
        await status_command(client, message)

    @app.on_message(filters.text & ~filters.command(["start", "help", "cancel", "status"]))
    async def _text(client: Client, message: Message) -> None:
        # تجاهل الرسائل من القنوات
        if message.chat and message.chat.type in ("channel",):
            return
        await handle_text_message(client, message)

    _handlers_logger.info("تم تسجيل جميع معالجات الرسائل")
