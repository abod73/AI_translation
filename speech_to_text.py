"""
speech_to_text.py
=================
تفريغ الصوت من الفيديو إلى نص عبر OpenAI Whisper.

يستخدم subprocess فقط (لا يستخدم مكتبة whisper Python).

الأمر المنفذ:
    whisper downloads/video.mp4 \
        --task transcribe \
        --language Turkish \
        --model small \
        --output_format srt \
        --output_dir downloads/
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import Callable, Optional

from config import (
    WHISPER_BINARY,
    WHISPER_MODEL,
    WHISPER_LANGUAGE,
    WHISPER_TASK,
    WHISPER_OUTPUT_FORMAT,
    DOWNLOADS_DIR,
    OPERATION_TIMEOUT_SECONDS,
    MAX_RETRIES,
)
from logger import get_child_logger, logger

_stt_logger = get_child_logger(logger.name, "speech_to_text")


# ============================================================
# فئة WhisperTranscriber
# ============================================================
class WhisperTranscriber:
    """
    يففرغ الصوت من الفيديو إلى نص باستخدام Whisper.

    يدعم:
    - تشغيل Whisper عبر subprocess فقط
    - مراقبة التقدم
    - إعادة المحاولة عند الفشل
    - العثور على ملف SRT الناتج
    """

    def __init__(self) -> None:
        self.binary: str = WHISPER_BINARY
        self.model: str = WHISPER_MODEL
        self.language: str = WHISPER_LANGUAGE
        self.task: str = WHISPER_TASK
        self.output_format: str = WHISPER_OUTPUT_FORMAT
        self.output_dir: Path = DOWNLOADS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def transcribe(
        self,
        video_path: str | Path,
        output_dir: Optional[str | Path] = None,
        language: Optional[str] = None,
        model: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        max_retries: int = MAX_RETRIES,
    ) -> Optional[Path]:
        """
        ينفذ تفريغ الصوت من الفيديو.

        Args:
            video_path: مسار ملف الفيديو.
            output_dir: مجلد الإخراج (افتراضي downloads/).
            language: لغة الفيديو (افتراضي Turkish).
            model: اسم النموذج (افتراضي small).
            progress_callback: دالة التقدم.
            max_retries: عدد المحاولات.

        Returns:
            مسار ملف SRT الناتج أو None عند الفشل.
        """
        video_path = Path(video_path)
        if not video_path.exists():
            _stt_logger.error(f"ملف الفيديو غير موجود: {video_path}")
            return None

        out_dir = Path(output_dir) if output_dir else self.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        lang = language or self.language
        mdl = model or self.model

        # بناء الأمر - حرفياً كما طلب المستخدم:
        # whisper downloads/video.mp4 \
        #     --task transcribe \
        #     --language Turkish \
        #     --model small \
        #     --output_format srt \
        #     --output_dir downloads/
        cmd = [
            self.binary,
            str(video_path),
            "--task", self.task,
            "--language", lang,
            "--model", mdl,
            "--output_format", self.output_format,
            "--output_dir", str(out_dir),
            "--verbose", "True",   # إخراج تقدم تفصيلي
        ]

        _stt_logger.info(
            f"بدء تفريغ الصوت من: {video_path}\n"
            f"اللغة: {lang}\n"
            f"النموذج: {mdl}\n"
            f"مجلد الإخراج: {out_dir}"
        )

        last_error: Optional[str] = None

        for attempt in range(1, max_retries + 1):
            _stt_logger.info(f"محاولة التفريغ {attempt}/{max_retries}")

            try:
                result = await self._run_whisper(
                    cmd, video_path, out_dir, progress_callback
                )
                if result is not None:
                    _stt_logger.info(f"تم التفريغ بنجاح: {result}")
                    return result
            except asyncio.TimeoutError:
                last_error = "انتهت مهلة التفريغ"
                _stt_logger.error(last_error)
            except Exception as exc:
                last_error = str(exc)
                _stt_logger.error(f"خطأ في التفريغ: {exc}", exc_info=True)

            if attempt < max_retries:
                wait = 2.0 * attempt
                _stt_logger.info(f"الانتظار {wait}s قبل إعادة المحاولة...")
                await asyncio.sleep(wait)

        _stt_logger.error(
            f"فشل التفريغ بعد {max_retries} محاولات. آخر خطأ: {last_error}"
        )
        return None

    async def _run_whisper(
        self,
        cmd: list[str],
        video_path: Path,
        out_dir: Path,
        progress_callback: Optional[Callable[[float, str], None]],
    ) -> Optional[Path]:
        """يشغل أمر whisper ويراقب التقدم."""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # أنماط التقدم من Whisper
        progress_re = re.compile(r"(\d+)%")
        # Whisper يطبع نسب التقدم أحياناً
        time_re = re.compile(r"\[?(\d{2}:\d{2}:\d{2})")

        video_stem = video_path.stem
        expected_srt = out_dir / f"{video_stem}.{self.output_format}"

        # مهلة كبيرة للعمليات الطويلة
        start_time = time.monotonic()

        async def _read_stdout() -> str:
            buffer = ""
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    buffer += text + "\n"
                    _stt_logger.debug(f"[whisper] {text}")

                    # محاولة تحليل التقدم
                    m = progress_re.search(text)
                    if m and progress_callback:
                        pct = float(m.group(1))
                        try:
                            progress_callback(pct, text)
                        except Exception:
                            pass
                # التحقق من المهلة
                if time.monotonic() - start_time > OPERATION_TIMEOUT_SECONDS:
                    _stt_logger.error("تجاوزت المهلة، سيتم الإيقاف")
                    proc.kill()
                    break
            return buffer

        async def _read_stderr() -> str:
            assert proc.stderr is not None
            chunks = []
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    chunks.append(text)
                    _stt_logger.debug(f"[whisper stderr] {text}")
            return "\n".join(chunks)

        try:
            stdout_task = asyncio.create_task(_read_stdout())
            stderr_task = asyncio.create_task(_read_stderr())
            await asyncio.wait_for(proc.wait(), timeout=OPERATION_TIMEOUT_SECONDS)
            await asyncio.gather(stdout_task, stderr_task)
            stderr_output = stderr_task.result()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise

        if proc.returncode != 0:
            _stt_logger.error(
                f"whisper فشل (returncode={proc.returncode}): {stderr_output[:1000]}"
            )
            return None

        # العثور على ملف SRT الناتج
        # Whisper قد ينتج: video.srt أو video.txt إلخ
        candidates = list(out_dir.glob(f"{video_stem}.*"))
        srt_candidates = [c for c in candidates if c.suffix.lower() == f".{self.output_format}"]

        if srt_candidates:
            srt_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return srt_candidates[0]

        # محاولة أخيرة: البحث عن أي ملف SRT في المجلد
        all_srts = sorted(
            out_dir.glob("*.srt"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if all_srts:
            _stt_logger.warning(f"تم العثور على SRT غير متوقع: {all_srts[0]}")
            return all_srts[0]

        _stt_logger.error("لم يتم العثور على ملف SRT بعد التفريغ")
        return None

    def get_supported_models(self) -> list[str]:
        """يعيد قائمة نماذج Whisper المدعومة."""
        return ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]


# ============================================================
# نسخة عامة للاستخدام المباشر
# ============================================================
_transcriber_instance: Optional[WhisperTranscriber] = None


def get_transcriber() -> WhisperTranscriber:
    """يعيد نسخة singleton من WhisperTranscriber."""
    global _transcriber_instance
    if _transcriber_instance is None:
        _transcriber_instance = WhisperTranscriber()
    return _transcriber_instance


async def transcribe_video(
    video_path: str | Path,
    output_dir: Optional[str | Path] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Optional[Path]:
    """
    دالة مساعدة لتفريغ صوت فيديو.

    Args:
        video_path: مسار الفيديو.
        output_dir: مجلد الإخراج.
        progress_callback: دالة التقدم.

    Returns:
        مسار ملف SRT أو None.
    """
    return await get_transcriber().transcribe(
        video_path=video_path,
        output_dir=output_dir,
        progress_callback=progress_callback,
    )
