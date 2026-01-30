from __future__ import annotations

import time

from telebot import TeleBot, types as tp

from config import Settings
from app.utils.keyboards import Keyboards
from app.utils.db_manager import get_session
from app.database.repos import GameRepo, OptimisticLockError
from app.workers.timers import cancel_uno_timeout
from app.utils.text_models import mention
from app.services.game_service import GameService

UNO_WORDS = {"uno", "уно", "uno!", "уно!"}


class UnoWordHandler:
    def __init__(self, bot: TeleBot) -> None:
        self.bot = bot
        self.svc = GameService()
        self.kb = Keyboards()
        self.settings = Settings()

        @bot.message_handler(
            func=lambda m: bool(m.text) and m.text.strip().lower() in UNO_WORDS,
            chat_types=["group", "supergroup"],
        )
        def on_uno_word(message: tp.Message) -> None:
            chat_id = message.chat.id
            uid = message.from_user.id if message.from_user else 0
            if not uid:
                return

            need_cancel = False
            state_after: dict | None = None

            with get_session() as s:
                repo = GameRepo(s)
                game = repo.get_by_chat(chat_id)
                if not game or game.status != "playing":
                    return

                for _ in range(3):
                    try:
                        state = game.state or {}

                        # кікнуті не можуть реагувати
                        if self.svc.is_kicked(state, uid):
                            return
                        up = state.get("uno_pending") or {}
                        if not up.get("active") or up.get("resolved"):
                            return
                        if int(up.get("player_id", 0)) != int(uid):
                            return
                        if time.time() > float(up.get("expires_at", 0)):
                            return

                        # ✅ одразу резолвимо pending
                        up["said"] = True
                        up["active"] = False
                        up["resolved"] = True
                        state["uno_pending"] = up

                        # ✅ чистимо uno timer у state
                        state.setdefault("timers", {})["uno"] = {}

                        game.state = state
                        repo.save(game, expected_version=game.version, state=game.state)

                        state_after = state
                        need_cancel = True
                        break

                    except OptimisticLockError:
                        s.rollback()
                        game = repo.get_by_chat(chat_id)
                        if not game:
                            return
            if need_cancel:
                cancel_uno_timeout(chat_id, uid)
                try:
                    u = message.from_user
                    name = (u.first_name if u and u.first_name else None) or (
                        ("@" + u.username) if u and u.username else str(uid)[-4:]
                    )
                    self.bot.send_message(
                        chat_id,
                        f"✅ {mention(uid, name)} сказав <b>UNO</b>!",
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                except Exception:
                    pass

            # ✅ після UNO — показуємо повний стан столу (верхня карта/колір/хід/карти)
            if state_after:
                try:
                    if str(state_after.get("status") or "").lower() == "finished":
                        return

                    top = state_after.get("top_card") or {}
                    cur_color = state_after.get("current_color")  # важливо для wild/p4
                    meta = state_after.get("player_meta", {}) or {}

                    cur_uid = int(self.svc.current_player_id(state_after))
                    mcur = meta.get(str(cur_uid), {}) or {}
                    cur_name = mcur.get("name") or (("@" + mcur["username"]) if mcur.get("username") else str(cur_uid)[-4:])

                    # --- верхня карта (людський вигляд) ---
                    kind = str(top.get("kind") or "")
                    val = top.get("value")
                    top_color_raw = str(top.get("color") or "")

                    # назва типу
                    kind_pretty = self.settings.other_type_cards.get(kind, kind)
                    # для цифр — показуємо значення
                    if kind == "num":
                        kind_pretty = str(val)

                    # колір: для wild/p4 беремо current_color
                    color_key = cur_color if kind in ("wild", "p4") else top_color_raw
                    color_pretty = self.settings.colors.get(color_key, color_key)

                    self.bot.send_message(
                        chat_id,
                        (
                            f"🃏 <b>Верхня карта:</b> {kind_pretty}\n"
                            f"🎨 <b>Поточний колір:</b> {color_pretty}\n"
                            f"➡️ <b>Далі хід:</b> {mention(cur_uid, cur_name)}"
                        ),
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                        reply_markup=self.kb.game.get_cards_kb(chat_id),
                    )
                except Exception:
                    pass
