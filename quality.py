"""
quality.py
==========
إدارة خيارات الجودة وتوافقها مع yt-dlp.

يربط بين:
- اسم الجودة (240p, 360p, 480p, 720p, 1080p, Best)
- صيغة yt-dlp المناسبة
- الوصف المعروض للمستخدم
"""

from __future__ import annotations

from typing import Dict, List, Optional

from config import QUALITY_OPTIONS, QUALITY_FORMAT_MAP
from logger import get_child_logger, logger

_quality_logger = get_child_logger(logger.name, "quality")


def get_all_qualities() -> List[str]:
    """يعيد قائمة بأسماء جميع الجودات المدعومة."""
    return [opt["label"] for opt in QUALITY_OPTIONS]


def get_format_for_quality(quality_label: str) -> Optional[str]:
    """
    يعيد صيغة yt-dlp المناسبة لجودة معينة.

    Args:
        quality_label: اسم الجودة (مثل "720p" أو "Best").

    Returns:
        صيغة yt-dlp أو None إذا كانت الجودة غير معروفة.
    """
    fmt = QUALITY_FORMAT_MAP.get(quality_label)
    if fmt is None:
        _quality_logger.warning(f"جودة غير معروفة: {quality_label}")
    return fmt


def get_quality_description(quality_label: str) -> Optional[str]:
    """يعيد وصف الجودة المعروض للمستخدم."""
    for opt in QUALITY_OPTIONS:
        if opt["label"] == quality_label:
            return opt["description"]
    return None


def get_quality_info(quality_label: str) -> Optional[Dict[str, str]]:
    """
    يعيد معلومات كاملة عن جودة معينة.

    Returns:
        قاموس يحتوي على label, format, description أو None.
    """
    for opt in QUALITY_OPTIONS:
        if opt["label"] == quality_label:
            return dict(opt)
    return None


def is_valid_quality(quality_label: str) -> bool:
    """يتحقق إذا كانت الجودة موجودة في قائمتنا."""
    return quality_label in QUALITY_FORMAT_MAP


def get_default_quality() -> str:
    """يعيد الجودة الافتراضية (720p)."""
    return "720p"


def build_ytdlp_format_args(quality_label: str) -> List[str]:
    """
    يبني وسائط yt-dlp لخيار الجودة المختار.

    Args:
        quality_label: اسم الجودة.

    Returns:
        قائمة وسائط سطر الأوامر لـ yt-dlp (مثل ["-f", "bestvideo[height<=720]+bestaudio/best"]).
    """
    fmt = get_format_for_quality(quality_label)
    if fmt is None:
        _quality_logger.warning(
            f"جودة غير معروفة '{quality_label}'، استخدام الافتراضية 720p"
        )
        fmt = get_format_for_quality(get_default_quality())
    return ["-f", fmt]


def get_quality_summary() -> str:
    """يعيد ملخصاً نصياً لكل خيارات الجودة (للعرض في الرسائل)."""
    lines: List[str] = ["📊 خيارات الجودة المتاحة:\n"]
    for opt in QUALITY_OPTIONS:
        lines.append(f"• {opt['label']}: {opt['description']}")
    return "\n".join(lines)


def validate_quality_for_size(quality_label: str, estimated_size_mb: float) -> bool:
    """
    يتحقق إذا كانت الجودة مناسبة لحجم متوقع.

    للملفات الكبيرة جداً، نقترح جودة أقل.

    Args:
        quality_label: الجودة المختارة.
        estimated_size_mb: الحجم المتوقع بالميجابايت.

    Returns:
        True إذا كانت مناسبة، False إذا كان يُنصح بتخفيض الجودة.
    """
    # عتبات بسيطة
    thresholds = {
        "1080p": 1500,
        "720p": 1000,
        "480p": 500,
        "360p": 200,
        "240p": 100,
        "Best": 2000,
    }
    threshold = thresholds.get(quality_label, 1000)
    return estimated_size_mb <= threshold


def suggest_lower_quality(quality_label: str) -> Optional[str]:
    """يقترح جودة أقل مباشرة من المعطاة."""
    order = [opt["label"] for opt in QUALITY_OPTIONS]
    try:
        idx = order.index(quality_label)
        if idx > 0:
            return order[idx - 1]
    except ValueError:
        pass
    return None
