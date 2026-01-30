from datetime import datetime

from telebot import TeleBot, types as tp

from app.models import User
from app.utils import Keyboards, TextModel
from app.database import DataController


class StartCommandHandler:
    def __init__(self, bot: TeleBot) -> None:
        self.kb = Keyboards()
        self.db = DataController()
        self.text = TextModel()

        @bot.message_handler(chat_types=["private"], commands=["start"])
        def start_message(message: tp.Message) -> None:
            user_id = message.from_user.id
            user = self.db.get_first(User, tg_id=user_id)

            if not user:
                self.db.add(
                    User,
                    tg_id=user_id,
                    name=message.from_user.full_name,
                    created_at=datetime.now(),
                )

            bot.reply_to(
                message,
                self.text.START_MESSAGE,
                reply_markup=self.kb.commands.start_kb(),
            )
