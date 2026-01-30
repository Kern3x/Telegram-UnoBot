from telebot import TeleBot, types as tp

from app.utils import Keyboards
from app.utils.text_models import TextModel
from app.database.init_db import DataController


class GameMessageHandler:
    def __init__(self, bot: TeleBot) -> None:
        self.kb = Keyboards()
        self.db = DataController()

        @bot.message_handler(
            chat_types=["private"], func=lambda msg: msg.text == "🔥 Зіграти в групі"
        )
        def group_game_message(message: tp.Message) -> None:
            bot.reply_to(
                message, TextModel.GROUP_GAME_MESSAGE, reply_markup=self.kb.commands.add_group_kb()
            )
