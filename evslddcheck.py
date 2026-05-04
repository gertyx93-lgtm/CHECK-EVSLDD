import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/root/.cache/ms-playwright"

BOT_TOKEN = "8607321079:AAEUoyb8XM6ASlvk7FafGYyegOQkRKJ-loc"
LOG_CHAT_ID = -4943000725
ADMIN_IDS = [7636751730, 7181364375]

SITE_URL = "https://tm-control.cc"
SITE_LOGIN = "horunochka"
SITE_PASSWORD = "heltyx125"

PORT = int(os.environ.get("PORT", 8080))

allowed_users: set = set(ADMIN_IDS)
user_invoices: dict = {}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Глобальный браузер
_playwright_instance = None
_browser = None
_context = None
_logged_in = False


class InvoiceForm(StatesGroup):
    amount = State()


class AdminForm(StatesGroup):
    add_user = State()


# ───────── Клавиатуры ─────────

def start_kb(user_id: int):
    kb = [[InlineKeyboardButton(text="Создать чек", callback_data="create_invoice")]]
    if user_id in ADMIN_IDS:
        kb.append([InlineKeyboardButton(text="Админ панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def invoice_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Обновить чек", callback_data="invoice_refresh"),
            InlineKeyboardButton(text="🗑 Удалить чек", callback_data="invoice_delete"),
        ]
    ])


def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Выдать доступ", callback_data="admin_add_user")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_back")],
    ])


# ───────── Playwright ─────────

async def get_context():
    global _playwright_instance, _browser, _context
    if _browser is None or not _browser.is_connected():
        _playwright_instance = await async_playwright().start()
        _browser = await _playwright_instance.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ]
        )
        _context = await _browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            locale="en-US",
        )
        await _context.grant_permissions(["clipboard-read", "clipboard-write"])
        logging.info("Браузер запущен")
    return _context


async def site_login(page):
    await page.goto(f"{SITE_URL}/auth/login", timeout=60000, wait_until="domcontentloaded")
    await page.wait_for_selector("input[name='login']", timeout=30000)
    await page.fill("input[name='login']", SITE_LOGIN)
    await page.fill("input[name='password']", SITE_PASSWORD)
    await page.click("button[type='submit']")
    await page.wait_for_url(f"{SITE_URL}/**", timeout=30000)
    await page.wait_for_timeout(2000)

async def ensure_logged_in(page):
    global _logged_in
    if _logged_in:
        await page.goto(f"{SITE_URL}/shared_domains", timeout=30000)
        if "/auth/login" in page.url:
            _logged_in = False
            await site_login(page)
            await page.goto(f"{SITE_URL}/shared_domains", timeout=30000)
    else:
        await site_login(page)
        await page.goto(f"{SITE_URL}/shared_domains", timeout=30000)
    
    logging.info(f"Текущий URL: {page.url}")
    _logged_in = True


async def site_create_invoice(amount: str) -> str | None:
    try:
        context = await get_context()
        page = await context.new_page()
        try:
            await ensure_logged_in(page)

            await page.wait_for_selector(
                "button[data-slot='popover-trigger'][data-variant='outline']",
                timeout=15000
            )
            await page.click(
                "button[data-slot='popover-trigger'][data-variant='outline']",
                timeout=10000
            )

            amount_input = await page.wait_for_selector(
                "input[name='amount']", timeout=10000, state="visible"
            )
            await amount_input.fill(amount, force=True)

            currency_input = await page.wait_for_selector(
                "input[name='currency']", timeout=10000, state="visible"
            )
            await currency_input.fill("USDT", force=True)

            await page.evaluate("""
                const btn = document.querySelector("button[data-slot='button'][data-variant='default'][type='submit']");
                if (btn) btn.click();
            """)

            await page.wait_for_selector(
                "button[data-slot='tooltip-trigger']", timeout=10000
            )

            await page.evaluate("""
                const btns = document.querySelectorAll("button[data-slot='tooltip-trigger']");
                if (btns.length > 0) btns[0].click();
            """)

            await page.wait_for_timeout(500)

            link = await page.evaluate("navigator.clipboard.readText()")
            logging.info(f"Ссылка на чек: {link}")
            return link if link and "http" in link else None

        finally:
            await page.close()

    except Exception as e:
        logging.error(f"Playwright create_invoice error: {e}")
        global _browser, _context, _playwright_instance
        try:
            if _browser:
                await _browser.close()
        except Exception:
            pass
        _browser = None
        _context = None
        _playwright_instance = None
        return None


async def site_delete_invoice(invoice_id: str) -> bool:
    try:
        context = await get_context()
        page = await context.new_page()
        try:
            await ensure_logged_in(page)

            await page.wait_for_selector(
                "button[data-slot='alert-dialog-trigger'][data-variant='destructive']",
                timeout=15000
            )
            await page.evaluate("""
                const btn = document.querySelector("button[data-slot='alert-dialog-trigger'][data-variant='destructive']");
                if (btn) btn.click();
            """)

            try:
                confirm_btn = await page.wait_for_selector(
                    "button[data-slot='alert-dialog-action']",
                    timeout=5000
                )
                await confirm_btn.click()
                await page.wait_for_selector(
                    "button[data-slot='alert-dialog-trigger'][data-variant='destructive']",
                    state="detached", timeout=5000
                )
            except Exception:
                pass

            return True

        finally:
            await page.close()

    except Exception as e:
        logging.error(f"Playwright delete_invoice error: {e}")
        return False


async def site_refresh_invoice(invoice_id: str) -> bool:
    try:
        context = await get_context()
        page = await context.new_page()
        try:
            await ensure_logged_in(page)

            await page.wait_for_selector(
                "button[data-slot='tooltip-trigger']",
                timeout=15000
            )
            await page.evaluate("""
                const btns = document.querySelectorAll("button[data-slot='tooltip-trigger']");
                if (btns.length >= 2) btns[1].click();
            """)

            await page.wait_for_timeout(500)
            return True

        finally:
            await page.close()

    except Exception as e:
        logging.error(f"Playwright refresh_invoice error: {e}")
        return False


# ───────── Хендлеры ─────────

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

    if user_id not in allowed_users:
        await message.answer("⛔ У вас нет доступа к боту.")
        return

    await message.answer(
        "<b>Чек-бот EVSLDD</b>\n\n"
        "Для создания чека на оплату нажмите кнопку ниже.",
        reply_markup=start_kb(user_id),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "create_invoice")
async def cb_create_invoice(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id

    if user_id not in allowed_users:
        await callback.message.answer("⛔ У вас нет доступа.")
        return

    await callback.message.answer(
        "<b>Валюта: USDT</b>\n\n"
        "Введите сумму для чека (от 1 до 500 000):",
        parse_mode="HTML"
    )
    await state.set_state(InvoiceForm.amount)


@dp.message(InvoiceForm.amount)
async def handle_amount(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip()

    if not text.isdigit():
        await message.answer("⚠️ Введите целое число.")
        return

    amount = int(text)
    if amount < 1 or amount > 500000:
        await message.answer("⚠️ Сумма должна быть от 1 до 500 000.")
        return

    await state.clear()
    wait_msg = await message.answer("⏳ Создаю чек, подождите...")

    link = await site_create_invoice(str(amount))

    try:
        await wait_msg.delete()
    except Exception:
        pass

    if not link:
        await message.answer(
            "❌ Не удалось создать чек. Попробуйте позже.",
            reply_markup=start_kb(user_id)
        )
        return

    user_invoices[user_id] = {
        "link": link,
        "amount": str(amount),
        "invoice_id": link.split("/")[-1] if "/" in link else link
    }

    fn = message.from_user.first_name or ''
    un = f"@{message.from_user.username}" if message.from_user.username else str(user_id)

    await message.answer(
        f"✅ <b>Ваш чек успешно создан</b>\n\n"
        f"<b>Сумма:</b> {amount} USDT\n"
        f"<b>Ссылка на чек:</b> {link}",
        reply_markup=invoice_kb(),
        parse_mode="HTML"
    )

    try:
        await bot.send_message(
            chat_id=LOG_CHAT_ID,
            text=(
                f"🧾 <b>Новый чек</b>\n\n"
                f"<b>Пользователь:</b> {fn} ({un})\n"
                f"<b>ID:</b> <code>{user_id}</code>\n"
                f"<b>Сумма:</b> {amount} USDT\n"
                f"<b>Ссылка:</b> {link}"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Log send error: {e}")


@dp.callback_query(F.data == "invoice_refresh")
async def cb_invoice_refresh(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    invoice = user_invoices.get(user_id)

    if not invoice:
        await callback.message.answer("⚠️ Активный чек не найден.")
        return

    wait_msg = await callback.message.answer("⏳ Обновляю чек...")
    await site_refresh_invoice(invoice["invoice_id"])
    try:
        await wait_msg.delete()
    except Exception:
        pass

    await callback.message.answer("🔄 <b>Ваш чек успешно обновлён</b>", parse_mode="HTML")

    un = f"@{callback.from_user.username}" if callback.from_user.username else str(user_id)
    try:
        await bot.send_message(
            chat_id=LOG_CHAT_ID,
            text=(
                f"🔄 <b>Чек обновлён</b>\n"
                f"<b>Пользователь:</b> {un} (<code>{user_id}</code>)\n"
                f"<b>Ссылка:</b> {invoice['link']}"
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass


@dp.callback_query(F.data == "invoice_delete")
async def cb_invoice_delete(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    invoice = user_invoices.get(user_id)

    if not invoice:
        await callback.message.answer("⚠️ Активный чек не найден.")
        return

    wait_msg = await callback.message.answer("⏳ Удаляю чек...")
    await site_delete_invoice(invoice["invoice_id"])
    try:
        await wait_msg.delete()
    except Exception:
        pass

    del user_invoices[user_id]

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.answer("🗑 <b>Чек успешно удалён с панели</b>", parse_mode="HTML")

    un = f"@{callback.from_user.username}" if callback.from_user.username else str(user_id)
    try:
        await bot.send_message(
            chat_id=LOG_CHAT_ID,
            text=(
                f"🗑 <b>Чек удалён</b>\n"
                f"<b>Пользователь:</b> {un} (<code>{user_id}</code>)"
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass


# ───────── Админ панель ─────────

@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет прав.", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(
        "<b>Админ панель</b>\n\n"
        f"Пользователей с доступом: <b>{len(allowed_users) - len(ADMIN_IDS)}</b>",
        reply_markup=admin_kb(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "admin_add_user")
async def cb_admin_add_user(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет прав.", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(
        "Введите Telegram ID пользователя которому хотите выдать доступ:"
    )
    await state.set_state(AdminForm.add_user)


@dp.message(AdminForm.add_user)
async def handle_add_user(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    text = message.text.strip()
    if not text.isdigit():
        await message.answer("⚠️ ID должен быть числом. Попробуй ещё раз.")
        return

    new_user_id = int(text)
    await state.clear()

    if new_user_id in allowed_users:
        await message.answer(
            f"⚠️ Пользователь <code>{new_user_id}</code> уже имеет доступ.",
            parse_mode="HTML",
            reply_markup=start_kb(message.from_user.id)
        )
        return

    allowed_users.add(new_user_id)
    await message.answer(
        f"✅ Доступ выдан пользователю <code>{new_user_id}</code>",
        parse_mode="HTML",
        reply_markup=start_kb(message.from_user.id)
    )

    try:
        await bot.send_message(
            chat_id=new_user_id,
            text="✅ Вам выдан доступ к боту. Напишите /start для начала работы."
        )
    except Exception:
        pass

    try:
        await bot.send_message(
            chat_id=LOG_CHAT_ID,
            text=(
                f"👤 <b>Выдан доступ</b>\n"
                f"<b>ID:</b> <code>{new_user_id}</code>\n"
                f"<b>Выдал:</b> <code>{message.from_user.id}</code>"
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass


@dp.callback_query(F.data == "admin_back")
async def cb_admin_back(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "<b>Чек-бот EVSLDD</b>\n\n"
        "Для создания чека на оплату нажмите кнопку ниже.",
        reply_markup=start_kb(callback.from_user.id),
        parse_mode="HTML"
    )


# ───────── Веб-сервер ─────────

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
    logging.info("Bot2 started with polling!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
