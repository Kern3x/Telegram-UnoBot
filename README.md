# Telegram UNO Bot

A multiplayer UNO game for Telegram groups, implemented with pyTelegramBotAPI, SQLAlchemy, APScheduler, and Docker.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.x-D71F00)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

## Overview

Telegram UNO Bot brings a persistent multiplayer UNO experience into group chats. Players join a lobby in the group, manage their hands through Telegram interactions, play standard action cards, and compete for coins, experience, levels, and leaderboard positions.

## Features

- Group-based game lobbies
- Persistent games, groups, and player profiles
- Standard number cards and action cards:
  - Skip
  - Reverse
  - Draw Two
  - Wild
  - Wild Draw Four
- Private hand interaction and sticker-based card moves
- Turn timers and automatic timeout handling
- Timed UNO declaration window and late-call penalty
- Multi-card dump handling
- Player rewards, experience, levels, and win tracking
- Group and global leaderboards
- Docker deployment with persistent application data
- Optional PostgreSQL configuration

## Game Flow

1. Add the bot to a Telegram group.
2. Run `/uno` to create or reopen the group lobby.
3. Players join through the lobby controls.
4. Start the match after the lobby is ready.
5. Players select cards through the bot interface.
6. The bot validates moves, advances turns, applies action cards, and manages timers.
7. Final placements receive coins and experience.

## Commands

| Command | Description |
| --- | --- |
| `/start` | Open the bot and initialize the player profile |
| `/uno` | Create or display the UNO lobby in a group |
| `/top10_coins` | Group leaderboard by coins |
| `/top10_xp` | Group leaderboard by experience |
| `/top_global_coins` | Global leaderboard by coins |
| `/top_global_xp` | Global leaderboard by experience |

## Architecture

```text
app/
├── bot.py                  # Bot initialization and handler registration
├── database/               # Database setup and repositories
├── domain/entities/        # Card domain model
├── handlers/
│   ├── commands/           # Bot commands and lobby entry
│   ├── message/            # Group and private message handling
│   └── query/              # Lobby, hand, draw, color, and move callbacks
├── models/                 # User, group, and game persistence models
├── services/               # Deck, game, and reward rules
├── utils/                  # Keyboards, card catalog, announcements, scheduler jobs
└── workers/                # Turn and UNO timers
```

Game rules are kept in the service layer, Telegram updates are handled by dedicated handlers, and SQLAlchemy repositories persist game state separately from transport logic.

## Tech Stack

- Python 3.11
- pyTelegramBotAPI
- SQLAlchemy
- APScheduler
- Pillow
- SQLite or PostgreSQL
- Docker Compose

## Configuration

Create a local `.env` file:

```dotenv
TOKEN=replace_with_your_telegram_bot_token
```

Optional configuration includes:

| Variable | Purpose |
| --- | --- |
| `DB_URL` / `DATABASE_URL` | SQLAlchemy database connection |
| `TURN_SECONDS` | Maximum duration of a player turn |
| `UNO_SECONDS` | UNO declaration window |
| `STICKER_SET_NAME` | Telegram sticker set used for cards |
| `ADD_GROUP_BOT_URL` | Link used to add the bot to a group |
| `REWARD_*_COINS_RANGE` | Placement-based coin rewards |
| `REWARD_*_XP_RANGE` | Placement-based experience rewards |

Never commit the real Telegram token or database credentials.

## Run Locally

```bash
git clone https://github.com/Kern3x/Telegram-UnoBot.git
cd Telegram-UnoBot

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python start_bot.py
```

## Run with Docker

After creating `.env`:

```bash
docker compose up --build -d
```

View logs:

```bash
docker compose logs -f bot
```

Stop the bot:

```bash
docker compose down
```

The `bot-data` Docker volume preserves application data between container restarts.

## Repository Structure

```text
.
├── app/
├── config.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── start_bot.py
└── README.md
```
