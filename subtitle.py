"""
subtitle.py
===========
قراءة وكتابة ملفات SRT.

يدعم:
- تحليل ملفات SRT (الترقيم، التوقيت، النص)
- الحفاظ على الترقيم والتوقيت والفراغات
- إنشاء ملفات SRT جديدة من المقاطع
- التحقق من صحة البنية
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from logger import get_child_logger, logger
from utils import format_time, parse_time, merge_segments

_subtitle_logger = get_child_logger(logger.name, "subtitle")


# نمط السطر الزمني في SRT: 00:00:01,000 --> 00:00:05,000
TIMING_PATTERN = re.compile(
    r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})"
)


@dataclass
class SubtitleSegment:
    """مقطع ترجمة واحد في ملف SRT."""

    index: int                              # الرقم
    start: float                            # البداية (ثوانٍ)
    end: float                              # النهاية (ثوانٍ)
    text: str                               # النص
    raw_timing: str = ""                    # السطر الزمني الأصلي (للحفاظ على الصيغة)

    def to_srt_block(self) -> str:
        """يحوّل المقطع إلى كتلة SRT نصية."""
        # استخدام raw_timing إذا وُجد للحفاظ على الصيغة الأصلية
        if self.raw_timing:
            timing_line = self.raw_timing
        else:
            timing_line = f"{format_time(self.start)} --> {format_time(self.end)}"
        return f"{self.index}\n{timing_line}\n{self.text}\n"

    def duration(self) -> float:
        """مدة المقطع بالثواني."""
        return max(self.end - self.start, 0.0)


@dataclass
class SRTFile:
    """يمثل ملف SRT كاملاً."""

    segments: List[SubtitleSegment] = field(default_factory=list)
    source_path: Optional[Path] = None
    header: str = ""  # أي رأس قبل أول كتلة (نادر)

    def __len__(self) -> int:
        return len(self.segments)

    def __iter__(self) -> Iterator[SubtitleSegment]:
        return iter(self.segments)

    def __getitem__(self, idx: int) -> SubtitleSegment:
        return self.segments[idx]

    def add_segment(self, segment: SubtitleSegment) -> None:
        """يضيف مقطعاً ويعيد ترقيم القائمة."""
        self.segments.append(segment)
        self._renumber()

    def _renumber(self) -> None:
        """يعيد ترقيم كل المقاطع بشكل تسلسلي."""
        for i, seg in enumerate(self.segments, start=1):
            seg.index = i

    def to_text(self) -> str:
        """يحوّل الملف كاملاً إلى نص SRT."""
        blocks = []
        for seg in self.segments:
            blocks.append(seg.to_srt_block())
        return "\n".join(blocks)

    def save(self, path: str | Path) -> Path:
        """يحفظ الملف إلى مسار."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_text(), encoding="utf-8")
        _subtitle_logger.info(f"تم حفظ ملف SRT: {path} ({len(self.segments)} مقطع)")
        return path

    def get_texts_only(self) -> List[str]:
        """يعيد قائمة بالنصوص فقط بدون التوقيت والترقيم."""
        return [seg.text for seg in self.segments]

    def replace_texts(self, new_texts: List[str]) -> None:
        """
        يستبدل نصوص المقاطع بقائمة نصوص جديدة مع الحفاظ على التوقيت والترقيم.

        Args:
            new_texts: قائمة النصوص الجديدة (بنفس عدد المقاطع).
        """
        if len(new_texts) != len(self.segments):
            _subtitle_logger.warning(
                f"عدد النصوص الجديدة ({len(new_texts)}) != عدد المقاطع ({len(self.segments)})"
            )
            # نطبق على قدر ما نستطيع
        for i, new_text in enumerate(new_texts):
            if i < len(self.segments):
                self.segments[i].text = new_text.strip()

    def merge_close_segments(self, max_gap: float = 0.5) -> None:
        """يدمج المقاطع المتقاربة باستخدام utils.merge_segments."""
        seg_dicts = [
            {"start": s.start, "end": s.end, "text": s.text, "index": s.index}
            for s in self.segments
        ]
        merged = merge_segments(seg_dicts, max_gap=max_gap)
        self.segments = [
            SubtitleSegment(
                index=m["index"],
                start=m["start"],
                end=m["end"],
                text=m["text"],
            )
            for m in merged
        ]
        _subtitle_logger.info(f"دمج المقاطع: {len(seg_dicts)} → {len(self.segments)}")


# ============================================================
# دوال القراءة والكتابة
# ============================================================
def parse_srt(content: str) -> SRTFile:
    """
    يحلل نص SRT إلى كائن SRTFile.

    يحافظ على:
    - الترقيم
    - التوقيت (يسمح بصيغتي , و . للمللي ثانية)
    - الفراغات بين الأسطر في النص

    Args:
        content: نص ملف SRT.

    Returns:
        كائن SRTFile.
    """
    srt = SRTFile()
    # تطبيع نهايات الأسطر
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    # تقسيم إلى كتل بفاصل سطر فارغ (أو أكثر)
    # قد يكون هناك فراغات متعددة
    blocks = re.split(r"\n\s*\n", content.strip())

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split("\n")
        if len(lines) < 2:
            continue

        # السطر الأول: الرقم
        idx = 0
        index_str = lines[0].strip()
        try:
            index = int(index_str)
        except ValueError:
            # قد يكون السطر الأول هو التوقيت مباشرة
            if TIMING_PATTERN.search(lines[0]):
                index = len(srt.segments) + 1
                idx = 0
            else:
                _subtitle_logger.debug(f"تجاهل كتلة غير صالحة: {block[:80]}")
                continue
        else:
            idx = 1

        # السطر الثاني (أو الأول): التوقيت
        if idx >= len(lines):
            continue
        timing_match = TIMING_PATTERN.search(lines[idx])
        if not timing_match:
            _subtitle_logger.debug(f"لا يوجد توقيت صالح في: {lines[idx]}")
            continue

        start_str, end_str = timing_match.group(1), timing_match.group(2)
        try:
            start = parse_time(start_str)
            end = parse_time(end_str)
        except ValueError as exc:
            _subtitle_logger.warning(f"توقيت غير صالح: {exc}")
            continue

        # باقي الأسطر: النص
        text_lines = lines[idx + 1 :]
        text = "\n".join(text_lines).strip()

        seg = SubtitleSegment(
            index=index,
            start=start,
            end=end,
            text=text,
            raw_timing=f"{start_str} --> {end_str}",
        )
        srt.segments.append(seg)

    # إعادة الترقيم للتأكد من التسلسل
    srt._renumber()
    _subtitle_logger.info(f"تم تحليل {len(srt.segments)} مقطع SRT")
    return srt


def parse_srt_file(file_path: str | Path) -> SRTFile:
    """يقرأ ملف SRT من القرص ويحلله."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"ملف SRT غير موجود: {path}")

    content = path.read_text(encoding="utf-8", errors="replace")
    srt = parse_srt(content)
    srt.source_path = path
    return srt


def write_srt_file(
    segments: List[SubtitleSegment],
    output_path: str | Path,
) -> Path:
    """يكتب قائمة مقاطع إلى ملف SRT."""
    srt = SRTFile(segments=list(segments))
    srt._renumber()
    return srt.save(output_path)


def create_srt_from_segments(
    segments: List[dict],
    output_path: str | Path,
) -> Path:
    """
    ينشئ ملف SRT من قائمة قواميس مقاطع.

    كل قاموس يحتوي على: start, end, text
    """
    srt = SRTFile()
    for i, seg in enumerate(segments, start=1):
        srt.segments.append(
            SubtitleSegment(
                index=i,
                start=float(seg["start"]),
                end=float(seg["end"]),
                text=str(seg["text"]).strip(),
            )
        )
    return srt.save(output_path)


def validate_srt_file(file_path: str | Path) -> Tuple[bool, str]:
    """
    يتحقق من صحة ملف SRT.

    Returns:
        (True, "") إذا كان صالحاً، (False, "رسالة الخطأ") خلاف ذلك.
    """
    try:
        srt = parse_srt_file(file_path)
    except FileNotFoundError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"خطأ في التحليل: {exc}"

    if not srt.segments:
        return False, "ملف SRT فارغ"

    for seg in srt.segments:
        if seg.end < seg.start:
            return False, f"مقطع {seg.index}: النهاية قبل البداية"
        if not seg.text:
            return False, f"مقطع {seg.index}: نص فارغ"

    return True, ""


def extract_text_blocks(srt: SRTFile, batch_size: int = 8) -> List[List[Tuple[int, str]]]:
    """
    يقسم نصوص SRT إلى دفعات للترجمة.

    Args:
        srt: ملف SRT.
        batch_size: حجم الدفعة.

    Returns:
        قائمة دفعات، كل دفعة قائمة من (index, text).
    """
    batches: List[List[Tuple[int, str]]] = []
    current: List[Tuple[int, str]] = []
    for seg in srt.segments:
        current.append((seg.index, seg.text))
        if len(current) >= batch_size:
            batches.append(current)
            current = []
    if current:
        batches.append(current)
    return batches
