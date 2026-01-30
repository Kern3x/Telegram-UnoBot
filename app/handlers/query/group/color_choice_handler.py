from __future__ import annotations

from telebot import TeleBot, types as tp

from config import Settings
from app.utils.keyboards import Keyboards
from app.database.repos import GameRepo, OptimisticLockError
from app.utils.db_manager import get_session
from app.services.game_service import GameService
from app.utils.text_models import mention
from app.utils.announce import podium_lines
from app.utils.level_up_notify import send_level_up_notifications
from app.services.reward_service import apply_rewards_if_needed
from app.workers.timers import (
    prepare_turn_timer,
    schedule_turn_timeout,
    cancel_turn_timeout,
)


class ColorChoiceCallbackHandler:
    def __init__(self, bot: TeleBot) -> None:
        self.bot = bot
        self.svc = GameService()
        self.kb = Keyboards()
        self.settings = Settings()

        @bot.callback_query_handler(
            func=lambda c: bool(c.data) and c.data.startswith("color:")
        )
        def on_color_choice(call: tp.CallbackQuery) -> None:
            try:
                _, chat_id_s, color = call.data.split(":", 2)
                chat_id = int(chat_id_s)
            except Exception:
                self.bot.answer_callback_query(
                    call.id, "Некоректні дані кнопки.", show_alert=True
                )
                return

            uid = call.from_user.id
            start_turn: tuple[int, str, int] | None = None
            need_cancel_turn: bool = False
            kicked_events: list[dict] = []
            game_state: dict = {}
            level_ups_to_notify: dict = {}

            with get_session() as s:
                repo = GameRepo(s)
                game = repo.get_by_chat(chat_id)
                if not game or game.status != "playing":
                    self.bot.answer_callback_query(
                        call.id, "Гра не активна.", show_alert=True
                    )
                    return

                for _ in range(3):
                    try:
                        state = game.state or {}

                        ok, msg = self.svc.choose_color(state, uid=uid, color=color)
                        if not ok:
                            self.bot.answer_callback_query(
                                call.id, msg, show_alert=True
                            )
                            return

                        # якщо під час добору (+4) когось кікнуло і гра завершилась — не ставимо новий хід
                        if str(state.get("status") or "").lower() == "finished":
                            t = state.setdefault("timers", {})
                            t["turn"] = {}
                            t["uno"] = {}
                            state["timers"] = t
                            need_cancel_turn = True

                            game.state = state
                            game.status = "finished"
                            game_state = game.state
                            kicked_events = self.svc.pop_kick_events(state)
                            level_ups_to_notify = apply_rewards_if_needed(s, state, self.settings)
                            if level_ups_to_notify and not state.get("level_ups_notified"):
                                state["level_ups_notified"] = True
                            repo.save(
                                game,
                                expected_version=game.version,
                                state=game.state,
                                status=game.status,
                            )
                            start_turn = None
                            break

                        # choose_color() вже зрушив turn_idx (і може виставити skip_next_turn).
                        # prepare_turn_timer сам проковтне skip-chain і поставить state["timers"]["turn"].
                        seconds = 30
                        # на всяк випадок прибираємо старий turn job
                        cancel_turn_timeout(chat_id)
                        next_uid, token = prepare_turn_timer(self.svc, state, seconds=seconds)
                        start_turn = (next_uid, token, seconds)

                        game.state = state
                        game_state = game.state
                        kicked_events = self.svc.pop_kick_events(state)
                        repo.save(game, expected_version=game.version, state=game.state)
                        break

                    except OptimisticLockError:
                        s.rollback()
                        game = repo.get_by_chat(chat_id)
                        if not game:
                            self.bot.answer_callback_query(
                                call.id, "Гра зникла.", show_alert=True
                            )
                            return

            # після save — плануємо job (replace_existing=True, старий реально перезапишеться)
            if need_cancel_turn:
                cancel_turn_timeout(chat_id)

            if start_turn is not None:
                u, tok, sec = start_turn
                schedule_turn_timeout(chat_id, u, tok, seconds=sec)

            # повідомляємо про кік (після save)
            for ev in kicked_events:
                try:
                    ku = int(ev.get("uid") or 0)
                    cards = int(ev.get("cards") or 0)
                    meta = game_state.get("player_meta", {}) or {}
                    m = (meta or {}).get(str(ku), {}) if meta else {}
                    nm = m.get("name") or (("@" + m["username"]) if m.get("username") else str(ku)[-4:])
                    self.bot.send_message(
                        chat_id,
                        f"🚫 {mention(ku, nm)} вибув(ла) з гри: у руці стало <b>{cards}</b> карт (ліміт 25).",
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                except Exception:
                    pass

            # level-up notifications
            if level_ups_to_notify:
                send_level_up_notifications(
                    self.bot,
                    chat_id,
                    level_ups_to_notify,
                    game_state.get("player_meta", {}) or {},
                )

            self.bot.answer_callback_query(call.id, "🎨 Колір обрано")

            # прибрати повідомлення з клавою
            try:
                self.bot.delete_message(chat_id, call.message.message_id)
            except Exception:
                pass

            # якщо гра завершилась (наприклад, +4 кікнув і лишив 1 гравця) — просто оголошуємо переможця
            if str(game_state.get("status") or "").lower() == "finished":
                try:
                    self.bot.send_message(
                        chat_id,
                        "\n".join(podium_lines(game_state)),
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                except Exception:
                    pass
                return


            try:
                top = game_state.get("top_card") or {}
                cur_uid = int(self.svc.current_player_id(game_state))
                name = (
                    game_state.get("player_meta", {})
                    .get(str(cur_uid), {})
                    .get("name", "Гравець")
                )
                color = self.settings.colors.get(color, color)
                top_color = self.settings.colors.get(
                    top.get("color", ""), top.get("color", "")
                )

                if top.get("color") in ["wild", "p4"]:
                    top_color = ""

                kind = self.settings.other_type_cards.get(top.get("kind", ""), "")
                top_value = top.get('value') or ""

                if kind in ["wild", "p4", "p2", "skip", "rev"]:
                    kind = self.settings.other_type_cards.get(kind, "")

                if kind == "num":
                    kind = ""

                self.bot.send_message(
                    chat_id,
                    (
                        f"🎨 Колір обрано: {color}\n"
                        f"🃏 Верхня карта: {kind} {top_value} {top_color}\n"
                        f"➡️ Далі хід: {mention(cur_uid, name)}"
                    ),
                    parse_mode="HTML",
                    reply_markup=self.kb.game.get_cards_kb(chat_id),
                )
            except Exception:
                pass
