from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

# Валюты, доступные для выбора
CURRENCIES = [
    "EUR", "RUB", "USDT", "USD", "UAH", "TRY", "GEL", "KZT", "AZN", "MDL", "SAR", "TJS"
]

# Имена колонок (0-based index)
COLUMNS = {
    "name": 0,              # Имя пользователя
    "currency_in": 1,       # Валюта получил
    "amount_in": 2,         # Сумма получил
    "currency_out": 3,      # Валюта отдал
    "amount_out": 4,        # Сумма отдал
    "commission": 5,        # Комиссия (1–10)
    "expenses": 6,          # Расходы % (доп. издержки)
    "comment": 7,           # Комментарий
    "date_fixed": 8,        # Дата фиксации
    "profit_eur": 9         # Прибыль в евро 💶 (с учётом расходов)
}

# Главное меню
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Новая заявка"), KeyboardButton(text="Отмена")]
    ],
    resize_keyboard=True
)

# Кнопки выбора валют (с улучшенным отображением)
currency_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="EUR"), KeyboardButton(text="RUB"), KeyboardButton(text="USDT"), KeyboardButton(text="USD")],
        [KeyboardButton(text="UAH"), KeyboardButton(text="TRY"), KeyboardButton(text="GEL"), KeyboardButton(text="KZT"), KeyboardButton(text="AZN")],
        [KeyboardButton(text="MDL"), KeyboardButton(text="SAR"), KeyboardButton(text="TJS")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
    input_field_placeholder="Выбери валюту из списка ниже 👇"
)

# Инлайн-меню для групп (показывается после слова "фикс")
main_inline_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Новая заявка", callback_data="menu:new")],
    [InlineKeyboardButton(text="Отмена", callback_data="menu:cancel")],
])

# Инлайн-выбор валют (для групп и надёжного отображения в любом чате)
# Отдельно для этапов: ПОЛУЧИЛ (cur_in) и ОТДАЛ (cur_out)

def _inline_currency_rows(prefix: str):
    return [
        [InlineKeyboardButton(text=t, callback_data=f"{prefix}:{t}") for t in ["EUR", "RUB", "USDT", "USD"]],
        [InlineKeyboardButton(text=t, callback_data=f"{prefix}:{t}") for t in ["UAH", "TRY", "GEL", "KZT", "AZN"]],
        [InlineKeyboardButton(text=t, callback_data=f"{prefix}:{t}") for t in ["MDL", "SAR", "TJS"]],
    ]

currency_inline_kb_in = InlineKeyboardMarkup(inline_keyboard=_inline_currency_rows("cur_in"))
currency_inline_kb_out = InlineKeyboardMarkup(inline_keyboard=_inline_currency_rows("cur_out"))