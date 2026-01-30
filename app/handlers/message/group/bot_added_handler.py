from telebot import TeleBot, types as tp

from app.models import Group
from app.database.init_db import DataController


class BotAddedHandler:
    def __init__(self, bot: TeleBot) -> None:
        self.db = DataController()

        @bot.my_chat_member_handler()
        def on_my_chat_member(update: tp.ChatMemberUpdated) -> None:
            chat = update.chat
            if chat.type not in ("group", "supergroup"):
                return

            old_status = update.old_chat_member.status
            new_status = update.new_chat_member.status

            if old_status in ("left", "kicked") and new_status in (
                "member",
                "administrator",
            ):
                chat_id = chat.id
                owner_id = self._get_owner_id(bot, chat_id) or 0
                self.db.add(Group, chat_id=chat_id, title=chat.title, owner_id=owner_id)

                bot.send_message(chat_id, "Привіт! Дякую, що додали мене 👋")

    def _get_owner_id(self, bot: TeleBot, chat_id: int) -> int | None:
        try:
            admins = bot.get_chat_administrators(chat_id)
        except Exception:
            return None

        for admin in admins:
            if admin.status == "creator":
                return admin.user.id

        return None
