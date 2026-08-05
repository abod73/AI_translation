"""
telegram_sender.py
==================
إرسال الملفات (فيديو، SRT) إلى المستخدم عبر تيليجرام.

يدعم:
- إرسال فيديو حتى 2000 ميجابايت
- إرسال ملفات SRT
- إرسال رسائل مع InlineKeyboard
- تعديل الرسائل
- شريط تقدم أثناء الرفع
- معالجة الأخطاء وإعادة المحاولة
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Optional

from pyrogram import Client
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InputMediaVideo,
)

from config import TELEGRAM_MAX_SIZE_BYTES, MAX_RETRIES
from logger import get_child_logger, logger
from progress import ProgressTracker, human_readable_size, format_eta
from utils import get_file_size, format_file_size

_sender_logger = get_child_logger(logger.name, "telegram_sender")


class TelegramSender:
    """
    يرسل الملفات والرسائل إلى المستخدم عبر تيليجرام.

    يستخدم Pyrogram Client المُمرر.
    """

    def __init__(self, client: Client) -> None:
        self.client: Client = client

    # ============================================================
    # إرسال فيديو
    # ============================================================
    async def send_video(
        self,
        chat_id: int,
        video_path: str | Path,
        caption: str = "",
        duration: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        thumb: Optional[str | Path] = None,
        reply_to_message_id: Optional[int] = None,
        progress_message: Optional[Message] = None,
    ) -> Optional[Message]:
        """
        يرسل فيديو إلى المستخدم.

        Args:
            chat_id: معرف المحادثة.
            video_path: مسار ملف الفيديو.
            caption: تعليق على الفيديو.
            duration: مدة الفيديو بالثواني.
            width: عرض الفيديو.
            height: ارتفاع الفيديو.
            thumb: مسار الصورة المصغرة.
            reply_to_message_id: معرف الرسالة للرد عليها.
            progress_message: رسالة لعرض التقدم (تُعدّل أثناء الرفع).

        Returns:
            الرسالة المرسلة أو None عند الفشل.
        """
        video_path = Path(video_path)
        if not video_path.exists():
            _sender_logger.error(f"ملف الفيديو غير موجود: {video_path}")
            return None

        file_size = get_file_size(video_path)
        if file_size > TELEGRAM_MAX_SIZE_BYTES:
            _sender_logger.error(
                f"حجم الفيديو {format_file_size(file_size)} يتجاوز الحد {format_file_size(TELEGRAM_MAX_SIZE_BYTES)}"
            )
            # محاولة ضغط الفيديو؟ حالياً نرجع None
            return None

        _sender_logger.info(
            f"إرسال فيديو: {video_path} ({format_file_size(file_size)}) إلى {chat_id}"
        )

        # متتبع التقدم
        tracker = ProgressTracker(
            message_text_fn=lambda c, t, s, e: f"رفع: {c}/{t}",
        )
        tracker.start()

        async def _progress(current: int, total: int) -> None:
            if not tracker.should_update():
                return
            tracker._last_update = time.monotonic()
            text = tracker.build_message(
                current,
                total,
                prefix="📤 جاري رفع الفيديو...",
            )
            if progress_message:
                try:
                    await progress_message.edit_text(text)
                except Exception:
                    pass

        last_error: Optional[str] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # التأكد من صحة المسار
                video_str = str(video_path.absolute())
                kwargs = {
                    "chat_id": chat_id,
                    "video": video_str,
                    "caption": caption,
                    "supports_streaming": True,
                    "progress": _progress,
                }
                if duration is not None:
                    kwargs["duration"] = duration
                if width is not None:
                    kwargs["width"] = width
                if height is not None:
                    kwargs["height"] = height
                if thumb is not None:
                    thumb_path = Path(thumb)
                    if thumb_path.exists():
                        kwargs["thumb"] = str(thumb_path.absolute())
                if reply_to_message_id is not None:
                    kwargs["reply_to_message_id"] = reply_to_message_id

                message = await self.client.send_video(**kwargs)
                _sender_logger.info(
                    f"تم إرسال الفيديو بنجاح (محاولة {attempt})"
                )
                return message

            except Exception as exc:
                last_error = str(exc)
                _sender_logger.warning(
                    f"محاولة {attempt}/{MAX_RETRIES} فشلت: {exc}"
                )
                if attempt < MAX_RETRIES:
                    wait = 2.0 * attempt
                    await asyncio.sleep(wait)

        _sender_logger.error(
            f"فشل إرسال الفيديو بعد {MAX_RETRIES} محاولات: {last_error}"
        )
        return None

    # ============================================================
    # إرسال ملف (document)
    # ============================================================
    async def send_document(
        self,
        chat_id: int,
        file_path: str | Path,
        caption: str = "",
        file_name: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
        progress_message: Optional[Message] = None,
    ) -> Optional[Message]:
        """
        يرسل ملفاً (document) إلى المستخدم.

        Args:
            chat_id: معرف المحادثة.
            file_path: مسار الملف.
            caption: تعليق على الملف.
            file_name: اسم الملف المعروض.
            reply_to_message_id: معرف الرسالة للرد عليها.
            progress_message: رسالة لعرض التقدم.

        Returns:
            الرسالة المرسلة أو None.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            _sender_logger.error(f"الملف غير موجود: {file_path}")
            return None

        file_size = get_file_size(file_path)
        if file_size > TELEGRAM_MAX_SIZE_BYTES:
            _sender_logger.error(
                f"حجم الملف {format_file_size(file_size)} يتجاوز الحد"
            )
            return None

        _sender_logger.info(
            f"إرسال ملف: {file_path} ({format_file_size(file_size)}) إلى {chat_id}"
        )

        tracker = ProgressTracker(
            message_text_fn=lambda c, t, s, e: f"رفع: {c}/{t}",
        )
        tracker.start()

        async def _progress(current: int, total: int) -> None:
            if not tracker.should_update():
                return
            tracker._last_update = time.monotonic()
            text = tracker.build_message(
                current,
                total,
                prefix="📤 جاري رفع الملف...",
            )
            if progress_message:
                try:
                    await progress_message.edit_text(text)
                except Exception:
                    pass

        last_error: Optional[str] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                kwargs = {
                    "chat_id": chat_id,
                    "document": str(file_path.absolute()),
                    "caption": caption,
                    "progress": _progress,
                }
                if file_name:
                    kwargs["file_name"] = file_name
                if reply_to_message_id is not None:
                    kwargs["reply_to_message_id"] = reply_to_message_id

                message = await self.client.send_document(**kwargs)
                _sender_logger.info(
                    f"تم إرسال الملف بنجاح (محاولة {attempt})"
                )
                return message

            except Exception as exc:
                last_error = str(exc)
                _sender_logger.warning(
                    f"محاولة {attempt}/{MAX_RETRIES} فشلت: {exc}"
                )
                if attempt < MAX_RETRIES:
                    wait = 2.0 * attempt
                    await asyncio.sleep(wait)

        _sender_logger.error(
            f"فشل إرسال الملف بعد {MAX_RETRIES} محاولات: {last_error}"
        )
        return None

    # ============================================================
    # إرسال رسالة نصية
    # ============================================================
    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        reply_to_message_id: Optional[int] = None,
        parse_mode: Optional[str] = None,
    ) -> Optional[Message]:
        """يرسل رسالة نصية."""
        try:
            return await self.client.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id,
                parse_mode=parse_mode,
            )
        except Exception as exc:
            _sender_logger.error(f"فشل إرسال الرسالة: {exc}")
            return None

    # ============================================================
    # تعديل رسالة
    # ============================================================
    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> Optional[Message]:
        """يعدّل رسالة موجودة."""
        try:
            return await self.client.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
            )
        except Exception as exc:
            _sender_logger.debug(f"تعذر تعديل الرسالة: {exc}")
            return None

    # ============================================================
    # إرسال ملف SRT
    # ============================================================
    async def send_srt_file(
        self,
        chat_id: int,
        srt_path: str | Path,
        caption: str = "",
        reply_to_message_id: Optional[int] = None,
        progress_message: Optional[Message] = None,
    ) -> Optional[Message]:
        """
        يرسل ملف SRT.

        يعيّن اسم الملف إلى video.srt افتراضياً.
        """
        srt_path = Path(srt_path)
        return await self.send_document(
            chat_id=chat_id,
            file_path=srt_path,
            caption=caption,
            file_name="video.srt",
            reply_to_message_id=reply_to_message_id,
            progress_message=progress_message,
        )

    # ============================================================
    # إرسال رسالة مع لوحة مفاتيح
    # ============================================================
    async def send_with_keyboard(
        self,
        chat_id: int,
        text: str,
        keyboard: InlineKeyboardMarkup,
        reply_to_message_id: Optional[int] = None,
    ) -> Optional[Message]:
        """يرسل رسالة مع InlineKeyboardMarkup."""
        return await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            reply_to_message_id=reply_to_message_id,
        )

    # ============================================================
    # حذف رسالة
    # ============================================================
    async def delete_message(
        self,
        chat_id: int,
        message_id: int,
    ) -> bool:
        """يحذف رسالة."""
        try:
            await self.client.delete_messages(
                chat_id=chat_id,
                message_ids=[message_id],
            )
            return True
        except Exception as exc:
            _sender_logger.warning(f"تعذر حذف الرسالة {message_id}: {exc}")
            return False
