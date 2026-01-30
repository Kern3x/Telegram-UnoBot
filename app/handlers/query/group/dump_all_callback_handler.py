from __future__ import annotations

from telebot import TeleBot, types as tp

from config import Settings
from app.database.repos import GameRepo, OptimisticLockError
from app.utils.db_manager import get_session
from app.utils.text_models import mention
from app.utils.keyboards import Keyboards
from app.services.game_service import GameService
from app.utils.announce import announce_after_move
from app.utils.level_up_notify import send_level_up_notifications
from app.services.reward_service import apply_rewards_if_needed
from app.workers.timers import (
    prepare_turn_timer,
    schedule_turn_timeout,
    cancel_turn_timeout,
    prepare_uno_timer,
    schedule_uno_timeout,
    cancel_uno_timeout,
    clear_uno_timer,
)


class DumpAllCallbackHandler:
    def __init__(self, bot: TeleBot) -> None:
        self.bot = bot
        self.svc = GameService()
        self.kb = Keyboards()
        self.settings = Settings()

        @bot.callback_query_handler(
            func=lambda c: bool(c.data) and c.data.startswith("dump:")
        )
        def on_dump(call: tp.CallbackQuery) -> None:
            # dump:{chat_id}:{owner_uid}:{group}
            try:
                _, chat_id_s, owner_uid_s, group = call.data.split(":", 3)
                chat_id = int(chat_id_s)
                owner_uid = int(owner_uid_s)
            except Exception:
                self.bot.answer_callback_query(
                    call.id, "Некоректна кнопка.", show_alert=True
                )
                return

            uid = call.from_user.id

            # персонально
            if int(uid) != int(owner_uid):
                self.bot.answer_callback_query(
                    call.id, "Ця кнопка не для тебе 🙂", show_alert=True
                )
                return

            start_turn: tuple[int, str, int] | None = None
            start_uno: tuple[int, str, int] | None = None
            uno_prompt_text: str | None = None
            pending_color_msg: tuple[int, str] | None = None
            announce_state: dict | None = None
            kicked_events: list[dict] = []
            level_ups_to_notify: dict = {}
            need_cancel_turn: bool = False
            need_cancel_uno: bool = False
            uno_job_uid_to_cancel: int | None = None

            with get_session() as s:
                repo = GameRepo(s)
                game = repo.get_by_chat(chat_id)
                suppress_announce_due_uno: bool = False

                if not game or game.status != "playing":
                    self.bot.answer_callback_query(
                        call.id, "Гра не активна.", show_alert=True
                    )
                    return

                for _ in range(3):
                    try:
                        state = game.state or {}

                        # кікнуті не можуть грати
                        if self.svc.is_kicked(state, uid):
                            self.bot.answer_callback_query(
                                call.id,
                                "Ти вибув(ла) з цієї гри до завершення (ліміт карт).",
                                show_alert=True,
                            )
                            return

                        ok, code = self.svc.play_group_dump(state, uid=uid, group=group)
                        if not ok:
                            self.bot.answer_callback_query(
                                call.id, str(code), show_alert=True
                            )
                            return

                        # -------- FINISH --------
                        if str(state.get("status") or "").lower() == "finished":
                            t = state.setdefault("timers", {})
                            uno_job_uid_to_cancel = int((t.get("uno") or {}).get("uid") or 0) or None
                            t["turn"] = {}
                            t["uno"] = {}
                            state["timers"] = t
                            try:
                                clear_uno_timer(state)
                            except Exception:
                                pass

                            need_cancel_turn = True
                            need_cancel_uno = True
                            start_turn = None
                            start_uno = None

                            game.state = state
                            game.status = "finished"
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
                            announce_state = state
                            break

                        # UNO timer prepare/clear
                        hand_after = (state.get("hands") or {}).get(str(uid), []) or []
                        if len(hand_after) == 1:
                            suppress_announce_due_uno = True
                            uno_token = prepare_uno_timer(state, uid, seconds=10)
                            start_uno = (uid, uno_token, 10)
                            try:
                                meta = state.get("player_meta", {}) or {}
                                m = meta.get(str(uid), {}) or {}
                                nm = m.get("name") or (
                                    ("@" + m["username"]) if m.get("username") else str(uid)[-4:]
                                )
                                uno_prompt_text = (
                                    f"⚡ {mention(uid, nm)}: лишилась <b>1</b> карта! "
                                    f"Напиши <b>UNO</b> за <b>10</b>с, інакше +2."
                                )
                            except Exception:
                                uno_prompt_text = None
                        else:
                            clear_uno_timer(state)
                            cancel_uno_timeout(chat_id, uid)

                        if code == "PENDING_COLOR":
                            # ❗ не анонсимо тут, тільки клава вибору кольору
                            cancel_turn_timeout(chat_id)
                            pending_color_msg = (
                                chat_id,
                                f"🎨 {mention(uid, 'Гравець')} обери колір:",
                            )

                            game.state = state
                            kicked_events = self.svc.pop_kick_events(state)
                            repo.save(
                                game, expected_version=game.version, state=game.state
                            )
                            announce_state = None
                            break

                        # normal: next turn timer
                        cancel_turn_timeout(chat_id)
                        seconds = 30
                        next_uid, turn_token = prepare_turn_timer(
                            self.svc, state, seconds=seconds
                        )
                        start_turn = (next_uid, turn_token, seconds)

                        game.state = state
                        kicked_events = self.svc.pop_kick_events(state)
                        repo.save(game, expected_version=game.version, state=game.state)

                        announce_state = None if suppress_announce_due_uno else state
                        break

                    except OptimisticLockError:
                        s.rollback()
                        game = repo.get_by_chat(chat_id)
                        if not game:
                            self.bot.answer_callback_query(
                                call.id, "Гра зникла.", show_alert=True
                            )
                            return

            # після save
            bot.edit_message_text(
                inline_message_id=call.inline_message_id,
                text="✅ Карти скинуто."
            )
            self.bot.answer_callback_query(call.id, "✅ Скинуто")

            if need_cancel_turn:
                cancel_turn_timeout(chat_id)

            if need_cancel_uno:
                if uno_job_uid_to_cancel:
                    cancel_uno_timeout(chat_id, int(uno_job_uid_to_cancel))
                else:
                    cancel_uno_timeout(chat_id, uid)

            # повідомляємо про кік (після save)
            for ev in kicked_events:
                try:
                    ku = int(ev.get("uid") or 0)
                    cards = int(ev.get("cards") or 0)
                    meta = (announce_state or {}).get("player_meta", {}) if announce_state else {}
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
                    (announce_state or {}).get("player_meta", {}) or {},
                )

            if pending_color_msg is not None:
                try:
                    self.bot.send_message(
                        pending_color_msg[0],
                        pending_color_msg[1],
                        parse_mode="HTML",
                        reply_markup=self.kb.game.color_choice_kb(chat_id),
                    )
                except Exception:
                    pass

            if start_uno is not None:
                u, tok, sec = start_uno
                schedule_uno_timeout(chat_id, u, tok, seconds=sec)

                if uno_prompt_text:
                    try:
                        self.bot.send_message(
                            chat_id,
                            uno_prompt_text,
                            parse_mode="HTML",
                            disable_web_page_preview=True,
                        )
                    except Exception:
                        pass

            if start_turn is not None:
                u, tok, sec = start_turn
                schedule_turn_timeout(chat_id, u, tok, seconds=sec)

            if announce_state is not None:
                announce_after_move(
                    self.bot, self.kb, chat_id, uid, announce_state, self.svc, self.settings
                )
