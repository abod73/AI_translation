"""
subtitle_editor.py
==================
أدوات لتحرير ملفات SRT مع الحفاظ على البنية الأصلية.

يدعم:
- الحفاظ على التوقيت
- الحفاظ على الترقيم
- الحفاظ على الفراغات
- استبدال النصوص فقط
- إعادة بناء ملف SRT من نصوص مترجمة
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from logger import get_child_logger, logger
from subtitle import SRTFile, SubtitleSegment, parse_srt_file

_editor_logger = get_child_logger(logger.name, "subtitle_editor")


@dataclass
class SubtitleEditResult:
    """نتيجة عملية التحرير."""

    success: bool
    srt: Optional[SRTFile] = None
    error: str = ""
    original_count: int = 0
    new_count: int = 0


class SubtitleEditor:
    """
    يحرر ملفات SRT مع الحفاظ على البنية الأصلية.

    الفلسفة:
    - لا نلمس التوقيت الأصلي
    - لا نلمس الترقيم الأصلي
    - لا نلمس الفراغات بين الأسطر داخل المقطع
    - نستبدل النص فقط
    """

    def __init__(self) -> None:
        pass

    def load(self, file_path: str | Path) -> SRTFile:
        """يحمّل ملف SRT."""
        srt = parse_srt_file(file_path)
        _editor_logger.info(f"تم تحميل {len(srt.segments)} مقطع من {file_path}")
        return srt

    def replace_texts_preserving_structure(
        self,
        srt: SRTFile,
        new_texts: Dict[int, str],
    ) -> SRTFile:
        """
        يستبدل النصوص في ملف SRT مع الحفاظ على كل البنية الأصلية.

        Args:
            srt: ملف SRT الأصلي.
            new_texts: قاموس {index: new_text}.

        Returns:
            ملف SRT جديد بنفس البنية ونصوص جديدة.
        """
        replaced = 0
        for seg in srt.segments:
            if seg.index in new_texts:
                new_text = new_texts[seg.index].strip()
                seg.text = new_text
                replaced += 1

        _editor_logger.info(
            f"تم استبدال {replaced}/{len(srt.segments)} مقطع"
        )
        return srt

    def replace_texts_in_order(
        self,
        srt: SRTFile,
        new_texts: List[str],
    ) -> SRTFile:
        """
        يستبدل النصوص بالترتيب (النص الأول للمقطع الأول، إلخ).

        Args:
            srt: ملف SRT.
            new_texts: قائمة النصوص الجديدة بنفس ترتيب المقاطع.

        Returns:
            ملف SRT بنصوص جديدة.
        """
        if len(new_texts) != len(srt.segments):
            _editor_logger.warning(
                f"عدد النصوص ({len(new_texts)}) != عدد المقاطع ({len(srt.segments)})"
            )

        for i, seg in enumerate(srt.segments):
            if i < len(new_texts):
                seg.text = new_texts[i].strip()

        return srt

    def save(
        self,
        srt: SRTFile,
        output_path: str | Path,
    ) -> Path:
        """يحفظ ملف SRT."""
        return srt.save(output_path)

    def rebuild_srt_with_translations(
        self,
        original_srt_path: str | Path,
        translated_texts: List[str],
        output_path: str | Path,
    ) -> Path:
        """
        يعيد بناء ملف SRT عربي مع الحفاظ على البنية الأصلية.

        Args:
            original_srt_path: مسار ملف SRT الأصلي (التركي).
            translated_texts: قائمة النصوص المترجمة بالترتيب.
            output_path: مسار ملف الإخراج.

        Returns:
            مسار الملف الجديد.
        """
        # تحميل الأصلي
        original = self.load(original_srt_path)

        # استبدال النصوص بالترتيب
        new_srt = self.replace_texts_in_order(original, translated_texts)

        # الحفظ
        result_path = self.save(new_srt, output_path)

        _editor_logger.info(
            f"تم إنشاء ملف SRT عربي: {result_path} "
            f"({len(new_srt.segments)} مقطع)"
        )
        return result_path

    def split_long_segments(
        self,
        srt: SRTFile,
        max_chars_per_line: int = 42,
        max_lines: int = 2,
    ) -> SRTFile:
        """
        يقسم النصوص الطويلة في المقاطع إلى أسطر متعددة للعرض.

        Args:
            srt: ملف SRT.
            max_chars_per_line: أقصى عدد أحرف في السطر.
            max_lines: أقصى عدد أسطر في المقطع.

        Returns:
            ملف SRT معدّل.
        """
        for seg in srt.segments:
            words = seg.text.split()
            if not words:
                continue

            lines: List[str] = []
            current_line = ""

            for word in words:
                candidate = (current_line + " " + word).strip() if current_line else word
                if len(candidate) <= max_chars_per_line:
                    current_line = candidate
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word

                    # إذا تجاوزنا عدد الأسطر المسموح، ندمج الباقي
                    if len(lines) >= max_lines:
                        # الباقي يُضاف للسطر الأخير
                        idx_remaining = words.index(word)
                        remaining = " ".join(words[idx_remaining:])
                        lines[-1] = lines[-1] + " " + remaining
                        current_line = ""
                        break

            if current_line:
                lines.append(current_line)

            # قص إلى max_lines
            if len(lines) > max_lines:
                # دمج الأسطر الزائدة في الأخير
                lines = lines[: max_lines - 1] + [" ".join(lines[max_lines - 1 :])]

            seg.text = "\n".join(lines)

        return srt

    def adjust_timing(
        self,
        srt: SRTFile,
        offset_seconds: float = 0.0,
        scale: float = 1.0,
    ) -> SRTFile:
        """
        يضبط توقيت المقاطع بإزاحة أو تحجيم.

        Args:
            srt: ملف SRT.
            offset_seconds: إزاحة بالثواني (موجبة أو سالفة).
            scale: معامل تحجيم (1.0 = بدون تغيير).

        Returns:
            ملف SRT بعد التعديل.
        """
        for seg in srt.segments:
            seg.start = max(0.0, seg.start * scale + offset_seconds)
            seg.end = max(seg.start + 0.001, seg.end * scale + offset_seconds)
            # مسح raw_timing لإعادة توليده
            seg.raw_timing = ""

        return srt

    def remove_empty_segments(self, srt: SRTFile) -> SRTFile:
        """يحذف المقاطع ذات النص الفارغ."""
        before = len(srt.segments)
        srt.segments = [s for s in srt.segments if s.text.strip()]
        srt._renumber()
        after = len(srt.segments)
        if before != after:
            _editor_logger.info(f"حذف {before - after} مقطع فارغ")
        return srt

    def clean_text(self, srt: SRTFile) -> SRTFile:
        """ينظّف نصوص المقاطع (إزالة المسافات الزائدة، توحيد الأسطر)."""
        for seg in srt.segments:
            # إزالة المسافات في بداية/نهاية كل سطر
            lines = [line.strip() for line in seg.text.split("\n")]
            # إزالة الأسطر الفارغة في البداية والنهاية
            while lines and not lines[0]:
                lines.pop(0)
            while lines and not lines[-1]:
                lines.pop()
            # توحيد المسافات المتعددة
            lines = [re.sub(r"\s+", " ", line) for line in lines]
            seg.text = "\n".join(lines)
        return srt


# ============================================================
# نسخة عامة للاستخدام المباشر
# ============================================================
_editor_instance: Optional[SubtitleEditor] = None


def get_editor() -> SubtitleEditor:
    """يعيد نسخة singleton من SubtitleEditor."""
    global _editor_instance
    if _editor_instance is None:
        _editor_instance = SubtitleEditor()
    return _editor_instance


def rebuild_arabic_srt(
    original_srt_path: str | Path,
    translated_texts: List[str],
    output_path: str | Path,
) -> Path:
    """
    دالة مساعدة لإعادة بناء ملف SRT عربي.

    Args:
        original_srt_path: ملف SRT التركي الأصلي.
        translated_texts: النصوص المترجمة بالترتيب.
        output_path: مسار الإخراج.

    Returns:
        مسار الملف الناتج.
    """
    return get_editor().rebuild_srt_with_translations(
        original_srt_path=original_srt_path,
        translated_texts=translated_texts,
        output_path=output_path,
    )
