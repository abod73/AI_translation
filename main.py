"""
main.py
=======
نقطة الدخول الرئيسية للمشروع.

يستخدم nest_asyncio.apply() للسماح بتشغيل asyncio في بيئات
مثل Google Colab و Jupyter التي لها حلقة event loop خاصة.
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback
from pathlib import Path

# ============================================================
# تطبيق nest_asyncio أولاً (مهم جداً لـ Google Colab)
# ============================================================
try:
    import nest_asyncio
    nest_asyncio.apply()
    print("✅ تم تطبيق nest_asyncio")
except ImportError:
    print("⚠️ nest_asyncio غير مثبت. قد لا يعمل البوت في Google Colab.")
    print("   ثبّته عبر: pip install nest_asyncio")
except Exception as exc:
    print(f"⚠️ تعذر تطبيق nest_asyncio: {exc}")


# ============================================================
# استيراد بعد تطبيق nest_asyncio
# ============================================================
from config import (
    BASE_DIR,
    ensure_directories,
    validate_config,
    BOT_NAME,
    BOT_DESCRIPTION,
    DOWNLOADS_DIR,
    OUTPUTS_DIR,
    TEMP_DIR,
    SESSIONS_DIR,
    FONTS_DIR,
    LOGS_DIR,
)
from logger import setup_logger, logger
from bot import start_bot, stop_bot


# ============================================================
# فحص البيئة
# ============================================================
def check_environment() -> bool:
    """يفحص بيئة التشغيل ويعطي تحذيرات."""
    print("\n" + "=" * 60)
    print(f"🤖 {BOT_NAME}")
    print(f"📋 {BOT_DESCRIPTION}")
    print("=" * 60 + "\n")

    # التحقق من Python
    py_version = sys.version_info
    print(f"🐍 Python: {py_version.major}.{py_version.minor}.{py_version.micro}")
    if py_version < (3, 10):
        print("⚠️ يُنصح باستخدام Python 3.12+")
    elif py_version >= (3, 12):
        print("✅ إصدار Python متوافق (3.12+)")
    else:
        print("✅ إصدار Python مقبول")

    # التحقق من المجلدات
    print("\n📁 المجلدات:")
    for name, path in [
        ("downloads", DOWNLOADS_DIR),
        ("outputs", OUTPUTS_DIR),
        ("temp", TEMP_DIR),
        ("sessions", SESSIONS_DIR),
        ("fonts", FONTS_DIR),
        ("logs", LOGS_DIR),
    ]:
        exists = "✅" if path.exists() else "❌"
        print(f"  {exists} {name}: {path}")

    # التحقق من GPU
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1e9
            print(f"\n🎮 GPU متاح: {gpu_name} ({gpu_mem:.1f} GB)")
            print("   ✅ مناسب لتشغيل Whisper و Qwen2.5-3B")
        else:
            print("\n⚠️ لا يوجد GPU. سيكون الأداء بطيئاً جداً.")
            print("   يُنصح باستخدام Google Colab مع GPU T4.")
    except ImportError:
        print("\n⚠️ PyTorch غير مثبت. سيتم تثبيته عبر requirements.txt")

    # التحقق من FFmpeg
    import shutil
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        print(f"\n🎬 FFmpeg: {ffmpeg_path}")
    else:
        print("\n⚠️ FFmpeg غير مثبت.")

    # التحقق من yt-dlp
    ytdlp_path = shutil.which("yt-dlp")
    if ytdlp_path:
        print(f"📥 yt-dlp: {ytdlp_path}")
    else:
        print("\n⚠️ yt-dlp غير مثبت.")

    # التحقق من Whisper
    whisper_path = shutil.which("whisper")
    if whisper_path:
        print(f"🎙️ Whisper: {whisper_path}")
    else:
        print("\n⚠️ Whisper غير مثبت.")

    # التحقق من متغيرات البيئة
    print("\n🔐 متغيرات البيئة:")
    api_id = os.environ.get("API_ID", "")
    api_hash = os.environ.get("API_HASH", "")
    bot_token = os.environ.get("BOT_TOKEN", "")

    print(f"  {'✅' if api_id else '❌'} API_ID: {'مضبوط' if api_id else 'غير مضبوط'}")
    print(f"  {'✅' if api_hash else '❌'} API_HASH: {'مضبوط' if api_hash else 'غير مضبوط'}")
    print(f"  {'✅' if bot_token else '❌'} BOT_TOKEN: {'مضبوط' if bot_token else 'غير مضبوط'}")

    if not (api_id and api_hash and bot_token):
        print("\n❌ متغيرات البيئة غير مكتملة!")
        print("   اضبطها قبل تشغيل البوت:")
        print('   os.environ["API_ID"] = "your_api_id"')
        print('   os.environ["API_HASH"] = "your_api_hash"')
        print('   os.environ["BOT_TOKEN"] = "your_bot_token"')
        return False

    print("\n✅ جميع المتطلبات جاهزة\n")
    return True


# ============================================================
# نقطة الدخول الرئيسية
# ============================================================
async def main_async() -> None:
    """نقطة الدخول غير المتزامنة."""
    # فحص البيئة
    if not check_environment():
        sys.exit(1)

    # التحقق من الإعدادات
    try:
        validate_config()
    except EnvironmentError as exc:
        logger.error(f"إعدادات غير صالحة:\n{exc}")
        sys.exit(1)

    # التأكد من المجلدات
    ensure_directories()

    logger.info("=" * 60)
    logger.info(f"بدء تشغيل {BOT_NAME}")
    logger.info("=" * 60)

    # تشغيل البوت
    try:
        await start_bot()
    except KeyboardInterrupt:
        logger.info("تم الإيقاف بواسطة المستخدم")
    except Exception as exc:
        logger.error(f"خطأ فادح: {exc}", exc_info=True)
        traceback.print_exc()
        sys.exit(1)
    finally:
        await stop_bot()
        logger.info("تم إيقاف البوت")


def main() -> None:
    """نقطة الدخول المتزامنة."""
    # محاولة استخدام asyncio.run أولاً
    try:
        asyncio.run(main_async())
    except RuntimeError as exc:
        # في بيئات مثل Colab، قد تكون هناك حلقة event loop نشطة
        if "event loop" in str(exc).lower() or "asyncio.run" in str(exc):
            print("⚠️ تم اكتشاف حلقة event loop نشطة. استخدام nest_asyncio...")
            # nest_asyncio.apply() يجب أن يكون قد تم تطبيقه بالفعل في الأعلى
            loop = asyncio.get_event_loop()
            loop.run_until_complete(main_async())
        else:
            raise
    except KeyboardInterrupt:
        print("\nتم الإيقاف بواسطة المستخدم")


if __name__ == "__main__":
    main()
