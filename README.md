# ExcelBot — Sheets ↔ Telegram (Python)

## 1) Подготовить Google Service Account
- В Google Cloud Console создать проект → Сервисный аккаунт → ключ JSON → сохранить как `credentials.json` в корень.
- Открыть Google Sheets → Share → добавить email сервис-аккаунта с правами **Editor**.

## 2) Заполнить .env
Скопируй `.env.example` в `.env` и подставь значения:
- BOT_TOKEN — токен бота от @BotFather
- SPREADSHEET_ID — ID таблицы (из URL между `/d/` и `/edit`)
- SHEET_NAME — имя листа (по умолчанию Tasks)
- GROUP_CHAT_ID — ID целевой группы (включи бота и сделай его админом, можно узнать через @RawDataBot)
- SEND_INTERVAL_SEC — интервал проверки (по умолчанию 180 сек)

## 3) Установка
```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt