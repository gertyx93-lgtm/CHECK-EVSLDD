import asyncio
import logging
import os
import json
import random
import string
import subprocess
import sys
import re
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)

# ───────── АВТОУСТАНОВКА PLAYWRIGHT ─────────
def ensure_playwright_browsers():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        logging.info("Playwright browsers OK")
    except Exception:
        logging.info("Installing Playwright browsers...")
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"],
            check=True
        )
        logging.info("Playwright browsers installed.")

ensure_playwright_browsers()

# ───────── НАСТРОЙКИ ─────────
BOT_TOKEN = "8607321079:AAEUoyb8XM6ASlvk7FafGYyegOQkRKJ-loc"
LOG_CHAT_ID = -1003842299691
ADMIN_IDS = [7636751730, 7181364375]

SITE_URL = "https://tm-control.cc"
SITE_LOGIN = "horunochka"
SITE_PASSWORD = "heltyx125"

PORT = int(os.environ.get("PORT", 8080))
CHANNEL_LINK = "https://t.me/+L1b9aprvcJc5MTc6"

# Пути к фотографиям
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
    "ГЕРЦОГ",          # 0 — базовый
    "МАРКИЗ",          # 1
    "ГРАФ",            # 2
    "ВИКОНТ",          # 3
    "БАРОН",           # 4
    "ПРИНЦ",           # 5 — высший
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
E_STAR       = ce("5373318693650458620")   # для домена
E_DELETE     = ce("5240241223632954241")   # для удаления чека (крестик)
E_PERCENT    = ce("5372874186010158207")   # для процента
E_RANK       = ce("5460980668378931880")   # для ранга
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
    # Обеспечиваем наличие новых полей у старых пользователей
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
    """Клавиатура выбора ранга (выше Герцога — ранги 1-5)."""
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

    # Генерируем "случайный" ID-подобный номер на основе user_id (стабильный)
    random.seed(user_id)
    fake_id = ''.join([str(random.randint(0, 9)) for _ in range(16)])
    random.seed()  # сбрасываем seed

    return (
        f"{E_PROFILE} <b>Ваш профиль</b>\n\n"
        f"{E_ID} <b>ID:</b> <code>{user_id}</code>\n"
        f"{E_ID} <b>Юзернейм:</b> {uname}\n"
        f"{E_ID} <b>Тег:</b> <i>{tag}</i>\n\n"
        f"<code></code>{E_CUP} <b>ПРОЦЕНТ ВОРКЕРА:</b> {percent}%\n\n"
        f"{E_PROFIT} <b>Общий профит:</b> <b>{profit} USDT</b>\n"
        f"{E_INVOICES} <b>Активных чеков:</b> <b>{count}</b>\n\n"
        f"<code></code> {E_RANK} <b>РАНГ:</b> {rank_name}\n\n"
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

# ───────── ОТПРАВКА С ФОТО (ВСЕГДА НОВОЕ СОО + УДАЛЕНИЕ СТАРОГО) ─────────
async def send_with_photo(
    target,
    text: str,
    photo_key: str,
    reply_markup=None,
    edit: bool = False,
    delete_prev: bool = False,
) -> "Message | None":
    global _photo_cache

    # Удаляем предыдущее сообщение
    try:
        await target.delete()
    except Exception:
        pass

    send_photo = target.answer_photo
    send_text  = target.answer

    if photo_key in _photo_cache:
        try:
            return await send_photo(
                photo=_photo_cache[photo_key],
                caption=text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        except Exception as e:
            logging.warning(f"Кэш {photo_key} не сработал: {e}")
            _photo_cache.pop(photo_key, None)

    photo_path = PHOTOS.get(photo_key)
    if photo_path and os.path.exists(photo_path):
        try:
            photo = FSInputFile(photo_path)
            msg = await send_photo(
                photo=photo,
                caption=text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            if msg and msg.photo:
                _photo_cache[photo_key] = msg.photo[-1].file_id
                logging.info(f"Кэшировано фото: {photo_key}")
            return msg
        except Exception as e:
            logging.warning(f"Не удалось отправить фото {photo_key}: {e}")

    return await send_text(text, reply_markup=reply_markup, parse_mode="HTML")

# ───────── ЛОГИРОВАНИЕ В АДМИН ЧАТ ─────────
async def log_to_admin(bot: "Bot", text: str):
    try:
        await bot.send_message(LOG_CHAT_ID, text, parse_mode="HTML")
    except Exception as e:
        logging.warning(f"Не удалось отправить лог: {e}")

# ───────── PLAYWRIGHT (ОПТИМИЗИРОВАНО ДЛЯ СКОРОСТИ) ─────────
_playwright_instance = None
_browser = None
_context = None

async def get_context():
    global _playwright_instance, _browser, _context
    if _browser is None or not _browser.is_connected():
        await reset_browser()
        _playwright_instance = await async_playwright().start()
        _browser = await _playwright_instance.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--disable-extensions",
                "--disable-gpu",
                "--disable-images",          # не грузим картинки — быстрее
                "--blink-settings=imagesEnabled=false",
            ]
        )
        _context = await _browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            java_script_enabled=True,
        )
        await _context.grant_permissions(["clipboard-read", "clipboard-write"])
        # Блокируем ненужные ресурсы для ускорения
        await _context.route(
            "**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,eot,ico}",
            lambda route: route.abort()
        )
        await _context.route(
            "**/analytics*",
            lambda route: route.abort()
        )
    return _context

async def reset_browser():
    global _browser, _context, _playwright_instance
    for obj, method in [(_browser, "close"), (_playwright_instance, "stop")]:
        try:
            if obj:
                await getattr(obj, method)()
        except Exception:
            pass
    _browser = None
    _context = None
    _playwright_instance = None

async def site_login(page):
    logging.info("Выполняю логин...")
    await page.goto(f"{SITE_URL}/auth/login", timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_selector("input[name='login']", timeout=15000)
    await page.fill("input[name='login']", SITE_LOGIN)
    await page.fill("input[name='password']", SITE_PASSWORD)
    await page.click("button[type='submit']")
    await page.wait_for_url(f"{SITE_URL}/**", timeout=20000)
    await page.wait_for_timeout(1000)
    logging.info(f"Залогинился. URL: {page.url}")

async def ensure_logged_in(page):
    await page.goto(f"{SITE_URL}/domains", timeout=20000, wait_until="domcontentloaded")
    await page.wait_for_timeout(1000)
    if "/auth/login" in page.url or "/login" in page.url:
        logging.info("Сессия истекла, логинюсь заново...")
        await site_login(page)
        await page.goto(f"{SITE_URL}/domains", timeout=20000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)
    logging.info(f"ensure_logged_in: {page.url}")

async def _open_invoice_form(page, domain_name: str = None) -> bool:
    logging.info(f"_open_invoice_form: URL={page.url}, domain={domain_name}")

    try:
        await page.wait_for_selector('[data-slot="dropdown-menu-trigger"]', timeout=10000)
    except Exception as e:
        logging.error(f"Кнопки меню не появились: {e}")
        return False

    await page.wait_for_timeout(300)

    triggers = await page.query_selector_all('[data-slot="dropdown-menu-trigger"]')
    logging.info(f"Всего триггеров: {len(triggers)}")

    SKIP_KEYWORDS = ["ID:", SITE_LOGIN, "horunochka", "Open user menu", "avatar"]

    async def is_profile_trigger(t) -> bool:
        try:
            parent_text = await t.evaluate(
                "el => { let p = el.parentElement; for(let i=0;i<6;i++){ if(p && p.textContent.trim().length > 3) return p.textContent.trim().slice(0,200); p = p?.parentElement; } return ''; }"
            )
            return any(kw.lower() in parent_text.lower() for kw in SKIP_KEYWORDS)
        except Exception:
            return False

    async def try_trigger(t) -> list | None:
        if not await t.is_visible():
            return None
        await t.click()
        await page.wait_for_timeout(400)
        try:
            await page.wait_for_selector('div[role="menu"][data-state="open"]', timeout=2000)
        except Exception:
            return None
        texts = await page.evaluate("""
            () => {
                const m = document.querySelector('div[role="menu"][data-state="open"]');
                if (!m) return [];
                return Array.from(m.querySelectorAll('div[role="menuitem"]')).map(i => i.textContent.trim());
            }
        """)
        return texts if texts else None

    found_texts = None
    for t in triggers:
        if await is_profile_trigger(t):
            logging.info("Пропускаем триггер профиля")
            continue

        texts = await try_trigger(t)
        if texts is None:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(200)
            continue

        logging.info(f"Меню: {texts}")
        if any("Invoice" in x for x in texts):
            found_texts = texts
            break
        else:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(200)

    if not found_texts:
        logging.error("Invoice не найден ни в одном меню")
        try:
            await page.screenshot(path="debug_no_invoice.png")
        except Exception:
            pass
        return False

    invoice_el = await page.query_selector(
        'div[role="menu"][data-state="open"] div[role="menuitem"]:has-text("Invoice")'
    )
    if invoice_el:
        await invoice_el.click()
    else:
        await page.evaluate("""
            () => {
                const m = document.querySelector('div[role="menu"][data-state="open"]');
                if (!m) return;
                for (const item of m.querySelectorAll('div[role="menuitem"]')) {
                    if (item.textContent.includes('Invoice')) { item.click(); return; }
                }
            }
        """)

    logging.info("Invoice кликнут")

    try:
        await page.wait_for_selector("[data-slot='drawer-content'][data-state='open']", timeout=7000)
        logging.info("Drawer открылся")
    except Exception as e:
        logging.error(f"Drawer не открылся: {e}")
        try:
            await page.screenshot(path="debug_drawer.png")
        except Exception:
            pass
        return False

    await page.wait_for_timeout(300)
    return True

async def _fill_and_submit_invoice(page, amount: str, tx_id: str, title: str) -> bool:
    for sel in [
        "[data-slot='drawer-content'] button[data-slot='popover-trigger']",
        "[data-vaul-drawer] button[data-slot='popover-trigger']",
        "button[data-slot='popover-trigger']",
    ]:
        try:
            btn = await page.wait_for_selector(sel, timeout=3000)
            if btn and await btn.is_visible():
                await btn.click()
                logging.info(f"Add (+) clicked: {sel}")
                break
        except Exception:
            continue

    await page.wait_for_timeout(500)

    # Параллельное заполнение полей
    for selector, value in {
        "input[name='amount']":   amount,
        "input[name='currency']": "USDT",
        "input[name='tx_id']":    tx_id,
        "input[name='title']":    title,
    }.items():
        try:
            el = await page.wait_for_selector(selector, timeout=3000)
            if el:
                await el.fill(value)
        except Exception as e:
            logging.warning(f"Поле {selector} не найдено: {e}")

    submitted = False
    for sel in ["button[type='submit']:has-text('Create')", "button[type='submit']"]:
        try:
            btn = await page.wait_for_selector(sel, timeout=3000)
            if btn and await btn.is_visible():
                await btn.click()
                submitted = True
                logging.info(f"Submit: {sel}")
                break
        except Exception:
            continue

    if not submitted:
        await page.evaluate("""
            const btns = document.querySelectorAll("button[type='submit']");
            for (const b of btns) { if (b.offsetParent !== null) { b.click(); break; } }
        """)

    return True

async def _get_invoice_link(page) -> str | None:
    await page.wait_for_timeout(2000)

    for sel in [
        "button[data-slot='tooltip-trigger']",
        "button[title*='copy' i]",
        "button[aria-label*='copy' i]",
        "button[aria-label*='Copy' i]",
    ]:
        try:
            btns = await page.query_selector_all(sel)
            if btns:
                await btns[0].click()
                await page.wait_for_timeout(500)
                link = await page.evaluate("navigator.clipboard.readText()")
                if link and "http" in link:
                    logging.info(f"Ссылка через clipboard: {link}")
                    return link
        except Exception:
            continue

    for tag in ["input", "textarea"]:
        try:
            for el in await page.query_selector_all(tag):
                val = await el.input_value()
                if val and "http" in val:
                    return val
        except Exception:
            pass

    try:
        for el in await page.query_selector_all("a[href*='http']"):
            href = await el.get_attribute("href")
            if href and SITE_URL not in href:
                return href
    except Exception:
        pass

    try:
        content = await page.content()
        for url in re.findall(r'https?://[^\s"\'<>]+', content):
            if SITE_URL not in url:
                return url
    except Exception:
        pass

    logging.error("Не удалось получить ссылку на чек")
    return None

async def site_create_invoice(amount: str, tx_id: str, title: str, domain_name: str = None) -> str | None:
    try:
        context = await get_context()
        page    = await context.new_page()
        try:
            await ensure_logged_in(page)
            if not await _open_invoice_form(page, domain_name):
                return None
            await _fill_and_submit_invoice(page, amount, tx_id, title)
            return await _get_invoice_link(page)
        finally:
            await page.close()
    except Exception as e:
        logging.error(f"site_create_invoice критическая ошибка: {e}")
        await reset_browser()
        return None

async def site_delete_invoice(link: str) -> bool:
    try:
        context = await get_context()
        page    = await context.new_page()
        try:
            await ensure_logged_in(page)
            if not await _open_invoice_form(page):
                return False

            await page.wait_for_timeout(300)

            for sel in [
                "button[data-slot='alert-dialog-trigger'][data-variant='destructive']",
                "button[data-variant='destructive']",
                "button:has-text('Delete')",
            ]:
                try:
                    btn = await page.wait_for_selector(sel, timeout=3000)
                    if btn and await btn.is_visible():
                        await btn.click()
                        break
                except Exception:
                    continue

            for sel in [
                "button[data-slot='alert-dialog-action']",
                "button:has-text('Confirm')",
                "button:has-text('Yes')",
            ]:
                try:
                    btn = await page.wait_for_selector(sel, timeout=4000)
                    if btn:
                        await btn.click()
                        await page.wait_for_timeout(800)
                        return True
                except Exception:
                    continue

            return False
        finally:
            await page.close()
    except Exception as e:
        logging.error(f"site_delete_invoice ошибка: {e}")
        await reset_browser()
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

# ───────── ВСПОМОГАТЕЛЬНЫЕ ─────────
def gen_tx_id() -> str:
    return ''.join(random.choices(string.hexdigits.lower(), k=64))

def fmt_user(tg_user) -> str:
    uname = f"@{tg_user.username}" if tg_user.username else f"id={tg_user.id}"
    return f"{uname} (<code>{tg_user.id}</code>)"

# ───────── ХЕНДЛЕРЫ ─────────

# ── Хелпер для удаления сообщения пользователя и предыдущего сообщения бота ──
async def delete_user_msg_and_prev_bot_msg(message: Message, state: FSMContext):
    """Удаляет сообщение пользователя и предыдущее сообщение бота из state."""
    try:
        await message.delete()
    except Exception:
        pass
    state_data = await state.get_data()
    prev_msg_id = state_data.get("prev_msg_id")
    if prev_msg_id:
        try:
            await bot.delete_message(message.chat.id, prev_msg_id)
        except Exception:
            pass

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    data    = load_data()

    # Удаляем команду /start
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
    await message.answer_photo(
        photo=_photo_cache.get("menu") or (FSInputFile(PHOTOS["menu"]) if os.path.exists(PHOTOS["menu"]) else None) or "https://via.placeholder.com/400x200",
        caption=format_main_menu(user, user_id, message.from_user.username),
        reply_markup=main_menu_kb(user_id),
        parse_mode="HTML"
    ) if _photo_cache.get("menu") or os.path.exists(PHOTOS.get("menu", "")) else await message.answer(
        format_main_menu(user, user_id, message.from_user.username),
        reply_markup=main_menu_kb(user_id),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "back_main")
async def cb_back_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    data = load_data()
    user = get_user(data, callback.from_user.id)
    save_data(data)
    await send_with_photo(callback.message,
                          format_main_menu(user, callback.from_user.id, callback.from_user.username),
                          "menu", reply_markup=main_menu_kb(callback.from_user.id))

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
    msg = await send_with_photo(callback.message, text, "change_tag", reply_markup=kb)
    if msg:
        await state.update_data(prev_msg_id=msg.message_id)
    await state.set_state(ProfileForm.change_tag)

@dp.message(ProfileForm.change_tag)
async def handle_change_tag(message: Message, state: FSMContext):
    tag = message.text.strip()
    if len(tag) > 32:
        await message.answer("⚠️ Тег слишком длинный. Максимум 32 символа.")
        return
    data = load_data()
    user = get_user(data, message.from_user.id)
    old_tag = user.get("tag") or "не установлен"
    user["tag"] = tag
    save_data(data)
    await state.clear()
    await delete_user_msg_and_prev_bot_msg(message, state)
    msg = await send_with_photo(message,
                          format_main_menu(user, message.from_user.id, message.from_user.username),
                          "menu", reply_markup=main_menu_kb(message.from_user.id))
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
    await send_with_photo(callback.message,
                          f"{E_WALLET} <b>Кошелёк</b>\n\nСтатус: {wallet_text}",
                          "wallet", reply_markup=wallet_menu_kb(bool(wallet)))

@dp.callback_query(F.data == "bind_wallet")
async def cb_bind_wallet(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="wallet_menu")]
    ])
    msg = await send_with_photo(callback.message,
                          f"{E_WALLET} <b>USDT TRC-20</b>\n\nВведите адрес вашего кошелька:",
                          "wallet", reply_markup=kb)
    if msg:
        await state.update_data(prev_msg_id=msg.message_id)
    await state.set_state(ProfileForm.bind_wallet)

@dp.message(ProfileForm.bind_wallet)
async def handle_bind_wallet(message: Message, state: FSMContext):
    wallet = message.text.strip()
    if len(wallet) < 10:
        await message.answer("⚠️ Некорректный адрес. Попробуйте снова.")
        return
    data = load_data()
    user = get_user(data, message.from_user.id)
    old_wallet = user.get("wallet") or "не привязан"
    user["wallet"] = wallet
    save_data(data)
    await state.clear()
    await delete_user_msg_and_prev_bot_msg(message, state)
    await send_with_photo(message,
                          format_main_menu(user, message.from_user.id, message.from_user.username),
                          "menu", reply_markup=main_menu_kb(message.from_user.id))
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
    await send_with_photo(callback.message,
                          f"{E_CREATE} <b>Создание</b>\n\nВыберите действие:",
                          "create_menu", reply_markup=create_menu_kb())

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
    await send_with_photo(callback.message,
                          format_invoices_list(invoices, 0),
                          "my_invoices", reply_markup=invoices_list_kb(invoices, 0))

@dp.callback_query(F.data.startswith("inv_page_"))
async def cb_inv_page(callback: CallbackQuery):
    await callback.answer()
    page_num = int(callback.data.replace("inv_page_", ""))
    data     = load_data()
    user     = get_user(data, callback.from_user.id)
    invoices = user.get("invoices", [])
    await send_with_photo(callback.message,
                          format_invoices_list(invoices, page_num),
                          "my_invoices", reply_markup=invoices_list_kb(invoices, page_num))

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
    await send_with_photo(callback.message,
                          format_single_invoice(invoices[idx], idx),
                          "my_invoices", reply_markup=single_invoice_kb(idx))

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

    status_msg = await send_with_photo(callback.message,
                                       f"{E_WAIT} <b>Удаляю чек...</b>",
                                       "my_invoices")
    ok = await site_delete_invoice(inv["link"])
    if ok:
        user["invoices"].pop(idx)
        save_data(data)
        result_text = f"{E_OK} <b>Чек удалён.</b>\n\n"
    else:
        result_text = f"{E_ERROR} Не удалось удалить чек. Попробуйте позже.\n\n"

    updated = user.get("invoices", [])
    target  = status_msg if status_msg else callback.message
    await send_with_photo(target,
                          result_text + format_invoices_list(updated, 0),
                          "my_invoices", reply_markup=invoices_list_kb(updated, 0))
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
        await callback.message.answer(
            f"{E_ERROR} Нет активных чеков.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Назад", callback_data="back_main")]
            ]),
            parse_mode="HTML"
        )
        return
    last_inv = invoices[-1]

    status_msg = await send_with_photo(callback.message,
                                       f"{E_WAIT} <b>Удаляю чек...</b>",
                                       "my_invoices")
    ok = await site_delete_invoice(last_inv["link"])
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="В меню", callback_data="back_main")]
    ])

    if ok:
        user["invoices"].pop()
        save_data(data)
        result = f"{E_OK} <b>Чек удалён.</b>"
    else:
        result = f"{E_ERROR} Не удалось удалить чек."

    target = status_msg if status_msg else callback.message
    await send_with_photo(target, result, "my_invoices", reply_markup=back_kb)
    await log_to_admin(bot,
        f"{E_ERROR} <b>Чек удалён (быстрое удаление)</b>\n"
        f"👤 {fmt_user(callback.from_user)}\n"
        f"<b>Сумма:</b> {last_inv.get('amount')} USDT\n"
        f"<b>Ссылка:</b> {last_inv.get('link')}"
    )

# ── УДАЛИТЬ ЧЕК АДМИНИСТРАТОРОМ (кнопка в логе) ──
@dp.callback_query(F.data.startswith("admin_del_inv_"))
async def cb_admin_del_inv(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔️ Нет прав.", show_alert=True)
        return
    await callback.answer()

    # Формат: admin_del_inv_{owner_user_id}_{inv_index}
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
        await callback.message.edit_text(
            f"⚠️ Чек уже удалён или не найден.",
            reply_markup=None
        )
        return

    inv = invoices[inv_idx]

    await callback.message.edit_text(
        callback.message.text + "\n\n⏳ Удаляю чек...",
        reply_markup=None
    )

    ok = await site_delete_invoice(inv["link"])
    if ok:
        user["invoices"].pop(inv_idx)
        save_data(data)
        await callback.message.edit_text(
            callback.message.text.replace("⏳ Удаляю чек...", f"{E_OK} Чек удалён администратором."),
        )
        # Уведомляем владельца чека
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
        await callback.message.edit_text(
            f"{E_ERROR} Не удалось удалить чек. Попробуйте позже.",
        )

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
    msg = await send_with_photo(callback.message, text, "create_invoice", reply_markup=kb)
    if msg:
        await state.update_data(prev_msg_id=msg.message_id)
    await state.set_state(InvoiceForm.amount)

@dp.message(InvoiceForm.amount)
async def handle_invoice_amount(message: Message, state: FSMContext):
    raw = message.text.strip().replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        await message.answer("⚠️ Введите число. Например: <b>1000</b>", parse_mode="HTML")
        return
    if amount < 0 or amount > 500000:
        await message.answer("⚠️ Сумма должна быть от 0 до 500 000.")
        return
    await state.update_data(amount=raw)

    # Удаляем сообщение пользователя и предыдущее сообщение бота
    state_data = await state.get_data()
    try:
        await message.delete()
    except Exception:
        pass
    prev_msg_id = state_data.get("prev_msg_id")
    if prev_msg_id:
        try:
            await bot.delete_message(message.chat.id, prev_msg_id)
        except Exception:
            pass

    msg = await message.answer(
        f"{E_EDIT_TAG} <b>Введите TX ID транзакции</b>\n\n"
        f"Или нажмите кнопку для генерации случайного:",
        reply_markup=tx_id_kb(),
        parse_mode="HTML"
    )
    if msg:
        await state.update_data(prev_msg_id=msg.message_id)
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
    msg = await send_with_photo(callback.message, text, "create_invoice",
                                reply_markup=invoice_title_kb())
    if msg:
        await state.update_data(prev_msg_id=msg.message_id)
    await state.set_state(InvoiceForm.title)

@dp.message(InvoiceForm.tx_id)
async def handle_invoice_tx_id(message: Message, state: FSMContext):
    tx = message.text.strip()
    await state.update_data(tx_id=tx)

    state_data = await state.get_data()
    try:
        await message.delete()
    except Exception:
        pass
    prev_msg_id = state_data.get("prev_msg_id")
    if prev_msg_id:
        try:
            await bot.delete_message(message.chat.id, prev_msg_id)
        except Exception:
            pass

    msg = await message.answer(
        f"{E_EDIT_TAG} <b>Выберите название счёта:</b>",
        reply_markup=invoice_title_kb(),
        parse_mode="HTML"
    )
    if msg:
        await state.update_data(prev_msg_id=msg.message_id)
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

    status_msg = await send_with_photo(message,
                                       f"{E_WAIT} <b>Создаю чек...</b>",
                                       "create_invoice")

    link = await site_create_invoice(amount, tx_id, title)
    target = status_msg if status_msg else message

    if not link:
        await send_with_photo(
            target,
            f"{E_ERROR} <b>Не удалось создать чек.</b>\n\nПопробуйте позже.",
            "create_invoice",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="В меню", callback_data="back_main")]
            ])
        )
        return

    data = load_data()
    user = get_user(data, user_id)
    inv_idx = len(user["invoices"])
    user["invoices"].append({"link": link, "amount": amount, "tx_id": tx_id, "title": title})
    save_data(data)

    result_text = (
        f"{E_DONE} <b>Чек создан!</b>\n\n"
        f"<b>Сумма:</b> {amount} USDT\n"
        f"<b>Название:</b> {title}\n"
        f"{E_EDIT_TAG} <b>TX ID:</b> <code>{tx_id}</code>\n\n"
        f"<b>Ссылка:</b>\n<code>{link}</code>"
    )
    await send_with_photo(target, result_text, "create_invoice",
                          reply_markup=invoice_actions_kb())

    # Логируем с кнопкой "УДАЛИТЬ ЧЕК" для админов
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
    await send_with_photo(callback.message, format_admin_panel(data), "menu",
                          reply_markup=admin_kb(data))

@dp.callback_query(F.data == "admin_add")
async def cb_admin_add(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔️ Нет прав.", show_alert=True)
        return
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="admin_panel")]
    ])
    msg = await send_with_photo(callback.message,
                          "<b>Выдать доступ</b>\n\nВведите Telegram ID пользователя:",
                          "menu", reply_markup=kb)
    if msg:
        await state.update_data(prev_msg_id=msg.message_id)
    await state.set_state(AdminForm.add_user)

@dp.message(AdminForm.add_user)
async def handle_admin_add(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not message.text.strip().isdigit():
        await message.answer("⚠️ ID должен быть числом.")
        return
    new_id = int(message.text.strip())
    data   = load_data()
    await state.clear()
    try:
        await message.delete()
    except Exception:
        pass
    if new_id in data["allowed"]:
        await message.answer(f"⚠️ Пользователь <code>{new_id}</code> уже имеет доступ.", parse_mode="HTML")
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
    await message.answer(
        f"{E_OK} <b>Доступ выдан</b>\n\n"
        f"👤 ID: <code>{new_id}</code>\n"
        f"Тег: <i>{default_tag}</i>",
        parse_mode="HTML"
    )
    try:
        await bot.send_message(new_id,
            f"{E_ACCESS_OK} <b>Вам выдан доступ!</b>\n\nВведите /start для начала работы.",
            parse_mode="HTML")
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
    msg = await send_with_photo(callback.message,
                          "<b>Забрать доступ</b>\n\nВведите Telegram ID пользователя:",
                          "menu", reply_markup=kb)
    if msg:
        await state.update_data(prev_msg_id=msg.message_id)
    await state.set_state(AdminForm.remove_user)

@dp.message(AdminForm.remove_user)
async def handle_admin_remove(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not message.text.strip().isdigit():
        await message.answer("⚠️ ID должен быть числом.")
        return
    rem_id = int(message.text.strip())
    data   = load_data()
    await state.clear()
    try:
        await message.delete()
    except Exception:
        pass
    if rem_id not in data["allowed"]:
        await message.answer(f"⚠️ Пользователь <code>{rem_id}</code> не имеет доступа.", parse_mode="HTML")
        return
    data["allowed"].remove(rem_id)
    if rem_id not in data.get("revoked", []):
        data["revoked"].append(rem_id)
    save_data(data)
    await message.answer(
        f"{E_OK} <b>Доступ забран</b>\n\n👤 ID: <code>{rem_id}</code>",
        parse_mode="HTML"
    )
    try:
        await bot.send_message(rem_id,
            f"{E_ERROR} <b>Ваш доступ к боту отозван.</b>",
            parse_mode="HTML")
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
    msg = await send_with_photo(callback.message,
                          "<b>Начисление профита</b>\n\nВведите Telegram ID пользователя:",
                          "menu", reply_markup=kb)
    if msg:
        await state.update_data(prev_msg_id=msg.message_id)
    await state.set_state(AdminForm.profit_id)

@dp.message(AdminForm.profit_id)
async def handle_profit_id(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not message.text.strip().isdigit():
        await message.answer("⚠️ ID должен быть числом.")
        return
    await state.update_data(profit_uid=int(message.text.strip()))
    try:
        await message.delete()
    except Exception:
        pass
    msg = await message.answer("<b>Введите сумму для начисления (USDT):</b>", parse_mode="HTML")
    if msg:
        await state.update_data(prev_msg_id=msg.message_id)
    await state.set_state(AdminForm.profit_amount)

@dp.message(AdminForm.profit_amount)
async def handle_profit_amount(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    raw = message.text.strip().replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        await message.answer("⚠️ Введите число.")
        return
    form_data = await state.get_data()
    uid       = form_data["profit_uid"]
    await state.clear()
    try:
        await message.delete()
    except Exception:
        pass
    data = load_data()
    user = get_user(data, uid)
    user["profit"] = round(user.get("profit", 0) + amount, 2)
    save_data(data)
    await message.answer(
        f"{E_OK} <b>Профит начислен</b>\n\n"
        f"👤 ID: <code>{uid}</code>\n"
        f"Начислено: <b>{amount} USDT</b>\n"
        f"Итого: <b>{user['profit']} USDT</b>",
        parse_mode="HTML"
    )
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

# ── ПОВЫСИТЬ ПРОЦЕНТ ──
@dp.callback_query(F.data == "admin_percent")
async def cb_admin_percent(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔️ Нет прав.", show_alert=True)
        return
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="admin_panel")]
    ])
    msg = await send_with_photo(callback.message,
                          f"{E_PERCENT} <b>Повысить процент воркера</b>\n\n"
                          f"Введите Telegram ID пользователя:",
                          "menu", reply_markup=kb)
    if msg:
        await state.update_data(prev_msg_id=msg.message_id)
    await state.set_state(AdminForm.percent_id)

@dp.message(AdminForm.percent_id)
async def handle_percent_id(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not message.text.strip().isdigit():
        await message.answer("⚠️ ID должен быть числом.")
        return
    await state.update_data(percent_uid=int(message.text.strip()))
    try:
        await message.delete()
    except Exception:
        pass
    state_data = await state.get_data()
    prev_msg_id = state_data.get("prev_msg_id")
    if prev_msg_id:
        try:
            await bot.delete_message(message.chat.id, prev_msg_id)
        except Exception:
            pass
    msg = await message.answer(
        f"{E_PERCENT} <b>Введите новый процент</b>\n\n"
        f"Допустимые значения: <b>от 50 до 100</b>",
        parse_mode="HTML"
    )
    if msg:
        await state.update_data(prev_msg_id=msg.message_id)
    await state.set_state(AdminForm.percent_value)

@dp.message(AdminForm.percent_value)
async def handle_percent_value(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    raw = message.text.strip()
    if not raw.isdigit():
        await message.answer("⚠️ Введите целое число от 50 до 100.")
        return
    percent = int(raw)
    if percent < 50 or percent > 100:
        await message.answer("⚠️ Процент должен быть от 50 до 100.")
        return
    form_data = await state.get_data()
    uid = form_data["percent_uid"]
    await state.clear()
    try:
        await message.delete()
    except Exception:
        pass
    state_data = await state.get_data()
    prev_msg_id = state_data.get("prev_msg_id")
    if prev_msg_id:
        try:
            await bot.delete_message(message.chat.id, prev_msg_id)
        except Exception:
            pass
    data = load_data()
    user = get_user(data, uid)
    old_percent = user.get("percent", 50)
    user["percent"] = percent
    save_data(data)
    await message.answer(
        f"{E_OK} <b>Процент изменён</b>\n\n"
        f"👤 ID: <code>{uid}</code>\n"
        f"Было: <b>{old_percent}%</b> → Стало: <b>{percent}%</b>",
        parse_mode="HTML"
    )
    try:
        await bot.send_message(
            uid,
            f"{E_PERCENT} <b>Ваш процент был повышен администратором!</b>\n\n"
            f"Новый процент воркера: <b>{percent}%</b>",
            parse_mode="HTML"
        )
    except Exception:
        pass
    await log_to_admin(bot,
        f"{E_PERCENT} <b>Процент изменён</b>\n"
        f"Кому: <code>{uid}</code>\n"
        f"Было: <b>{old_percent}%</b> → Стало: <b>{percent}%</b>\n"
        f"Кто изменил: {fmt_user(message.from_user)}"
    )

# ── ИЗМЕНИТЬ РАНГ ──
@dp.callback_query(F.data == "admin_rank")
async def cb_admin_rank(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔️ Нет прав.", show_alert=True)
        return
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="admin_panel")]
    ])
    msg = await send_with_photo(callback.message,
                          f"{E_RANK} <b>Изменить ранг</b>\n\n"
                          f"Введите Telegram ID пользователя:",
                          "menu", reply_markup=kb)
    if msg:
        await state.update_data(prev_msg_id=msg.message_id)
    await state.set_state(AdminForm.rank_id)

@dp.message(AdminForm.rank_id)
async def handle_rank_id(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not message.text.strip().isdigit():
        await message.answer("⚠️ ID должен быть числом.")
        return
    target_id = int(message.text.strip())
    await state.clear()
    try:
        await message.delete()
    except Exception:
        pass
    # Показываем клавиатуру выбора ранга
    data = load_data()
    user = get_user(data, target_id)
    current_rank = RANKS[user.get("rank", 0)]
    await message.answer(
        f"{E_RANK} <b>Выберите новый ранг</b>\n\n"
        f"👤 ID: <code>{target_id}</code>\n"
        f"Текущий ранг: <b>{current_rank}</b>\n\n"
        f"<i>Доступны ранги выше Герцога:</i>",
        reply_markup=rank_select_kb(target_id),
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("set_rank_"))
async def cb_set_rank(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔️ Нет прав.", show_alert=True)
        return
    await callback.answer()
    # Формат: set_rank_{user_id}_{rank_idx}
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
    await callback.message.edit_text(
        f"{E_OK} <b>Ранг изменён!</b>\n\n"
        f"👤 ID: <code>{target_id}</code>\n"
        f"Было: <b>{old_rank}</b> → Стало: <b>{'⭐' * rank_idx} {new_rank}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад в панель", callback_data="admin_panel")]
        ]),
        parse_mode="HTML"
    )
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
