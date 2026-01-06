## Структуризатор хаоса Х‑2000 — SaaS (Railway)

Этот каталог — скелет облачной версии под Railway:

- **web (FastAPI)**: Telegram webhook + API + (в будущем) dashboard
- **worker**: обработка входящих (Groq транскрипт/саммари + атомизация + классификация + напоминания)
- **db (Postgres)**: источник истины + резерв
- **obsidian connector (позже)**: раз в день тянет данные из облака и пишет 4 файла в Vault

### MVP‑цели (итерация 1)

- ingest из Telegram (текст/voice позже) → запись в БД
- команда `/done` → показать последние 10 задач с кнопками → закрыть по кнопке
- daily 07:00 МСК: отправка #неделя tasks
- weekly суббота 07:00 МСК: отправка #3мес tasks+ideas

### Переменные окружения (Railway Variables)

- `TELEGRAM_BOT_TOKEN` (secret)
- `TELEGRAM_WEBHOOK_SECRET` (secret) — строка, которую Telegram будет присылать в заголовке `X-Telegram-Bot-Api-Secret-Token`
- `SHORTCUTS_TOKEN` (secret) — токен для iOS Shortcuts (передаётся заголовком `X-Shortcuts-Token`)
- `DATABASE_URL` (secret) — Railway Postgres (источник истины)
- `GROQ_API_KEY` (secret) — Groq OpenAI-compatible API key (для транскрипта и саммари)
- `TZ=Europe/Moscow`

### Groq модели (MVP)

- Транскрибация: `whisper-large-v3` (голосовые из Telegram)
- Саммари/классификация: `llama-3.1-8b-instant`

Обе модели выбираются в коде по умолчанию, можно переопределить позже.

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


