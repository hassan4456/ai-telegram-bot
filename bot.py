# -*- coding: utf-8 -*-
"""
بوت تليجرام لخدمات نصية وصوتية بالذكاء الاصطناعي
مبني على agentrouter.org (متوافق مع OpenAI API)

يدعم الباقات الذكية، تفعيل الدفع بضغطة زر واحدة للأدمن، ونظام الإحالة ودعوة الأصدقاء.
"""

import os
import sqlite3
import logging
from datetime import datetime

from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
AGENTROUTER_BASE_URL = os.getenv("AGENTROUTER_BASE_URL", "https://agentrouter.org/v1")
TEXT_MODEL = os.getenv("TEXT_MODEL", "gpt-4o-mini")
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")
TTS_VOICE = os.getenv("TTS_VOICE", "alloy")
STT_MODEL = os.getenv("STT_MODEL", "whisper-1")

ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
FREE_TRIAL_LIMIT = int(os.getenv("FREE_TRIAL_LIMIT", "4"))

INSTAPAY_INFO = os.getenv("INSTAPAY_INFO", "01016336323")
VODAFONE_CASH_NUMBER = os.getenv("VODAFONE_CASH_NUMBER", "01016336323")

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_data.db")
TMP_DIR = os.path.join(os.path.dirname(__file__), "tmp")
os.makedirs(TMP_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

client = OpenAI(api_key=AGENTROUTER_API_KEY, base_url=AGENTROUTER_BASE_URL)

# ============ تعريف الخدمات ============

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
            referred_by INTEGER DEFAULT 0,
            invites_count INTEGER DEFAULT 0,
            created_at TEXT
        )
        """
    )
    # تحديث الأعمدة لو كانت قاعدة البيانات قديمة
    try:
        conn.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE users ADD COLUMN invites_count INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


def get_or_create_user(user_id: int, username: str):
    conn = db_connect()
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    is_new = False
    if row is None:
        conn.execute(
            "INSERT INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
            (user_id, username, datetime.utcnow().isoformat()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        is_new = True
    conn.close()
    return is_new, row


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


def activate_subscription(user_id: int):
    conn = db_connect()
    conn.execute("UPDATE users SET subscription_active = 1 WHERE user_id = ?", (user_id,))
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


def process_referral(referrer_id: int, new_user_id: int):
    conn = db_connect()
    conn.execute(
        "UPDATE users SET invites_count = invites_count + 1, points_balance = points_balance + 3 WHERE user_id = ?",
        (referrer_id,),
    )
    conn.execute(
        "UPDATE users SET referred_by = ? WHERE user_id = ?",
        (referrer_id, new_user_id),
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


# ============ الحالة المؤقتة والقوائم ============
user_state = {}


def main_menu():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📝 الخدمات النصية", callback_data="menu_text")],
            [InlineKeyboardButton("🎧 الخدمات الصوتية", callback_data="menu_audio")],
            [InlineKeyboardButton("📦 الباقات والاشتراكات", callback_data="show_packages")],
            [InlineKeyboardButton("🔗 دعوة الأصدقاء (محاولات مجانية)", callback_data="show_referral")],
            [InlineKeyboardButton("💳 رصيدي / اشتراكي", callback_data="check_balance")],
        ]
    )


def packages_menu_text():
    return (
        "📦 **اختر الباقة المناسبة لك بالضغط على الأزرار أدناه:**\n\n"
        "1️⃣ **الباقة 1 (100 جنيه)**\n"
        "   • **النقاط:** 300 نقطة\n"
        "   • **المزايا:** تكفي لتوليد ~8 فيديوهات أو 20 صورة احترافية.\n"
        "   • **الصلاحية:** شهر كامل.\n\n"
        "2️⃣ **الباقة 2 (250 جنيه) - الأكثر طلباً 🔥**\n"
        "   • **النقاط:** 800 نقطة (+100 نقطة هدية)\n"
        "   • **المزايا:** تكفي لتوليد ~22 فيديو أو 55 صورة.\n"
        "   • **الصلاحية:** شهر كامل.\n\n"
        "3️⃣ **الباقة 3 (500 جنيه) - كبار المستخدمين 👑**\n"
        "   • **النقاط:** 2000 نقطة\n"
        "   • **المزايا:** تكفي لإنتاج 50 فيديو واستخدام مكثف.\n"
        "   • **الصلاحية:** شهر كامل.\n\n"
        "👇 **اضغط على رقم الباقة التي تريد الاشتراك فيها:**"
    )


def packages_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("1️⃣ اختيار باقة 100 جنيه (300 نقطة)", callback_data="select_pkg:100:300:100 جنيه")],
            [InlineKeyboardButton("2️⃣ اختيار باقة 250 جنيه (800 نقطة) 🔥", callback_data="select_pkg:250:800:250 جنيه")],
            [InlineKeyboardButton("3️⃣ اختيار باقة 500 جنيه (2000 نقطة) 👑", callback_data="select_pkg:500:2000:500 جنيه")],
            [InlineKeyboardButton("⬅️ رجوع للقائمة الرئيسية", callback_data="back_main")],
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


# ============ أوامر البوت ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    is_new, _ = get_or_create_user(user_id, user.username or user.first_name)
    user_state[user_id] = {}

    # معالجة نظام الإحالة (Referral)
    if is_new and context.args:
        try:
            referrer_id = int(context.args[0])
            if referrer_id != user_id:
                process_referral(referrer_id, user_id)
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=(
                            f"🎉 **خبر رائع!**\n"
                            f"انضم مستخدم جديد ({user.first_name}) عن طريق رابط الدعوة الخاص بك!\n"
                            f"🎁 **تم إضافة 3 محاولات (نقاط) مجانية لحسابك بنجاح.**"
                        ),
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    logger.error(f"Error notifying referrer: {e}")
        except ValueError:
            pass

    await update.message.reply_text(
        f"أهلاً بك يا {user.first_name} 👋\n\n"
        f"عندك {FREE_TRIAL_LIMIT} محاولات مجانية لتجربة البوت.\n"
        "اختار الخدمة المطلوبة من القائمة التالية:",
        reply_markup=main_menu(),
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"الـ Chat ID بتاعك: {update.effective_chat.id}")


async def send_subscription_prompt(reply_func):
    text = (
        "انتهت المحاولات المجانية الخاصة بك! 🙏\n\n"
        "للمتابعة والاستمرار، يرجى اختيار الباقة المناسبة لك:"
    )
    await reply_func(text, reply_markup=packages_keyboard(), parse_mode="Markdown")


# ============ القوائم والتفاعلات ============

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "back_main":
        user_state[user_id] = {}
        await query.edit_message_text("اختار نوع الخدمة:", reply_markup=main_menu())

    elif data == "menu_text":
        await query.edit_message_text("اختار الخدمة النصية:", reply_markup=text_services_menu())

    elif data == "menu_audio":
        await query.edit_message_text("اختار الخدمة الصوتية:", reply_markup=audio_services_menu())

    elif data == "show_packages":
        await query.edit_message_text(packages_menu_text(), parse_mode="Markdown", reply_markup=packages_keyboard())

    elif data.startswith("select_pkg:"):
        _, price, points, name = data.split(":")
        user_state[user_id] = user_state.get(user_id, {})
        user_state[user_id]["selected_package"] = {
            "name": f"باقة {name}",
            "price": price,
            "points": int(points),
        }
        msg = (
            f"✅ **لقد اخترت: باقة {name} ({points} نقطة)**\n\n"
            f"💳 **طرق الدفع المتاحة:**\n"
            f"📱 **فودافون كاش:** `{VODAFONE_CASH_NUMBER}`\n"
            f"💳 **انستاباي:** `{INSTAPAY_INFO}`\n\n"
            f"💵 **المبلغ المطلوب تحويله:** {price} جنيه\n\n"
            f"📷 **الخطوة الأخيرة:**\n"
            f"بعد التحويل، ارفع **صورة الإيصال (ScreenShot)** هنا في الشات وسيتم التفعيل فوراً!"
        )
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 تغير الباقة", callback_data="show_packages")]])
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=back_kb)

    elif data == "show_referral":
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username
        ref_link = f"https://t.me/{bot_username}?start={user_id}"

        _, row = get_or_create_user(user_id, query.from_user.username or query.from_user.first_name)
        invites_count = row["invites_count"] if row and "invites_count" in row.keys() else 0
        earned_points = invites_count * 3

        ref_text = (
            "🎁 **نظام دعوة الأصدقاء (احصل على محاولات مجانية!)**\n\n"
            "شارك رابطك الخاص مع أصدقائك أو في الجروبات، "
            "ومع كل شخص ينضم للبوت عن طريقك **ستحصل على 3 محاولات مجانية فوراً!** 🎉\n\n"
            f"🔗 **رابط الدعوة الخاص بك:**\n"
            f"`{ref_link}`\n\n"
            f"📊 **إحصائياتك:**\n"
            f"• عدد الأصدقاء المسجلين: **{invites_count} شخص**\n"
            f"• المحاولات المكتسبة: **{earned_points} نقطة/محاولة**"
        )

        share_url = f"https://t.me/share/url?url={ref_link}&text=جرب%20هذا%20البوت%20الرائع%20لخدمات%20الذكاء%20الاصطناعي!"
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📲 مشاركة الرابط مع صديق", url=share_url)],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="back_main")],
            ]
        )
        await query.edit_message_text(ref_text, parse_mode="Markdown", reply_markup=keyboard)

    elif data.startswith("admin_approve:"):
        if query.from_user.id != ADMIN_CHAT_ID:
            await query.answer("عذراً، هذا الأمر للمشرف فقط.", show_alert=True)
            return
        _, target_id_str, points_str = data.split(":")
        target_id = int(target_id_str)
        points = int(points_str)

        add_points(target_id, points)

        updated_caption = f"{query.message.caption}\n\n✅ **تم التفعيل بنجاح وإضافة {points} نقطة!**"
        await query.edit_message_caption(caption=updated_caption, parse_mode="Markdown")

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🎉 **تم التأكد من الدفع وتفعيل حسابك!**\nتم إضافة **{points} نقطة** لرصيدك بنجاح. يمكنك استخدام البوت الآن.",
            )
        except Exception as e:
            logger.error(f"Failed to notify user {target_id}: {e}")

    elif data.startswith("admin_reject:"):
        if query.from_user.id != ADMIN_CHAT_ID:
            await query.answer("عذراً، هذا الأمر للمشرف فقط.", show_alert=True)
            return
        _, target_id_str = data.split(":")
        target_id = int(target_id_str)

        updated_caption = f"{query.message.caption}\n\n❌ **تم رفض الطلب.**"
        await query.edit_message_caption(caption=updated_caption, parse_mode="Markdown")

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="❌ **عذراً، لم نتمكن من التأكد من عملية التحويل.**\nإذا كانت هناك مشكلة يرجى التواصل مع الدعم الفني.",
            )
        except Exception as e:
            logger.error(f"Failed to notify user {target_id}: {e}")

    elif data.startswith("text_svc:"):
        key = data.split(":", 1)[1]
        service = TEXT_SERVICES[key]
        user_state[user_id] = {"mode": "text", "service": key}
        await query.edit_message_text(f"{service['label']}\n\n{service['prompt_hint']}")

    elif data.startswith("audio_svc:"):
        key = data.split(":", 1)[1]
        service = AUDIO_SERVICES[key]
        user_state[user_id] = {"mode": "audio", "service": key}
        hint = "ابعتلي النص اللي عايز تحوله لصوت." if key == "tts" else "ابعتلي رسالة صوتية (Voice Message) أو ملف صوتي."
        await query.edit_message_text(f"{service['label']}\n\n{hint}")

    elif data == "check_balance":
        _, row = get_or_create_user(user_id, query.from_user.username or query.from_user.first_name)
        remaining_trial = max(0, FREE_TRIAL_LIMIT - row["free_trials_used"])
        sub_status = "مفعّل ✅" if row["subscription_active"] == 1 else "غير مفعّل"
        await query.edit_message_text(
            f"📊 **بيانات رصيدك:**\n\n"
            f"• المحاولات المجانية المتبقية: {remaining_trial}\n"
            f"• رصيد النقاط المدفوعة: {row['points_balance']}\n"
            f"• الاشتراك الشهري: {sub_status}",
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )


# ============ استقبال النصوص ============

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    get_or_create_user(user_id, update.effective_user.username or update.effective_user.first_name)

    state = user_state.get(user_id, {})
    mode = state.get("mode")
    service_key = state.get("service")

    if mode not in ("text", "audio"):
        await update.message.reply_text("من فضلك اختار خدمة الأول من القائمة:", reply_markup=main_menu())
        return

    allowed, 
