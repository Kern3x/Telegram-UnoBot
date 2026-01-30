from telebot import TeleBot, types as tp

from app.models import User
from app.utils import Keyboards
from app.utils.text_models import TextModel
from app.database.init_db import DataController


class ProfileMessageHandler:
    def __init__(self, bot: TeleBot) -> None:
        self.kb = Keyboards()
        self.db = DataController()

        @bot.message_handler(
            chat_types=["private"], func=lambda msg: msg.text == "🎮 Профіль"
        )
        def profile_message(message: tp.Message) -> None:
            user: User = self.db.get_first(User, tg_id=message.from_user.id)

            if user:
                bot.reply_to(
                    message,
                    TextModel.PROFILE_MESSAGE.format(
                        user.name,
                        user.games_played,
                        user.wins,
                        user.level,
                        user.xp,
                        user.next_level_experience,
                        user.level + 1,
                        user.coins,
                        user.created_at.strftime("%d.%m.%Y %H:%M"),
                    ),
                    # reply_markup=self.kb.commands.add_group_kb(),
                )
