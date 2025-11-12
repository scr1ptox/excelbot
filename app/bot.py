import asyncio
from datetime import datetime
from decimal import Decimal

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from loguru import logger

from .config import settings
from .constants import main_kb, currency_kb, main_inline_kb, currency_inline_kb_in, currency_inline_kb_out
from .google_sheets import Sheets
from .storage import Storage
from .rates import convert_to_eur

bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()

# --- Cleanup helpers ---
async def _append_cleanup(state: FSMContext, *ids: int):
    data = await state.get_data()
    bucket = list(data.get("cleanup_ids", []))
    for mid in ids:
        if mid and mid not in bucket:
            bucket.append(mid)
    await state.update_data(cleanup_ids=bucket)

async def _cleanup_all(message: Message, state: FSMContext):
    data = await state.get_data()
    ids: list[int] = list(data.get("cleanup_ids", []))
    # try to delete from newest to oldest
    for mid in reversed(ids):
        try:
            await bot.delete_message(message.chat.id, mid)
        except Exception:
            pass
    await state.update_data(cleanup_ids=[])


async def send_and_delete_prev(message: Message, text: str, state: FSMContext, **kwargs):
    data = await state.get_data()
    prev_bot = data.get("last_bot_msg")
    prev_user = data.get("last_user_msg")

    # delete previous bot prompt
    if prev_bot:
        try:
            await bot.delete_message(message.chat.id, prev_bot)
        except Exception:
            pass
    # delete previous user answer
    if prev_user:
        try:
            await bot.delete_message(message.chat.id, prev_user)
        except Exception:
            pass

    sent = await message.answer(text, **kwargs)

    # track current pair for cleanup and as "last"
    await _append_cleanup(state, message.message_id, sent.message_id)
    await state.update_data(last_bot_msg=sent.message_id, last_user_msg=message.message_id)

sheets = Sheets(settings.spreadsheet_id, settings.sheet_name)
storage = Storage()


def _match(text: str | None, variants: set[str]) -> bool:
    return (text or "").strip().lower() in variants


@dp.message(F.chat.type.in_({"group", "supergroup"}) & F.text.func(lambda t: _match(t, {"фикс"})))
async def group_fix(message: Message, state: FSMContext):
    sent = await message.answer("Бот активирован. Что делаем?", reply_markup=main_inline_kb)
    await _append_cleanup(state, message.message_id, sent.message_id)


from aiogram.types import CallbackQuery

@dp.callback_query(F.data == "menu:new")
async def cb_menu_new(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await new_deal_start(call.message, state)

@dp.callback_query(F.data == "menu:cancel")
async def cb_menu_cancel(call: CallbackQuery, state: FSMContext):
    await call.answer("Отменено")
    await _cleanup_all(call.message, state)
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass


# ===== Основные хендлеры =====
@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type == "private":
        await message.answer(
            "👋 Привет! Это ExcelBot.\nВыбери действие:",
            reply_markup=main_kb,
        )


@dp.message(F.text.func(lambda t: _match(t, {"отмена"})))
async def cancel_flow(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Отменено.", reply_markup=main_kb)


# ===== FSM =====


class DealForm(StatesGroup):
    currency_in = State()
    amount_in = State()
    currency_out = State()
    amount_out = State()
    commission = State()
    expenses = State()
    comment = State()


@dp.message(F.text.func(lambda t: _match(t, {"новая заявка"})))
async def new_deal_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(DealForm.currency_in)
    await send_and_delete_prev(message, "Выбери валюту, которую ПОЛУЧИЛ:", state, reply_markup=currency_inline_kb_in)


@dp.message(DealForm.currency_in)
async def step_currency_in(message: Message, state: FSMContext):
    await state.update_data(currency_in=message.text.strip())
    await state.set_state(DealForm.amount_in)
    await send_and_delete_prev(message, "Введи сумму, которую ПОЛУЧИЛ:", state)


@dp.callback_query(DealForm.currency_in, F.data.startswith("cur_in:"))
async def cb_currency_in(call: CallbackQuery, state: FSMContext):
    _, val = call.data.split(":", 1)
    await state.update_data(currency_in=val)
    await call.answer()
    await state.set_state(DealForm.amount_in)
    await call.message.edit_text(f"Валюта ПОЛУЧИЛ: {val}\n\nТеперь введи сумму, которую ПОЛУЧИЛ:")


@dp.message(DealForm.amount_in)
async def step_amount_in(message: Message, state: FSMContext):
    await state.update_data(amount_in=message.text.strip())
    await state.set_state(DealForm.currency_out)
    await send_and_delete_prev(message, "Выбери валюту, которую ОТДАЛ:", state, reply_markup=currency_inline_kb_out)


@dp.message(DealForm.currency_out)
async def step_currency_out(message: Message, state: FSMContext):
    await state.update_data(currency_out=message.text.strip())
    await state.set_state(DealForm.amount_out)
    await send_and_delete_prev(message, "Введи сумму, которую ОТДАЛ:", state)


@dp.callback_query(DealForm.currency_out, F.data.startswith("cur_out:"))
async def cb_currency_out(call: CallbackQuery, state: FSMContext):
    _, val = call.data.split(":", 1)
    await state.update_data(currency_out=val)
    await call.answer()
    await state.set_state(DealForm.amount_out)
    await call.message.edit_text(f"Валюта ОТДАЛ: {val}\n\nТеперь введи сумму, которую ОТДАЛ:")


@dp.message(DealForm.amount_out)
async def step_amount_out(message: Message, state: FSMContext):
    # Сохраняем сумму ОТДАЛ
    await state.update_data(amount_out=message.text.strip())

    # Считаем ориентир комиссии по курсу: (EUR(получил) - EUR(отдал)) / EUR(отдал) * 100
    data = await state.get_data()
    try:
        amount_in = Decimal(str(data.get("amount_in", "0")).replace(",", "."))
        amount_out = Decimal(str(data.get("amount_out", "0")).replace(",", "."))
        cur_in = data.get("currency_in", "?")
        cur_out = data.get("currency_out", "?")
        today = datetime.now().date()

        eur_in = await convert_to_eur(amount_in, cur_in, today)
        eur_out = await convert_to_eur(amount_out, cur_out, today)
        suggested = None
        if eur_in is not None and eur_out not in (None, Decimal("0")) and eur_out > 0:
            profit_eur = (eur_in - eur_out)
            suggested = (profit_eur / eur_out * Decimal("100")).quantize(Decimal("0.01"))
    except Exception:
        suggested = None

    # Сохраняем ориентир в состоянии и спрашиваем у пользователя его процент
    await state.set_state(DealForm.commission)
    if suggested is not None:
        await state.update_data(suggested_commission=str(suggested))
        await send_and_delete_prev(
            message,
            f"💰 По курсу прибыль составила примерно <b>{suggested}</b> %.\n\nУкажи свой процент прибыли (если другой). Если согласен — напиши '-' или оставь как есть:",
            state,
        )
    else:
        await send_and_delete_prev(
            message,
            "Укажи свой процент прибыли (0–10) без знака %:",
            state,
        )


@dp.message(DealForm.commission)
async def step_commission(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    data = await state.get_data()
    suggested = data.get("suggested_commission")

    if txt in {"", "-", "—"} and suggested:
        commission = suggested
    else:
        raw = txt.replace("%", "").replace(",", ".")
        try:
            val = Decimal(raw)
        except Exception:
            val = Decimal("0")
        if val < 0:
            val = Decimal("0")
        if val > 10:
            val = Decimal("10")
        commission = str(val.quantize(Decimal("0.01")))

    await state.update_data(commission=commission)
    await state.set_state(DealForm.expenses)
    await send_and_delete_prev(message, "Укажи РАСХОДЫ (в %), 0–100 без знака %:\nЕсли нет расходов — напиши '-' или '0'", state)

@dp.message(DealForm.expenses)
async def step_expenses(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if txt in {"", "-", "—"}:
        expenses_pct = "0"
    else:
        raw = txt.replace("%", "").replace(",", ".")
        try:
            val = Decimal(raw)
        except Exception:
            val = Decimal("0")
        if val < 0:
            val = Decimal("0")
        if val > 100:
            val = Decimal("100")
        expenses_pct = str(val.quantize(Decimal("0.01")))
    await state.update_data(expenses=expenses_pct)
    await state.set_state(DealForm.comment)
    await send_and_delete_prev(message, "Комментарий (если нет — напиши '-'):", state)


@dp.message(DealForm.comment)
async def step_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    user = (message.from_user.full_name or message.from_user.username or "Неизвестный").strip()
    comment = message.text.strip()
    if comment == "-":
        comment = ""

    try:
        # Подготовка данных
        currency_in = data.get("currency_in", "?")
        currency_out = data.get("currency_out", "?")
        amount_in = Decimal(data.get("amount_in", "0").replace(",", "."))
        amount_out = Decimal(data.get("amount_out", "0").replace(",", "."))

        today = datetime.now().date()

        eur_in = await convert_to_eur(amount_in, currency_in, today)
        eur_out = await convert_to_eur(amount_out, currency_out, today)

        profit_eur_gross = None
        if eur_in is not None and eur_out is not None:
            profit_eur_gross = (eur_in - eur_out)

        # Комиссия: приоритет — введённая пользователем; иначе авто-маркап
        commission_str = (data.get("commission") or "").strip()
        if not commission_str:
            if profit_eur_gross is not None and eur_out is not None and eur_out > 0:
                commission_pct = (profit_eur_gross / eur_out * Decimal("100")).quantize(Decimal("0.01"))
                commission_str = str(commission_pct)
            else:
                commission_str = ""

        # Расходы в процентах (из состояния), влияет на чистую прибыль
        expenses_str = (data.get("expenses") or "0").strip()
        try:
            expenses_pct = Decimal(expenses_str.replace(",", "."))
        except Exception:
            expenses_pct = Decimal("0")
        if expenses_pct < 0:
            expenses_pct = Decimal("0")
        if expenses_pct > 100:
            expenses_pct = Decimal("100")

        profit_eur = None
        if profit_eur_gross is not None:
            profit_eur = (profit_eur_gross * (Decimal("1") - expenses_pct / Decimal("100"))).quantize(Decimal("0.01"))

        row = [
            user,
            currency_in,
            str(amount_in),
            currency_out,
            str(amount_out),
            commission_str,
            expenses_str,
            comment,
            today.strftime("%d.%m.%Y"),
            str(profit_eur) if profit_eur is not None else "н/д",
        ]

        sheets.append_deal(row)
        ok = await message.answer("✅ Заявка зафиксирована и добавлена в таблицу.")
        # include the final user message and ok-message into cleanup
        await _append_cleanup(state, message.message_id, ok.message_id)
        # full wipe: 'фикс' final message
        await _cleanup_all(message, state)

        # Удаляем диалоговые сообщения (если права позволяют)
        # try:
        #     await asyncio.sleep(1)
        #     await message.delete()
        # except Exception:
        #     pass

    except Exception as e:
        logger.exception(e)
        await message.answer("⚠️ Ошибка при обработке заявки. Проверь ввод или подключение.")

    await state.clear()