# 🚀 Telegram SkeletonBot

A lightweight starter template for building Telegram bots with **pyTelegramBotAPI (TeleBot)**. It includes only the essentials: a clean structure, config loading, optional DB manager, Docker, and a place for your handlers.

## Features
- Minimal, readable project layout
- Environment-based configuration via `.env`
- Optional SQLAlchemy DB manager (engine/session + `create_tables()`)
- Docker & Docker Compose setup
- Ready-to-extend handlers module

## Tech Stack
- Python 3.11
- pyTelegramBotAPI (TeleBot)
- SQLAlchemy (optional)
- Docker / Docker Compose
- python-dotenv

## Project Structure
```
.
├─ app/
│  ├─ database/
│  │  ├─ __init__.py             # Exports DataController from init_db.py
│  │  └─ init_db.py              # Class with universal CRUD methods
│  ├─ handlers/
│  │  ├─ commands/               # Directory with command handlers
│  │  │   ├─ start.py            # Start command handler example
│  │  │   └─ __init__.py         # Exports command handlers form "commands/" directory
│  │  ├─ message/                # Directory with message handlers
│  │  │   ├─ message_handler.py  # Message handler example
│  │  │   └─ __init__.py         # Exports message handlers form "message/" directory
│  │  ├─ query/                  # Directory with query handlers
│  │  │   ├─ query_handler.py    # Query handler example
│  │  │   └─ __init__.py         # Exports query handlers form "query/" directory
│  │  └─ __init__.py             # Exports handlers from all directories in "handlers/"
│  ├─ models/
│  │  ├─ __init__.py             # (add your models here; sample below)
│  │  └─ user.py                 # SQLAlchemy model example
│  └─ utils/
│  │   ├─ keryboards/            # Keyboards directory
│  │   │   ├─ kb_classes/        # Keyboards class directory
│  │   │   │   ├─ __init__.py    # Exports all keyboards
│  │   │   │   └─ test_kbs.py    # Keyboard example
│  │   │   ├─ __init__.py        # Exports Keyboards class from kb_initer.py
│  │   │   └─ kb_initer.py       # Main class of Keyboards, which init all keyboards from "kb_classes/" directory 
│  │   ├─ __init__.py            # Exports utilities (e.g., Keyboards)
│  │   └─ db_manager.py          # SQLAlchemy engine/session + create_tables()
│  └─ bot.py                     # TeleBot initialization, handler registration, start
├─ config.py                     # Reads .env, base/dev configs
├─ start_bot.py                  # Entry point (creates and runs the bot)
├─ requirements.txt              # Dependencies
├─ Dockerfile                    # Bot image
└─ docker-compose.yml            # Bot + (optional) Postgres
```

> **Note:** Ensure `app/handlers/message.py` exists (or update `__init__.py` imports accordingly). Optionally add `app/utils/keyboards.py` if you plan to use custom keyboards.

## Quick Start (Local)
1. **Clone**
   ```bash
   git clone https://github.com/Kern3x/Telegram-SkeletonBot.git
   cd Telegram-SkeletonBot
   ```

2. **Virtualenv & deps**
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Create `.env` in project root**
   ```dotenv
   TOKEN=123456:telegram-bot-token
   # Optional DB:
   POSTGRES_DB=botdb
   POSTGRES_USER=botuser
   POSTGRES_PASSWORD=botpass
   # If running without Docker Compose, use a local DB URL or SQLite:
   # DB_URL=sqlite:///./bot.db
   # For Docker Compose (service name 'db'):
   # DB_URL=postgresql+psycopg2://botuser:botpass@db:5432/botdb
   ```

4. **Run**
   ```bash
   python start_bot.py
   ```

## Quick Start (Docker)
> Requires Docker & Docker Compose.

1. Fill `.env` (see example above).
2. Start services:
   ```bash
   docker compose up --build
   ```
   This builds the bot image and (optionally) brings up Postgres.

## Configuration
- `config.py` reads `.env` and exposes the base config with:
  - `BOT_TOKEN` — bot token (`TOKEN` in `.env`)
  - `DB_URL` — database URL (optional)
- You can add an `ENV` variable (e.g., `development` / `production`) and switch configs accordingly.

## Add Your First Handler
Create `app/handlers/message/message.py`:
```python
# app/handlers/message/message.py
from telebot.types import Message

class TestMessageHandler:
    def __init__(self, bot):
        self.bot = bot

        @self.bot.message_handler(commands=["start"])
        def handle_start(msg: Message):
            self.bot.reply_to(msg, "Hello! I'm alive ✅")

        @self.bot.message_handler(func=lambda m: True)
        def echo(msg: Message):
            self.bot.reply_to(msg, f"You wrote: {msg.text}")
```

The bot already imports and registers this handler in `app/bot.py` (via `handlers.__init__`).

## Entry Point
`start_bot.py` is a tiny launcher:
```python
from app.bot import TelegramBot

bot = TelegramBot()
bot.start()
```

## Database
- `app/utils/db_manager.py` provides a basic SQLAlchemy setup.
- `create_tables()` will call `Base.metadata.create_all(engine)`.
- Add your ORM models and make sure they inherit from the shared `Base`.

## Logging & Production Notes
- Consider adding Python `logging` and graceful shutdown (SIGTERM/SIGINT) handling.
- For higher scale, prefer **Webhook** over **polling**.
- If using Alpine-based images with `psycopg2-binary` or other C extensions, you might need extra system packages.

## Requirements (example)
Adjust `requirements.txt` to your needs. A minimal set:
```txt
pyTelegramBotAPI
python-dotenv
SQLAlchemy
psycopg2-binary    # if you use Postgres
```

## Roadmap / TODO
- [ ] pytest scaffolding
- [ ] GitHub Actions (lint/test/build)
