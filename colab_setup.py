# ============================================================
# خلية Google Colab الموحدة - AI_translation Bot
# ============================================================
# انسخ هذا الكود بأكمله في خلية واحدة في Google Colab
# وشغّلها. ستقوم بكل شيء تلقائياً:
#   1. تثبيت جميع المتطلبات
#   2. تنزيل المشروع وإنشاء المجلدات
#   3. تحميل نموذج Qwen2.5-3B-Instruct
#   4. تشغيل البوت
# ============================================================

# ------------------------------------------------------------
# 1) تثبيت المتطلبات
# ------------------------------------------------------------
import subprocess
import sys
import os

print("=" * 60)
print("🚀 AI_translation Bot - تثبيت المتطلبات")
print("=" * 60)

# تثبيت FFmpeg و apt packages
print("\n📦 تثبيت FFmpeg و yt-dlp...")
subprocess.run([
    "apt-get", "update", "-qq"
], check=False)
subprocess.run([
    "apt-get", "install", "-y", "-qq",
    "ffmpeg", "fonts-noto", "fonts-noto-cjk",
], check=False)

# تثبيت حزم Python
print("\n📦 تثبيت حزم Python...")
packages_to_install = [
    "pyrogram==2.0.106",
    "tgcrypto==1.2.5",
    "nest_asyncio==1.6.0",
    "yt-dlp>=2024.8.6",
    "ffmpeg-python==0.2.0",
    "openai-whisper==20231117",
    "transformers>=4.44.0",
    "accelerate>=0.30.0",
    "sentencepiece>=0.2.0",
    "protobuf>=5.0.0",
    "safetensors>=0.4.0",
    "tokenizers>=0.19.0",
    "huggingface_hub>=0.24.0",
    "regex>=2024.7.24",
    "aiofiles>=24.1.0",
    "python-dotenv==1.0.1",
]

# تثبيت PyTorch مع CUDA أولاً (مهم لـ Colab GPU)
print("\n📦 تثبيت PyTorch مع دعم CUDA...")
subprocess.run([
    sys.executable, "-m", "pip", "install", "-q",
    "torch", "torchvision",
    "--index-url", "https://download.pytorch.org/whl/cu121"
], check=False)

# تثبيت باقي الحزم
for pkg in packages_to_install:
    print(f"  ✓ {pkg}")
subprocess.run([
    sys.executable, "-m", "pip", "install", "-q", *packages_to_install
], check=False)

print("\n✅ تم تثبيت جميع المتطلبات بنجاح")


# ------------------------------------------------------------
# 2) إعداد متغيرات البيئة (عدّلها بقيمك)
# ------------------------------------------------------------
print("\n" + "=" * 60)
print("🔐 إعداد بيانات اعتماد تيليجرام")
print("=" * 60)

# ⚠️ عدّل هذه القيم بقيمك من:
# - https://my.telegram.org (للحصول على API_ID و API_HASH)
# - https://t.me/BotFather (للحصول على BOT_TOKEN)

os.environ["API_ID"] = os.environ.get("API_ID", "ضع_رقم_API_ID_هنا")
os.environ["API_HASH"] = os.environ.get("API_HASH", "ضع_API_HASH_هنا")
os.environ["BOT_TOKEN"] = os.environ.get("BOT_TOKEN", "ضع_BOT_TOKEN_هنا")

# التحقق
if "ضع_" in os.environ["API_ID"] or "ضع_" in os.environ["API_HASH"] or "ضع_" in os.environ["BOT_TOKEN"]:
    print("\n⚠️  تنبيه: لم تضبط بيانات اعتماد تيليجرام بعد!")
    print("عدّل الأسطر التالية بقيمك الحقيقية ثم أعد تشغيل الخلية:")
    print('  os.environ["API_ID"] = "123456"')
    print('  os.environ["API_HASH"] = "abcdef..."')
    print('  os.environ["BOT_TOKEN"] = "123:ABC..."')
    print("\nللحصول على القيم:")
    print("  1. API_ID و API_HASH من https://my.telegram.org")
    print("  2. BOT_TOKEN من https://t.me/BotFather")
else:
    print("\n✅ تم ضبط بيانات الاعتماد")


# ------------------------------------------------------------
# 3) تنزيل المشروع وإنشاء المجلدات
# ------------------------------------------------------------
print("\n" + "=" * 60)
print("📁 إنشاء هيكل المشروع")
print("=" * 60)

# مسار المشروع في Colab
PROJECT_DIR = "/content/AI_translation"
os.makedirs(PROJECT_DIR, exist_ok=True)
os.chdir(PROJECT_DIR)

# إنشاء المجلدات
directories = [
    "downloads", "outputs", "temp",
    "sessions", "fonts", "logs",
]
for d in directories:
    os.makedirs(d, exist_ok=True)
    print(f"  ✓ {d}/")

# تحميل الخطوط العربية لـ FFmpeg (لحرق الترجمة)
print("\n📦 تحميل الخطوط العربية...")
try:
    import urllib.request
    font_url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansArabic/NotoSansArabic-Regular.ttf"
    font_path = os.path.join(PROJECT_DIR, "fonts", "NotoSansArabic-Regular.ttf")
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
    print(f"  ✓ {font_path}")
except Exception as e:
    print(f"  ⚠️ تعذر تحميل الخط: {e}")

print("\n✅ تم إنشاء هيكل المشروع")


# ------------------------------------------------------------
# 4) كتابة ملفات المشروع
# ------------------------------------------------------------
print("\n" + "=" * 60)
print("📝 كتابة ملفات المشروع")
print("=" * 60)

# ملاحظة: في هذه الخلية، نفترض أنك رفعت ملفات المشروع إلى Colab
# أو استنسختها من GitHub. إذا لم تكن الملفات موجودة، استخدم:

# الخيار 1: استنساخ من GitHub (عدّل الرابط)
# subprocess.run(["git", "clone", "https://github.com/yourusername/AI_translation.git", PROJECT_DIR])

# الخيار 2: رفع الملفات يدوياً عبر واجهة Colab
# (Files > Upload to session storage)

# التحقق من وجود ملفات المشروع
required_files = [
    "main.py", "bot.py", "handlers.py", "callback.py", "config.py",
    "downloader.py", "translator.py", "speech_to_text.py",
    "subtitle.py", "subtitle_editor.py", "subtitle_merger.py",
    "video_merger.py", "telegram_sender.py", "video_info.py",
    "quality.py", "keyboards.py", "logger.py", "progress.py",
    "utils.py", "requirements.txt",
]

missing_files = [f for f in required_files if not os.path.exists(os.path.join(PROJECT_DIR, f))]

if missing_files:
    print(f"\n⚠️  ملفات مفقودة: {missing_files}")
    print("يرجى رفع ملفات المشروع إلى:", PROJECT_DIR)
    print("\nأو استنسخها من GitHub:")
    print(f'  !git clone https://github.com/yourusername/AI_translation.git {PROJECT_DIR}')
else:
    print("\n✅ جميع ملفات المشروع موجودة")


# ------------------------------------------------------------
# 5) تسخين نموذج Qwen2.5-3B-Instruct
# ------------------------------------------------------------
print("\n" + "=" * 60)
print("🤖 تحميل نموذج Qwen2.5-3B-Instruct")
print("=" * 60)

# إضافة مجلد المشروع إلى المسار
sys.path.insert(0, PROJECT_DIR)

# تطبيق nest_asyncio (مهم لـ Colab)
import nest_asyncio
nest_asyncio.apply()
print("✅ تم تطبيق nest_asyncio")

try:
    import torch
    print(f"\n🎮 PyTorch: {torch.__version__}")
    if torch.cuda.is_available():
        print(f"✅ GPU متاح: {torch.cuda.get_device_name(0)}")
        gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"   الذاكرة: {gpu_mem:.1f} GB")
    else:
        print("⚠️  لا يوجد GPU! سيكون الأداء بطيئاً جداً.")
        print("   تأكد من تفعيل GPU من: Runtime > Change runtime type > T4 GPU")
except ImportError:
    print("❌ PyTorch غير مثبت")

# تحميل النموذج (اختياري - قد يستغرق وقتاً طويلاً)
PRELOAD_MODEL = True  # غيّر إلى False لتأجيل التحميل

if PRELOAD_MODEL and not missing_files:
    try:
        print("\n⏳ جاري تحميل النموذج (قد يستغرق عدة دقائق)...")
        from translator import warmup_translator
        warmup_translator()
        print("✅ تم تحميل النموذج بنجاح")
    except Exception as e:
        print(f"⚠️  تعذر تحميل النموذج الآن: {e}")
        print("   سيتم تحميله عند أول طلب ترجمة.")


# ------------------------------------------------------------
# 6) التحقق من FFmpeg و yt-dlp و Whisper
# ------------------------------------------------------------
print("\n" + "=" * 60)
print("🔍 التحقق من الأدوات")
print("=" * 60)

import shutil

tools = {
    "ffmpeg": shutil.which("ffmpeg"),
    "ffprobe": shutil.which("ffprobe"),
    "yt-dlp": shutil.which("yt-dlp"),
    "whisper": shutil.which("whisper"),
}

for name, path in tools.items():
    if path:
        print(f"  ✅ {name}: {path}")
    else:
        print(f"  ❌ {name}: غير مثبت")
        # محاولة التثبيت
        if name == "yt-dlp":
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "yt-dlp"])
        elif name == "whisper":
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openai-whisper"])


# ------------------------------------------------------------
# 7) تشغيل البوت
# ------------------------------------------------------------
print("\n" + "=" * 60)
print("🚀 تشغيل البوت")
print("=" * 60)

if missing_files:
    print("\n❌ لا يمكن تشغيل البوت - ملفات مفقودة")
    print("يرجى رفع ملفات المشروع أولاً")
else:
    # تشغيل البوت
    try:
        from main import main as run_main
        print("\n▶️  بدء تشغيل البوت...")
        print("   (اضغط Ctrl+C أو زر الإيقاف لإيقاف البوت)")
        print()
        run_main()
    except KeyboardInterrupt:
        print("\n\n⏹️  تم إيقاف البوت بواسطة المستخدم")
    except Exception as e:
        print(f"\n❌ خطأ في تشغيل البوت: {e}")
        import traceback
        traceback.print_exc()


# ============================================================
# نهاية الخلية
# ============================================================
