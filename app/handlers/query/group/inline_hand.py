from __future__ import annotations

from pathlib import Path
from collections import Counter

from telebot import TeleBot, types as tp

from app.database.repos import GameRepo
from app.utils.db_manager import get_session
from app.utils.card_file_cache import load_cache
from app.utils.card_catalog import CardCatalog
from app.services.game_service import GameService


class InlineHandQueryHandler:
    def __init__(self, bot: TeleBot) -> None:
        self.bot = bot
        self.card_catalog = CardCatalog(Path("app/assets"))
        self.svc = GameService()

        @bot.inline_handler(
            func=lambda q: (q.query or "").strip().startswith("Мої карти")
        )
        def inline_hand(query: tp.InlineQuery):
            cache = load_cache()
            user_id = query.from_user.id
            parts = (query.query or "").split()

            if len(parts) < 3 or not parts[2].lstrip("-").isdigit():
                return bot.answer_inline_query(
                    query.id,
                    [],
                    cache_time=1,
                    is_personal=True,
                    switch_pm_text="Неправильний формат. Натисни кнопку ще раз.",
                    switch_pm_parameter="invalid_inline_hand",
                )

            chat_id = int(parts[2])

            with get_session() as s:
                repo = GameRepo(s)
                game = repo.get_by_chat(chat_id)

                if not game:
                    return bot.answer_inline_query(
                        query.id,
                        [],
                        cache_time=1,
                        is_personal=True,
                        switch_pm_text="Гру не знайдено",
                        switch_pm_parameter="no_game",
                    )

                state = game.state or {}
                players = set(state.get("players", []) or [])
                if user_id not in players:
                    return bot.answer_inline_query(
                        query.id,
                        [],
                        cache_time=1,
                        is_personal=True,
                        switch_pm_text="Ви не у грі",
                        switch_pm_parameter="not_in_game",
                    )

                # кікнуті не можуть користуватися рукою/дампом
                if self.svc.is_kicked(state, user_id):
                    return bot.answer_inline_query(
                        query.id,
                        [],
                        cache_time=1,
                        is_personal=True,
                        switch_pm_text="🚫 Ти вибув(ла) з цієї гри до завершення (ліміт 25 карт).",
                        switch_pm_parameter="kicked",
                    )

                hand: list[dict] = (state.get("hands") or {}).get(
                    str(user_id), []
                ) or []
                if not hand:
                    return bot.answer_inline_query(
                        query.id,
                        [],
                        cache_time=1,
                        is_personal=True,
                        switch_pm_text="В тебе немає карт",
                        switch_pm_parameter="no_hand",
                    )

                results: list = []

                # ------------------ DUMP ARTICLES (тільки коли твій хід і нема pending_color) ------------------
                is_my_turn = int(self.svc.current_player_id(state)) == int(user_id)
                pending_color = state.get("pending_color") or {}
                has_pending_color = bool(
                    pending_color.get("active") and not pending_color.get("resolved")
                )

                if is_my_turn and not has_pending_color:
                    top = state.get("top_card")
                    cur_color = state.get("current_color")

                    # групуємо карти по “значенню/іконці” (group_key має відповідати твоєму play_group_dump)
                    groups = [self.svc.group_key(c) for c in hand]
                    cnt = Counter(groups)

                    # робимо Article тільки для тих груп, де 2+ карт
                    for group, n in cnt.items():
                        if n < 2:
                            continue

                        # перевіряємо: перша карта цієї групи має бути зіграбельна ЗАРАЗ
                        first_card = next(
                            (c for c in hand if self.svc.group_key(c) == group), None
                        )
                        if not first_card:
                            continue
                        if not self.svc.can_play(first_card, top, cur_color):
                            continue

                        title = self._dump_title(group, n)
                        text = self._dump_text(group, n)

                        kb = tp.InlineKeyboardMarkup()
                        kb.add(
                            tp.InlineKeyboardButton(
                                text=f"🗑 Скинути всі такі ({n})",
                                callback_data=f"dump:{chat_id}:{user_id}:{group}",
                            )
                        )

                        results.append(
                            tp.InlineQueryResultArticle(
                                id=f"dump:{game.id}:{user_id}:{group}",
                                title=title,
                                description="Натисни, щоб зʼявилась кнопка скидання в чаті",
                                input_message_content=tp.InputTextMessageContent(
                                    message_text=text,
                                    parse_mode="HTML",
                                    disable_web_page_preview=True,
                                ),
                                reply_markup=kb,
                            )
                        )

                # ------------------ STICKERS (твоя рука) ------------------
                for idx, card in enumerate(hand):
                    k = self.card_catalog.card_key(card)
                    file_id = cache.get(k)
                    if not file_id:
                        continue

                    results.append(
                        tp.InlineQueryResultCachedSticker(
                            id=f"{game.id}:{user_id}:{idx}",
                            sticker_file_id=file_id,
                        )
                    )

                return bot.answer_inline_query(
                    query.id,
                    results,
                    cache_time=0,
                    is_personal=True,
                )

    @staticmethod
    def _dump_title(group: str, n: int) -> str:
        # title в списку інлайн-результатів
        pretty = InlineHandQueryHandler._pretty_group(group)
        return f"🗑 Скинути всі: {pretty} ({n})"

    @staticmethod
    def _dump_text(group: str, n: int) -> str:
        # текст, який відправиться в чат при виборі Article
        pretty = InlineHandQueryHandler._pretty_group(group)
        return (
            f"🗑 <b>Скидання групи</b>\n"
            f"Тип: <b>{pretty}</b>\n"
            f"К-сть: <b>{n}</b>\n\n"
            f"Натисни кнопку нижче 👇"
        )

    @staticmethod
    def _pretty_group(group: str) -> str:
        # group приходить з GameService.group_key()
        # приклади: "num:5", "p2", "p4", "wild", "skip", "rev"
        if group.startswith("num:"):
            v = group.split(":", 1)[1]
            return f"{v}"
        if group == "p2":
            return "+2"
        if group == "p4":
            return "+4"
        if group == "wild":
            return "WILD"
        if group == "skip":
            return "SKIP"
        if group == "rev":
            return "REV"
        return group.upper()
