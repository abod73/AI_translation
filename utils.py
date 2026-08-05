"""
utils.py
========
أدوات مساعدة عامة للمشروع.

أهم الدوال:
- merge_segments(): يدمج المقاطع التي الفرق بينها <= 0.5 ثانية.
- format_time(): يحوّل الثواني إلى صيغة SRT (HH:MM:SS,mmm).
- parse_time(): يحوّل صيغة SRT الزمنية إلى ثوانٍ.
- get_file_size(): يجلب حجم ملف.
- clean_temp_files(): يحذف الملفات المؤقتة.
- safe_filename(): ينظّف اسم الملف من الرموز غير الصالحة.
"""

from __future__ import annotations

import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from logger import get_child_logger, logger
from config import TEMP_DIR

_utils_logger = get_child_logger(logger.name, "utils")


# ============================================================
# تحويل الأزمنة
# ============================================================
def format_time(seconds: float) -> str:
    """
    يحوّل عدد الثواني إلى صيغة SRT الزمنية: HH:MM:SS,mmm

    Args:
        seconds: الزمن بالثواني (قد يكون كسرياً).

    Returns:
        نص بصيغة HH:MM:SS,mmm

    Example:
        >>> format_time(3661.5)
        '01:01:01,500'
    """
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def parse_time(time_str: str) -> float:
    """
    يحوّل صيغة SRT الزمنية إلى عدد الثواني.

    Args:
        time_str: نص بصيغة HH:MM:SS,mmm أو HH:MM:SS.mmm

    Returns:
        الزمن بالثواني كعدد عشري.

    Example:
        >>> parse_time("01:01:01,500")
        3661.5
    """
    time_str = time_str.strip().replace(",", ".")
    parts = time_str.split(":")
    if len(parts) != 3:
        raise ValueError(f"صيغة زمن غير صالحة: {time_str}")
    hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


# ============================================================
# دالة merge_segments المطلوبة
# ============================================================
def merge_segments(
    segments: List[Dict[str, Any]],
    max_gap: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    يدمج المقاطع التي الفرق بين نهاية أحدها وبداية الذي يليه
    أقل أو يساوي max_gap ثانية.

    كل مقطع هو قاموس يحتوي على:
        - start: بداية المقطع (ثوانٍ)
        - end: نهاية المقطع (ثوانٍ)
        - text: نص المقطع
        - (اختياري) index: رقم المقطع

    Args:
        segments: قائمة المقاطع.
        max_gap: أقصى فرق بالثواني للدمج (افتراضي 0.5).

    Returns:
        قائمة مقاطع مدموجة جديدة.
    """
    if not segments:
        return []

    # ننسخ القائمة لتفادي تعديل الأصل
    merged: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {
        "start": segments[0]["start"],
        "end": segments[0]["end"],
        "text": segments[0]["text"].strip(),
    }

    for seg in segments[1:]:
        gap = seg["start"] - current["end"]
        if gap <= max_gap:
            # الدمج: نمدد النهاية ونضيف النص مع فراغ
            current["end"] = max(current["end"], seg["end"])
            seg_text = seg["text"].strip()
            if seg_text:
                current["text"] = (current["text"] + " " + seg_text).strip()
        else:
            merged.append(current)
            current = {
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
            }

    merged.append(current)

    # إعادة ترقيم المقاطع
    for i, seg in enumerate(merged, start=1):
        seg["index"] = i

    _utils_logger.debug(
        f"merge_segments: {len(segments)} → {len(merged)} مقطع (max_gap={max_gap})"
    )
    return merged


# ============================================================
# أدوات الملفات
# ============================================================
def get_file_size(file_path: str | Path) -> int:
    """يجلب حجم ملف بالبايتات. يعيد 0 إذا لم يكن موجوداً."""
    path = Path(file_path)
    if not path.exists():
        return 0
    return path.stat().st_size


def format_file_size(size_bytes: int) -> str:
    """يحول حجم البايتات إلى صيغة مقروءة."""
    if size_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(size_bytes)
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"


def safe_filename(filename: str) -> str:
    """
    ينظّف اسم الملف من الرموز غير الصالحة في أنظمة الملفات.

    يحافظ على الحروف العربية واللاتينية والأرقام والشرطات.
    """
    # تطبيع اليونيكود
    filename = unicodedata.normalize("NFC", filename)
    # إزالة الرموز غير المرغوبة مع الإبقاء على العربية واللاتينية والأرقام
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename)
    # تقليص الفراغات المتعددة
    filename = re.sub(r"\s+", " ", filename).strip()
    # تحديد الطول الأقصى
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[: 200 - len(ext)] + ext
    return filename or "untitled"


def clean_temp_files(pattern: str = "*") -> None:
    """يحذف كل الملفات المؤقتة المطابقة للنمط."""
    if not TEMP_DIR.exists():
        return
    deleted = 0
    for item in TEMP_DIR.glob(pattern):
        try:
            if item.is_file():
                item.unlink()
                deleted += 1
            elif item.is_dir():
                # حذف محتويات المجلد الفرعي
                for sub in item.rglob("*"):
                    if sub.is_file():
                        sub.unlink()
                item.rmdir()
                deleted += 1
        except Exception as exc:
            _utils_logger.warning(f"تعذر حذف {item}: {exc}")
    _utils_logger.info(f"تم حذف {deleted} ملف/مجلد مؤقت")


def ensure_parent_dir(file_path: str | Path) -> Path:
    """يتأكد من وجود المجلد الأب للملف."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# ============================================================
# أدوات النصوص
# ============================================================
def split_text_into_chunks(
    text: str,
    max_length: int = 1000,
    separator: str = "\n",
) -> List[str]:
    """
    يقسم نصاً طويلاً إلى أجزاء لا تتجاوز max_length حرفاً.

    يحاول القسمة عند الفواصل الطبيعية (أسطر، جمل).
    """
    if len(text) <= max_length:
        return [text]

    chunks: List[str] = []
    current = ""

    for line in text.split(separator):
        if len(current) + len(line) + len(separator) <= max_length:
            current = (current + separator + line) if current else line
        else:
            if current:
                chunks.append(current)
            # إذا كان السطر نفسه أطول من الحد الأقصى، نقسمه بالقوة
            if len(line) > max_length:
                for i in range(0, len(line), max_length):
                    chunks.append(line[i : i + max_length])
                current = ""
            else:
                current = line

    if current:
        chunks.append(current)

    return chunks


def normalize_arabic_text(text: str) -> str:
    """يطبّع النص العربي (إزالة التشكيل، توحيد الألف)."""
    # إزالة التشكيل
    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)
    # توحيد الألف
    text = re.sub(r"[إأآا]", "ا", text)
    # توحيد الياء
    text = re.sub(r"[ىي]", "ي", text)
    # توحيد الهاء
    text = re.sub(r"ة", "ه", text)
    return text


def is_arabic_text(text: str) -> bool:
    """يتحقق إذا كان النص يحتوي على حروف عربية بشكل أساسي."""
    if not text:
        return False
    arabic_chars = len(re.findall(r"[\u0600-\u06FF]", text))
    latin_chars = len(re.findall(r"[a-zA-Z]", text))
    return arabic_chars > latin_chars


# ============================================================
# أدوات التوقيت
# ============================================================
def wait_with_timeout(
    condition_fn,
    timeout: float = 60.0,
    interval: float = 0.5,
) -> bool:
    """
    ينتظر تحقق شرط معين مع مهلة زمنية.

    Args:
        condition_fn: دالة ترجع True/False.
        timeout: أقصى مدة انتظار بالثواني.
        interval: الفاصل بين الفحوصات.

    Returns:
        True إذا تحقق الشرط، False إذا انتهت المهلة.
    """
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if condition_fn():
            return True
        time.sleep(interval)
    return False


def chunk_list(items: List[Any], chunk_size: int) -> List[List[Any]]:
    """يقسم قائمة إلى دفعات بحجم chunk_size."""
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def extract_name_placeholder(text: str) -> Tuple[str, List[str]]:
    """
    يستخرج علامات NAME_X من النص ويستبدلها ب placeholders موحدة.

    Returns:
        (النص بعد الاستبدال, قائمة الأسماء الأصلية)
    """
    names: List[str] = []

    def _replace(match: re.Match) -> str:
        names.append(match.group(0))
        return f"__NAME_{len(names) - 1}__"

    replaced = re.sub(r"NAME_\d+", _replace, text)
    return replaced, names


def restore_name_placeholders(text: str, names: List[str]) -> str:
    """يعيد الأسماء إلى مواضعها بعد الترجمة."""
    for i, name in enumerate(names):
        text = text.replace(f"__NAME_{i}__", name)
    return text
