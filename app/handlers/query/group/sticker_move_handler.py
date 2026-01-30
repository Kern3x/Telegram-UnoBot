from __future__ import annotations

from telebot import TeleBot, types as tp

from config import Settings
from app.database.repos import GameRepo, OptimisticLockError
from app.utils.db_manager import get_session
from app.utils.card_file_cache import sticker_file_id_to_card_key
from app.utils.text_models import mention
from app.services.game_service import GameService
from app.utils.keyboards import Keyboards
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
    clear_uno_timer,  # alias, або заміни на clear_uno_state
)


class StickerMoveHandler:
    def __init__(self, bot: TeleBot) -> None:
        self.bot = bot
        self.svc = GameService()
        self.kb = Keyboards()
        self.settings = Settings()

        @bot.message_handler(
            content_types=["sticker"], chat_types=["group", "supergroup"]
        )
        def on_sticker(message: tp.Message) -> None:
            chat_id = message.chat.id
            uid = message.from_user.id if message.from_user else 0
            if not uid or not message.sticker:
                return

            card_key = sticker_file_id_to_card_key(message.sticker.file_id)
            if not card_key:
                return

            # дії після save
            start_turn: tuple[int, str, int] | None = None
            start_uno: tuple[int, str, int] | None = None
            uno_prompt_text: str | None = None
            need_cancel_uno: bool = False
            need_cancel_turn: bool = False
            uno_job_uid_to_cancel: int | None = None
            pending_color_prompt: bool = False
            announce_state: dict | None = None
            kicked_events: list[dict] = []
            level_ups_to_notify: dict = {}

            with get_session() as s:
                repo = GameRepo(s)
                game = repo.get_by_chat(chat_id)
                suppress_announce_due_uno: bool = False

                if not game or game.status != "playing":
                    return

                for _ in range(3):
                    try:
                        state = game.state or {}

                        # кікнуті не можуть грати/реагувати
                        if self.svc.is_kicked(state, uid):
                            self._try_delete(chat_id, message.message_id)
                            return

                        players = state.get("players") or []
                        if uid not in players:
                            return

                        # тільки поточний гравець
                        if int(self.svc.current_player_id(state)) != int(uid):
                            self._try_delete(chat_id, message.message_id)
                            return

                        hand: list[dict] = (state.get("hands") or {}).get(
                            str(uid), []
                        ) or []
                        idx = self._find_card_index_by_key(hand, card_key)
                        if idx is None:
                            self._try_delete(chat_id, message.message_id)
                            return

                        ok, code = self.svc.play_card(state, uid=uid, card_index=idx)
                        if not ok:
                            try:
                                self.bot.reply_to(message, f"⛔ {code}")
                            except Exception:
                                pass
                            return

                        # -------- FINISH --------
                        if str(state.get("status") or "").lower() == "finished":
                            # на всяк: прибираємо таймери зі state, а job скасуємо після save
                            t = state.setdefault("timers", {})
                            uno_job_uid_to_cancel = int((t.get("uno") or {}).get("uid") or 0) or None
                            t["turn"] = {}
                            t["uno"] = {}
                            state["timers"] = t
                            # також гасимо UNO pending
                            try:
                                clear_uno_timer(state)
                            except Exception:
                                pass

                            need_cancel_turn = True
                            need_cancel_uno = True
                            start_turn = None
                            start_uno = None
                            pending_color_prompt = False

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

                        # -------- UNO timer prepare/clear (тільки в state, без schedule) --------
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
                            # закриваємо UNO pending + чистимо timers["uno"]
                            clear_uno_timer(state)
                            # і після save скасуємо job (на всяк)
                            need_cancel_uno = True

                        # -------- pending color --------
                        if code == "PENDING_COLOR":
                            cancel_turn_timeout(chat_id)
                            start_turn = None  # на всяк
                            announce_state = None  # ❗ НЕ оголошуємо завершення ходу

                            pending_color_msg = (
                                chat_id,
                                f"🎨 {mention(uid, 'Гравець')} обери колір:",
                            )
                            pending_color_prompt = True

                            game.state = state
                            kicked_events = self.svc.pop_kick_events(state)
                            repo.save(
                                game, expected_version=game.version, state=game.state
                            )

                            break

                        # -------- normal move: prepare next turn timer --------
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
                            return

            # -------- поза сесією: cancel/schedule + меседжі --------

            if need_cancel_turn:
                cancel_turn_timeout(chat_id)

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

            if need_cancel_uno:
                # скасовуємо job для UNO, якщо він був записаний у state
                if uno_job_uid_to_cancel:
                    cancel_uno_timeout(chat_id, int(uno_job_uid_to_cancel))
                else:
                    cancel_uno_timeout(chat_id, uid)

            if pending_color_prompt:
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
                # replace_existing=True у scheduler => старий turn job реально перезапишеться
                schedule_turn_timeout(chat_id, u, tok, seconds=sec)

            if announce_state is not None:
                announce_after_move(
                    self.bot,
                    self.kb,
                    chat_id,
                    uid,
                    announce_state,
                    self.svc,
                    self.settings,
                )

    @staticmethod
    def _find_card_index_by_key(hand: list[dict], card_key: str) -> int | None:
        for i, c in enumerate(hand):
            if StickerMoveHandler._dict_to_key(c) == card_key:
                return i
        return None

    @staticmethod
    def _dict_to_key(card: dict) -> str:
        kind = str(card.get("kind") or "").lower()
        val = card.get("value", None)
        col = str(card.get("color") or "").lower()

        if kind == "num":
            return f"num:{int(val)}:{col}"
        if kind in ("p2", "plus2"):
            return f"p2:{col}"
        if kind == "skip":
            return f"skip:{col}"
        if kind in ("rev", "reverse"):
            return f"rev:{col}"
        if kind == "wild":
            return "wild"
        if kind in ("p4", "plus4"):
            return "p4"
        return f"{kind}:{val}:{col}"

    def _try_delete(self, chat_id: int, message_id: int) -> None:
        try:
            self.bot.delete_message(chat_id, message_id)
        except Exception:
            pass
