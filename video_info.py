"""
video_info.py
=============
يجلب معلومات الفيديو (العنوان، المدة، الحجم، الصيغ المتاحة)
باستخدام yt-dlp عبر subprocess فقط.

لا يستخدم مكتبة yt_dlp Python مباشرة، فقط subprocess.
"""

from __future__ import annotations

import asyncio
import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import YT_DLP_BINARY, OPERATION_TIMEOUT_SECONDS
from logger import get_child_logger, logger

_video_info_logger = get_child_logger(logger.name, "video_info")


@dataclass
class VideoInfo:
    """بيانات الفيديو المستخرجة من yt-dlp."""

    title: str = ""
    duration_seconds: float = 0.0
    uploader: str = ""
    uploader_url: str = ""
    view_count: int = 0
    like_count: int = 0
    description: str = ""
    thumbnail_url: str = ""
    webpage_url: str = ""
    extractor: str = ""
    formats: List[Dict[str, Any]] = field(default_factory=list)
    best_format_id: str = ""
    estimated_size_mb: float = 0.0

    def to_display(self) -> str:
        """يعرض معلومات الفيديو في صيغة مقروءة."""
        lines: List[str] = []

        if self.title:
            lines.append(f"🎬 العنوان: {self.title}")
        if self.uploader:
            lines.append(f"👤 القناة: {self.uploader}")
        if self.duration_seconds > 0:
            mins = int(self.duration_seconds // 60)
            secs = int(self.duration_seconds % 60)
            lines.append(f"⏱️ المدة: {mins:02d}:{secs:02d}")
        if self.view_count > 0:
            lines.append(f"👁️ المشاهدات: {self.view_count:,}")
        if self.like_count > 0:
            lines.append(f"👍 الإعجابات: {self.like_count:,}")
        if self.estimated_size_mb > 0:
            lines.append(f"📦 الحجم المتوقع: {self.estimated_size_mb:.1f} MB")
        if self.extractor:
            lines.append(f"🔗 المصدر: {self.extractor}")
        if self.webpage_url:
            lines.append(f"🌐 الرابط: {self.webpage_url}")

        return "\n".join(lines)


def _is_valid_url(url: str) -> bool:
    """يتحقق من صحة رابط الفيديو."""
    if not url or not isinstance(url, str):
        return False
    # أنماط روابط شائعة
    patterns = [
        r"^https?://(www\.)?youtube\.com/watch\?v=",
        r"^https?://youtu\.be/",
        r"^https?://(www\.)?instagram\.com/",
        r"^https?://(www\.)?tiktok\.com/",
        r"^https?://(www\.)?vimeo\.com/",
        r"^https?://(www\.)?dailymotion\.com/",
        r"^https?://(www\.)?facebook\.com/",
        r"^https?://(www\.)?twitter\.com/",
        r"^https?://(www\.)?x\.com/",
        r"^https?://",
    ]
    return any(re.match(p, url.strip()) for p in patterns)


async def get_video_info(url: str) -> Optional[VideoInfo]:
    """
    يجلب معلومات الفيديو باستخدام yt-dlp --dump-json.

    Args:
        url: رابط الفيديو.

    Returns:
        كائن VideoInfo أو None عند الفشل.
    """
    if not _is_valid_url(url):
        _video_info_logger.error(f"رابط غير صالح: {url}")
        return None

    # بناء أمر yt-dlp لجلب البيانات فقط بدون تحميل
    cmd = [
        YT_DLP_BINARY,
        "--dump-json",          # إخراج JSON
        "--no-warnings",
        "--no-playlist",        # تحميل فيديو واحد فقط
        "--skip-download",      # بدون تحميل
        url,
    ]

    _video_info_logger.info(f"جلب معلومات الفيديو: {url}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=OPERATION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            _video_info_logger.error("انتهت مهلة جلب معلومات الفيديو")
            return None

        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace") if stderr else ""
            _video_info_logger.error(
                f"فشل yt-dlp (returncode={proc.returncode}): {error_msg[:500]}"
            )
            return None

        if not stdout:
            _video_info_logger.error("إخراج فارغ من yt-dlp")
            return None

        # yt-dlp قد يخرج عدة أسطر JSON للـ playlist
        first_line = stdout.decode("utf-8", errors="replace").strip().split("\n")[0]
        data = json.loads(first_line)

        return _parse_ytdlp_json(data)

    except json.JSONDecodeError as exc:
        _video_info_logger.error(f"فشل تحليل JSON: {exc}")
        return None
    except FileNotFoundError:
        _video_info_logger.error(f"yt-dlp غير مثبت: {YT_DLP_BINARY}")
        return None
    except Exception as exc:
        _video_info_logger.error(f"خطأ غير متوقع: {exc}", exc_info=True)
        return None


def _parse_ytdlp_json(data: Dict[str, Any]) -> VideoInfo:
    """يحلل JSON المستخرج من yt-dlp إلى كائن VideoInfo."""
    info = VideoInfo()
    info.title = data.get("title", "")
    info.duration_seconds = float(data.get("duration", 0) or 0)
    info.uploader = data.get("uploader", "") or data.get("channel", "")
    info.uploader_url = data.get("uploader_url", "")
    info.view_count = int(data.get("view_count", 0) or 0)
    info.like_count = int(data.get("like_count", 0) or 0)
    info.description = data.get("description", "") or ""
    info.thumbnail_url = data.get("thumbnail", "")
    info.webpage_url = data.get("webpage_url", "") or data.get("original_url", "")
    info.extractor = data.get("extractor", "") or data.get("extractor_key", "")
    info.formats = data.get("formats", []) or []

    # محاولة تقدير الحجم
    filesize = data.get("filesize") or data.get("filesize_approx")
    if filesize:
        info.estimated_size_mb = float(filesize) / (1024 * 1024)
    else:
        # محاولة أخذ أفضل صيغة
        if info.formats:
            best = info.formats[-1]
            fsize = best.get("filesize") or best.get("filesize_approx")
            if fsize:
                info.estimated_size_mb = float(fsize) / (1024 * 1024)
            info.best_format_id = str(best.get("format_id", ""))

    return info


async def get_available_formats(url: str) -> List[Dict[str, Any]]:
    """
    يجلب قائمة الصيغ المتاحة للفيديو.

    Args:
        url: رابط الفيديو.

    Returns:
        قائمة بصيغ الفيديو المتاحة.
    """
    info = await get_video_info(url)
    if info is None:
        return []
    return info.formats


async def validate_url(url: str) -> bool:
    """يتحقق من أن الرابط صالح وفيديو متاح للتحميل."""
    info = await get_video_info(url)
    return info is not None and bool(info.title)


def format_size(bytes_size: int) -> str:
    """صياغة حجم الملف."""
    if bytes_size <= 0:
        return "غير معروف"
    units = ["B", "KB", "MB", "GB"]
    size = float(bytes_size)
    for unit in units:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
