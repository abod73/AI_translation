"""
callback.py
===========
معالجات Callback Queries من أزرار InlineKeyboard.

يدعم:
- اختيار الجودة (240p, 360p, 480p, 720p, 1080p, Best)
- نعم/لا لاستخراج الكلام
- نعم/لا للترجمة
- إلغاء العملية
- البدء والمساعدة
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Optional

from pyrogram import Client
from pyrogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
)

from config import (
    DOWNLOADS_DIR,
    OUTPUTS_DIR,
    STEP_IDLE,
    STEP_WAITING_QUALITY,
    STEP_DOWNLOADING,
    STEP_VIDEO_SENT,
    STEP_TRANSCRIBING,
    STEP_SRT_SENT,
    STEP_TRANSLATING,
    STEP_TRANSLATION_SENT,
    TELEGRAM_MAX_SIZE_BYTES,
)
from keyboards import (
    CALLBACK_QUALITY_PREFIX,
    CALLBACK_YES,
    CALLBACK_NO,
    CALLBACK_CANCEL,
    CALLBACK_START,
    CALLBACK_HELP,
    CALLBACK_TRANSCRIBE,
    CALLBACK_TRANSLATE,
    CALLBACK_BURN_SUBS,
    CALLBACK_NEW_VIDEO,
    parse_quality_callback,
    transcribe_keyboard,
    translate_keyboard,
    burn_subs_keyboard,
    main_menu_keyboard,
    start_keyboard,
)
from logger import get_child_logger, logger
from handlers import (
    user_sessions,
    get_user_session,
    update_session,
    get_session_step,
    set_session_step,
    clear_session,
    WELCOME_TEXT,
    HELP_TEXT,
)
from downloader import download_video
from speech_to_text import transcribe_video
from translator import translate_srt_file_async
from subtitle_editor import rebuild_arabic_srt
from subtitle import parse_srt_file
from telegram_sender import TelegramSender
from utils import get_file_size, format_file_size, clean_temp_files
from video_info import get_video_info

_callback_logger = get_child_logger(logger.name, "callback")


# ============================================================
# دالة مساعدة لإرسال رد على callback
# ============================================================
async def _answer_callback(callback: CallbackQuery, text: str = "") -> None:
    """يجيب على callback query لإزالة مؤشر التحميل."""
    try:
        await callback.answer(text)
    except Exception:
        pass


async def _edit_message(
    callback: CallbackQuery,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    """يعدّل الرسالة المرفقة بالـ callback."""
    try:
        await callback.edit_message_text(
            text=text,
            reply_markup=reply_markup,
        )
    except Exception as exc:
        _callback_logger.debug(f"تعذر تعديل الرسالة: {exc}")


# ============================================================
# معالج Callback الرئيسي
# ============================================================
async def handle_callback_query(client: Client, callback: CallbackQuery) -> None:
    """المعالج الرئيسي لكل callback queries."""
    user_id = callback.from_user.id
    data = callback.data or ""

    _callback_logger.info(f"Callback من المستخدم {user_id}: {data}")

    # توجيه حسب نوع الـ callback
    if data.startswith(CALLBACK_QUALITY_PREFIX):
        await _handle_quality_selection(client, callback, user_id, data)
    elif data == CALLBACK_TRANSCRIBE:
        await _handle_transcribe(client, callback, user_id)
    elif data == CALLBACK_TRANSLATE:
        await _handle_translate(client, callback, user_id)
    elif data == CALLBACK_BURN_SUBS:
        await _handle_burn_subs(client, callback, user_id)
    elif data == CALLBACK_YES:
        await _answer_callback(callback, "تم التأكيد")
    elif data == CALLBACK_NO:
        await _handle_no(client, callback, user_id)
    elif data == CALLBACK_CANCEL:
        await _handle_cancel(client, callback, user_id)
    elif data == CALLBACK_START:
        await _handle_start(client, callback, user_id)
    elif data == CALLBACK_HELP:
        await _handle_help(client, callback, user_id)
    elif data == CALLBACK_NEW_VIDEO:
        await _handle_new_video(client, callback, user_id)
    else:
        _callback_logger.warning(f"callback غير معروف: {data}")
        await _answer_callback(callback, "خيار غير معروف")


# ============================================================
# معالجة اختيار الجودة
# ============================================================
async def _handle_quality_selection(
    client: Client,
    callback: CallbackQuery,
    user_id: int,
    data: str,
) -> None:
    """يعالج اختيار المستخدم للجودة."""
    quality = parse_quality_callback(data)
    if quality is None:
        await _answer_callback(callback, "جودة غير صالحة")
        return

    session = get_user_session(user_id)
    url = session.get("url")

    if not url:
        await _answer_callback(callback, "انتهت الجلسة، أرسل رابطاً جديداً")
        await _edit_message(
            callback,
            "⚠️ انتهت الجلسة. أرسل رابط فيديو جديد للبدء.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await _answer_callback(callback, f"تم اختيار: {quality}")

    # تحديث الجلسة
    update_session(
        user_id,
        quality=quality,
        current_step=STEP_DOWNLOADING,
    )

    # تعديل الرسالة لإظهار بدء التحميل
    await _edit_message(
        callback,
        f"📥 **بدء التحميل**\n\n"
        f"📊 الجودة: `{quality}`\n"
        f"🔗 الرابط: {url}\n\n"
        f"⏳ جاري التحميل... قد يستغرق هذا بعض الوقت.",
        reply_markup=None,
    )

    # إرسال رسالة منفصلة للتقدم
    progress_msg = await client.send_message(
        chat_id=user_id,
        text="📦 التحميل: 0%",
    )
    update_session(user_id, info_message_id=progress_msg.id)

    # تشغيل التحميل
    last_progress = [0.0]
    last_update = [time.monotonic()]

    def progress_cb(pct: float, msg: str) -> None:
        last_progress[0] = pct
        now = time.monotonic()
        if now - last_update[0] >= 3.0:  # تحديث كل 3 ثوانٍ
            last_update[0] = now
            asyncio.create_task(_update_progress_message(progress_msg, pct, msg))

    video_path = await download_video(
        url=url,
        quality_label=quality,
        user_id=user_id,
        progress_callback=progress_cb,
    )

    if video_path is None or not Path(video_path).exists():
        await progress_msg.edit_text(
            "❌ فشل تحميل الفيديو.\n"
            "حاول مرة أخرى برابط آخر أو جودة أقل.",
            reply_markup=main_menu_keyboard(),
        )
        clear_session(user_id)
        return

    # التحقق من الحجم
    file_size = get_file_size(video_path)
    if file_size > TELEGRAM_MAX_SIZE_BYTES:
        await progress_msg.edit_text(
            f"❌ حجم الفيديو ({format_file_size(file_size)}) يتجاوز الحد المسموح "
            f"({format_file_size(TELEGRAM_MAX_SIZE_BYTES)}).\n"
            f"حاول اختيار جودة أقل.",
            reply_markup=main_menu_keyboard(),
        )
        clear_session(user_id)
        return

    # إرسال الفيديو للمستخدم
    await progress_msg.edit_text("📤 جاري رفع الفيديو إلى تيليجرام...")

    sender = TelegramSender(client)
    video_message = await sender.send_video(
        chat_id=user_id,
        video_path=video_path,
        caption=(
            f"🎬 **الفيديو جاهز!**\n"
            f"📊 الجودة: `{quality}`\n"
            f"📦 الحجم: `{format_file_size(file_size)}`"
        ),
        progress_message=progress_msg,
    )

    if video_message is None:
        await progress_msg.edit_text(
            "❌ فشل إرسال الفيديو.\nحاول مرة أخرى.",
            reply_markup=main_menu_keyboard(),
        )
        clear_session(user_id)
        return

    # تحديث الجلسة
    update_session(
        user_id,
        video_path=str(video_path),
        video_message_id=video_message.id,
        current_step=STEP_VIDEO_SENT,
    )

    # سؤال: استخراج الكلام التركي؟
    await client.send_message(
        chat_id=user_id,
        text=(
            "🎙️ **هل تريد استخراج الكلام التركي من الفيديو؟**\n\n"
            "سيتم استخدام Whisper لتفريغ الصوت إلى نص تركي بصيغة SRT."
        ),
        reply_markup=transcribe_keyboard(),
        reply_to_message_id=video_message.id,
    )

    await progress_msg.delete()

    _callback_logger.info(f"المستخدم {user_id}: تم إرسال الفيديو وانتظار قرار التفريغ")


# ============================================================
# معالجة استخراج الكلام
# ============================================================
async def _handle_transcribe(
    client: Client,
    callback: CallbackQuery,
    user_id: int,
) -> None:
    """يعالج اختيار استخراج الكلام."""
    session = get_user_session(user_id)
    video_path = session.get("video_path")

    if not video_path or not Path(video_path).exists():
        await _answer_callback(callback, "الفيديو غير موجود، أعد المحاولة")
        await _edit_message(
            callback,
            "❌ الفيديو غير موجود. أرسل رابطاً جديداً.",
            reply_markup=main_menu_keyboard(),
        )
        clear_session(user_id)
        return

    await _answer_callback(callback, "بدء استخراج الكلام")
    update_session(user_id, current_step=STEP_TRANSCRIBING)

    await _edit_message(
        callback,
        "🎙️ **جاري استخراج الكلام التركي**\n\n"
        "⏳ قد يستغرق هذا عدة دقائق حسب طول الفيديو.\n"
        "🔍 النموذج: Whisper (small)\n"
        "🌐 اللغة: Turkish",
        reply_markup=None,
    )

    # رسالة تقدم
    progress_msg = await client.send_message(
        chat_id=user_id,
        text="⏳ جاري التفريغ...",
    )

    # تشغيل Whisper
    srt_path = await transcribe_video(
        video_path=video_path,
        output_dir=DOWNLOADS_DIR,
        progress_callback=None,
    )

    if srt_path is None or not Path(srt_path).exists():
        await progress_msg.edit_text(
            "❌ فشل استخراج الكلام.\n"
            "تأكد من أن الفيديو يحتوي على صوت واضح.",
            reply_markup=main_menu_keyboard(),
        )
        clear_session(user_id)
        return

    # إرسال ملف SRT
    await progress_msg.edit_text("📤 جاري رفع ملف SRT...")

    sender = TelegramSender(client)
    srt_message = await sender.send_srt_file(
        chat_id=user_id,
        srt_path=srt_path,
        caption=(
            "📄 **ملف SRT التركي جاهز!**\n"
            "📝 تم تفريغ الكلام من الفيديو."
        ),
        progress_message=progress_msg,
    )

    if srt_message is None:
        await progress_msg.edit_text(
            "❌ فشل إرسال ملف SRT.",
            reply_markup=main_menu_keyboard(),
        )
        return

    # تحديث الجلسة
    update_session(
        user_id,
        turkish_srt_path=str(srt_path),
        current_step=STEP_SRT_SENT,
    )

    # سؤال: ترجمة إلى العربية؟
    await client.send_message(
        chat_id=user_id,
        text=(
            "🌐 **هل تريد ترجمة الملف إلى العربية؟**\n\n"
            "سيتم استخدام Qwen2.5-3B-Instruct لترجمة النصوص التركية إلى العربية.\n"
            "✅ يتم الحفاظ على التوقيت والترقيم والبنية الأصلية."
        ),
        reply_markup=translate_keyboard(),
        reply_to_message_id=srt_message.id,
    )

    await progress_msg.delete()

    _callback_logger.info(f"المستخدم {user_id}: تم تفريغ الكلام وانتظار قرار الترجمة")


# ============================================================
# معالجة الترجمة
# ============================================================
async def _handle_translate(
    client: Client,
    callback: CallbackQuery,
    user_id: int,
) -> None:
    """يعالج اختيار الترجمة إلى العربية."""
    session = get_user_session(user_id)
    turkish_srt_path = session.get("turkish_srt_path")

    if not turkish_srt_path or not Path(turkish_srt_path).exists():
        await _answer_callback(callback, "ملف SRT غير موجود")
        await _edit_message(
            callback,
            "❌ ملف SRT التركي غير موجود.",
            reply_markup=main_menu_keyboard(),
        )
        clear_session(user_id)
        return

    await _answer_callback(callback, "بدء الترجمة")
    update_session(user_id, current_step=STEP_TRANSLATING)

    await _edit_message(
        callback,
        "🌐 **جاري ترجمة النص إلى العربية**\n\n"
        "🤖 النموذج: Qwen2.5-3B-Instruct\n"
        "⏳ قد يستغرق هذا عدة دقائق حسب عدد المقاطع.",
        reply_markup=None,
    )

    # رسالة تقدم
    progress_msg = await client.send_message(
        chat_id=user_id,
        text="⏳ تحميل النموذج وبدء الترجمة...",
    )

    # مسار الإخراج
    arabic_srt_path = OUTPUTS_DIR / f"user_{user_id}_video_arabic.srt"

    # دالة التقدم
    last_update = [time.monotonic()]
    total_segments = 0

    def progress_cb(current: int, total: int) -> None:
        nonlocal total_segments
        total_segments = total
        now = time.monotonic()
        if now - last_update[0] >= 5.0:
            last_update[0] = now
            pct = (current / total * 100) if total > 0 else 0
            asyncio.create_task(
                progress_msg.edit_text(
                    f"🌐 **جاري الترجمة...**\n\n"
                    f"📊 التقدم: `{current}/{total}` ({pct:.1f}%)\n"
                    f"⏳ الرجاء الانتظار..."
                )
            )

    # تشغيل الترجمة
    result_path = await translate_srt_file_async(
        turkish_srt_path=turkish_srt_path,
        arabic_srt_path=arabic_srt_path,
        progress_callback=progress_cb,
    )

    if result_path is None or not Path(result_path).exists():
        await progress_msg.edit_text(
            "❌ فشلت الترجمة.\n"
            "تأكد من تثبيت النموذج بشكل صحيح.",
            reply_markup=main_menu_keyboard(),
        )
        return

    # إرسال ملف SRT العربي
    await progress_msg.edit_text("📤 جاري رفع ملف SRT العربي...")

    sender = TelegramSender(client)
    arabic_message = await sender.send_srt_file(
        chat_id=user_id,
        srt_path=result_path,
        caption=(
            "🌐 **ملف SRT العربي جاهز!**\n"
            "✅ تمت الترجمة مع الحفاظ على التوقيت والترقيم.\n"
            "🔧 تم تطبيق تصحيحات الأخطاء الشائعة."
        ),
        progress_message=progress_msg,
    )

    if arabic_message is None:
        await progress_msg.edit_text(
            "❌ فشل إرسال ملف SRT العربي.",
            reply_markup=main_menu_keyboard(),
        )
        return

    # تحديث الجلسة
    update_session(
        user_id,
        arabic_srt_path=str(result_path),
        current_step=STEP_TRANSLATION_SENT,
    )

    # سؤال: دمج الترجمة في الفيديو؟
    await client.send_message(
        chat_id=user_id,
        text=(
            "🎬 **هل تريد دمج الترجمة العربية في الفيديو؟**\n\n"
            "سيتم حرق الترجمة في الفيديو عبر FFmpeg."
        ),
        reply_markup=burn_subs_keyboard(),
        reply_to_message_id=arabic_message.id,
    )

    await progress_msg.delete()

    _callback_logger.info(f"المستخدم {user_id}: تمت الترجمة وانتظار قرار الدمج")


# ============================================================
# معالجة دمج الترجمة
# ============================================================
async def _handle_burn_subs(
    client: Client,
    callback: CallbackQuery,
    user_id: int,
) -> None:
    """يعالج دمج الترجمة في الفيديو."""
    session = get_user_session(user_id)
    video_path = session.get("video_path")
    arabic_srt_path = session.get("arabic_srt_path")

    if not video_path or not Path(video_path).exists():
        await _answer_callback(callback, "الفيديو غير موجود")
        return
    if not arabic_srt_path or not Path(arabic_srt_path).exists():
        await _answer_callback(callback, "ملف الترجمة غير موجود")
        return

    await _answer_callback(callback, "بدء الدمج")

    await _edit_message(
        callback,
        "🎬 **جاري دمج الترجمة في الفيديو**\n\n"
        "⏳ قد يستغرق هذا عدة دقائق حسب طول الفيديو.",
        reply_markup=None,
    )

    progress_msg = await client.send_message(
        chat_id=user_id,
        text="⏳ جاري معالجة الفيديو...",
    )

    # استدعاء FFmpeg
    from video_merger import burn_subtitles_to_video
    output_path = OUTPUTS_DIR / f"user_{user_id}_video_with_subs.mp4"

    result = await burn_subtitles_to_video(
        video_path=video_path,
        srt_path=arabic_srt_path,
        output_path=output_path,
        progress_callback=None,
    )

    if result is None or not Path(result).exists():
        await progress_msg.edit_text(
            "❌ فشل دمج الترجمة.",
            reply_markup=main_menu_keyboard(),
        )
        return

    # إرسال الفيديو الناتج
    await progress_msg.edit_text("📤 جاري رفع الفيديو بالترجمة...")

    sender = TelegramSender(client)
    await sender.send_video(
        chat_id=user_id,
        video_path=result,
        caption=(
            "🎬 **الفيديو بالترجمة العربية جاهز!**\n"
            "✅ تم دمج الترجمة في الفيديو."
        ),
        progress_message=progress_msg,
    )

    await progress_msg.delete()

    # عرض قائمة الإكمال
    await client.send_message(
        chat_id=user_id,
        text=(
            "✅ **اكتملت جميع المراحل بنجاح!**\n\n"
            "🎬 الفيديو الأصلي\n"
            "📄 ملف SRT التركي\n"
            "🌐 ملف SRT العربي\n"
            "🎬 الفيديو بالترجمة\n\n"
            "هل تريد بدء عملية جديدة؟"
        ),
        reply_markup=main_menu_keyboard(),
    )

    # تنظيف الجلسة
    clear_session(user_id)


# ============================================================
# معالجة "لا"
# ============================================================
async def _handle_no(
    client: Client,
    callback: CallbackQuery,
    user_id: int,
) -> None:
    """يعالج اختيار 'لا' في أي خطوة."""
    step = get_session_step(user_id)
    await _answer_callback(callback, "تم")

    if step == STEP_VIDEO_SENT:
        msg = "✅ تم إرسال الفيديو. يمكنك البدء من جديد بإرسال رابط آخر."
    elif step == STEP_SRT_SENT:
        msg = "✅ تم إرسال ملف SRT التركي. يمكنك البدء من جديد بإرسال رابط آخر."
    elif step == STEP_TRANSLATION_SENT:
        msg = "✅ تم إرسال ملف SRT العربي. يمكنك البدء من جديد بإرسال رابط آخر."
    else:
        msg = "✅ تم. أرسل رابطاً جديداً للبدء من جديد."

    await _edit_message(
        callback,
        msg,
        reply_markup=main_menu_keyboard(),
    )
    clear_session(user_id)


# ============================================================
# معالجة الإلغاء
# ============================================================
async def _handle_cancel(
    client: Client,
    callback: CallbackQuery,
    user_id: int,
) -> None:
    """يعالج زر الإلغاء."""
    await _answer_callback(callback, "تم الإلغاء")
    clear_session(user_id)
    await _edit_message(
        callback,
        "❌ تم إلغاء العملية.\n\nأرسل رابطاً جديداً للبدء من جديد.",
        reply_markup=main_menu_keyboard(),
    )


# ============================================================
# معالجة البدء
# ============================================================
async def _handle_start(
    client: Client,
    callback: CallbackQuery,
    user_id: int,
) -> None:
    """يعالج زر البدء."""
    await _answer_callback(callback)
    clear_session(user_id)
    await _edit_message(
        callback,
        WELCOME_TEXT,
        reply_markup=start_keyboard(),
    )


# ============================================================
# معالجة المساعدة
# ============================================================
async def _handle_help(
    client: Client,
    callback: CallbackQuery,
    user_id: int,
) -> None:
    """يعالج زر المساعدة."""
    await _answer_callback(callback)
    await _edit_message(callback, HELP_TEXT)


# ============================================================
# معالجة فيديو جديد
# ============================================================
async def _handle_new_video(
    client: Client,
    callback: CallbackQuery,
    user_id: int,
) -> None:
    """يعالج زر فيديو جديد."""
    await _answer_callback(callback)
    clear_session(user_id)
    await _edit_message(
        callback,
        "🎬 **جلسة جديدة**\n\nأرسل رابط الفيديو التركي للبدء.",
    )


# ============================================================
# دالة مساعدة لتحديث رسالة التقدم
# ============================================================
async def _update_progress_message(
    message: Message,
    pct: float,
    extra: str = "",
) -> None:
    """يحدّث رسالة التقدم بالنسبة المئوية."""
    try:
        bar_length = 20
        filled = int(bar_length * pct / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        text = f"📦 التحميل: [{bar}] {pct:.1f}%"
        if extra:
            text += f"\n{extra}"
        await message.edit_text(text)
    except Exception:
        pass


# ============================================================
# تسجيل معالج Callback
# ============================================================
def register_callback_handler(app: Client) -> None:
    """يسجل معالج callback queries في تطبيق Pyrogram."""

    @app.on_callback_query()
    async def _callback(client: Client, callback: CallbackQuery) -> None:
        await handle_callback_query(client, callback)

    _callback_logger.info("تم تسجيل معالج callback queries")
