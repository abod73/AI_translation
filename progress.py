"""
progress.py
===========
شريط التقدم للعمليات الطويلة (تحميل، رفع، تفريغ).

يستخدمه Pyrogram لإظهار نسبة التقدم أثناء:
- تحميل الفيديو بـ yt-dlp
- رفع الفيديو/ملف SRT إلى تيليجرام
- عمليات Whisper والترجمة
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable, Optional

from logger import get_child_logger, logger

_progress_logger = get_child_logger(logger.name, "progress")


def human_readable_size(num_bytes: float) -> str:
    """يحوّل البايتات إلى صيغة مقروءة."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"


def human_readable_speed(speed: float) -> str:
    """يحوّل السرعة (بايت/ثانية) إلى صيغة مقروءة."""
    return human_readable_size(speed) + "/s"


def format_eta(seconds: float) -> str:
    """يحوّل الثواني إلى صيغة زمنية متبقية."""
    if seconds < 0 or seconds > 10**8:
        return "∞"
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours = int(minutes // 60)
    mins = minutes % 60
    return f"{hours}h{mins:02d}m"


class ProgressTracker:
    """
    متتبع تقدم عمليات التحميل والرفع.

    يُستخدم كـ callback لـ Pyrogram ويعرض رسائل تقدم.
    """

    def __init__(
        self,
        message_text_fn: Callable[[float, int, int, float], str],
        update_interval: float = 5.0,
    ) -> None:
        """
        Args:
            message_text_fn: دالة تنتج نص الرسالة بناءً على
                (current, total, speed, eta).
            update_interval: الفاصل الأدنى بين التحديثات بالثواني.
        """
        self.message_text_fn = message_text_fn
        self.update_interval = update_interval
        self._last_update: float = 0.0
        self._start_time: float = 0.0
        self._last_bytes: int = 0

    def start(self) -> None:
        self._start_time = time.monotonic()
        self._last_bytes = 0
        self._last_update = 0.0

    def should_update(self) -> bool:
        """هل حان وقت تحديث الرسالة؟"""
        now = time.monotonic()
        return (now - self._last_update) >= self.update_interval

    def compute_progress(
        self, current: int, total: int
    ) -> tuple[float, float, float]:
        """
        يحسب النسبة، السرعة، والوقت المتبقي.

        Returns:
            (percentage, speed_bytes_per_sec, eta_seconds)
        """
        elapsed = max(time.monotonic() - self._start_time, 0.001)
        percentage = (current / total * 100) if total > 0 else 0.0
        speed = current / elapsed if elapsed > 0 else 0.0
        if speed > 0:
            remaining_bytes = max(total - current, 0)
            eta = remaining_bytes / speed
        else:
            eta = -1.0
        return percentage, speed, eta

    def build_message(
        self,
        current: int,
        total: int,
        prefix: str = "",
        extra: str = "",
    ) -> str:
        """يبني نص رسالة التقدم."""
        percentage, speed, eta = self.compute_progress(current, total)

        # شريط تقدم نصي
        bar_length = 20
        filled = int(bar_length * percentage / 100)
        bar = "█" * filled + "░" * (bar_length - filled)

        lines = [
            f"{prefix}" if prefix else "",
            f"[{bar}] {percentage:.1f}%",
            f"الحجم: {human_readable_size(current)} / {human_readable_size(total)}",
            f"السرعة: {human_readable_speed(speed)}",
            f"الوقت المتبقي: {format_eta(eta)}",
        ]
        if extra:
            lines.append(extra)
        return "\n".join(line for line in lines if line)


async def progress_callback(
    current: int,
    total: int,
    client,
    message,
    prefix: str = "جاري الرفع...",
    tracker: Optional[ProgressTracker] = None,
    extra_text: str = "",
) -> None:
    """
    Callback تقدم جاهز للاستخدام مع Pyrogram send_video/send_document.

    Args:
        current: عدد البايتات المكتملة.
        total: إجمالي البايتات.
        client: عميل Pyrogram.
        message: رسالة تيليجرام المراد تعديلها.
        prefix: نص يظهر قبل شريط التقدم.
        tracker: متتبع التقدم (يُنشأ تلقائياً إذا لم يُمرر).
        extra_text: نص إضافي يظهر بعد الإحصائيات.
    """
    if tracker is None:
        tracker = ProgressTracker(
            message_text_fn=lambda c, t, s, e: f"Progress: {c}/{t}"
        )
        tracker.start()

    if not tracker.should_update():
        return

    tracker._last_update = time.monotonic()
    text = tracker.build_message(current, total, prefix=prefix, extra=extra_text)

    try:
        await message.edit_text(text)
    except Exception as exc:
        # تجاهل أخطاء تعديل الرسالة (مثل "message not modified")
        _progress_logger.debug(f"تعذر تحديث رسالة التقدم: {exc}")


async def update_progress_message(
    message,
    text: str,
    interval: float = 2.0,
    last_update: Optional[list] = None,
) -> bool:
    """
    يحدّث رسالة تيليجرام بالنص الجديد مع منع التحديثات المتكررة.

    Args:
        message: رسالة تيليجرام.
        text: النص الجديد.
        interval: الفاصل الأدنى بين التحديثات.
        last_update: قائمة بعنصر واحد تحتوي على آخر وقت تحديث.

    Returns:
        True إذا تم التحديث، False إذا تم تجاهله.
    """
    now = time.monotonic()
    if last_update is not None and (now - last_update[0]) < interval:
        return False
    if last_update is not None:
        last_update[0] = now

    try:
        await message.edit_text(text)
        return True
    except Exception:
        return False


async def run_with_spinner(
    coro,
    message,
    prefix: str = "جاري المعالجة",
    spinner_chars: str = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏",
    interval: float = 0.5,
):
    """
    يشغّل مهمة غير متزامنة مع عرض مؤشر دوران.

    Args:
        coro: الكوروتين المطلوب تشغيله.
        message: رسالة تيليجرام لعرض المؤشر.
        prefix: نص يسبق المؤشر.
        spinner_chars: أحرف المؤشر الدوار.
        interval: فاصل التحديث.

    Returns:
        نتيجة الكوروتين.
    """
    task = asyncio.create_task(coro)
    idx = 0
    while not task.done():
        spinner = spinner_chars[idx % len(spinner_chars)]
        try:
            await message.edit_text(f"{prefix} {spinner}")
        except Exception:
            pass
        idx += 1
        try:
            await asyncio.wait_for(asyncio.shield(asyncio.sleep(interval)), timeout=interval)
        except asyncio.TimeoutError:
            break
    return task.result()
