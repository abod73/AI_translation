"""
bot.py
======
تهيئة وتشغيل بوت تيليجرام باستخدام Pyrogram.

يستبدل idle() بحلقة:
    while True:
        await asyncio.sleep(3600)
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import Optional

from pyrogram import Client
from pyrogram.types import BotCommand

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    SESSION_PATH,
    BOT_NAME,
    ensure_directories,
    validate_config,
)
from handlers import register_handlers
from callback import register_callback_handler
from logger import get_child_logger, logger

_bot_logger = get_child_logger(logger.name, "bot")


# ============================================================
# متغيرات عامة
# ============================================================
_bot_client: Optional[Client] = None
_is_running: bool = False


# ============================================================
# إنشاء عميل Pyrogram
# ============================================================
def create_bot_client() -> Client:
    """ينشئ عميل Pyrophywith الإعدادات المطلوبة."""
    if API_ID == 0 or not API_HASH or not BOT_TOKEN:
        raise EnvironmentError(
            "متغيرات البيئة غير مضبوطة. تأكد من تعيين:\n"
            "  API_ID\n"
            "  API_HASH\n"
            "  BOT_TOKEN"
        )

    client = Client(
        name=str(SESSION_PATH),
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        workdir=str(SESSION_PATH.parent),
        in_memory=False,
        # إعدادات التحميل
        max_concurrent_transmissions=2,
        # مهلات
        request_timeout=120,
    )

    _bot_logger.info(f"تم إنشاء عميل Pyrogram: {SESSION_PATH}")
    return client


# ============================================================
# ضبط أوامر البوت
# ============================================================
async def set_bot_commands(client: Client) -> None:
    """يضبط أوامر البوت المعروضة في قائمة الأوامر."""
    commands = [
        BotCommand("start", "بدء استخدام البوت"),
        BotCommand("help", "عرض التعليمات"),
        BotCommand("cancel", "إلغاء العملية الحالية"),
        BotCommand("status", "عرض حالة جلستك"),
    ]

    try:
        await client.set_bot_commands(commands)
        _bot_logger.info("تم ضبط أوامر البوت")
    except Exception as exc:
        _bot_logger.warning(f"تعذر ضبط أوامر البوت: {exc}")


# ============================================================
# بدء تشغيل البوت
# ============================================================
async def start_bot() -> Client:
    """
    يبدأ تشغيل البوت.

    - يتحقق من الإعدادات
    - ينشئ العميل
    - يسجل المعالجات
    - يبدأ العميل
    - يستبدل idle() بحلقة while True

    Returns:
        عميل Pyrogram جاهز.
    """
    global _bot_client, _is_running

    # التحقق من الإعدادات
    validate_config()

    # التأكد من المجلدات
    ensure_directories()

    _bot_logger.info(f"بدء تشغيل البوت: {BOT_NAME}")

    # إنشاء العميل
    _bot_client = create_bot_client()

    # تسجيل المعالجات
    register_handlers(_bot_client)
    register_callback_handler(_bot_client)

    # بدء العميل
    await _bot_client.start()
    _bot_logger.info("تم بدء عميل Pyrogram")

    # ضبط أوامر البوت
    await set_bot_commands(_bot_client)

    # عرض معلومات البوت
    me = await _bot_client.get_me()
    _bot_logger.info(
        f"البوت يعمل الآن:\n"
        f"  الاسم: {me.first_name}\n"
        f"  المعرف: @{me.username}\n"
        f"  ID: {me.id}"
    )

    _is_running = True

    # استبدال idle() بحلقة while True كما طلب المستخدم
    _bot_logger.info("بدء حلقة التشغيل الرئيسية (while True)")
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        _bot_logger.info("تم استلام إشارة الإيقاف")
    except asyncio.CancelledError:
        _bot_logger.info("تم إلغاء حلقة التشغيل")
    finally:
        await stop_bot()

    return _bot_client


# ============================================================
# إيقاف البوت
# ============================================================
async def stop_bot() -> None:
    """يوقف البوت بأمان."""
    global _bot_client, _is_running

    _is_running = False

    if _bot_client is not None:
        try:
            await _bot_client.stop()
            _bot_logger.info("تم إيقاف البوت بأمان")
        except Exception as exc:
            _bot_logger.error(f"خطأ أثناء الإيقاف: {exc}")
        finally:
            _bot_client = None


# ============================================================
# معالج إشارات الإيقاف
# ============================================================
def _setup_signal_handlers() -> None:
    """يضبط معالجات إشارات النظام للإيقاف النظيف."""
    def _signal_handler(signum, frame) -> None:
        _bot_logger.info(f"استلام إشارة {signum}")
        # رفع KeyboardInterrupt لإيقاف الحلقة
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGINT, _signal_handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _signal_handler)
    except (ValueError, AttributeError):
        # قد لا يعمل في بعض البيئات (مثل Colab)
        pass


# ============================================================
# نقطة الدخول (إذا تم تشغيل bot.py مباشرة)
# ============================================================
async def main() -> None:
    """نقطة الدخول الرئيسية."""
    _setup_signal_handlers()
    await start_bot()


def run_bot() -> None:
    """يشغل البوت (متزامن)."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _bot_logger.info("تم الإيقاف بواسطة المستخدم")
    except Exception as exc:
        _bot_logger.error(f"خطأ فادح: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run_bot()
