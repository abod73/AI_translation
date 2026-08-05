"""
config.py
=========
ملف الإعدادات المركزي للمشروع.

يحتوي على جميع المتغيرات والثوابت التي يحتاجها البوت:
- بيانات اعتماد تيليجرام (API_ID, API_HASH, BOT_TOKEN)
- مسارات المجلدات
- إعدادات yt-dlp و Whisper و Qwen
- خيارات الجودة
- إعدادات الترجمة

جميع القيم الحساسة تُقرأ من متغيرات البيئة.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final, Dict, List


# ============================================================
# مسار المشروع الأساسي
# ============================================================
# نحدد مسار المشروع بناءً على موقع هذا الملف
BASE_DIR: Final[Path] = Path(__file__).resolve().parent

# ============================================================
# المجلدات الرئيسية
# ============================================================
DOWNLOADS_DIR: Final[Path] = BASE_DIR / "downloads"
OUTPUTS_DIR: Final[Path] = BASE_DIR / "outputs"
TEMP_DIR: Final[Path] = BASE_DIR / "temp"
SESSIONS_DIR: Final[Path] = BASE_DIR / "sessions"
FONTS_DIR: Final[Path] = BASE_DIR / "fonts"
LOGS_DIR: Final[Path] = BASE_DIR / "logs"


def ensure_directories() -> None:
    """ينشئ جميع المجلدات المطلوبة إذا لم تكن موجودة."""
    for directory in (
        DOWNLOADS_DIR,
        OUTPUTS_DIR,
        TEMP_DIR,
        SESSIONS_DIR,
        FONTS_DIR,
        LOGS_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


# ============================================================
# بيانات اعتماد تيليجرام
# ============================================================
# تُقرأ من متغيرات البيئة في Google Colab
API_ID: Final[int] = int(os.environ.get("API_ID", "0"))
API_HASH: Final[str] = os.environ.get("API_HASH", "")
BOT_TOKEN: Final[str] = os.environ.get("BOT_TOKEN", "")

# اسم جلسة Pyrogram
SESSION_NAME: Final[str] = "ai_translation_bot"
SESSION_PATH: Final[Path] = SESSIONS_DIR / SESSION_NAME

# ============================================================
# إعدادات yt-dlp
# ============================================================
YT_DLP_BINARY: Final[str] = "yt-dlp"

# الحد الأقصى لحجم الفيديو المسموح بإرساله عبر تيليجرام (2000 ميجابايت)
TELEGRAM_MAX_SIZE_MB: Final[int] = 2000
TELEGRAM_MAX_SIZE_BYTES: Final[int] = TELEGRAM_MAX_SIZE_MB * 1024 * 1024

# ============================================================
# إعدادات Whisper
# ============================================================
WHISPER_BINARY: Final[str] = "whisper"
WHISPER_MODEL: Final[str] = "small"
WHISPER_LANGUAGE: Final[str] = "Turkish"
WHISPER_TASK: Final[str] = "transcribe"
WHISPER_OUTPUT_FORMAT: Final[str] = "srt"

# ============================================================
# إعدادات Qwen2.5-3B-Instruct
# ============================================================
QWEN_MODEL_NAME: Final[str] = "Qwen/Qwen2.5-3B-Instruct"
QWEN_DEVICE: Final[str] = "cuda"  # GPU T4 على Google Colab
QWEN_TORCH_DTYPE: Final[str] = "auto"  # auto يختار bfloat16 أو float16
QWEN_MAX_NEW_TOKENS: Final[int] = 2048
QWEN_TEMPERATURE: Final[float] = 0.3
QWEN_TOP_P: Final[float] = 0.9
QWEN_REPETITION_PENALTY: Final[float] = 1.1

# عدد الأسطر المترجمة في الدفعة الواحدة (لتفادي تجاوز حد السياق)
QWEN_BATCH_SIZE: Final[int] = 8

# ============================================================
# إعدادات FFmpeg
# ============================================================
FFMPEG_BINARY: Final[str] = "ffmpeg"
FFPROBE_BINARY: Final[str] = "ffprobe"

# ============================================================
# خيارات الجودة المتاحة
# ============================================================
# كل خيار يحتوي على:
# - label: النص المعروض للمستخدم
# - format_id: صيغة yt-dlp المناسبة
# - description: وصف مختصر
QUALITY_OPTIONS: Final[List[Dict[str, str]]] = [
    {
        "label": "240p",
        "format": "bestvideo[height<=240]+bestaudio/best[height<=240]/best",
        "description": "أدنى جودة - حجم صغير",
    },
    {
        "label": "360p",
        "format": "bestvideo[height<=360]+bestaudio/best[height<=360]/best",
        "description": "جودة منخفضة - حجم متوسط",
    },
    {
        "label": "480p",
        "format": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
        "description": "جودة متوسطة",
    },
    {
        "label": "720p",
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "description": "جودة عالية HD",
    },
    {
        "label": "1080p",
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "description": "جودة عالية جداً Full HD",
    },
    {
        "label": "Best",
        "format": "bestvideo+bestaudio/best",
        "description": "أعلى جودة متاحة",
    },
]

# ============================================================
# إعدادات الترجمة والـ Prompt
# ============================================================
# Prompt حرفي كما طلب المستخدم - لا يُعدّل
TRANSLATION_SYSTEM_PROMPT: Final[str] = (
    "أنت خبير دبلجة وترجمة مسلسلات تركية إلى العربية.\n"
    "ترجم المعنى وليس الكلمات.\n"
    "اكتب عربية فصحى طبيعية.\n"
    "لا تستخدم ترجمة حرفية.\n"
    "إذا كانت كلمة Blue أو Mavi يقصد بها الاكتئاب فاكتب الاكتئاب.\n"
    "إذا كانت اسماً فلا تترجمها.\n"
    "صحح الأخطاء التالية:\n"
    "مملوءة → مليئة\n"
    "إتفقنا → اتّفقنا\n"
    "ياصديقي → يا صديقي\n"
    "صلوا أن → ادعوا أن\n"
    "اللون الأزرق → الاكتئاب (إذا كان السياق يدل على ذلك)\n"
    "لا تترجم\n"
    "NAME_X\n"
    "وأخرج الترجمة فقط."
)

# ============================================================
# إعدادات إدارة الحالة
# ============================================================
# قاموس جلسات المستخدمين في الذاكرة فقط (لا قاعدة بيانات)
# user_sessions: Dict[int, Dict[str, Any]] = {}
# يتم استيراده من handlers.py مباشرة

# الخطوات الممكنة في جلسة المستخدم
STEP_IDLE: Final[str] = "idle"
STEP_WAITING_QUALITY: Final[str] = "waiting_quality"
STEP_DOWNLOADING: Final[str] = "downloading"
STEP_VIDEO_SENT: Final[str] = "video_sent"
STEP_TRANSCRIBING: Final[str] = "transcribing"
STEP_SRT_SENT: Final[str] = "srt_sent"
STEP_TRANSLATING: Final[str] = "translating"
STEP_TRANSLATION_SENT: Final[str] = "translation_sent"

# ============================================================
# إعدادات الشبكة وإعادة المحاولة
# ============================================================
MAX_RETRIES: Final[int] = 3
RETRY_DELAY_SECONDS: Final[float] = 2.0
OPERATION_TIMEOUT_SECONDS: Final[int] = 3600  # ساعة كاملة للعمليات الطويلة

# ============================================================
# إعدادات اللغة والواجهة
# ============================================================
BOT_LANGUAGE: Final[str] = "ar"
BOT_NAME: Final[str] = "AI Translation Bot"
BOT_DESCRIPTION: Final[str] = (
    "بوت تيليجرام لتحميل المقاطع التركية وتفريغها وترجمتها إلى العربية باستخدام الذكاء الاصطناعي"
)


def validate_config() -> None:
    """يتحقق من صحة الإعدادات الحرجة قبل تشغيل البوت."""
    errors: List[str] = []
    if API_ID == 0:
        errors.append("API_ID غير مضبوط. اضبط متغير البيئة API_ID.")
    if not API_HASH:
        errors.append("API_HASH غير مضبوط. اضبط متغير البيئة API_HASH.")
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN غير مضبوط. اضبط متغير البيئة BOT_TOKEN.")
    if errors:
        raise EnvironmentError("\n".join(errors))


# تصدير مختصر لخيارات الجودة كقاموس label → format
QUALITY_FORMAT_MAP: Final[Dict[str, str]] = {
    opt["label"]: opt["format"] for opt in QUALITY_OPTIONS
}
