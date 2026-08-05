"""
downloader.py
=============
تحميل الفيديو باستخدام yt-dlp عبر subprocess فقط.

لا يستخدم مكتبة yt_dlp Python مباشرة.
الأمر المنفذ:
    yt-dlp -f "[format]" -o downloads/video.mp4 "URL"
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from typing import Callable, Optional

from config import (
    YT_DLP_BINARY,
    DOWNLOADS_DIR,
    OPERATION_TIMEOUT_SECONDS,
    TELEGRAM_MAX_SIZE_BYTES,
)
from logger import get_child_logger, logger
from quality import get_format_for_quality, get_default_quality
from utils import safe_filename, get_file_size, format_file_size

_downloader_logger = get_child_logger(logger.name, "downloader")


# ============================================================
# فئة Downloader
# ============================================================
class VideoDownloader:
    """
    يحمّل الفيديوهات باستخدام yt-dlp عبر subprocess.

    يدير:
    - اختيار الصيغة بناءً على الجودة المطلوبة
    - مراقبة التقدم
    - إعادة المحاولة عند الفشل
    - تنظيف الملفات القديمة
    """

    def __init__(self) -> None:
        self.download_dir: Path = DOWNLOADS_DIR
        self.download_dir.mkdir(parents=True, exist_ok=True)

    async def download(
        self,
        url: str,
        quality_label: str,
        output_filename: str = "video.mp4",
        progress_callback: Optional[Callable[[float, str], None]] = None,
        max_retries: int = 3,
    ) -> Optional[Path]:
        """
        يحمّل الفيديو بالجودة المحددة.

        Args:
            url: رابط الفيديو.
            quality_label: اسم الجودة (مثل "720p" أو "Best").
            output_filename: اسم الملف الناتج.
            progress_callback: دالة تُستدعى بنسبة التقدم (0-100) ونص.
            max_retries: عدد محاولات إعادة المحاولة.

        Returns:
            مسار الملف المحمّل أو None عند الفشل.
        """
        # التحقق من الجودة
        fmt = get_format_for_quality(quality_label)
        if fmt is None:
            _downloader_logger.warning(
                f"جودة غير معروفة '{quality_label}'، استخدام {get_default_quality()}"
            )
            fmt = get_format_for_quality(get_default_quality())

        # اسم الملف الناتج
        safe_name = safe_filename(output_filename)
        if not safe_name.endswith(".mp4"):
            safe_name += ".mp4"
        output_path = self.download_dir / safe_name
        # yt-dlp يستخدم قالب المسار
        output_template = str(output_path.with_suffix(".%(ext)s"))

        # بناء الأمر - حرفياً كما طلب المستخدم:
        # yt-dlp -f "[format]" -o downloads/video.mp4 "URL"
        cmd = [
            YT_DLP_BINARY,
            "-f", fmt,
            "-o", output_template,
            "--no-playlist",
            "--no-warnings",
            "--newline",                # كل سطر تقدم في سطر جديد
            "--no-part",                # عدم استخدام ملفات .part
            url,
        ]

        _downloader_logger.info(
            f"بدء تحميل الفيديو: {url}\n"
            f"الجودة: {quality_label}\n"
            f"الصيغة: {fmt}\n"
            f"المخرج: {output_path}"
        )

        last_error: Optional[str] = None

        for attempt in range(1, max_retries + 1):
            _downloader_logger.info(f"محاولة التحميل {attempt}/{max_retries}")

            try:
                result = await self._run_download(
                    cmd, output_path, progress_callback
                )
                if result is not None:
                    _downloader_logger.info(
                        f"تم التحميل بنجاح: {result} "
                        f"({format_file_size(get_file_size(result))})"
                    )
                    # التحقق من حجم الملف
                    size = get_file_size(result)
                    if size > TELEGRAM_MAX_SIZE_BYTES:
                        _downloader_logger.warning(
                            f"حجم الملف {format_file_size(size)} يتجاوز "
                            f"الحد الأقصى {format_file_size(TELEGRAM_MAX_SIZE_BYTES)}"
                        )
                    return result
            except asyncio.TimeoutError:
                last_error = "انتهت مهلة التحميل"
                _downloader_logger.error(last_error)
            except Exception as exc:
                last_error = str(exc)
                _downloader_logger.error(f"خطأ في التحميل: {exc}", exc_info=True)

            # انتظار قبل إعادة المحاولة
            if attempt < max_retries:
                wait = 2.0 * attempt
                _downloader_logger.info(f"الانتظار {wait}s قبل إعادة المحاولة...")
                await asyncio.sleep(wait)

        _downloader_logger.error(f"فشل التحميل بعد {max_retries} محاولات. آخر خطأ: {last_error}")
        return None

    async def _run_download(
        self,
        cmd: list[str],
        output_path: Path,
        progress_callback: Optional[Callable[[float, str], None]],
    ) -> Optional[Path]:
        """يشغل أمر yt-dlp ويراقب التقدم."""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # مراقبة التقدم من stdout
        progress_re = re.compile(
            r"\[download\]\s+([0-9.]+)%\s+of\s+~?\s*([0-9.]+[KMG]?i?B)\s+at\s+([0-9.]+[KMG]?i?B/s)\s+ETA\s+([0-9:]+)"
        )
        generic_re = re.compile(r"\[download\]\s+([0-9.]+)%")

        last_progress: float = 0.0

        async def _read_stdout() -> str:
            """يقرأ stdout ويحدّث التقدم."""
            nonlocal last_progress
            buffer = ""
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                buffer += text + "\n"

                # تحليل التقدم
                m = progress_re.search(text)
                if m:
                    pct = float(m.group(1))
                    size = m.group(2)
                    speed = m.group(3)
                    eta = m.group(4)
                    if pct > last_progress:
                        last_progress = pct
                    if progress_callback:
                        msg = f"{pct:.1f}% | {size} | {speed} | ETA {eta}"
                        try:
                            progress_callback(pct, msg)
                        except Exception:
                            pass
                else:
                    m2 = generic_re.search(text)
                    if m2:
                        pct = float(m2.group(1))
                        if pct > last_progress:
                            last_progress = pct
                        if progress_callback:
                            try:
                                progress_callback(pct, f"{pct:.1f}%")
                            except Exception:
                                pass
            return buffer

        async def _read_stderr() -> str:
            """يقرأ stderr."""
            assert proc.stderr is not None
            chunks = []
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                chunks.append(line.decode("utf-8", errors="replace"))
            return "".join(chunks)

        # تشغيل القراءتين بالتوازي مع مهلة
        try:
            stdout_task = asyncio.create_task(_read_stdout())
            stderr_task = asyncio.create_task(_read_stderr())
            await asyncio.wait_for(
                proc.wait(),
                timeout=OPERATION_TIMEOUT_SECONDS,
            )
            await asyncio.gather(stdout_task, stderr_task)
            stderr_output = stderr_task.result()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise

        if proc.returncode != 0:
            _downloader_logger.error(
                f"yt-dlp فشل (returncode={proc.returncode}): "
                f"{stderr_output[:1000]}"
            )
            return None

        # إيجاد الملف الناتج (قد يكون بأي امتداد)
        # نبحث عن أي ملف في مجلد التحميل بأسماء الفيديو المتوقعة
        candidates = list(self.download_dir.glob("video.*"))
        candidates = [c for c in candidates if c.suffix.lower() in (".mp4", ".webm", ".mkv", ".m4a")]

        # إذا وجدنا أكثر من ملف، نختار الأحدث
        if candidates:
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            chosen = candidates[0]
            # إعادة تسمية إلى .mp4 إذا لزم
            if chosen.suffix.lower() != ".mp4":
                final = chosen.with_suffix(".mp4")
                chosen.rename(final)
                chosen = final
            return chosen

        # محاولة أخيرة: التحقق من المسار المتوقع
        if output_path.exists():
            return output_path

        _downloader_logger.error("لم يتم العثور على ملف الفيديو بعد التحميل")
        return None

    async def download_turkish_video(
        self,
        url: str,
        quality_label: str,
        user_id: int,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Optional[Path]:
        """
        يحمّل فيديو تركي مع تنظيف الملفات القديمة للمستخدم.

        Args:
            url: رابط الفيديو.
            quality_label: اسم الجودة.
            user_id: معرف المستخدم لتمييز الملفات.
            progress_callback: دالة التقدم.

        Returns:
            مسار الملف أو None.
        """
        # تنظيف ملفات هذا المستخدم السابقة
        for old in self.download_dir.glob(f"user_{user_id}_*"):
            try:
                old.unlink()
            except Exception:
                pass

        filename = f"user_{user_id}_video.mp4"
        return await self.download(
            url=url,
            quality_label=quality_label,
            output_filename=filename,
            progress_callback=progress_callback,
        )

    def cleanup_user_files(self, user_id: int) -> None:
        """يحذف ملفات مستخدم معين."""
        for f in self.download_dir.glob(f"user_{user_id}_*"):
            try:
                f.unlink()
                _downloader_logger.debug(f"حذف: {f}")
            except Exception as exc:
                _downloader_logger.warning(f"تعذر حذف {f}: {exc}")


# ============================================================
# نسخة عامة للاستخدام المباشر
# ============================================================
_downloader_instance: Optional[VideoDownloader] = None


def get_downloader() -> VideoDownloader:
    """يعيد نسخة singleton من VideoDownloader."""
    global _downloader_instance
    if _downloader_instance is None:
        _downloader_instance = VideoDownloader()
    return _downloader_instance


async def download_video(
    url: str,
    quality_label: str,
    user_id: int,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Optional[Path]:
    """
    دالة مساعدة لتحميل فيديو.

    Args:
        url: رابط الفيديو.
        quality_label: الجودة.
        user_id: معرف المستخدم.
        progress_callback: دالة التقدم.

    Returns:
        مسار الملف أو None.
    """
    return await get_downloader().download_turkish_video(
        url=url,
        quality_label=quality_label,
        user_id=user_id,
        progress_callback=progress_callback,
    )
