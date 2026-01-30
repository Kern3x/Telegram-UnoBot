from datetime import datetime

from telebot import TeleBot, types as tp

from config import Settings
from app.models import User
from app.database.repos import GameRepo
from app.utils import Keyboards, TextModel
from app.utils.db_manager import get_session
from app.utils.text_models import mention
from app.database.init_db import DataController


class UnoStartCommandHandler:
    def __init__(self, bot: TeleBot) -> None:
        self.bot = bot
        self.kb = Keyboards()
        self.text = TextModel()
        self.settings = Settings()
        self.db = DataController()

        def ensure_game(chat_id: int, title: str):
            with get_session() as s:
                repo = GameRepo(s)
                game = repo.get_by_chat(chat_id)

                if not game:
                    game = repo.create_lobby(chat_id, title)

                return game

        def render_status(state: dict) -> str:
            title = state.get("title") or "Група"
            players = state.get("players") or []
            hands = state.get("hands") or {}

            cur = None
            if state.get("status") == "playing" and players:
                cur = players[state.get("turn_idx", 0) % len(players)]

            lines = [f"🎮 <b>UNO — Лобі</b> ({title})"]

            if players:
                lines.append("")
                lines.append("👥 Гравці:")
                for uid in players:
                    name = mention(
                        uid,
                        state.get("player_meta", {}).get(str(uid), {}).get("name")
                        or str(uid)[-4:],
                    )

                    lines.append(f"• {name} — {len(hands.get(str(uid), []))} карт")

            if cur:
                name = mention(
                    cur,
                    state.get("player_meta", {}).get(str(cur), {}).get("name")
                    or str(cur)[-4:],
                )
                lines.append("")
                lines.append(f"⏱ Хід: {name} ({self.settings.TURN_SECONDS}с.)")

            lines.append("")
            lines.append("Натисни кнопку нижче 👇")

            return "\n".join(lines)

        @bot.message_handler(chat_types=["group", "supergroup"], commands=["uno"])
        def cmd_uno(message: tp.Message):
            user = self.db.get_first(User, tg_id=message.from_user.id)

            if not user:
                self.db.add(
                    User,
                    tg_id=message.from_user.id,
                    name=message.from_user.full_name,
                    groups={"groups": [message.chat.id]},
                    created_at=datetime.now(),
                )

            game = ensure_game(
                message.chat.id,
                message.chat.title or "Група",
            )

            msg = self.bot.send_message(
                message.chat.id,
                render_status(game.state),
                reply_markup=self.kb.game.lobby_kb(game.status),
                parse_mode="HTML",
            )

            self.bot.pin_chat_message(
                message.chat.id, msg.message_id, disable_notification=True
            )
