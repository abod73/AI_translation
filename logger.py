"""
logger.py
=========
إعداد التسجيل (Logging) المركزي للمشروع.

- يسجل إلى ملف في logs/bot.log
- يسجل إلى الـ console بألوان
- يدعم التدوير التلقائي للملفات
- صيغة موحدة لكل الرسائل
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path
from typing import Final

from config import LOGS_DIR, BOT_NAME


# صيغة السجل الموحدة
LOG_FORMAT: Final[str] = (
    "%(asctime)s | %(name)-25s | %(levelname)-8s | %(message)s"
)
DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"

# ألوان الـ console لكل مستوى
class ColorFormatter(logging.Formatter):
    """ملون مخصص لمخرجات الـ console."""

    COLORS: dict[int, str] = {
        logging.DEBUG: "\033[36m",      # سماوي
        logging.INFO: "\033[32m",       # أخضر
        logging.WARNING: "\033[33m",    # أصفر
        logging.ERROR: "\033[31m",      # أحمر
        logging.CRITICAL: "\033[41m",   # خلفية حمراء
    }
    RESET: Final[str] = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, self.RESET)
        record.levelname = f"{color}{record.levelname:<8}{self.RESET}"
        return super().format(record)


def setup_logger(name: str = BOT_NAME, level: int = logging.INFO) -> logging.Logger:
    """
    ينشئ ويعيد مسجلاً جاهزاً للاستخدام.

    Args:
        name: اسم المسجل.
        level: مستوى التسجيل (افتراضي INFO).

    Returns:
        logging.Logger جاهز للاستخدام.
    """
    # التأكد من وجود مجلد السجلات
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file: Path = LOGS_DIR / "bot.log"

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    # منع إضافة الـ handlers مرتين
    if logger.handlers:
        return logger

    # المعالج الخاص بالملف مع التدوير
    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=10 * 1024 * 1024,  # 10 ميجابايت
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

    # المعالج الخاص بالـ console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(
        ColorFormatter(LOG_FORMAT, DATE_FORMAT)
    )

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_child_logger(parent_name: str, child_name: str) -> logging.Logger:
    """
    ينشئ مسجلاً فرعياً تابعاً لمسجل رئيسي.

    Args:
        parent_name: اسم المسجل الأب.
        child_name: اسم المسجل الفرعي.

    Returns:
        logging.Logger فرعي.
    """
    return logging.getLogger(f"{parent_name}.{child_name}")


# المسجل الافتراضي للمشروع
logger: logging.Logger = setup_logger()


def log_exception(logger: logging.Logger, message: str, exc: Exception) -> None:
    """يسجل استثناءً مع رسالة سياقية."""
    logger.error(f"{message}: {type(exc).__name__}: {exc}", exc_info=True)
