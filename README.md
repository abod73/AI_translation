# AI_translation 🤖🎬

<div dir="rtl">

بوت تيليجرام متكامل لتحميل المقاطع التركية، تفريغ الكلام إلى نص، وترجمته إلى العربية باستخدام الذكاء الاصطناعي. يعمل بالكامل على **Google Colab** مع **GPU T4**.

## ✨ المميزات

- 📥 **تحميل الفيديوهات التركية** من YouTube, Instagram, TikTok, Vimeo وغيرها باستخدام `yt-dlp`.
- 🎚️ **دعم جودات متعددة**: 240p, 360p, 480p, 720p, 1080p, Best.
- 📤 **إرسال الفيديو** للمستخدم حتى حجم 2000 ميجابايت.
- 🎙️ **تفريغ الكلام التركي** باستخدام OpenAI Whisper عبر `subprocess`.
- 🌐 **ترجمة النص إلى العربية** باستخدام **Qwen2.5-3B-Instruct** من HuggingFace.
- 🔒 **لا يعتمد على أي API مدفوع** (لا OpenAI API، لا Google API).
- 🎯 **الحفاظ على البنية الأصلية** لملف SRT (التوقيت، الترقيم، الفراغات).
- 🔧 **تصحيح الأخطاء الشائعة** في الترجمة عبر دالة `fix_common_errors()`.
- 🎬 **دمج الترجمة في الفيديو** عبر FFmpeg (soft أو hard burn).
- 💾 **إدارة الحالة في الذاكرة** فقط (`user_sessions = {}`، لا قاعدة بيانات).

## 📋 المتطلبات

| المتطلب | الإصدار |
|---------|---------|
| Python | 3.12+ |
| GPU | T4 (موصى به) أو CPU |
| FFmpeg | أحدث إصدار |
| yt-dlp | 2024.8.6+ |
| Whisper | 20231117 |
| PyTorch | 2.0+ (مع CUDA) |
| Transformers | 4.44+ |
| Pyrogram | 2.0.106 |

## 🏗️ هيكل المشروع

```
AI_translation/
├── main.py              # نقطة الدخول (nest_asyncio.apply)
├── bot.py               # تهيئة البوت (while True بدلاً من idle)
├── handlers.py          # معالجات الرسائل + user_sessions
├── callback.py          # معالجات InlineKeyboard
├── config.py            # الإعدادات المركزية
├── downloader.py        # تحميل عبر yt-dlp (subprocess)
├── translator.py        # Qwen2.5-3B-Instruct + fix_common_errors
├── speech_to_text.py    # Whisper (subprocess)
├── subtitle.py          # تحليل وكتابة SRT
├── subtitle_editor.py   # تحرير SRT مع الحفاظ على البنية
├── subtitle_merger.py   # دمج المقاطع المتقاربة (≤ 0.5s)
├── video_merger.py      # FFmpeg لدمج الترجمة
├── telegram_sender.py   # إرسال الملفات مع التقدم
├── video_info.py        # معلومات الفيديو
├── quality.py           # خيارات الجودة
├── keyboards.py         # لوحات InlineKeyboard
├── logger.py            # التسجيل
├── progress.py          # شريط التقدم
├── utils.py             # أدوات (merge_segments, format_time...)
├── requirements.txt     # التبعيات
├── README.md            # هذا الملف
├── downloads/           # الفيديوهات المحمّلة
├── outputs/             # الملفات النهائية
├── temp/                # الملفات المؤقتة
├── sessions/            # جلسات Pyrogram
├── fonts/               # الخطوط للترجمة
└── logs/                # ملفات السجل
```

## 🚀 التشغيل على Google Colab

### 1. افتح Google Colab

أنشئ Notebook جديد واختر **GPU T4** من:
`Runtime > Change runtime type > T4 GPU`

### 2. اضبط متغيرات البيئة

```python
import os
os.environ["API_ID"] = "your_api_id"
os.environ["API_HASH"] = "your_api_hash"
os.environ["BOT_TOKEN"] = "your_bot_token"
```

للحصول على هذه القيم:
- اذهب إلى https://my.telegram.org
- سجّل الدخول برقم هاتفك
- أنشئ تطبيقاً جديداً للحصول على `API_ID` و `API_HASH`
- تحدّث إلى [@BotFather](https://t.me/BotFather) على تيليجرام لإنشاء بوت والحصول على `BOT_TOKEN`

### 3. شغّل الخلية الموحدة

انسخ محتوى ملف `colab_setup.py` (أو من قسم Colab في هذا الـ README) في خلية واحدة وشغّلها. ستقوم بـ:

1. تثبيت جميع المتطلبات.
2. استنساخ المشروع (أو إنشائه من الصفر).
3. إنشاء المجلدات.
4. تحميل نموذج Qwen2.5-3B-Instruct.
5. تشغيل البوت.

## 📖 شرح المراحل

### المرحلة الأولى: التحميل

1. يرسل المستخدم رابط فيديو تركي.
2. يعرض البوت لوحة اختيار الجودة (240p, 360p, 480p, 720p, 1080p, Best).
3. بعد الاختيار، ينفذ:
   ```bash
   yt-dlp -f "[format]" -o downloads/video.mp4 "URL"
   ```
4. يُرسل الفيديو للمستخدم (حتى 2000 ميجابايت).

### المرحلة الثانية: تفريغ الكلام

1. بعد إرسال الفيديو، يعرض البوت سؤال: "هل تريد استخراج الكلام التركي؟".
2. عند الضغط على "نعم"، ينفذ:
   ```bash
   whisper downloads/video.mp4 \
       --task transcribe \
       --language Turkish \
       --model small \
       --output_format srt \
       --output_dir downloads/
   ```
3. يُرسل ملف `video.srt`.

### المرحلة الثالثة: الترجمة

1. بعد إرسال ملف SRT، يعرض البوت سؤال: "هل تريد ترجمة الملف إلى العربية؟".
2. عند الضغط على "نعم":
   - يقرأ ملف SRT.
   - يحافظ على التوقيت، الترقيم، والفراغات.
   - يرسل النص فقط إلى **Qwen2.5-3B-Instruct**.
   - يعيد إنشاء ملف SRT العربي.
   - يطبق `fix_common_errors()` لتصحيح الأخطاء.
3. يُرسل ملف SRT العربي.

### المرحلة الرابعة (اختيارية): دمج الترجمة

1. بعد إرسال SRT العربي، يعرض البوت سؤال: "هل تريد دمج الترجمة في الفيديو؟".
2. عند الضغط على "نعم"، يستخدم FFmpeg لحرق الترجمة في الفيديو.
3. يُرسل الفيديو الناتج.

## 🎯 الـ Prompt المستخدم في الترجمة

يُستخدم الـ Prompt التالي حرفياً (في `config.py`):

```
أنت خبير دبلجة وترجمة مسلسلات تركية إلى العربية.
ترجم المعنى وليس الكلمات.
اكتب عربية فصحى طبيعية.
لا تستخدم ترجمة حرفية.
إذا كانت كلمة Blue أو Mavi يقصد بها الاكتئاب فاكتب الاكتئاب.
إذا كانت اسماً فلا تترجمها.
صحح الأخطاء التالية:
مملوءة → مليئة
إتفقنا → اتّفقنا
ياصديقي → يا صديقي
صلوا أن → ادعوا أن
اللون الأزرق → الاكتئاب (إذا كان السياق يدل على ذلك)
لا تترجم
NAME_X
وأخرج الترجمة فقط.
```

## 🔧 دالة `fix_common_errors()`

تستخدم Regex لتصحيح الأخطاء الشائعة:

| الخطأ | التصحيح |
|-------|---------|
| مملوءة | مليئة |
| إتفقنا | اتّفقنا |
| ياصديقي | يا صديقي |
| صلوا أن | ادعوا أن |
| اللون الأزرق | الاكتئاب |
| Blue / Mavi | الاكتئاب |
| المسافات قبل علامات الترقيم | تُزال |
| المسافات المتعددة | تُوحَّد |

## 🗂️ إدارة الحالة

تتم في الذاكرة فقط عبر القاموس:

```python
user_sessions = {}
```

لكل مستخدم:
- `video_path`: مسار الفيديو.
- `turkish_srt_path`: مسار ملف SRT التركي.
- `arabic_srt_path`: مسار ملف SRT العربي.
- `current_step`: الخطوة الحالية.

## 🛠️ استبدال `idle()` بحلقة `while True`

في `bot.py`:

```python
# بدلاً من:
# await idle()

# نستخدم:
while True:
    await asyncio.sleep(3600)
```

## 🔀 دالة `merge_segments()`

في `utils.py`، تدمج المقاطع التي الفرق بينها أقل أو يساوي 0.5 ثانية:

```python
def merge_segments(segments, max_gap=0.5):
    # دمج المقاطع المتقاربة
    ...
```

## 📊 تحميل الفيديو

يستخدم `subprocess` فقط (لا يستخدم مكتبة `yt_dlp`):

```python
cmd = [
    "yt-dlp",
    "-f", format_string,
    "-o", "downloads/video.mp4",
    "URL",
]
```

## 🎙️ تفريغ الكلام

يستخدم `subprocess` فقط (لا يستخدم مكتبة `whisper`):

```python
cmd = [
    "whisper", "downloads/video.mp4",
    "--task", "transcribe",
    "--language", "Turkish",
    "--model", "small",
    "--output_format", "srt",
    "--output_dir", "downloads/",
]
```

## 🌐 تحميل Qwen2.5-3B-Instruct

من HuggingFace باستخدام `transformers`:

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-3B-Instruct")
model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-3B-Instruct",
    torch_dtype="auto",
    device_map="auto",
)
```

## ⚠️ ملاحظات مهمة

1. **لا توجد قاعدة بيانات**: كل البيانات في الذاكرة فقط.
2. **لا يستخدم API مدفوع**: كل المعالجة محلية.
3. **يتطلب GPU**: للترجمة بسرعة معقولة (T4 على Colab كافٍ).
4. **الحد الأقصى للفيديو**: 2000 ميجابايت (حد تيليجرام).
5. **معالجة الأخطاء**: البوت يعيد المحاولة 3 مرات قبل الفشل.

## 🐛 استكشاف الأخطاء

### المشكلة: "event loop is already running"
**الحل**: تأكد من تشغيل `nest_asyncio.apply()` في `main.py` (تم ذلك افتراضياً).

### المشكلة: "out of memory" أثناء الترجمة
**الحل**: استخدم GPU T4 أو أعلى. يمكن تقليل `QWEN_BATCH_SIZE` في `config.py`.

### المشكلة: Whisper بطيء جداً
**الحل**: استخدم نموذج `tiny` أو `base` بدلاً من `small` (في `config.py`).

### المشكلة: فشل تحميل الفيديو
**الحل**: تحقق من الرابط وأن الفيديو متاح للعموم. قد تحتاج لاستخدام VPN لبعض المنصات.

### المشكلة: فشل إنشاء البوت
**الحل**: تحقق من صحة `API_ID`, `API_HASH`, `BOT_TOKEN`.

## 📝 الترخيص

هذا المشروع مفتوح المصدر ويمكن استخدامه وتعديله بحرية.

## 🤝 المساهمة

المساهمات مرحب بها! يرجى فتح issue أو pull request.

## 📞 التواصل

للأسئلة والدعم، افتح issue في المستودع.

</div>
