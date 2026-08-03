# -*- coding: utf-8 -*-
"""
بوت تليجرام لخدمات نصية وصوتية بالذكاء الاصطناعي
- قائمة رئيسية ثابتة تحت الشاشة
- نظام إحالة (دعوة صديق = محاولات مجانية إضافية)
- عرض باقات مرقمة + دفع يدوي + موافقة/رفض من الأدمن + رسالة يدوية للمستخدم
"""

import os
import sqlite3
import logging
from datetime import datetime

from openai import OpenAI
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============ الإعدادات ============
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
AGENTROUTER_API_KEY = os.getenv("AGENTROUTER_API_KEY", "")
AGENTROUTER_BASE_URL = os.getenv("AGENTROUTER_BASE_URL", "https://openrouter.ai/api/v1")
TEXT_MODEL = os.getenv("TEXT_MODEL", "openrouter/free")
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")
TTS_VOICE = os.getenv("TTS_VOICE", "alloy")
STT_MODEL = os.getenv("STT_MODEL", "whisper-1")

ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
FREE_TRIAL_LIMIT = int(os.getenv("FREE_TRIAL_LIMIT", "4"))
REFERRAL_BONUS = int(os.getenv("REFERRAL_BONUS", "3"))

INSTAPAY_INFO = os.getenv("INSTAPAY_INFO", "اسم انستاباي / رقم المحفظة هنا")
VODAFONE_CASH_NUMBER = os.getenv("VODAFONE_CASH_NUMBER", "01xxxxxxxxx")

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_data.db")
TMP_DIR = os.path.join(os.path.dirname(__file__), "tmp")
os.makedirs(TMP_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

client = OpenAI(api_key=AGENTROUTER_API_KEY, base_url=AGENTROUTER_BASE_URL)

# ============ الباقات (عدّل هنا الأسعار والمميزات براحتك) ============

PACKAGES = {
    1: {
        "price_egp": 50,
        "points": 100,
        "features": ["١٠٠ محاولة على كل الخدمات النصية", "صالحة لحد ما تخلص"],
    },
    2: {
        "price_egp": 100,
        "points": 250,
        "features": ["٢٥٠ محاولة على كل الخدمات النصية", "أفضل سعر للنقطة", "صالحة لحد ما تخلص"],
    },
    3: {
        "price_egp": 200,
        "points": 600,
        "features": ["٦٠٠ محاولة على كل الخدمات النصية", "أفضل قيمة", "صالحة لحد ما تخلص"],
    },
}

# ============ تعريف الخدمات النصية ============

TEXT_SERVICES = {
    "caption": {
        "label": "🎨 كابشنز وأفكار ريلز وهاشتاجات",
        "system": (
            "أنت مساعد متخصص في كتابة محتوى سوشيال ميديا باللهجة المصرية "
            "العامية الودودة. اكتب كابشنز وأفكار ريلز وهاشتاجات جذابة ومختصرة. "
            "اذهب مباشرة للمحتوى من غير مقدمات طويلة."
        ),
        "prompt_hint": "ابعتلي موضوع البوست أو المنتج.",
    },
    "cv": {
        "label": "📄 سيرة ذاتية وخطابات تقديم",
        "system": (
            "أنت خبير توظيف ومتخصص في كتابة السير الذاتية وخطابات التقديم "
            "بصيغة احترافية وواضحة. رتب المحتوى بشكل منظم وسهل القراءة."
        ),
        "prompt_hint": "ابعتلي بياناتك (الوظيفة المطلوبة + خبراتك ومهاراتك).",
    },
    "summary": {
        "label": "📚 تلخيص وكتابة أبحاث ومقالات",
        "system": (
            "أنت مساعد أكاديمي متخصص في تلخيص النصوص الطويلة واستخراج "
            "أهم النقاط بشكل منظم وواضح، أو المساعدة في صياغة أبحاث ومقالات."
        ),
        "prompt_hint": "ابعتلي النص اللي عايز تلخصه، أو موضوع المقال/البحث.",
    },
    "translate": {
        "label": "🌐 ترجمة نصوص",
        "system": (
            "أنت مترجم محترف. ترجم النص المُرسل بدقة مع الحفاظ على المعنى "
            "والسياق. لو مفيش لغة محددة، ترجم من/إلى الإنجليزية والعربية حسب لغة النص."
        ),
        "prompt_hint": "ابعتلي النص اللي عايز تترجمه (وحدد اللغة المطلوبة لو حابب).",
    },
    "product": {
        "label": "🛍️ أوصاف منتجات",
        "system": (
            "أنت متخصص في كتابة أوصاف منتجات جذابة ومقنعة لمتاجر إلكترونية، "
            "تبرز مميزات المنتج بأسلوب تسويقي مختصر."
        ),
        "prompt_hint": "ابعتلي اسم المنتج ومواصفاته الأساسية.",
    },
    "email": {
        "label": "✉️ رسائل بريد إلكتروني احترافية",
        "system": (
            "أنت مساعد متخصص في صياغة رسائل بريد إلكتروني احترافية "
            "(تفاوض، اعتذار، متابعة، طلبات) بأسلوب مهذب وواضح."
        ),
        "prompt_hint": "اشرحلي الموقف والغرض من الرسالة.",
    },
    "plan": {
        "label": "🗓️ خطة نشر محتوى شهرية",
        "system": (
            "أنت استراتيجي محتوى سوشيال ميديا. اقترح خطة نشر مبسطة (أفكار "
            "بوستات موزعة على الأسبوع) بناءً على مجال العميل ومنصته."
        ),
        "prompt_hint": "قولي مجال نشاطك والمنصة اللي هتنشر عليها.",
    },
}

AUDIO_SERVICES = {
    "tts": {"label": "🔊 تحويل نص إلى صوت"},
    "stt": {"label": "📝 تحويل صوت إلى نص"},
    "audio_translate": {"label": "🌍 ترجمة رسالة صوتية لنص"},
}

# ============ قاعدة البيانات ============

def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db_connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            free_trials_used INTEGER DEFAULT 0,
            points_balance INTEGER DEFAULT 0,
            subscription_active INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT NULL,
            created_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def get_or_create_user(user_id: int, username: str, referred_by: int = None):
    conn = db_connect()
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    is_new = row is None
    if row is None:
        conn.execute(
            "INSERT INTO users (user_id, username, referred_by, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username, referred_by, datetime.utcnow().isoformat()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return row, is_new


def can_use_service(user_id: int):
    conn = db_connect()
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if row is None:
        return False, "user_not_found"
    if row["free_trials_used"] < FREE_TRIAL_LIMIT:
        return True, "trial"
    if row["subscription_active"] == 1:
        return True, "subscription"
    if row["points_balance"] > 0:
        return True, "points"
    return False, "none"


def consume_usage(user_id: int, reason: str):
    conn = db_connect()
    if reason == "trial":
        conn.execute(
            "UPDATE users SET free_trials_used = free_trials_used + 1 WHERE user_id = ?",
            (user_id,),
        )
    elif reason == "points":
        conn.execute(
            "UPDATE users SET points_balance = points_balance - 1 WHERE user_id = ?",
            (user_id,),
        )
    conn.commit()
    conn.close()


def add_points(user_id: int, amount: int):
    conn = db_connect()
    conn.execute(
        "UPDATE users SET points_balance = points_balance + ? WHERE user_id = ?",
        (amount, user_id),
    )
    conn.commit()
    conn.close()


# ============ استدعاء الذكاء الاصطناعي ============

def ask_ai_text(system_prompt: str, user_text: str) -> str:
    try:
        response = client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            max_tokens=700,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"AI text error: {e}")
        return "حصل خطأ أثناء التواصل مع الذكاء الاصطناعي، حاول تاني بعد شوية."


def text_to_speech(text: str, out_path: str) -> bool:
    try:
        with client.audio.speech.with_streaming_response.create(
            model=TTS_MODEL, voice=TTS_VOICE, input=text
        ) as response:
            response.stream_to_file(out_path)
        return True
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return False


def speech_to_text(file_path: str) -> str:
    try:
        with open(file_path, "rb") as f:
            result = client.audio.transcriptions.create(model=STT_MODEL, file=f)
        return result.text
    except Exception as e:
        logger.error(f"STT error: {e}")
        return "حصل خطأ أثناء تحويل الصوت لنص، حاول تاني بعد شوية."


def audio_translate(file_path: str) -> str:
    try:
        with open(file_path, "rb") as f:
            result = client.audio.translations.create(model=STT_MODEL, file=f)
        return result.text
    except Exception as e:
        logger.error(f"Audio translate error: {e}")
        return "حصل خطأ أثناء ترجمة الصوت، حاول تاني بعد شوية."


# ============ الحالة المؤقتة ============
user_state = {}
admin_state = {}

PERSISTENT_KEYBOARD = ReplyKeyboardMarkup(
    [["📋 القائمة الرئيسية"]], resize_keyboard=True, is_persistent=True
)

BACK_TO_MENU_INLINE = InlineKeyboardMarkup(
    [[InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_main")]]
)


def main_menu():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📝 الخدمات النصية", callback_data="menu_text")],
            [InlineKeyboardButton("🎧 الخدمات الصوتية", callback_data="menu_audio")],
            [InlineKeyboardButton("💳 الباقات والأسعار", callback_data="menu_packages")],
            [InlineKeyboardButton("🎁 ادعُ صديق واكسب نقاط", callback_data="menu_referral")],
            [InlineKeyboardButton("💰 رصيدي / اشتراكي", callback_data="check_balance")],
        ]
    )


def text_services_menu():
    rows = [
        [InlineKeyboardButton(v["label"], callback_data=f"text_svc:{k}")]
        for k, v in TEXT_SERVICES.items()
    ]
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def audio_services_menu():
    rows = [
        [InlineKeyboardButton(v["label"], callback_data=f"audio_svc:{k}")]
        for k, v in AUDIO_SERVICES.items()
    ]
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def packages_text():
    numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    lines = ["📦 *الباقات المتاحة:*\n"]
    for i, (num, pkg) in enumerate(PACKAGES.items()):
        emoji = numbers[i] if i < len(numbers) else f"{num}."
        lines.append(f"{emoji} باقة {pkg['price_egp']} جنيه - {pkg['points']} نقطة")
        for feat in pkg["features"]:
            lines.append(f"   • {feat}")
        lines.append("")
    lines.append("✏️ اكتب رقم الباقة اللي عايزها عشان تشترك فيها.")
    return "\n".join(lines)


# ============ أوامر البوت ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referred_by = None
    if context.args and context.args[0].startswith("ref_"):
        try:
            candidate = int(context.args[0].replace("ref_", ""))
            if candidate != user.id:
                referred_by = candidate
        except ValueError:
            pass

    row, is_new = get_or_create_user(user.id, user.username or user.first_name, referred_by)

    if is_new and referred_by:
        conn = db_connect()
        referrer = conn.execute("SELECT * FROM users WHERE user_id = ?", (referred_by,)).fetchone()
        conn.close()
        if referrer:
            add_points(referred_by, REFERRAL_BONUS)
            try:
                await context.bot.send_message(
                    referred_by,
                    f"🎉 حد جديد استخدم رابط الدعوة بتاعك! خدت {REFERRAL_BONUS} محاولات إضافية هدية.",
                )
            except Exception:
                pass

    user_state[user.id] = {}
    await update.message.reply_text(
        f"أهلاً {user.first_name} 👋\n\n"
        f"عندك {FREE_TRIAL_LIMIT} محاولات مجانية تجرب بيها البوت.\n"
        "اختار نوع الخدمة:",
        reply_markup=PERSISTENT_KEYBOARD,
    )
    await update.message.reply_text("القائمة:", reply_markup=main_menu())


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"الـ Chat ID بتاعك: {update.effective_chat.id}")


async def show_main_menu(update: Update):
    await update.message.reply_text("القائمة:", reply_markup=main_menu())


async def send_subscription_prompt(chat_send_func):
    await chat_send_func(
        "خلصت المحاولات المجانية والنقاط 🙏\n\n"
        "من فضلك اختار باقة من قائمة 'الباقات والأسعار' في القائمة الرئيسية عشان تكمل."
    )


# ============ القوائم ============

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "back_main":
        user_state[user_id] = {}
        await query.edit_message_text("القائمة:", reply_markup=main_menu())

    elif data == "menu_text":
        await query.edit_message_text("اختار الخدمة النصية:", reply_markup=text_services_menu())

    elif data == "menu_audio":
        await query.edit_message_text("اختار الخدمة الصوتية:", reply_markup=audio_services_menu())

    elif data == "menu_packages":
        user_state[user_id] = {"mode": "choose_package"}
        await query.edit_message_text(
            packages_text(),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ رجوع", callback_data="back_main")]]
            ),
        )

    elif data == "menu_referral":
        me = await context.bot.get_me()
        link = f"https://t.me/{me.username}?start=ref_{user_id}"
        await query.edit_message_text(
            f"🎁 ابعت الرابط ده لأصدقائك، وكل واحد يدخل من خلاله يديك "
            f"{REFERRAL_BONUS} محاولات إضافية مجاناً:\n\n{link}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ رجوع", callback_data="back_main")]]
            ),
        )

    elif data.startswith("text_svc:"):
        key = data.split(":", 1)[1]
        service = TEXT_SERVICES[key]
        user_state[user_id] = {"mode": "text", "service": key}
        await query.edit_message_text(f"{service['label']}\n\n{service['prompt_hint']}")

    elif data.startswith("audio_svc:"):
        key = data.split(":", 1)[1]
        service = AUDIO_SERVICES[key]
        user_state[user_id] = {"mode": "audio", "service": key}
        if key == "tts":
            hint = "ابعتلي النص اللي عايز تحوله لصوت."
        else:
            hint = "ابعتلي رسالة صوتية (Voice Message) أو ملف صوتي."
        await query.edit_message_text(f"{service['label']}\n\n{hint}")

    elif data == "check_balance":
        conn = db_connect()
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        remaining_trial = max(0, FREE_TRIAL_LIMIT - row["free_trials_used"])
        sub_status = "مفعّل ✅" if row["subscription_active"] == 1 else "غير مفعّل"
        await query.edit_message_text(
            f"محاولاتك المجانية المتبقية: {remaining_trial}\n"
            f"رصيد النقاط: {row['points_balance']}\n"
            f"الاشتراك الشهري: {sub_status}",
            reply_markup=main_menu(),
        )

    # ---- أزرار الأدمن على إيصال الدفع ----
    elif data.startswith("approve:"):
        if query.from_user.id != ADMIN_CHAT_ID:
            return
        _, target_id, pkg_num = data.split(":")
        target_id = int(target_id)
        pkg = PACKAGES.get(int(pkg_num))
        if pkg:
            add_points(target_id, pkg["points"])
            try:
                await context.bot.send_message(
                    target_id,
                    f"✅ تم شحن رصيدك بنجاح! اتضاف {pkg['points']} نقطة لحسابك. استمتع بالخدمة 🎉",
                )
            except Exception:
                pass
            await query.edit_message_text(query.message.text + "\n\n✅ تمت الموافقة والشحن")

    elif data.startswith("reject:"):
        if query.from_user.id != ADMIN_CHAT_ID:
            return
        target_id = int(data.split(":")[1])
        try:
            await context.bot.send_message(
                target_id,
                "للأسف لم نتمكن من تأكيد عملية الدفع. من فضلك تواصل معانا أو أعد المحاولة.",
            )
        except Exception:
            pass
        await query.edit_message_text(query.message.text + "\n\n❌ تم الرفض")

    elif data.startswith("msg:"):
        if query.from_user.id != ADMIN_CHAT_ID:
            return
        target_id = int(data.split(":")[1])
        admin_state[query.from_user.id] = {"messaging_user": target_id}
        await context.bot.send_message(
            ADMIN_CHAT_ID, f"✍️ اكتب الرسالة اللي عايز تبعتها للمستخدم {target_id}:"
        )


# ============ استقبال النصوص ============

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # ---- زرار القائمة الثابت ----
    if text == "📋 القائمة الرئيسية":
        user_state[user_id] = {}
        await show_main_menu(update)
        return

    # ---- الأدمن بيكتب رسالة لمستخدم معين ----
    if update.effective_chat.id == ADMIN_CHAT_ID and admin_state.get(ADMIN_CHAT_ID, {}).get("messaging_user"):
        target_id = admin_state[ADMIN_CHAT_ID]["messaging_user"]
        try:
            await context.bot.send_message(target_id, f"📩 رسالة من الدعم:\n\n{text}")
            await update.message.reply_text("تم إرسال الرسالة ✅")
        except Exception:
            await update.message.reply_text("حصل خطأ أثناء إرسال الرسالة.")
        admin_state[ADMIN_CHAT_ID] = {}
        return

    get_or_create_user(user_id, update.effective_user.username or update.effective_user.first_name)
    state = user_state.get(user_id, {})
    mode = state.get("mode")

    # ---- اختيار رقم باقة ----
    if mode == "choose_package":
        if text.strip() not in [str(k) for k in PACKAGES.keys()]:
            await update.message.reply_text("من فضلك اكتب رقم باقة صحيح من القائمة.")
            return
        pkg_num = int(text.strip())
        pkg = PACKAGES[pkg_num]
        user_state[user_id] = {"mode": "awaiting_payment", "package": pkg_num}
        await update.message.reply_text(
            f"اخترت باقة {pkg['price_egp']} جنيه ({pkg['points']} نقطة) 👍\n\n"
            f"حوّل المبلغ على واحد من الرقمين دول:\n\n"
            f"💳 انستاباي: {INSTAPAY_INFO}\n"
            f"📱 فودافون كاش: {VODAFONE_CASH_NUMBER}\n\n"
            "بعد التحويل، ابعت في نفس الشات:\n"
            "١) صورة سكرين شوت للتحويل\n"
            "٢) رقم الموبايل اللي حولت منه (في وصف الصورة)\n\n"
            "وهيتفعّل رصيدك خلال ساعات قليلة."
        )
        return

    if mode == "awaiting_payment":
        await update.message.reply_text(
            "من فضلك ابعت صورة سكرين شوت التحويل (مش نص) عشان نقدر نأكد الدفع."
        )
        return

    if mode not in ("text", "audio"):
        await show_main_menu(update)
        return

    allowed, reason = can_use_service(user_id)
    if not allowed:
        await send_subscription_prompt(update.message.reply_text)
        return

    await update.message.chat.send_action("typing")

    service_key = state.get("service")
    if mode == "text":
        service = TEXT_SERVICES[service_key]
        reply = ask_ai_text(service["system"], text)
        consume_usage(user_id, reason)
        await update.message.reply_text(reply, reply_markup=BACK_TO_MENU_INLINE)

    elif mode == "audio" and service_key == "tts":
        out_path = os.path.join(TMP_DIR, f"tts_{user_id}.mp3")
        ok = text_to_speech(text, out_path)
        if ok:
            consume_usage(user_id, reason)
            with open(out_path, "rb") as f:
                await update.message.reply_voice(f, reply_markup=BACK_TO_MENU_INLINE)
            os.remove(out_path)
        else:
            await update.message.reply_text("حصل خطأ أثناء توليد الصوت، حاول تاني.")
   
