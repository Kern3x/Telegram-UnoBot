from __future__ import annotations

import time
import uuid

from telebot import TeleBot, types as tp

from app.utils.db_manager import get_session
from app.database.repos import GameRepo, OptimisticLockError
from app.services.game_service import GameService
from app.utils.text_models import mention
from app.utils.announce import podium_lines
from app.utils.level_up_notify import send_level_up_notifications
from app.services.reward_service import apply_rewards_if_needed
from config import Settings

from app.workers.timers import (
    schedule_turn_timeout,
    cancel_turn_timeout,
    prepare_turn_timer,
)


class DrawCallbackHandler:
    def __init__(self, bot: TeleBot) -> None:
        self.bot = bot
        self.svc = GameService()

        @bot.callback_query_handler(
            func=lambda c: bool(c.data) and c.data.startswith("draw:")
        )
        def on_draw(call: tp.CallbackQuery) -> None:
            _, chat_id_s = call.data.split(":", 1)
            chat_id = int(chat_id_s)
            uid = call.from_user.id

            # після save
            restart_turn: tuple[int, str, int] | None = None
            kicked_events: list[dict] = []
            kicked_self: bool = False
            level_ups_to_notify: dict = {}
            game_state: dict = {}
            need_cancel_turn: bool = False

            with get_session() as s:
                repo = GameRepo(s)
                game = repo.get_by_chat(chat_id)
                if not game or game.status != "playing":
                    bot.answer_callback_query(
                        call.id, "Гра не активна.", show_alert=True
                    )
                    return

                for _ in range(3):
                    try:
                        state = game.state or {}

                        ok, msg = self.svc.draw_card_and_pass(state, uid=uid)
                        if not ok:
                            bot.answer_callback_query(call.id, msg, show_alert=True)
                            return

                        # якщо під час добору сталося авто-завершення (наприклад, кік залишив 1 гравця)
                        if str(state.get("status") or "").lower() == "finished":
                            t = state.setdefault("timers", {})
                            t["turn"] = {}
                            t["uno"] = {}
                            state["timers"] = t
                            need_cancel_turn = True
                            restart_turn = None

                            game.state = state
                            game.status = "finished"
                            game_state = game.state
                            kicked_events = self.svc.pop_kick_events(state)
                            level_ups_to_notify = apply_rewards_if_needed(s, state, Settings())
                            if level_ups_to_notify and not state.get("level_ups_notified"):
                                state["level_ups_notified"] = True
                            repo.save(
                                game,
                                expected_version=game.version,
                                state=game.state,
                                status=game.status,
                            )
                            break

                        seconds = 30

                        if msg == "KICKED":
                            # гравця кікнуло лімітом — хід переходить далі
                            kicked_self = True
                            cancel_turn_timeout(chat_id)
                            next_uid, token = prepare_turn_timer(self.svc, state, seconds=seconds)
                            restart_turn = (next_uid, token, seconds)
                        else:
                            # Це досі хід цього ж гравця => логічно “оновити” його turn timeout
                            token = uuid.uuid4().hex
                            state.setdefault("timers", {})["turn"] = {
                                "token": token,
                                "uid": int(uid),
                                "expires_at": time.time() + seconds,
                                "seconds": seconds,
                            }
                            restart_turn = (uid, token, seconds)

                        game.state = state
                        game_state = game.state
                        kicked_events = self.svc.pop_kick_events(state)
                        repo.save(game, expected_version=game.version, state=game.state)
                        break

                    except OptimisticLockError:
                        s.rollback()
                        game = repo.get_by_chat(chat_id)
                        if not game:
                            return

            if need_cancel_turn:
                cancel_turn_timeout(chat_id)

            if restart_turn is not None:
                u, tok, sec = restart_turn
                schedule_turn_timeout(chat_id, u, tok, seconds=sec)

            # повідомляємо про кік (після save)
            for ev in kicked_events:
                try:
                    ku = int(ev.get("uid") or 0)
                    cards = int(ev.get("cards") or 0)
                    meta = game_state.get("player_meta", {})  # best-effort
                    m = (meta or {}).get(str(ku), {}) if meta else {}
                    nm = m.get("name") or (("@" + m["username"]) if m.get("username") else str(ku)[-4:])
                    self.bot.send_message(
                        chat_id,
                        f"🚫 <a href=\"tg://user?id={ku}\">{nm}</a> вибув(ла) з гри: у руці стало <b>{cards}</b> карт (ліміт 25).",
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

            # якщо гра завершилась під час цього draw (наприклад, кік залишив 1 гравця) — повідомимо
            if str(game_state.get("status") or "").lower() == "finished":
                try:
                    bot.send_message(
                        chat_id,
                        "\n".join(podium_lines(game_state)),
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                except Exception:
                    pass

            if kicked_self:
                bot.answer_callback_query(call.id, "🚫 Тебе кікнуло: ліміт 25 карт.", show_alert=True)
            else:
                bot.answer_callback_query(
                    call.id, "➕ Взяв карту. Можеш зіграти.", show_alert=False
                )
