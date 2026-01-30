from telebot import types as tp

from config import Settings


class CommandsKeyboard:
    def __init__(self) -> None:
        self.settings = Settings()

    def start_kb(self) -> tp.ReplyKeyboardMarkup:
        kb = tp.ReplyKeyboardMarkup(resize_keyboard=True)

        kb.add(tp.KeyboardButton(text="🔥 Зіграти в групі"))

        kb.add(
            tp.KeyboardButton(text="😎 Зіграти з другом"),
            tp.KeyboardButton(text="👤 Рандомний суперник"),
        )

        kb.add(
            tp.KeyboardButton(text="🛍 Магазин"), tp.KeyboardButton(text="🎮 Профіль")
        )

        return kb

    def add_group_kb(self) -> tp.InlineKeyboardMarkup:
        kb = tp.InlineKeyboardMarkup(row_width=3)

        kb.add(
            tp.InlineKeyboardButton(
                "Додати до групи 📩", url=self.settings.ADD_GROUP_BOT_URL
            )
        )

        return kb
