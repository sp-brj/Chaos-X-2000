## Структуризатор хаоса Х‑2000 — SaaS (Railway)

Этот каталог — скелет облачной версии под Railway:

- **web (FastAPI)**: Telegram webhook + API + (в будущем) dashboard
- **worker**: обработка входящих (Groq транскрипт/саммари + атомизация + классификация + напоминания)
- **db (Postgres)**: источник истины + резерв
- **obsidian connector (позже)**: раз в день тянет данные из облака и пишет 4 файла в Vault

### MVP‑цели (итерация 1)

- ingest из Telegram (текст/voice) → запись в БД
- команда `/done` → показать последние 10 задач с кнопками → закрыть по кнопке
- daily 07:00 МСК: отправка #неделя tasks
- weekly суббота 07:00 МСК: отправка #3мес tasks+ideas

### Переменные окружения (Railway Variables)

- `TELEGRAM_BOT_TOKEN` (secret)
- `TELEGRAM_WEBHOOK_SECRET` (secret) — строка, которую Telegram будет присылать в заголовке `X-Telegram-Bot-Api-Secret-Token`
- `SHORTCUTS_TOKEN` (secret) — токен для iOS Shortcuts (передаётся заголовком `X-Shortcuts-Token`)
- `DATABASE_URL` (secret) — Railway Postgres (источник истины)
- `GROQ_API_KEY` (secret) — Groq OpenAI-compatible API key (для транскрипта и саммари)
- `GROQ_TRANSCRIBE_MODEL` (optional) — по умолчанию `whisper-large-v3`
- `GROQ_TRANSCRIPT_EDIT_MODEL` (optional) — “чистка” транскрипта по правилам диктовки (по умолчанию берём `GROQ_SUMMARY_MODEL` или `llama-3.1-8b-instant`)
- `GROQ_SUMMARY_MODEL` (optional) — по умолчанию `llama-3.1-8b-instant`
- `GOOGLE_SHEETS_ID` (optional) — id таблицы “Мои цели и планы”
- `GOOGLE_SHEETS_SA_JSON_B64` (optional, secret) — base64 JSON service account для Google Sheets API
- `ADMIN_TOKEN` (optional, secret) — защита ручных admin-эндпоинтов (например sync в Sheets)
- `GOOGLE_SHEETS_SYNC_ENABLED` (optional) — включить ежедневный автосинк в Sheets (default: true)
- `GOOGLE_SHEETS_SYNC_TIME` (optional) — время автосинка в формате `HH:MM` по TZ (default: `06:00`)
- `TZ=Europe/Moscow`

### Groq модели (MVP)

- Транскрибация: `whisper-large-v3` (голосовые из Telegram)
- Пост-обработка транскрипта (“редактор диктовки”): `llama-3.1-8b-instant` (можно заменить отдельной моделью через `GROQ_TRANSCRIPT_EDIT_MODEL`)
- Саммари/классификация: `llama-3.1-8b-instant`

Модели выбираются в коде по умолчанию, можно переопределить переменными окружения.

### Локальный запуск (для разработчика)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg://user:pass@host:5432/db"
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_WEBHOOK_SECRET="..."
uvicorn app.main:app --reload
```


