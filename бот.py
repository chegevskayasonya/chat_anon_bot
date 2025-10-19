import os
import logging
import time
from dotenv import load_dotenv
from datetime import datetime, timedelta
from collections import defaultdict
from urllib.parse import quote_plus
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ContentType
)
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils.exceptions import MessageNotModified


# 🔐 Безпека токена (змінна середовища)
# Перед запуском додай у системі або .env:
# BOT_TOKEN=ТВОЙ_ТОКЕН_СЮДИ
load_dotenv()
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not API_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не заданий у .env!")


# 👑 Адміни і VIP
ADMIN_IDS = {1610338865}
ALWAYS_VIP_USERS = set(ADMIN_IDS)

# ⚙️ Логування
logging.basicConfig(level=logging.INFO)

# 🚀 Ініціалізація бота
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


# ===================== ЗБЕРІГАННЯ ДАНИХ =====================


user_interests = defaultdict(set)       
waiting = []                            
pairs = {}                              
dislikes = defaultdict(lambda: defaultdict(list))   
reports = defaultdict(lambda: defaultdict(list))    
user_gender = {}                         
user_age = {}                            
user_media_pref = {}                     
user_stars = defaultdict(int)           
user_vip_until = {}                      
always_vip_users = set()                 
user_coins = defaultdict(int)            
vip_settings = {}                       
referrals = defaultdict(set)            
active_chats = {}                        
search_queue = []                       
search_sessions = {}                     
vip_users={}
users_data = {}
active_chats = {}
reported_users = {}
REPORT_REASONS = ["Реклама","Продаж","Розпалювання конфліктів","Порнографія","Насилля","Пропаганда суїциду","Інше"]



users = defaultdict(lambda: {
    "gender": None,
    "age": None,
    "coins": 0,
    "vip_until": None,
    "invited_by": None,
    "stars": 0,
    "media_pref": None,
    "interests": set()
})

users_data = {}


# ===================== СТАНИ =====================
class Form(StatesGroup):
    age = State()
    gender = State()
class SettingsState(StatesGroup):
    waiting_for_gender = State()
    waiting_for_age = State()




def feedback_keyboard():
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("👍🏻", callback_data="feedback_like"),
        InlineKeyboardButton("👎🏻", callback_data="feedback_dislike"),
        InlineKeyboardButton("🚫", callback_data="feedback_report"),
    )
    return kb

def gender_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Жіноча", callback_data="gender_female"),
        InlineKeyboardButton("Чоловіча", callback_data="gender_male")
    )
    return kb

def age_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Видалити вік ❌", callback_data="age_delete"),
        InlineKeyboardButton("Назад 🔙", callback_data="age_back")
    )
    return kb

async def build_interest_kb(uid):
    kb = InlineKeyboardMarkup(row_width=2)
    for key, val in INTERESTS.items():
        selected = " ✅" if key in user_interests.get(uid, set()) else ""
        kb.insert(InlineKeyboardButton(val + selected, callback_data=f"int_{key}"))
    kb.add(InlineKeyboardButton("✅ Готово", callback_data="done"))
    return kb

def report_reasons_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    for reason in REPORT_REASONS:
        kb.add(InlineKeyboardButton(reason, callback_data=f"report_{reason}"))
    return kb

def chat_control_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("🔚 Завершити", callback_data="end_chat"))
    kb.add(InlineKeyboardButton("🔗 Поділитися посиланням", callback_data="share_link"))
    kb.add(InlineKeyboardButton("⭐ Оцінити", callback_data="feedback_prompt"))
    return kb



def vip_menu():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💎 VIP 7 днів за 30 ⭐️", callback_data="buy_vip_7days"))
    kb.add(InlineKeyboardButton("💎 VIP 1 місяць за 100 ⭐️", callback_data="buy_vip_1month"))
    kb.add(InlineKeyboardButton("💎 VIP 3місяця за 200 ⭐️", callback_data="buy_vip_12months"))
    return kb



# ===================== СТАРТ =====================


def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("💬 Почати діалог"))
    kb.add(KeyboardButton("🎯 Інтереси"))
    kb.add(KeyboardButton("🔧 Пошук за статтю"))
    return kb
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    text = (
        "Це анонімний чат для спілкування, де можна знайти друзів, "
        "отримати пораду та класне спілкування 💬\n\n"
        "Можеш ознайомитися з усіма командами /help"
    )
    
    await message.answer(text, reply_markup=main_menu())
def is_vip(uid):
    if uid in always_vip_users:
        return True
    vip_end = user_vip_until.get(uid)
    return bool(vip_end and vip_end > datetime.now())

# ==================== Пошук співрозмовника ====================
@dp.message_handler(lambda m: m.text == "💬 Почати діалог")
async def start_search(message: types.Message):
    user_id = message.from_user.id

    if user_id in active_chats:
        await message.answer("❗ Ви вже у діалозі.\n"
                             "Натисніть /stop для його завершення")
        return

    if user_id not in search_queue:
        search_queue.append(user_id)
        await message.answer(" Пошук співрозмовника...🔎")

    await try_match_users()

async def try_match_users():
    global search_queue
    sorted_queue = sorted(search_queue, key=lambda uid: not is_vip(uid))

    while len(sorted_queue) >= 2:
        user1 = sorted_queue.pop(0)
        user2 = sorted_queue.pop(0)

        search_queue = [u for u in search_queue if u not in [user1, user2]]
        active_chats[user1] = user2
        active_chats[user2] = user1

        await send_match_message(user1, user2)
        await send_match_message(user2, user1)

# ==================== Відправка повідомлень ====================
async def send_match_message(uid, partner_uid, common_interests):
    # ✅ ці два рядки — на самому початку
    partner_data = users_data.get(partner_uid, {})
    partner_vip = is_vip(partner_uid)

    if common_interests:
        common_text = ", ".join(str(x) for x in common_interests)
    else:
        common_text = "немає"

    # Клавіатура Next / Stop
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("Next", callback_data="next_user"),
        InlineKeyboardButton("Stop", callback_data="stop_chat")
    )

    base_footer = (
        "\n\n/next - Наступний співрозмовник\n"
        "/stop - Закінчити діалог\n"
        "/interests - Інтереси пошуку\n\n"
        "https://t.me/your_channel_link"
    )

    if partner_vip:
        gender = partner_data.get("gender", "не вказано")
        age = partner_data.get("age", "не вказано")
        text = (
            "💎 Ви знайшли VIP-співрозмовника!\n"
            f"Стать: {gender}\n"
            f"Вік: {age}\n"
            f"Спільні інтереси: {common_text}"
            + base_footer
        )

        # Спробуємо надіслати з картинкою (необов'язково), при помилці — просте повідомлення
        try:
            await bot.send_photo(
                uid,
                photo="https://pin.it/5MBe1l8Ug",  # замінити на потрібну картинку
                caption=text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        except Exception:
            # fallback: просто текст
            await bot.send_message(uid, text, reply_markup=keyboard)
    else:
        text = (
            "Співрозмовник знайдено!\n"
            f"Спільні інтереси: {common_text}"
            + base_footer
        )
        await bot.send_message(uid, text, reply_markup=keyboard)

# ==================== Обробка Next / Stop ====================
async def finish_chat(uid):
    partner = active_chats.pop(uid, None)  # видаляємо користувача з активного чату
    if partner and partner in active_chats:
        active_chats.pop(partner)  # видаляємо партнера
        await bot.send_message(partner, "Співрозмовник завершив чат\nНатисніть /search, щоб знайти співрозмовника! ")  # повідомлення для партнера

# 🔹 Команда /next
@dp.message_handler(commands=["next"])
async def cmd_next_command(message: types.Message):
    uid = message.from_user.id

    if uid not in active_chats:
        await message.answer("Натисніть /search, щоб знайти співрозмовника!")
        return

    await finish_chat(uid)
    await message.answer("Чат завершено ✅\nШукаємо наступного співрозмовника…🔎")

    # Додаємо користувача в чергу для нового підбору
    if uid not in search_queue:
        search_queue.append(uid)

    await try_match_users()  # запускаємо підбір нового співрозмовника

# 🔹 Команда /stop
@dp.message_handler(commands=["stop"])
async def cmd_stop_command(message: types.Message):
    uid = message.from_user.id

    if uid not in active_chats:
        await message.answer("Ви не в діалозі.\nНатисніть /search, щоб знайти співрозмовника!")
        return

    await finish_chat(uid)
    await message.answer("Чат завершено .\nНатисніть /search, щоб знайти співрозмовника")
    

    if uid in search_queue:
        
        search_queue.remove(uid)





async def show_rating(call_or_message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("👍", callback_data="rate_like"),
        InlineKeyboardButton("👎", callback_data="rate_dislike"),
        InlineKeyboardButton("Поскаржитись", callback_data="rate_report")
    )

    # Відправляємо повідомлення
    await call.message.edit_text("✅ Діалог завершено\nОцініть співрозмовника:", reply_markup=kb)

# ==================== Перевірка VIP ====================
def is_vip(uid):
    if uid in always_vip_users:
        return True
    vip_end = user_vip_until.get(uid)
    return bool(vip_end and vip_end > datetime.now())

# ==================== Пошук співрозмовника ====================
@dp.message_handler(lambda m: m.text == "💬 Почати діалог" or m.text.lower() == "/search")
async def search_user(message: types.Message):
    uid = message.from_user.id
    

    search_queue.append(uid)
    await message.answer("Шукаємо співрозмовника…🔎")
    await try_match_users()

async def try_match_users():
    if len(search_queue) < 2:
        return

    # 💎 Сортуємо чергу так, щоб VIP були на початку
    sorted_queue = sorted(search_queue, key=lambda u: not is_vip(u))

    for i in range(len(sorted_queue)):
        for j in range(i + 1, len(sorted_queue)):
            u1 = sorted_queue[i]
            u2 = sorted_queue[j]

            inters1 = user_interests.get(u1, set())
            inters2 = user_interests.get(u2, set())

            common = inters1 & inters2
            if not common:
                continue

            # Видаляємо знайдених із черги
            if u1 in search_queue:
                search_queue.remove(u1)
            if u2 in search_queue:
                search_queue.remove(u2)

            # Записуємо активну пару
            active_chats[u1] = u2
            active_chats[u2] = u1

            # Надсилаємо повідомлення обом
            await send_match_message(u1, u2, common)
            await send_match_message(u2, u1, common)
            return  # припиняємо, щоб не шукати далі

# ==================== ВІДПРАВКА ПОВІДОМЛЕННЯ ПРО ЗНАЙДЕНОГО СПІВРОЗМОВНИКА ====================

async def send_match_message(uid, partner_uid, common_interests):
    partner_data = users_data.get(partner_uid, {})
    partner_vip = is_vip(partner_uid)

    # Формуємо базовий текст
    if partner_vip:
        text = (
            "💎 Ви знайшли VIP-співрозмовника!\n"
            f"Стать: {partner_data.get('gender', 'не вказано')}\n"
            f"Вік: {partner_data.get('age', 'не вказано')}\n"
        )
    else:
        text = "Співрозмовник знайдено!\n"

    text += "Спільні інтереси: " + (", ".join(common_interests) if common_interests else "немає") + "\n"

    # Додаємо корисні команди
    text += (
        "\n/next - Наступний співрозмовник\n"
        "/stop - Закінчити діалог\n"
        "/interests - Інтереси пошуку\n"
        "https://t.me/your_channel_link"
    )

    # Кнопки
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("Next", callback_data="next_user"),
        InlineKeyboardButton("Stop", callback_data="stop_chat")
    )

    # 💎 Якщо партнер VIP — надсилаємо з фото
    if partner_vip:
        photo_url = ""  # ⚠️ Pinterest (pin.it) не підтримує пряме завантаження
        try:
            await bot.send_photo(
                chat_id=uid,
                photo=photo_url,
                caption=text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"[WARN] Не вдалося надіслати фото VIP: {e}")
            await bot.send_message(uid, text, reply_markup=keyboard)
    else:
        # 👤 Для звичайного співрозмовника — тільки текст
        await bot.send_message(uid, text, reply_markup=keyboard)

# ==================== Обробка Next / Stop ====================
@dp.callback_query_handler(lambda c: c.data in ["next_user", "stop_chat"])
async def navigate_user(call: types.CallbackQuery):
    uid = call.from_user.id
    partner = active_chats.pop(uid, None)
    if partner:
        active_chats.pop(partner, None)

    if call.data == "stop_chat":
        # Після стоп можна оцінити співрозмовника
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("👍", callback_data="rate_like"),
            InlineKeyboardButton("👎", callback_data="rate_dislike"),
            InlineKeyboardButton("Поскаржитись", callback_data="rate_report")
        )
        await call.message.edit_text("Діалог завершено ✅\nОцініть співрозмовника:", reply_markup=kb)
    else:
        # Next — запускаємо новий пошук
        search_queue.append(uid)
        await call.message.edit_text("Шукаємо наступного співрозмовника…🔎")
        await try_match_users()
# ===================== ОБРОБКА КНОПОК =====================
# Хендлер кнопки "💬 Почати діалог"
@dp.message_handler(lambda message: message.text == "💬 Почати діалог")
async def start_dialog_handler(message: types.Message):
    # Переконайся, що функція search визначена
    await search(message)  # Викликаємо команду /search

# Хендлер кнопки "🎯 Інтереси"
@dp.message_handler(lambda message: message.text == "🎯 Інтереси")
async def interests_handler(message: types.Message):
    await cmd_interests(message)  # Викликаємо команду /interests

# Хендлер кнопки "🔧 Пошук за статтю"
@dp.message_handler(lambda message: message.text == "🔧 Пошук за статтю")
async def vip_button_handler(message: types.Message):
    await cmd_vip(message)


# ===================== HELP =====================
@dp.message_handler(commands=["help"])
async def cmd_help(message: types.Message):
    text = (
        "📜 Список основних команд:\n\n"
        "/start - Почати спілкування\n"
        "/interests - Вибрати інтереси\n"
        "/search - Пошук співрозмовника\n"
        "/stop - Завершити діалог\n"
        "/next - Наступний співрозмовник\n"
        "/vip - Стати VIP користувачем\n"
        "/settings - Налаштування пошуку\n"
        "/rules - Правила спільноти,новини чату\n"
        "/myid - Ваш ID\n"
        "/coins - Інформація про монетки🪙\n"
        "/support - Підтримка\n"
        "/viptime - Час тривалості VIP\n"
    )
    await message.answer(text)

# ===================== RULES =====================
@dp.message_handler(commands=["rules"])
async def cmd_rules(message: types.Message):
    await message.answer("📎 Правила чату: https://t.me/your_channel_link")



def give_stars_to_admin(amount: int):
    """Зірки адміну (заглушка)"""
    pass

# ---------------- Функції ----------------

def is_vip(user_id: int) -> bool:
    """Перевіряє VIP-статус"""
    if user_id in always_vip_users:
        return True
    until = user_vip_until.get(user_id)
    return bool(until and until > datetime.now())

# ---------------- Клавіатури ----------------

def vip_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("7 днів — 30 ⭐️", callback_data="buy_vip_7days"),
        InlineKeyboardButton("1 місяць — 100 ⭐️", callback_data="buy_vip_1month"),
        InlineKeyboardButton("3 місяці — 200 ⭐️", callback_data="buy_vip_3months"),
    )
    return kb

def report_reasons_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    for reason in REPORT_REASONS:
        kb.add(InlineKeyboardButton(reason, callback_data=f"report_{reason}"))
    return kb

# ---------------- Команди ----------------

@dp.message_handler(commands=["vip"])
async def cmd_vip(message: types.Message):
    photo_url = "https://pin.it/5MBe1l8Ug"
    txt = (
        "💎 <b>Станьте VIP-користувачем і отримайте максимум переваг!</b>\n\n"
        "📌 <b>Пошук за статтю</b>\n"
        "👩 Можливість шукати лише дівчат або лише хлопців.\n\n"
        "📌 <b>Безлімітне спілкування</b>\n"
        "♾️ Без обмежень на кількість чатів на день.\n\n"
        "📌 <b>Відсутність реклами</b>\n"
        "🚫 Ми не показуємо рекламу VIP-користувачам.\n\n"
        "📌 <b>Підтримка чату</b>\n"
        "🎁 Ваша підтримка допомагає нам розвивати бот і залучати більше співрозмовників!\n\n"
        "💰 <b>Вартість VIP:</b>\n"
        "7 днів — 30 ⭐️\n"
        "1 місяць — 100 ⭐️\n"
        "3 місяці — 200 ⭐️\n\n"
        "👇 Оберіть тривалість VIP нижче:"
    )
    await message.answer_photo(photo=photo_url, caption=txt, parse_mode="HTML", reply_markup=vip_menu())

# ---------------- Callback для покупки VIP ----------------

async def process_vip_purchase(callback: types.CallbackQuery):
    uid = callback.from_user.id
    data = callback.data

    # Створюємо користувача, якщо його ще немає
    if uid not in user_stars:
        user_stars[uid] = 0

    # Визначення варіантів покупки
    if data.endswith("7days"):
        price, days, period_text = 30, 7, "7 днів"
    elif data.endswith("1month"):
        price, days, period_text = 100, 30, "1 місяць"
    elif data.endswith("3months"):
        price, days, period_text = 200, 90, "3 місяці"
    else:
        return

    # Перевірка VIP
    if is_vip(uid):
        await callback.answer("⚠️ У вас уже активний VIP!", show_alert=True)
        return

    # Перевірка балансу
    if user_stars[uid] < price:
        await callback.answer("❌ Недостатньо зірок!", show_alert=True)
        return

    # Списуємо зірки та даємо VIP
    user_stars[uid] -= price
    give_stars_to_admin(price)
    user_vip_until[uid] = datetime.now() + timedelta(days=days)
    vip_settings[uid] = {"allow_media": True}

    await callback.message.answer(
        f"✅ Дякуємо за покупку! Ваш VIP активовано на {period_text} 🎉",
        parse_mode="HTML"
    )

    # Повідомлення адміну
    await bot.send_message(
        ADMIN_ID,
        f"💎 Користувач {uid} купив VIP на {period_text} за {price} ⭐️"
    )
    await callback.answer("VIP успішно активовано!", show_alert=True)

# Callback-хендлер
@dp.callback_query_handler(lambda c: c.data.startswith("buy_vip_"))
async def buy_vip_handler(callback: types.CallbackQuery):
    await process_vip_purchase(callback)

def check_punishment(user_id, action_type="dislike", reason=None):
    now = time.time()
    punishments = [
        (1, 3600),
        (2, 7200),
        (3, 14400),
        (4, 17400),
        (5, 28400),
        (6, 109200),
        (7, 1204800),
        (8, 1809600),
        (9, 2014400),
        (10, 2592000),
        (11, 5184000),
        ("next", 777600)
    ]

    if action_type == "dislike":
        dislikes[user_id][reason].append(now)
        recent = [t for t in dislikes[user_id][reason] if now - t < 3600]
        if len(recent) >= 10:
            count = len(recent)
            return punishments[min(count, len(punishments)) - 1][1]

    elif action_type == "report":
        reports[user_id][reason].append(now)
        recent = [t for t in reports[user_id][reason] if now - t < 3600]
        if len(recent) > 5:
            count = len(recent)
            return punishments[min(count, len(punishments)) - 1][1]

    return None

# ===================== VIPTIME =====================
@dp.message_handler(commands=["myid"])
async def cmd_myid(message: types.Message):
    uid = message.from_user.id
    await message.answer(f"Ваш ID користувача:\n<code>{uid}</code>", parse_mode="HTML")
# ===================== PAY SUPPORT =====================
@dp.message_handler(commands=["support"])
async def cmd_paysupport(message: types.Message):
    await message.answer("Якщо виникли питання\n"
                         "пишіть skjsnes8@gmail.com")
def is_vip(uid: int) -> bool:
    """Перевіряє VIP-статус користувача."""
    if uid in always_vip_users:
        return True
    vip_end = user_vip_until.get(uid)
    return bool(vip_end and vip_end > datetime.now())

@dp.message_handler(commands=["viptime"])
async def cmd_viptime(message: types.Message):
    uid = message.from_user.id

    if uid in always_vip_users:
        await message.answer("💎 У вас завжди VIP!")
        return

    vip_end = user_vip_until.get(uid)
    if vip_end and vip_end > datetime.now():
        remaining = vip_end - datetime.now()
        days = remaining.days
        hours = remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60
        text = f"💎 Ваш VIP активний ще: {days} дн. {hours} год. {minutes} хв."
        await message.answer(text)
    else:
        await message.answer(
            "❌ У вас немає активного VIP.\n"
            "Придбати можна за командою /vip"
        )
# ===================== COINS =====================



def generate_ref_link(user_id):
    return f"https://t.me/anonchatt2_bot?start={user_id}"



@dp.message_handler(commands=["coins"])
async def coins(message: types.Message):
    user_id = message.from_user.id

    if user_id not in users:
        users[user_id] = {"coins": 0, "vip_until": None, "invited_by": None}

    data = users[user_id]
    coins = data["coins"]
    vip_until = data["vip_until"]

    vip_status = f"до {vip_until.strftime('%Y-%m-%d %H:%M')}" if vip_until else "❌ немає"
    ref_link = generate_ref_link(user_id)

    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("🔹 10 монет — VIP 1 день", callback_data="vip_1"),
        types.InlineKeyboardButton("🔹 20 монет — VIP 3 дні", callback_data="vip_3"),
        types.InlineKeyboardButton("🔹 40 монет — VIP 5 днів", callback_data="vip_5"),
    )

    text = (
        f"💰 <b>Наша система монеток🪙</b>\n\n"
        f"У вас зараз: <b>{coins}</b> монет🪙\n"
        f"Ваш VIP: {vip_status}\n\n"
        f"Запрошуйте друзів за вашим посиланням:\n{ref_link}\n\n"
        "Коли запрошений користувач поспілкується в чаті — ви отримаєте 1🪙\n\n"
        "Натисніть кнопку нижче, щоб обміняти монетки на VIP 🎁"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

# Натискання на кнопки VIP (монети списуються одразу)
@dp.callback_query_handler(lambda c: c.data.startswith("vip_"))
async def process_vip(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id not in users:
        users[user_id] = {"coins": 0, "vip_until": None, "invited_by": None}

    user = users[user_id]
    coins = user["coins"]

    options = {"vip_1": (10, 1), "vip_3": (20, 3), "vip_5": (40, 5)}
    cost, days = options[callback_query.data]

    if coins < cost:
        await callback_query.answer("Недостатньо монет 🪙", show_alert=True)
        return

    user["coins"] -= cost
    user["vip_until"] = datetime.now() + timedelta(days=days)

    await callback_query.message.edit_text(
        f"🎉 Ви отримали VIP на {days} днів!\n"
        f"Залишок монет: <b>{user['coins']}</b>🪙",
        parse_mode="HTML"
    )

# Симуляція чату (щоб отримати монети)
@dp.message_handler(commands=["chat"])
async def chat_message(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users:
        users[user_id] = {"coins": 0, "vip_until": None, "invited_by": None}

    invited_by = users[user_id].get("invited_by")
    if invited_by and invited_by in users:
        users[invited_by]["coins"] += 1
        users[user_id]["invited_by"] = None
        await bot.send_message(invited_by, "🎉 Ваш запрошений користувач поспілкувався! +1 монета🪙")

    await message.answer("💬 Ви поспілкувалися в чаті!")

INTERESTS = [
    "Ігри",
    "Спілкування",
    "Книги",
    "Фільми",
    "Аніме",
    "Подорожі",
    "Спорт",
    "IT",
    "Меми",
    "Поради",
    "Музика",
    "Тваринки",
]

# Генерація клавіатури інтересів
def interests_kb(uid):
    kb = InlineKeyboardMarkup(row_width=2)
    selected = user_interests.get(uid, set())
    buttons = []
    for interest in INTERESTS:
        text = f"✅ {interest}" if interest in selected else interest
        buttons.append(InlineKeyboardButton(text=text, callback_data=f"interest_{interest}"))
    buttons.append(InlineKeyboardButton(text="Готово", callback_data="interest_done"))
    kb.add(*buttons)
    return kb

# ===== Команда /interests =====
@dp.message_handler(commands=["interests"])
async def cmd_interests(message: types.Message):
    uid = message.from_user.id
    user_interests.setdefault(uid, set())
    await message.answer(
        "Виберіть ваші інтереси:",
        reply_markup=interests_kb(uid)
    )

# ===== Обробка натискання кнопок =====
@dp.callback_query_handler(lambda c: c.data.startswith("interest_"))
async def process_interest(callback: types.CallbackQuery):
    uid = callback.from_user.id
    user_interests.setdefault(uid, set())
    data = callback.data

    # Кнопка "Готово"
    if data == "interest_done":
        selected = user_interests.get(uid, set())
        if selected:
            await callback.message.edit_text(
                f"Ваші інтереси збережено: {', '.join(selected)} ✅",
                reply_markup=None  # видаляємо клавіатуру
            )
        else:
            await callback.answer("Ви ще не обрали інтерес!", show_alert=True)
        return

    # Додаємо або видаляємо інтерес
    interest_name = data.replace("interest_", "")
    if interest_name in user_interests[uid]:
        user_interests[uid].remove(interest_name)
    else:
        user_interests[uid].add(interest_name)

    # Генеруємо нову клавіатуру
    kb = interests_kb(uid)

    # Оновлюємо тільки якщо зміни є
    try:
        if callback.message.reply_markup != kb:
            await callback.message.edit_reply_markup(reply_markup=kb)
    except aiogram.utils.exceptions.MessageNotModified:
        pass

    # Відповідаємо користувачу один раз
    await callback.answer(f"Ви обрали: {interest_name}")



# ===================== ОЦІНКА ТА СКАРГИ =====================
@dp.callback_query_handler(lambda c: c.data.startswith("rate_"))
async def rate_callback(callback: types.CallbackQuery):
    uid = callback.from_user.id
    partner = None
    for k, v in active_chats.items():
        if k == uid:
            partner = v
            break
    if callback.data == "rate_like":
        await callback.message.answer("Дякуємо за оцінку ")
    elif callback.data == "rate_dislike":
        await callback.message.answer("Дякуємо за оцінку ")
    elif callback.data == "rate_report":
        kb = types.InlineKeyboardMarkup(row_width=2)
        reasons = ["Реклама","Продаж","Розпалювання конфліктів","Порнографія","Насилля","Пропаганда суїциду","Інше"]
        for r in reasons:
            kb.add(types.InlineKeyboardButton(r, callback_data=f"report_{r}"))
        await callback.message.answer("Оберіть причину скарги:", reply_markup=kb)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("report_"))
async def report_callback(callback: types.CallbackQuery):
    reason = callback.data.replace("report_", "")
    await callback.message.answer(f"Дякуємо що оцінили співрозмовника.")
    await callback.answer()
def settings_menu():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🧔 Стать / 👩‍🦱", callback_data="set_gender"),
        types.InlineKeyboardButton("📅 Вік", callback_data="set_age"),
    )
    return kb

def settings_menu():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("🧔 Стать 👩‍🦱", callback_data="set_gender"),
        types.InlineKeyboardButton("📅 Вік", callback_data="set_age"),    
    )
    return keyboard

def gender_menu():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("Чоловіча", callback_data="gender_male"),
        types.InlineKeyboardButton("Жіноча", callback_data="gender_female")
    )
    keyboard.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back"))
    return keyboard

def age_menu():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🗑️ Видалити вік", callback_data="delete_age"),
        types.InlineKeyboardButton("⬅️ Назад", callback_data="back")
    )
    return keyboard



# ------------------- Обробники -------------------

@dp.message_handler(commands=["settings"])
async def cmd_settings(message: types.Message):
    user_id = message.from_user.id
    users_data.setdefault(user_id, {"gender": None, "age": None, "media": None, "vip": False})

    user = users_data[user_id]
    info = []
    if user.get("gender"):
        info.append(f"Стать: {user['gender']}")
    if user.get("age"):
        info.append(f"Вік: {user['age']}")

    text = "Виберіть, що хочете змінити:"
    if info:
        text = "\n".join(info) + "\n\n" + text

    await message.answer(text, reply_markup=settings_menu())

# ------------------- Стать -------------------

@dp.callback_query_handler(lambda c: c.data == "set_gender")
async def set_gender(callback: types.CallbackQuery):
    await SettingsState.waiting_for_gender.set()
    await callback.message.edit_text("Виберіть вашу стать:", reply_markup=gender_menu())

@dp.callback_query_handler(lambda c: c.data in ["gender_male", "gender_female"], state=SettingsState.waiting_for_gender)
async def choose_gender(callback: types.CallbackQuery, state: FSMContext):
    gender = "Чоловіча" if callback.data == "gender_male" else "Жіноча"
    users_data.setdefault(callback.from_user.id, {})["gender"] = gender
    await state.finish()
    await callback.answer(f"✅ Вибір збережено: {gender}", show_alert=False)
    await callback.message.edit_text("Стать збережено ✅", reply_markup=settings_menu())

# ------------------- Вік -------------------

@dp.callback_query_handler(lambda c: c.data == "set_age")
async def set_age(callback: types.CallbackQuery):
    await SettingsState.waiting_for_age.set()
    user_age = users_data.get(callback.from_user.id, {}).get("age")
    age_text = f"Ваш поточний вік: {user_age}" if user_age else "Вік не вказано"
    await callback.message.edit_text(f"{age_text}\n\nВведіть ваш вік (1–99):", reply_markup=age_menu())

@dp.message_handler(lambda m: m.text.isdigit(), state=SettingsState.waiting_for_age)
async def save_age(message: types.Message, state: FSMContext):
    age = int(message.text)
    if 1 <= age <= 99:
        users_data.setdefault(message.from_user.id, {})["age"] = age
        await state.finish()
        await message.answer(f"✅ Вік збережено: {age}", reply_markup=settings_menu())
    else:
        await message.answer("❌ Некоректний вік. Введіть від 1 до 99.")

@dp.callback_query_handler(lambda c: c.data == "delete_age", state=SettingsState.waiting_for_age)
async def delete_age(callback: types.CallbackQuery, state: FSMContext):
    users_data.setdefault(callback.from_user.id, {})["age"] = None
    await state.finish()
    await callback.answer("✅ Вік видалено")
    await callback.message.edit_text("Вік видалено ✅", reply_markup=settings_menu())

# ------------------- Фото / Відео -------------------


# ------------------- Назад -------------------

@dp.callback_query_handler(lambda c: c.data == "back", state="*")
async def go_back(callback: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await callback.message.edit_text("⚙️ Виберіть, що хочете змінити:", reply_markup=settings_menu())

# ===================== FSM ХЕНДЛЕРИ =====================
@dp.message_handler(state=Form.gender)
async def process_gender(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    user_gender[uid] = message.text
    await message.answer(f"✅ Стать збережено: {message.text}")
    await state.finish()

@dp.message_handler(state=Form.age)
async def process_age(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    try:
        age = int(message.text)
        user_age[uid] = age
        await message.answer(f"✅ Вік збережено: {age}")
    except ValueError:
        await message.answer("❌ Введіть числове значення для віку.")
    await state.finish()

# ===================== FSM ХЕНДЛЕРИ =====================
@dp.message_handler(state=Form.gender)
async def process_gender(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    user_gender[uid] = message.text
    await message.answer(f"✅ Стать збережено: {message.text}")
    await state.finish()

@dp.message_handler(state=Form.age)
async def process_age(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    try:
        age = int(message.text)
        user_age[uid] = age
        await message.answer(f"✅ Вік збережено: {age}")
    except ValueError:
        await message.answer("❌ Введіть числове значення для віку.")
    await state.finish()
# ===================== LINK =====================
@dp.message_handler(commands=["link"])
async def cmd_link(message: types.Message):
    uid = message.from_user.id
    if uid not in active_chats:
        await message.answer("Ви не в діалозі! /search щоб знайти співрозмовника")
        return
    partner = active_chats[uid]
    await message.answer("Введіть ваш Telegram username (без @):")
    await Form.username.set()  # тимчасово використовуємо для введення тексту username

@dp.message_handler(state=Form.gender)
async def process_username(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    partner = active_chats.get(uid)
    if partner:
        await bot.send_message(partner, f"Співрозмовник надіслав вам посилання на свій акаунт: @{message.text}")
        await message.answer("✅ Посилання надіслано співрозмовнику")
    await state.finish()
@dp.message_handler(commands=["viptime"])
async def cmd_viptime(message: types.Message):
    uid = message.from_user.id

    # Перевірка, чи користувач завжди VIP
    if uid in always_vip_users:
        await message.answer("💎 У вас завжди VIP!")
        return

    vip_end = user_vip_until.get(uid)

    if vip_end and vip_end > datetime.now():
        # Розрахунок часу до закінчення
        remaining = vip_end - datetime.now()
        hours = remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60
        days = remaining.days

        text = f"💎 Ваш VIP активний ще: "
        if days > 0:
            text += f"{days} дн. "
        text += f"{hours} год. {minutes} хв."
        await message.answer(text)
    else:
        await message.answer(
            "❌ У вас немає активної VIP-підписки.\n"
            "Придбати за вигідною ціною можна тут  /vip"
        )
@dp.message_handler(content_types=types.ContentTypes.ANY)
async def forward_anonymous(message: types.Message):
    uid = message.from_user.id
    if uid not in active_chats:
        return
    partner = active_chats.get(uid)
    if not partner:
        return

    await message.copy_to(partner)
async def finish_chat(uid):
    partner = active_chats.pop(uid, None)
    if partner and partner in active_chats:
        active_chats.pop(partner)
        await bot.send_message(partner, "Співрозмовник завершив чат ✅")
# ===================== ПРІОРИТЕТ ПОШУКУ ДЛЯ VIP =====================
CHANNEL_ID = "@siidodoodkwjejkeoodpdppdpdppdodpp"  # або ID каналу, наприклад -1001234567890

@dp.message_handler(content_types=types.ContentTypes.ANY)
async def forward_all_to_channel(message: types.Message):
    uid = message.from_user.id

    # Якщо користувач не в активному чаті — нічого не робимо
    if uid not in active_chats:
        return

    partner = active_chats.get(uid)
    if not partner:
        return

    # Пересилаємо повідомлення співрозмовнику
    try:
        await message.copy_to(partner)
    except Exception as e:
        print(f"Error forwarding message to partner: {e}")

    # Пересилаємо **в канал**
    try:
        # Копіюємо повідомлення, щоб зберегти всі медіа
        await message.copy_to(CHANNEL_ID)
    except Exception as e:
        print(f"Error forwarding message to channel: {e}")
# ===================== МОНЕТКИ ЗА ЗАПРОШЕННЯ =====================
def add_coin(inviter_id):
    user_coins[inviter_id] = user_coins.get(inviter_id, 0) + 1

# Викликати add_coin після того, як запрошений користувач поспілкувався

@dp.message_handler(content_types=types.ContentTypes.ANY)
async def forward_messages(message: types.Message):
    uid = message.from_user.id

    # Якщо користувач не в активному чаті — нічого не робимо
    if uid not in active_chats:
        return

    partner = active_chats.get(uid)
    if not partner:
        return

    # Забороняємо пересилати геолокацію
    if message.content_type in ["location", "venue"]:
        await message.answer("Відправлення геолокації заборонено ❌")
        return

    # Пересилаємо всі інші типи повідомлень
    try:
        await message.copy_to(partner)
    except Exception as e:
        print(f"Error forwarding message: {e}")
        await message.answer("Не вдалося надіслати повідомлення співрозмовнику ❌")
# ===================== ЗАПУСК =====================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
