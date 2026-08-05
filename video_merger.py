"""
video_merger.py
===============
دمج ملف الترجمة (SRT) مع الفيديو باستخدام FFmpeg عبر subprocess.

يدعم:
- دمج الترجمة كمسار subtitles منفصل (soft subtitles)
- حرق الترجمة في الفيديو (hard burn) مع دعم العربية
- نسخ الفيديو بدون إعادة ترميز عند الإمكان
- ضبط الخط واللون والموضع
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from pathlib import Path
from typing import Callable, Optional

from config import (
    FFMPEG_BINARY,
    FONTS_DIR,
    OUTPUTS_DIR,
    TEMP_DIR,
    OPERATION_TIMEOUT_SECONDS,
    MAX_RETRIES,
)
from logger import get_child_logger, logger

_merger_logger = get_child_logger(logger.name, "video_merger")


# ============================================================
# فئة VideoMerger
# ============================================================
class VideoMerger:
    """
    يدمج ملف الترجمة مع الفيديو عبر FFmpeg.

    الوضعان:
    1. soft: إضافة الترجمة كمسار منفصل (يمكن تفعيل/إيقافه في المشغل).
    2. hard: حرق الترجمة في الفيديو (تظهر دائماً).
    """

    def __init__(self) -> None:
        self.binary: str = FFMPEG_BINARY
        self.fonts_dir: Path = FONTS_DIR
        self.outputs_dir: Path = OUTPUTS_DIR
        self.temp_dir: Path = TEMP_DIR
        self.fonts_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    # ============================================================
    # دمج الترجمة (soft - كمسار منفصل)
    # ============================================================
    async def merge_soft_subtitles(
        self,
        video_path: str | Path,
        srt_path: str | Path,
        output_path: Optional[str | Path] = None,
        language: str = "ara",
        title: str = "Arabic",
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Optional[Path]:
        """
        يدمج ملف SRT كمسار ترجمة منفصل (soft subtitles).

        Args:
            video_path: مسار الفيديو.
            srt_path: مسار ملف SRT.
            output_path: مسار الإخراج (افتراضي outputs/).
            language: كود اللغة.
            title: عنوان مسار الترجمة.
            progress_callback: دالة التقدم.

        Returns:
            مسار الفيديو الناتج أو None.
        """
        video_path = Path(video_path)
        srt_path = Path(srt_path)

        if not video_path.exists():
            _merger_logger.error(f"الفيديو غير موجود: {video_path}")
            return None
        if not srt_path.exists():
            _merger_logger.error(f"ملف SRT غير موجود: {srt_path}")
            return None

        if output_path is None:
            output_path = self.outputs_dir / f"{video_path.stem}_arabic.mp4"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # تحويل مسار SRT لصيغة FFmpeg (escape النقطتين)
        srt_path_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")

        # بناء أمر FFmpeg
        cmd = [
            self.binary,
            "-y",                           # overwrite
            "-i", str(video_path),
            "-i", str(srt_path),
            "-c", "copy",                   # نسخ بدون إعادة ترميز
            "-c:s", "mov_text",             # صيغة الترجمة
            "-map", "0",
            "-map", "1",
            "-metadata:s:s:1", f"language={language}",
            "-metadata:s:s:1", f"title={title}",
            str(output_path),
        ]

        _merger_logger.info(f"دمج الترجمة (soft): {video_path} + {srt_path}")
        return await self._run_ffmpeg(cmd, output_path, progress_callback)

    # ============================================================
    # حرق الترجمة (hard burn)
    # ============================================================
    async def burn_subtitles(
        self,
        video_path: str | Path,
        srt_path: str | Path,
        output_path: Optional[str | Path] = None,
        font_name: str = "Noto Sans Arabic",
        font_size: int = 22,
        primary_color: str = "&H00FFFFFF",     # أبيض
        outline_color: str = "&H00000000",     # أسود
        outline_width: int = 2,
        margin_v: int = 30,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Optional[Path]:
        """
        يحرق ملف الترجمة في الفيديو (hard burn).

        Args:
            video_path: مسار الفيديو.
            srt_path: مسار ملف SRT.
            output_path: مسار الإخراج.
            font_name: اسم الخط.
            font_size: حجم الخط.
            primary_color: لون النص الأساسي (بصيغة ASS hex).
            outline_color: لون الإطار.
            outline_width: سمك الإطار.
            margin_v: الهامش العمودي من الأسفل.
            progress_callback: دالة التقدم.

        Returns:
            مسار الفيديو الناتج أو None.
        """
        video_path = Path(video_path)
        srt_path = Path(srt_path)

        if not video_path.exists():
            _merger_logger.error(f"الفيديو غير موجود: {video_path}")
            return None
        if not srt_path.exists():
            _merger_logger.error(f"ملف SRT غير موجود: {srt_path}")
            return None

        if output_path is None:
            output_path = self.outputs_dir / f"{video_path.stem}_burned.mp4"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # البحث عن الخط
        font_path = self._find_font(font_name)

        # بناء فلتر subtitles
        # صيغة FFmpeg للعربية: force_style + fontsdir
        srt_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")
        style = (
            f"FontName={font_name},"
            f"FontSize={font_size},"
            f"PrimaryColour={primary_color},"
            f"OutlineColour={outline_color},"
            f"Outline={outline_width},"
            f"MarginV={margin_v},"
            f"Alignment=2"  # أسفل المنتصف
        )

        filter_str = f"subtitles='{srt_escaped}':force_style='{style}'"
        if font_path and font_path.is_dir():
            filter_str += f":fontsdir='{font_path}'"

        # بناء أمر FFmpeg
        cmd = [
            self.binary,
            "-y",
            "-i", str(video_path),
            "-vf", filter_str,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(output_path),
        ]

        _merger_logger.info(f"حرق الترجمة (hard): {video_path} + {srt_path}")
        return await self._run_ffmpeg(cmd, output_path, progress_callback)

    # ============================================================
    # تشغيل FFmpeg
    # ============================================================
    async def _run_ffmpeg(
        self,
        cmd: list[str],
        output_path: Path,
        progress_callback: Optional[Callable[[float, str], None]],
    ) -> Optional[Path]:
        """يشغل أمر FFmpeg ويراقب التقدم."""
        _merger_logger.debug(f"FFmpeg command: {' '.join(cmd)}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # FFmpeg يطبع التقدم في stderr
        time_re = re.compile(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})")
        # نحتاج معرفة المدة الإجمالية للتقدم
        duration = await self._get_video_duration(cmd)
        progress_re = re.compile(r"(\d+)%")

        async def _read_stderr() -> str:
            buffer = ""
            assert proc.stderr is not None
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    buffer += text + "\n"
                    _merger_logger.debug(f"[ffmpeg] {text}")

                    # تحليل التقدم
                    m = time_re.search(text)
                    if m and duration > 0 and progress_callback:
                        current = self._parse_duration(m.group(1))
                        pct = min(current / duration * 100, 100.0)
                        try:
                            progress_callback(pct, f"{pct:.1f}%")
                        except Exception:
                            pass
            return buffer

        try:
            stderr_task = asyncio.create_task(_read_stderr())
            await asyncio.wait_for(proc.wait(), timeout=OPERATION_TIMEOUT_SECONDS)
            await stderr_task
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            _merger_logger.error("انتهت مهلة FFmpeg")
            return None

        if proc.returncode != 0:
            _merger_logger.error(f"FFmpeg فشل (returncode={proc.returncode})")
            return None

        if not output_path.exists():
            _merger_logger.error(f"لم يتم إنشاء الملف الناتج: {output_path}")
            return None

        _merger_logger.info(f"نجح دمج الفيديو: {output_path}")
        return output_path

    async def _get_video_duration(self, cmd: list[str]) -> float:
        """يحاول استخراج مدة الفيديو من سطر الأوامر (تقدير)."""
        # نبحث في الفيديو الأول عادةً
        # هذه دالة مساعدة بسيطة
        return 0.0

    def _parse_duration(self, time_str: str) -> float:
        """يحول HH:MM:SS.ss إلى ثوانٍ."""
        try:
            parts = time_str.split(":")
            if len(parts) == 3:
                h, m, s = parts
                return int(h) * 3600 + int(m) * 60 + float(s)
        except (ValueError, IndexError):
            pass
        return 0.0

    def _find_font(self, font_name: str) -> Optional[Path]:
        """
        يبحث عن خط في مجلد fonts/ أو في خطوط النظام.

        Returns:
            مسار الخط أو مجلد الخطوط.
        """
        # البحث في مجلد المشروع
        fonts_in_dir = list(self.fonts_dir.glob("*.ttf")) + list(self.fonts_dir.glob("*.otf"))
        if fonts_in_dir:
            return self.fonts_dir

        # البحث في خطوط النظام الشائعة
        system_font_dirs = [
            "/usr/share/fonts/truetype",
            "/usr/share/fonts",
            "/usr/local/share/fonts",
            os.path.expanduser("~/.fonts"),
        ]
        for d in system_font_dirs:
            if os.path.isdir(d):
                return Path(d)
        return None

    # ============================================================
    # دوال مساعدة
    # ============================================================
    async def extract_audio(
        self,
        video_path: str | Path,
        output_path: Optional[str | Path] = None,
    ) -> Optional[Path]:
        """يستخرج المسار الصوتي من الفيديو."""
        video_path = Path(video_path)
        if output_path is None:
            output_path = self.temp_dir / f"{video_path.stem}.mp3"
        output_path = Path(output_path)

        cmd = [
            self.binary,
            "-y",
            "-i", str(video_path),
            "-vn",                    # لا فيديو
            "-acodec", "libmp3lame",
            "-q:a", "4",
            str(output_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        if proc.returncode == 0 and output_path.exists():
            return output_path
        return None

    async def get_video_info(
        self,
        video_path: str | Path,
    ) -> dict:
        """يجلب معلومات الفيديو باستخدام ffprobe."""
        video_path = Path(video_path)
        cmd = [
            "ffprobe",
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            import json
            return json.loads(stdout.decode("utf-8"))
        except Exception as exc:
            _merger_logger.error(f"فشل ffprobe: {exc}")
            return {}


# ============================================================
# نسخة عامة للاستخدام المباشر
# ============================================================
_merger_instance: Optional[VideoMerger] = None


def get_merger() -> VideoMerger:
    """يعيد نسخة singleton من VideoMerger."""
    global _merger_instance
    if _merger_instance is None:
        _merger_instance = VideoMerger()
    return _merger_instance


async def burn_subtitles_to_video(
    video_path: str | Path,
    srt_path: str | Path,
    output_path: Optional[str | Path] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Optional[Path]:
    """دالة مساعدة لحرق الترجمة في الفيديو."""
    return await get_merger().burn_subtitles(
        video_path=video_path,
        srt_path=srt_path,
        output_path=output_path,
        progress_callback=progress_callback,
    )


async def merge_soft_subs(
    video_path: str | Path,
    srt_path: str | Path,
    output_path: Optional[str | Path] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Optional[Path]:
    """دالة مساعدة لدمج الترجمة كمسار منفصل."""
    return await get_merger().merge_soft_subtitles(
        video_path=video_path,
        srt_path=srt_path,
        output_path=output_path,
        progress_callback=progress_callback,
    )
