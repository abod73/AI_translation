"""
translator.py
=============
ترجمة نصوص SRT من التركية إلى العربية باستخدام Qwen2.5-3B-Instruct.

المتطلبات:
- تحميل النموذج من HuggingFace عبر transformers.
- لا يستخدم OpenAI API أو أي API مدفوع.
- يستخدم الـ Prompt الحرفي المحدد في config.TRANSLATION_SYSTEM_PROMPT.
- يحافظ على التوقيت والترقيم والفراغات في ملف SRT.
- يطبق fix_common_errors() لتصحيح الأخطاء الشائعة بالـ Regex.
"""

from __future__ import annotations

import asyncio
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import (
    QWEN_MODEL_NAME,
    QWEN_DEVICE,
    QWEN_TORCH_DTYPE,
    QWEN_MAX_NEW_TOKENS,
    QWEN_TEMPERATURE,
    QWEN_TOP_P,
    QWEN_REPETITION_PENALTY,
    QWEN_BATCH_SIZE,
    TRANSLATION_SYSTEM_PROMPT,
    MAX_RETRIES,
)
from logger import get_child_logger, logger
from utils import (
    split_text_into_chunks,
    extract_name_placeholder,
    restore_name_placeholders,
)

_translator_logger = get_child_logger(logger.name, "translator")


# ============================================================
# قواعد التصحيح بالـ Regex (للأخطاء الشائعة)
# ============================================================
# قائمة بقواعد (النمط، الاستبدال، الوصف) - تُطبق في fix_common_errors()
COMMON_ERROR_RULES: List[Tuple[str, str, str]] = [
    # مملوءة → مليئة
    (r"\bمملوءة\b", "مليئة", "مملوءة → مليئة"),
    # إتفقنا → اتّفقنا
    (r"\bإتفقنا\b", "اتّفقنا", "إتفقنا → اتّفقنا"),
    (r"\bإتفق\b", "اتّفق", "إتفق → اتّفق"),
    (r"\bإتفاق\b", "اتّفاق", "إتفاق → اتّفاق"),
    # ياصديقي → يا صديقي
    (r"\bياصديقي\b", "يا صديقي", "ياصديقي → يا صديقي"),
    (r"\bياصديق\b", "يا صديق", "ياصديق → يا صديق"),
    (r"\bياصاحبي\b", "يا صاحبي", "ياصاحبي → يا صاحبي"),
    (r"\bيااخي\b", "يا أخي", "يااخي → يا أخي"),
    (r"\bياابني\b", "يا ابني", "ياابني → يا ابني"),
    (r"\bياأبي\b", "يا أبي", "ياأبي → يا أبي"),
    (r"\bياامي\b", "يا أمي", "ياامي → يا أمي"),
    # صلوا أن → ادعوا أن
    (r"\bصلوا أن\b", "ادعوا أن", "صلوا أن → ادعوا أن"),
    (r"\bصلوا\b", "ادعوا", "صلوا → ادعوا (في سياق الدعاء)"),
    # اللون الأزرق → الاكتئاب (في السياق المناسب)
    (r"اللون الأزرق", "الاكتئاب", "اللون الأزرق → الاكتئاب"),
    (r"الأزرق", "الاكتئاب", "الأزرق → الاكتئاب (في سياق الاكتئاب)"),
    # Blue → الاكتئاب
    (r"\bBlue\b", "الاكتئاب", "Blue → الاكتئاب"),
    (r"\bMavi\b", "الاكتئاب", "Mavi → الاكتئاب"),
    # أخطاء شائعة إضافية
    (r"\bإلي\b", "إلى", "إلي → إلى"),
    (r"\bعلي\b", "على", "علي → على"),
    (r"\bفي\b(?=[ين])", "في", "تنظيف 'في'"),
    # مسافات قبل علامات الترقيم
    (r"\s+([،.!?؟:])", r"\1", "إزالة المسافات قبل علامات الترقيم"),
    # مسافات بعد علامات الترقيم
    (r"([،.!?؟:])(\S)", r"\1 \2", "إضافة مسافة بعد علامات الترقيم"),
    # توحيد المسافات المتعددة
    (r"  +", " ", "توحيد المسافات المتعددة"),
]


def fix_common_errors(text: str) -> str:
    """
    يصحح الأخطاء الشائعة في النص العربي باستخدام Regex.

    الأخطاء المعالجة:
    - مملوءة → مليئة
    - إتفقنا → اتّفقنا
    - ياصديقي → يا صديقي
    - صلوا أن → ادعوا أن
    - اللون الأزرق → الاكتئاب (إذا كان السياق يدل على ذلك)
    - إزالة المسافات الزائدة قبل/بعد علامات الترقيم
    - توحيد المسافات المتعددة

    Args:
        text: النص العربي المراد تصحيحه.

    Returns:
        النص بعد التصحيح.
    """
    if not text:
        return text

    corrected = text
    applied_count = 0

    for pattern, replacement, description in COMMON_ERROR_RULES:
        new_text, count = re.subn(pattern, replacement, corrected)
        if count > 0:
            applied_count += count
            _translator_logger.debug(
                f"تطبيق قاعدة '{description}': {count} مرة"
            )
        corrected = new_text

    # تنظيف أخيرة: إزالة الفراغات في بداية/نهاية كل سطر
    lines = [line.strip() for line in corrected.split("\n")]
    corrected = "\n".join(lines)

    # إزالة الفراغات الزائدة في بداية ونهاية النص
    corrected = corrected.strip()

    if applied_count > 0:
        _translator_logger.info(f"fix_common_errors: تم تصحيح {applied_count} خطأ")

    return corrected


# ============================================================
# فئة QwenTranslator
# ============================================================
class QwenTranslator:
    """
    مترجم نصوص باستخدام Qwen2.5-3B-Instruct من HuggingFace.

    - يحمّل النموذج مرة واحدة فقط (singleton).
    - يستخدم transformers (لا OpenAI API).
    - يدعم الترجمة بالدفعة (batch) لتسريع العملية.
    - يحافظ على البنية الأصلية للنص (الأسطر الجديدة، الترقيم).
    """

    def __init__(self) -> None:
        self.model_name: str = QWEN_MODEL_NAME
        self.device: str = QWEN_DEVICE
        self.torch_dtype: str = QWEN_TORCH_DTYPE
        self.max_new_tokens: int = QWEN_MAX_NEW_TOKENS
        self.temperature: float = QWEN_TEMPERATURE
        self.top_p: float = QWEN_TOP_P
        self.repetition_penalty: float = QWEN_REPETITION_PENALTY
        self.batch_size: int = QWEN_BATCH_SIZE

        # مراجع النموذج والـ tokenizer (تُحمّل لاحقاً)
        self._model = None
        self._tokenizer = None
        self._loaded: bool = False
        self._loading: bool = False
        self._lock = threading.Lock()

    # ============================================================
    # تحميل النموذج
    # ============================================================
    def load_model(self) -> None:
        """
        يحمّل النموذج و الـ tokenizer من HuggingFace.

        يجب استدعاؤها قبل الترجمة. آمنة للاستدعاء من خيوط متعددة.
        """
        with self._lock:
            if self._loaded:
                return

            if self._loading:
                # انتظار حتى ينتهي تحميل آخر
                while self._loading:
                    time.sleep(0.5)
                return

            self._loading = True

            try:
                _translator_logger.info(
                    f"بدء تحميل النموذج: {self.model_name} على {self.device}"
                )

                # استيراد مكتبات HuggingFace (تأخير الاستيراد لتسريع الإقلاع)
                import torch
                from transformers import (
                    AutoModelForCausalLM,
                    AutoTokenizer,
                )

                # تحديد الـ dtype
                if self.torch_dtype == "auto":
                    dtype = "auto"
                elif self.torch_dtype in ("bfloat16", "bf16"):
                    dtype = torch.bfloat16
                elif self.torch_dtype in ("float16", "fp16", "half"):
                    dtype = torch.float16
                else:
                    dtype = torch.float32

                _translator_logger.info("تحميل الـ tokenizer...")
                self._tokenizer = AutoTokenizer.from_pretrained(
                    self.model_name,
                    trust_remote_code=True,
                )

                _translator_logger.info("تحميل النموذج...")
                if dtype == "auto":
                    self._model = AutoModelForCausalLM.from_pretrained(
                        self.model_name,
                        trust_remote_code=True,
                        device_map="auto",
                    )
                else:
                    self._model = AutoModelForCausalLM.from_pretrained(
                        self.model_name,
                        trust_remote_code=True,
                        torch_dtype=dtype,
                        device_map="auto",
                    )

                # ضبط النموذج لوضع التقييم
                self._model.eval()

                # تحقق من توفر GPU
                if torch.cuda.is_available():
                    gpu_name = torch.cuda.get_device_name(0)
                    gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1e9
                    _translator_logger.info(
                        f"GPU متاح: {gpu_name} ({gpu_mem:.1f} GB)"
                    )
                else:
                    _translator_logger.warning("لا يوجد GPU! سيكون الأداء بطيئاً جداً")

                self._loaded = True
                _translator_logger.info("تم تحميل النموذج بنجاح")

            except Exception as exc:
                _translator_logger.error(
                    f"فشل تحميل النموذج: {exc}", exc_info=True
                )
                raise
            finally:
                self._loading = False

    def is_loaded(self) -> bool:
        """هل النموذج محمّل وجاهز؟"""
        return self._loaded

    # ============================================================
    # بناء الـ Prompt
    # ============================================================
    def _build_messages(
        self,
        turkish_text: str,
    ) -> List[Dict[str, str]]:
        """
        يبني قائمة الرسائل لـ Qwen بصيغة chat.

        Args:
            turkish_text: النص التركي المراد ترجمته.

        Returns:
            قائمة رسائل النظام والمستخدم.
        """
        return [
            {"role": "system", "content": TRANSLATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"ترجم النص التركي التالي إلى العربية. "
                    f"أخرج الترجمة فقط دون أي شرح أو مقدمة:\n\n"
                    f"{turkish_text}"
                ),
            },
        ]

    def _apply_chat_template(
        self,
        messages: List[Dict[str, str]],
    ) -> str:
        """يطبق قالب chat الخاص بـ Qwen على الرسائل."""
        if self._tokenizer is None:
            raise RuntimeError("الـ tokenizer غير محمّل")

        # Qwen2.5 يدعم apply_chat_template
        text = self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        return text

    # ============================================================
    # الترجمة الفردية
    # ============================================================
    def translate_text(self, turkish_text: str) -> str:
        """
        يترجم نصاً تركياً إلى العربية.

        Args:
            turkish_text: النص التركي.

        Returns:
            النص العربي المترجم.
        """
        if not self._loaded:
            self.load_model()

        if not turkish_text or not turkish_text.strip():
            return ""

        # استخراج علامات NAME_X قبل الترجمة
        text_with_placeholders, names = extract_name_placeholder(turkish_text)

        # بناء الـ prompt
        messages = self._build_messages(text_with_placeholders)
        prompt_text = self._apply_chat_template(messages)

        # توليد الترجمة
        import torch

        _translator_logger.debug(
            f"ترجمة نص بطول {len(turkish_text)} حرف"
        )

        # tokenize
        inputs = self._tokenizer(
            prompt_text,
            return_tensors="pt",
            truncation=True,
            max_length=4096,
        ).to(self._model.device)

        # التوليد
        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                temperature=self.temperature,
                top_p=self.top_p,
                repetition_penalty=self.repetition_penalty,
                do_sample=self.temperature > 0,
                pad_token_id=self._tokenizer.eos_token_id,
            )

        # استخراج النص المولّد فقط (بدون الـ prompt)
        input_length = inputs["input_ids"].shape[1]
        generated_tokens = outputs[0][input_length:]
        translated = self._tokenizer.decode(
            generated_tokens,
            skip_special_tokens=True,
        ).strip()

        # إعادة الأسماء إلى مواضعها
        translated = restore_name_placeholders(translated, names)

        # تطبيق fix_common_errors
        translated = fix_common_errors(translated)

        _translator_logger.debug(f"تمت الترجمة: {len(translated)} حرف")
        return translated

    # ============================================================
    # الترجمة بالدفعة (Batch)
    # ============================================================
    def translate_batch(
        self,
        turkish_texts: List[str],
        progress_callback: Optional[callable] = None,
    ) -> List[str]:
        """
        يترجم قائمة نصوص تركية دفعة واحدة (أو عدة دفعات).

        Args:
            turkish_texts: قائمة النصوص التركية.
            progress_callback: دالة التقدم (current, total).

        Returns:
            قائمة النصوص المترجمة بنفس الترتيب.
        """
        if not self._loaded:
            self.load_model()

        if not turkish_texts:
            return []

        _translator_logger.info(
            f"بدء ترجمة {len(turkish_texts)} نص بدفعات من {self.batch_size}"
        )

        results: List[str] = []
        total = len(turkish_texts)

        for i, text in enumerate(turkish_texts):
            try:
                # محاولات إعادة
                translated = ""
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        translated = self.translate_text(text)
                        if translated:
                            break
                    except Exception as exc:
                        _translator_logger.warning(
                            f"محاولة {attempt}/{MAX_RETRIES} فشلت للنص {i}: {exc}"
                        )
                        if attempt == MAX_RETRIES:
                            # في حال الفشل النهائي، نضع النص الأصلي
                            translated = text
                            _translator_logger.error(
                                f"فشلت الترجمة للنص {i} بعد {MAX_RETRIES} محاولات"
                            )
                        else:
                            time.sleep(1.0 * attempt)

                results.append(translated)

            except Exception as exc:
                _translator_logger.error(f"خطأ غير متوقع في النص {i}: {exc}")
                results.append(text)  # الاحتفاظ بالأصلي

            # تحديث التقدم
            if progress_callback:
                try:
                    progress_callback(i + 1, total)
                except Exception:
                    pass

            # تسجيل دوري
            if (i + 1) % 10 == 0 or (i + 1) == total:
                _translator_logger.info(
                    f"التقدم: {i + 1}/{total} ({(i + 1) * 100 / total:.1f}%)"
                )

        _translator_logger.info(f"اكتملت الترجمة: {len(results)}/{total}")
        return results

    # ============================================================
    # ترجمة ملف SRT كامل
    # ============================================================
    def translate_srt_texts(
        self,
        turkish_texts: List[str],
        progress_callback: Optional[callable] = None,
    ) -> List[str]:
        """
        يترجم نصوص مقاطع SRT.

        يحافظ على:
        - عدد النصوص (نفس عدد المدخلات)
        - ترتيب النصوص

        Args:
            turkish_texts: قائمة النصوص التركية.
            progress_callback: دالة التقدم.

        Returns:
            قائمة النصوص العربية المترجمة.
        """
        return self.translate_batch(
            turkish_texts,
            progress_callback=progress_callback,
        )


# ============================================================
# نسخة عامة للاستخدام المباشر (Singleton)
# ============================================================
_translator_instance: Optional[QwenTranslator] = None
_translator_lock = threading.Lock()


def get_translator() -> QwenTranslator:
    """يعيد نسخة singleton من QwenTranslator."""
    global _translator_instance
    if _translator_instance is None:
        with _translator_lock:
            if _translator_instance is None:
                _translator_instance = QwenTranslator()
    return _translator_instance


# ============================================================
# دالة الترجمة غير المتزامنة (لتعمل مع asyncio)
# ============================================================
async def translate_srt_file_async(
    turkish_srt_path: str | Path,
    arabic_srt_path: str | Path,
    progress_callback: Optional[callable] = None,
) -> Optional[Path]:
    """
    يترجم ملف SRT تركي إلى عربي بشكل غير متزامن.

    Args:
        turkish_srt_path: مسار ملف SRT التركي.
        arabic_srt_path: مسار ملف SRT العربي الناتج.
        progress_callback: دالة التقدم.

    Returns:
        مسار الملف العربي أو None عند الفشل.
    """
    from subtitle import parse_srt_file
    from subtitle_editor import get_editor

    # تحميل الملف التركي
    try:
        srt = parse_srt_file(turkish_srt_path)
    except Exception as exc:
        _translator_logger.error(f"فشل قراءة ملف SRT: {exc}")
        return None

    if not srt.segments:
        _translator_logger.error("ملف SRT فارغ")
        return None

    # استخراج النصوص فقط
    turkish_texts = [seg.text for seg in srt.segments]

    # تشغيل الترجمة في خيط منفصل (لتفادي حظر asyncio)
    translator = get_translator()

    def _do_translate() -> List[str]:
        return translator.translate_srt_texts(
            turkish_texts,
            progress_callback=progress_callback,
        )

    try:
        translated_texts = await asyncio.to_thread(_do_translate)
    except Exception as exc:
        _translator_logger.error(f"فشل الترجمة: {exc}", exc_info=True)
        return None

    if len(translated_texts) != len(turkish_texts):
        _translator_logger.warning(
            f"عدد النصوص المترجمة ({len(translated_texts)}) != الأصلية ({len(turkish_texts)})"
        )

    # إعادة بناء ملف SRT عربي مع الحفاظ على البنية
    try:
        editor = get_editor()
        result_path = editor.rebuild_srt_with_translations(
            original_srt_path=turkish_srt_path,
            translated_texts=translated_texts,
            output_path=arabic_srt_path,
        )
        _translator_logger.info(f"تم إنشاء ملف SRT عربي: {result_path}")
        return result_path
    except Exception as exc:
        _translator_logger.error(f"فشل إنشاء ملف SRT العربي: {exc}", exc_info=True)
        return None


def warmup_translator() -> None:
    """يحمّل النموذج مسبقاً (لتسريع أول طلب)."""
    _translator_logger.info("تسخين المترجم (تحميل النموذج)...")
    translator = get_translator()
    translator.load_model()
    _translator_logger.info("تم تسخين المترجم")
