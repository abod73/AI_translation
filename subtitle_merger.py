"""
subtitle_merger.py
==================
دمج مقاطع SRT المتقاربة.

يستخدم دالة merge_segments() من utils لدمج المقاطع التي الفرق
بينها أقل أو يساوي 0.5 ثانية (افتراضياً).

كذلك يدعم:
- دمج ملفات SRT متعددة في ملف واحد
- إعادة ترقيم المقاطع بعد الدمج
- الحفاظ على التوقيت النسبي
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from logger import get_child_logger, logger
from subtitle import SRTFile, SubtitleSegment, parse_srt_file
from utils import merge_segments

_merger_logger = get_child_logger(logger.name, "subtitle_merger")


class SubtitleMerger:
    """
    يدمج مقاطع SRT المتقاربة.

    القواعد:
    - إذا كانت الفجوة بين نهاية مقطع وبداية الذي يليه <= max_gap
      ثانية، يتم دمجهما في مقطع واحد.
    - النص المدموج = نص المقطع الأول + " " + نص الثاني.
    - التوقيت: البداية من الأول، النهاية = max(end1, end2).
    - إعادة ترقيم بعد الدمج.
    """

    def __init__(self, max_gap: float = 0.5) -> None:
        """
        Args:
            max_gap: أقصى فجوة بالثواني للدمج (افتراضي 0.5).
        """
        self.max_gap = max_gap

    def merge_close_segments(self, srt: SRTFile) -> SRTFile:
        """
        يدمج المقاطع المتقاربة في ملف SRT.

        Args:
            srt: ملف SRT.

        Returns:
            ملف SRT بعد الدمج.
        """
        if not srt.segments:
            return srt

        # تحويل إلى القاموس المطلوب لـ merge_segments
        seg_dicts = [
            {
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "index": s.index,
            }
            for s in srt.segments
        ]

        merged = merge_segments(seg_dicts, max_gap=self.max_gap)

        # إعادة بناء SRTFile
        new_segments = [
            SubtitleSegment(
                index=m["index"],
                start=m["start"],
                end=m["end"],
                text=m["text"],
            )
            for m in merged
        ]

        before_count = len(srt.segments)
        srt.segments = new_segments
        srt._renumber()

        _merger_logger.info(
            f"دمج المقاطع: {before_count} → {len(new_segments)} "
            f"(max_gap={self.max_gap}s)"
        )
        return srt

    def merge_files(
        self,
        srt_paths: List[str | Path],
        output_path: str | Path,
    ) -> Path:
        """
        يدمج عدة ملفات SRT في ملف واحد.

        المقاطع تُرتّب حسب التوقيت ويُعاد ترقيمها.

        Args:
            srt_paths: قائمة مسارات ملفات SRT.
            output_path: مسار الإخراج.

        Returns:
            مسار الملف المدموج.
        """
        all_segments: List[SubtitleSegment] = []

        for path in srt_paths:
            srt = parse_srt_file(path)
            all_segments.extend(srt.segments)
            _merger_logger.info(f"تم تحميل {len(srt.segments)} مقطع من {path}")

        # ترتيب حسب البداية
        all_segments.sort(key=lambda s: s.start)

        # إعادة ترقيم
        for i, seg in enumerate(all_segments, start=1):
            seg.index = i

        # إنشاء ملف SRT جديد
        merged_srt = SRTFile(segments=all_segments)
        result = merged_srt.save(output_path)

        _merger_logger.info(
            f"تم دمج {len(srt_paths)} ملف في {result} ({len(all_segments)} مقطع)"
        )
        return result

    def merge_overlapping(self, srt: SRTFile) -> SRTFile:
        """
        يدمج المقاطع المتداخلة (التي تتقاسم زمناً).

        مختلف عن merge_close_segments: هنا نقطة التداخل وليس الفجوة.
        """
        if not srt.segments:
            return srt

        merged: List[SubtitleSegment] = []
        current = srt.segments[0]

        for seg in srt.segments[1:]:
            if seg.start <= current.end:
                # تداخل: دمج
                current.end = max(current.end, seg.end)
                current.text = (current.text + " " + seg.text).strip()
            else:
                merged.append(current)
                current = seg

        merged.append(current)

        before_count = len(srt.segments)
        srt.segments = merged
        srt._renumber()

        _merger_logger.info(
            f"دمج المقاطع المتداخلة: {before_count} → {len(merged)}"
        )
        return srt

    def split_long_segment(
        self,
        segment: SubtitleSegment,
        max_duration: float = 7.0,
    ) -> List[SubtitleSegment]:
        """
        يقسم مقطعاً طويلاً إلى عدة مقاطع أقصر.

        Args:
            segment: المقطع المراد تقسيمه.
            max_duration: أقصى مدة بالثواني للمقطع الواحد.

        Returns:
            قائمة مقاطع بعد التقسيم.
        """
        duration = segment.duration()
        if duration <= max_duration:
            return [segment]

        # تقسيم النص على الجمل
        import re
        sentences = re.split(r"(?<=[.!؟?])\s+", segment.text.strip())
        if len(sentences) <= 1:
            # لا يمكن التقسيم بشكل طبيعي، نقسم بالتساوي
            return [segment]

        # توزيع الجمل على المقاطع حسب المدة
        total_chars = sum(len(s) for s in sentences)
        if total_chars == 0:
            return [segment]

        result: List[SubtitleSegment] = []
        current_text = ""
        current_start = segment.start
        seg_duration = segment.duration()

        for i, sent in enumerate(sentences):
            current_text = (current_text + " " + sent).strip()
            # إذا وصلنا لنسبة مناسبة أو آخر جملة
            ratio = len(current_text) / total_chars
            if ratio >= 0.5 or i == len(sentences) - 1:
                current_end = segment.start + seg_duration * ratio
                result.append(
                    SubtitleSegment(
                        index=0,  # سيُعاد ترقيمه
                        start=current_start,
                        end=min(current_end, segment.end),
                        text=current_text,
                    )
                )
                current_start = current_end
                current_text = ""

        # إعادة ترقيم
        for i, seg in enumerate(result, start=1):
            seg.index = i

        return result

    def normalize_all(self, srt: SRTFile) -> SRTFile:
        """يطبق كل عمليات الدمج والتنظيف دفعة واحدة."""
        srt = self.merge_close_segments(srt)
        srt = self.merge_overlapping(srt)
        return srt


# ============================================================
# نسخة عامة للاستخدام المباشر
# ============================================================
_merger_instance: Optional[SubtitleMerger] = None


def get_merger(max_gap: float = 0.5) -> SubtitleMerger:
    """يعيد نسخة singleton من SubtitleMerger."""
    global _merger_instance
    if _merger_instance is None or _merger_instance.max_gap != max_gap:
        _merger_instance = SubtitleMerger(max_gap=max_gap)
    return _merger_instance


def merge_close_subtitle_segments(
    srt: SRTFile,
    max_gap: float = 0.5,
) -> SRTFile:
    """دالة مساعدة لدمج المقاطع المتقاربة."""
    return get_merger(max_gap).merge_close_segments(srt)
