from telebot import TeleBot, types as tp

from app.models import User
from app.database.repos import GameRepo
from app.utils import Keyboards, TextModel
from app.database import DataController
from app.utils.db_manager import get_session


class TopCommandHandler:
    def __init__(self, bot: TeleBot) -> None:
        self.kb = Keyboards()
        self.db = DataController()
        self.text = TextModel()
        self.emoji = {
            "coins": "💰",
            "xp": "🧩",
        }

        def _render_top_users(users: list[User], by: str, mode: str) -> str:
            mode_str = "в групі" if mode == "group" else "у світі"
            lines = [
                f"🏆 Топ 10 гравців {mode_str} за <b>{by}</b>{self.emoji.get(by, by)}:"
            ]

            for idx, user in enumerate(users, start=1):
                name = user.name

                if idx == 1:
                    name = "🥇 " + user.name
                elif idx == 2:
                    name = "🥈 " + user.name
                elif idx == 3:
                    name = "🥉 " + user.name

                value = getattr(user, by, 0)
                lines.append(f"{idx}. {name} — {value}")

            return "\n".join(lines)

        @bot.message_handler(
            chat_types=["group", "supergroup"],
            commands=["top10_coins", "top10_xp", "top_global_coins", "top_global_xp"],
        )
        def top10_coins_message(message: tp.Message) -> None:
            with get_session() as s:
                group_id = message.chat.id
                repo = GameRepo(s)
                by = "coins"
                top_users = None
                mode = "group"

                if message.text == "/top10_coins":
                    top_users = repo.get_top_players_by(
                        limit=10, group_id=group_id, by="coins"
                    )

                elif message.text == "/top10_xp":
                    top_users = repo.get_top_players_by(
                        limit=10, group_id=group_id, by="xp"
                    )
                    by = "xp"

                elif message.text == "/top_global_coins":
                    top_users = repo.get_top_players_by(limit=10, by="coins")
                    mode = "global"

                elif message.text == "/top_global_xp":
                    top_users = repo.get_top_players_by(limit=10, by="xp")
                    by = "xp"
                    mode = "global"

                if message.text in ["/top10_coins", "/top10_xp"] and not top_users:
                    bot.send_message(message.chat.id, "Не знайдено гравців у групі.")
                    return

                elif (
                    message.text in ["/top_global_coins", "/top_global_xp"]
                    and not top_users
                ):
                    bot.send_message(message.chat.id, "Поки немає світових лідерів.")
                    return

                text = _render_top_users(top_users, by, mode)

            bot.send_message(message.chat.id, text, parse_mode="HTML")
