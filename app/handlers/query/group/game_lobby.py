from __future__ import annotations

from sqlalchemy import select
from datetime import datetime
from telebot import TeleBot, types as tp

from app.database.repos import GameRepo, OptimisticLockError
from app.utils.keyboards import Keyboards
from app.utils.text_models import mention
from app.utils.db_manager import get_session
from app.workers.timers import (
    prepare_turn_timer,
    schedule_turn_timeout,
    cancel_turn_timeout,
)
from app.models import User
from app.services.game_service import GameService
from app.database.init_db import DataController


class GameLobbyQueryHandler:
    def __init__(self, bot: TeleBot) -> None:
        self.bot = bot
        self.kb = Keyboards()
        self.svc = GameService()
        self.db = DataController()

        def _render_lobby_text(state: dict) -> str:
            title = state.get("title") or "Група"
            players = state.get("players") or []

            lines = [f"🎮 <b>UNO — Лобі</b> ({title})", ""]

            if not players:
                lines.append("Ніхто ще не приєднався.")
            else:
                lines.append("👥 Гравці:")
                meta = state.get("player_meta", {})

                for i, uid in enumerate(players, 1):
                    m = meta.get(str(uid), {})
                    display = m.get("name") or (
                        ("@" + m["username"]) if m.get("username") else str(uid)
                    )
                    lines.append(f"{i}. {mention(uid, display)}")

            lines += ["", "Натисни кнопку нижче 👇"]
            return "\n".join(lines)

        @self.bot.callback_query_handler(
            func=lambda call: bool(call.data) and call.data.startswith("lobby:")
        )
        def lobby_uno_query(call: tp.CallbackQuery) -> None:
            choice = call.data.split(":")[1]
            chat_id = call.message.chat.id
            uid = call.from_user.id

            started_turn: tuple[int, str, int] | None = (
                None  # (cur_uid, token, seconds)
            )
            cur_uid_for_ui: int | None = None
            pm_for_ui: dict = {}

            with get_session() as s:
                repo = GameRepo(s)
                game = repo.get_by_chat(chat_id)

                if not game:
                    self.bot.answer_callback_query(
                        call.id, "Лобі не знайдено. Напиши /uno"
                    )
                    return

                for _ in range(2):
                    try:
                        state = game.state or {}
                        players: list[int] = state.get("players", []) or []
                        pm: dict = state.get("player_meta", {}) or {}
                        pm_for_ui = pm

                        if choice == "join":
                            if uid in players:
                                self.bot.answer_callback_query(
                                    call.id, "⚠️ Ти вже в лобі ⚠️", show_alert=True
                                )
                                return

                            # кікнуті не можуть повернутися до кінця гри
                            if game.status == "playing" and self.svc.is_kicked(
                                state, uid
                            ):
                                self.bot.answer_callback_query(
                                    call.id,
                                    "🚫 Ти вибув(ла) з цієї гри до завершення (ліміт 25 карт).",
                                    show_alert=True,
                                )
                                return

                            players.append(uid)

                            user = call.from_user
                            name = (
                                " ".join(
                                    x for x in [user.first_name, user.last_name] if x
                                )
                                or "Player"
                            )
                            pm[str(uid)] = {"name": name, "username": user.username}

                            # гарантуємо hands та запис
                            hands = state.get("hands") or {}
                            hands.setdefault(str(uid), [])
                            state["hands"] = hands

                            # якщо гра вже йде — видати 7 карт
                            if game.status == "playing":
                                for _ in range(7):
                                    self.svc.draw_one(state, uid)

                            state["players"] = players
                            state["player_meta"] = pm
                            game.state = state

                            repo.save(
                                game, expected_version=game.version, state=game.state
                            )
                            self.bot.answer_callback_query(call.id, "Ти приєднався ✅")
                            break

                        if choice == "leave":
                            if uid not in players:
                                self.bot.answer_callback_query(
                                    call.id, "⚠️ Ти вже вийшов(ла) ⚠️", show_alert=True
                                )
                                return

                            players.remove(uid)
                            pm.pop(str(uid), None)

                            state["players"] = players
                            state["player_meta"] = pm

                            hands = state.get("hands") or {}
                            hands.pop(str(uid), None)
                            state["hands"] = hands

                            game.state = state
                            repo.save(
                                game, expected_version=game.version, state=game.state
                            )

                            self.bot.answer_callback_query(call.id, "Ти вийшов ❌")
                            break

                        if choice == "start":
                            if game.status == "playing":
                                self.bot.answer_callback_query(
                                    call.id, "Гра вже запущена.", show_alert=True
                                )
                                return

                            if len(players) < 2:
                                self.bot.answer_callback_query(
                                    call.id,
                                    "⚠️ Не достатньо гравців (мінімум 2) ⚠️",
                                    show_alert=True,
                                )
                                return

                            # на всяк випадок прибираємо старий turn job
                            cancel_turn_timeout(chat_id)

                            title = (
                                call.message.chat.title or state.get("title") or "Група"
                            )
                            new_state = self.svc.start_game_state(players)

                            new_state["title"] = title
                            new_state["player_meta"] = pm
                            new_state["table_chat_id"] = chat_id
                            new_state["table_message_id"] = call.message.message_id

                            # ставимо токен/uid в state
                            seconds = 30
                            cur_uid, token = prepare_turn_timer(
                                self.svc, new_state, seconds=seconds
                            )

                            game.state = new_state
                            game.status = "playing"

                            repo.save(
                                game,
                                expected_version=game.version,
                                state=game.state,
                                status=game.status,
                            )

                            # після save — плануємо job
                            started_turn = (cur_uid, token, seconds)
                            cur_uid_for_ui = cur_uid

                            existing = set(
                                s.scalars(
                                    select(User.tg_id).where(User.tg_id.in_(players))
                                )
                            )
                            missing = [uid for uid in players if uid not in existing]

                            for uid in missing:
                                s.add(
                                    User(
                                        tg_id=uid,
                                        name=pm.get(str(uid), {}).get("name", "Player"),
                                        created_at=datetime.now(),
                                    )
                                )

                            self.bot.answer_callback_query(call.id, "🎮 Гру розпочато!")
                            break

                        if choice == "stop":
                            user = self.bot.get_chat_member(chat_id, uid)
                            if user.status not in ["administrator", "creator"]:
                                self.bot.answer_callback_query(
                                    call.id,
                                    "⚠️ Тільки адміністратор може зупинити ⚠️",
                                    show_alert=True,
                                )
                                return

                            cancel_turn_timeout(chat_id)
                            repo.delete_lobby(game)

                            self.bot.edit_message_text(
                                text="🛑 Лобі зупинено адміністратором.",
                                chat_id=chat_id,
                                message_id=call.message.message_id,
                            )
                            self.bot.answer_callback_query(call.id, "Лобі зупинено")
                            return

                        self.bot.answer_callback_query(
                            call.id, "Невідома дія", show_alert=True
                        )
                        return

                    except OptimisticLockError:
                        s.rollback()
                        game = repo.get_by_chat(chat_id)
                        if not game:
                            self.bot.answer_callback_query(
                                call.id, "Лобі зникло", show_alert=True
                            )
                            return

                game = repo.get_by_chat(chat_id)
                if not game:
                    return

                # Оновлення UI — краще робити в сесії, але без доступу до лінивих полів.
                if game.status == "playing":
                    cur_show = cur_uid_for_ui
                    if cur_show is None:
                        # fallback: беремо з state
                        st = game.state or {}
                        cur_show = int(self.svc.current_player_id(st))

                    m = pm_for_ui.get(str(cur_show), {}) if cur_show is not None else {}
                    mention_cur = (
                        mention(cur_show, m.get("name") or str(cur_show))
                        if cur_show
                        else "-"
                    )

                    self.bot.edit_message_text(
                        text=(
                            "🎮 <b>Гру розпочато!</b>\n"
                            "Натисни <b>🃏 Мої карти</b> щоб показати свою руку.\n"
                            f"Хід: {mention_cur}"
                        ),
                        chat_id=chat_id,
                        message_id=call.message.message_id,
                        reply_markup=self.kb.game.get_cards_kb(chat_id),
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                else:
                    text = _render_lobby_text(game.state or {})
                    self.bot.edit_message_text(
                        text=text,
                        chat_id=chat_id,
                        message_id=call.message.message_id,
                        reply_markup=self.kb.game.lobby_kb(game.status),
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )

            # schedule job після виходу з сесії
            if started_turn is not None:
                u, tok, sec = started_turn
                schedule_turn_timeout(chat_id, u, tok, seconds=sec)
