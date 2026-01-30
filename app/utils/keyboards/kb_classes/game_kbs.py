from telebot import types as tp


class GameKeyboard:
    def lobby_kb(self, game_status: str) -> tp.InlineKeyboardMarkup:
        kb = tp.InlineKeyboardMarkup()

        kb.add(
            tp.InlineKeyboardButton("✅ Приєднатись", callback_data="lobby:join"),
            tp.InlineKeyboardButton("❌ Вийти", callback_data="lobby:leave"),
        )

        if game_status != "playing":
            kb.add(tp.InlineKeyboardButton("🎮 Почати", callback_data="lobby:start"))

        kb.add(tp.InlineKeyboardButton("🛑 Стоп (admin)", callback_data="lobby:stop"))

        return kb

    def get_cards_kb(self, chat_id: int) -> tp.InlineKeyboardMarkup:
        kb = tp.InlineKeyboardMarkup()

        kb.add(
            tp.InlineKeyboardButton(
                text="🃏 Мої карти",
                switch_inline_query_current_chat=f"Мої карти {chat_id}",
            ),
            tp.InlineKeyboardButton(
                text="Взяти карту ➕", callback_data=f"draw:{chat_id}"
            ),
        )

        return kb

    def color_choice_kb(self, chat_id: int) -> tp.InlineKeyboardMarkup:
        kb = tp.InlineKeyboardMarkup(row_width=4)

        kb.add(
            tp.InlineKeyboardButton("🔴", callback_data=f"color:{chat_id}:red"),
            tp.InlineKeyboardButton("🟢", callback_data=f"color:{chat_id}:green"),
            tp.InlineKeyboardButton("🔵", callback_data=f"color:{chat_id}:blue"),
            tp.InlineKeyboardButton("🟡", callback_data=f"color:{chat_id}:yellow"),
        )

        return kb
