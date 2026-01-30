from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Tuple

from telebot import TeleBot

from config import Settings
from app.utils.keyboards import Keyboards
from app.database.repos import GameRepo, OptimisticLockError
from app.services.game_service import GameService
from app.utils.db_manager import get_session
from app.workers.scheduler import get_scheduler
from app.utils.text_models import mention
from app.utils.announce import podium_lines
from app.services.reward_service import apply_rewards_if_needed
from app.utils.level_up_notify import send_level_up_notifications


_BOT: TeleBot | None = None


def set_bot(bot: TeleBot) -> None:
    global _BOT
    _BOT = bot


def _bot() -> TeleBot:
    if _BOT is None:
        raise RuntimeError("Timers BOT not set. Call app.workers.timers.set_bot(bot).")
    return _BOT


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _job_id_turn(chat_id: int) -> str:
    return f"uno_turn:{chat_id}"


def _job_id_uno(chat_id: int, uid: int) -> str:
    return f"uno_uno:{chat_id}:{uid}"


# -------------------- TURN TIMER --------------------


def prepare_turn_timer(
    svc: GameService, state: dict, seconds: int = 30
) -> Tuple[int, str]:
    """
    1) consume skip_next_turn chain
    2) write state["timers"]["turn"] = {token, uid, expires_at, seconds}
    return (uid, token)
    """
    while svc.consume_skip_if_marked(state):
        pass

    uid = int(svc.current_player_id(state))
    token = uuid.uuid4().hex

    state.setdefault("timers", {})["turn"] = {
        "token": token,
        "uid": uid,
        "expires_at": time.time() + seconds,
        "seconds": int(seconds),
    }
    return uid, token


def cancel_turn_timeout(chat_id: int) -> None:
    sch = get_scheduler()
    try:
        sch.remove_job(_job_id_turn(chat_id))
    except Exception:
        pass


def schedule_turn_timeout(
    chat_id: int, uid: int, token: str, seconds: int = 30
) -> None:
    sch = get_scheduler()
    sch.add_job(
        func=_turn_timeout_job,
        trigger="date",
        run_date=_utcnow() + timedelta(seconds=seconds),
        args=[chat_id, int(uid), token],
        id=_job_id_turn(chat_id),
        replace_existing=True,
    )


def _turn_timeout_job(chat_id: int, uid: int, token: str) -> None:
    svc = GameService()

    next_uid: int | None = None
    next_token: str | None = None
    seconds = 30
    game_state: dict = {}
    kicked_events: list[dict] = []
    level_ups_to_notify: dict = {}
    finished_game: bool = False

    with get_session() as s:
        repo = GameRepo(s)

        for _ in range(3):
            game = repo.get_by_chat(chat_id)
            if not game or game.status != "playing":
                cancel_turn_timeout(chat_id)
                return

            state = game.state or {}

            # якщо гра вже завершена у state (але game.status ще "playing") — синхронізуємо і виходимо
            if str(state.get("status") or "").lower() == "finished":
                t = state.setdefault("timers", {})
                t["turn"] = {}
                t["uno"] = {}
                state["timers"] = t
                try:
                    game.state = state
                    game.status = "finished"
                    game_state = game.state
                    level_ups_to_notify = apply_rewards_if_needed(s, state, Settings())
                    if level_ups_to_notify and not state.get("level_ups_notified"):
                        state["level_ups_notified"] = True
                    repo.save(
                        game,
                        expected_version=game.version,
                        state=game.state,
                        status=game.status,
                    )
                except OptimisticLockError:
                    s.rollback()
                    continue
                finished_game = True
                break
            turn_t = (state.get("timers") or {}).get("turn") or {}

            # не той таймер => хід вже оновився
            if turn_t.get("token") != token:
                return

            seconds = int(turn_t.get("seconds") or 30)

            # якщо вже не його хід — ігноруємо
            if int(svc.current_player_id(state)) != int(uid):
                return

            # якщо pending_color — не штрафуємо
            pc = state.get("pending_color") or {}
            if pc.get("active") and not pc.get("resolved"):
                return

            # штраф +2 і пропуск ходу (якщо це його хід)
            svc.apply_penalty_and_skip_if_possible(
                state, uid, reason="TURN_TIMEOUT", cards=2
            )

            # якщо когось кікнуло лімітом карт — зберігаємо події (і прибираємо з state, щоб не дублювати)
            kicked_events = svc.pop_kick_events(state)

            # якщо після штрафу/кіка гра завершилась (наприклад, залишився 1 гравець) — не плануємо наступний хід
            if str(state.get("status") or "").lower() == "finished":
                t = state.setdefault("timers", {})
                t["turn"] = {}
                t["uno"] = {}
                state["timers"] = t
                game.state = state
                game.status = "finished"
                game_state = game.state
                level_ups_to_notify = apply_rewards_if_needed(s, state, Settings())
                if level_ups_to_notify and not state.get("level_ups_notified"):
                    state["level_ups_notified"] = True
                repo.save(
                    game,
                    expected_version=game.version,
                    state=game.state,
                    status=game.status,
                )
                finished_game = True
                next_uid = None
                next_token = None
                break

            # підготовка наступного таймера (але не schedule тут)
            next_uid, next_token = prepare_turn_timer(svc, state, seconds=seconds)

            try:
                game.state = state
                game_state = game.state
                repo.save(game, expected_version=game.version, state=state)
                break
            except OptimisticLockError:
                s.rollback()
                continue
        else:
            return

    # schedule після save
    if next_uid is not None and next_token is not None:
        schedule_turn_timeout(chat_id, next_uid, next_token, seconds=seconds)

    name = (
        game_state.get("player_meta", {}).get(str(uid), {}).get("name") or str(uid)[-4:]
    )
    next_name = (
        game_state.get("player_meta", {}).get(str(next_uid), {}).get("name")
        or str(next_uid)[-4:]
        if next_uid is not None
        else "-"
    )

    # 1) спершу повідомляємо про кік (якщо було)
    for ev in kicked_events:
        ku = int(ev.get("uid") or 0)
        cards = int(ev.get("cards") or 0)
        km = game_state.get("player_meta", {}).get(str(ku), {})
        kn = km.get("name") or (
            ("@" + km["username"]) if km.get("username") else str(ku)[-4:]
        )
        _bot().send_message(
            chat_id,
            f"🚫 {mention(ku, kn)} вибув(ла) з гри: у руці стало <b>{cards}</b> карт (ліміт {svc.MAX_HAND}).",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    if finished_game:
        # finish and announce results
        cancel_turn_timeout(chat_id)
        try:
            _bot().send_message(
                chat_id,
                "\n".join(podium_lines(game_state)),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception:
            pass
        if level_ups_to_notify:
            send_level_up_notifications(_bot(), chat_id, level_ups_to_notify, game_state.get("player_meta", {}) or {})
        return

    # 2) стандартне повідомлення таймаута
    _bot().send_message(
        chat_id,
        f"⏳ Гравець {mention(uid, name)} не зробив хід за {seconds}с — штраф: +2 карти.\n"
        f"➡️ Тепер хід: {mention(next_uid, next_name)}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


# -------------------- UNO TIMER --------------------


def prepare_uno_timer(state: dict, uid: int, seconds: int = 10) -> str:
    token = uuid.uuid4().hex

    state.setdefault("timers", {})["uno"] = {
        "token": token,
        "uid": int(uid),
        "expires_at": time.time() + seconds,
        "seconds": int(seconds),
    }
    state["uno_pending"] = {
        "active": True,
        "resolved": False,
        "player_id": int(uid),
        "expires_at": time.time() + seconds,
        "said": False,
    }
    return token


def clear_uno_state(state: dict) -> None:
    state.setdefault("timers", {})["uno"] = {}
    up = state.get("uno_pending") or {}
    if up.get("active") and not up.get("resolved"):
        up["active"] = False
        up["resolved"] = True
        state["uno_pending"] = up


def cancel_uno_timeout(chat_id: int, uid: int) -> None:
    sch = get_scheduler()
    try:
        sch.remove_job(_job_id_uno(chat_id, uid))
    except Exception:
        pass


def schedule_uno_timeout(chat_id: int, uid: int, token: str, seconds: int = 10) -> None:
    sch = get_scheduler()
    sch.add_job(
        func=_uno_timeout_job,
        trigger="date",
        run_date=_utcnow() + timedelta(seconds=seconds),
        args=[chat_id, int(uid), token],
        id=_job_id_uno(chat_id, uid),
        replace_existing=True,
    )


def _uno_timeout_job(chat_id: int, uid: int, token: str) -> None:
    svc = GameService()

    next_uid: int | None = None
    next_token: str | None = None
    seconds = 10
    skipped_now = False
    kicked_events: list[dict] = []
    level_ups_to_notify: dict = {}
    finished_game: bool = False
    game_state: dict = {}

    with get_session() as s:
        repo = GameRepo(s)

        for _ in range(3):
            game = repo.get_by_chat(chat_id)
            if not game or game.status != "playing":
                cancel_uno_timeout(chat_id, uid)
                return

            state = game.state or {}

            # якщо гра вже завершена у state — синхронізуємо і виходимо
            if str(state.get("status") or "").lower() == "finished":
                t = state.setdefault("timers", {})
                t["turn"] = {}
                t["uno"] = {}
                state["timers"] = t
                try:
                    game.state = state
                    game.status = "finished"
                    game_state = game.state
                    level_ups_to_notify = apply_rewards_if_needed(s, state, Settings())
                    if level_ups_to_notify and not state.get("level_ups_notified"):
                        state["level_ups_notified"] = True
                    repo.save(
                        game,
                        expected_version=game.version,
                        state=game.state,
                        status=game.status,
                    )
                except OptimisticLockError:
                    s.rollback()
                    continue
                finished_game = True
                break
            uno_t = (state.get("timers") or {}).get("uno") or {}

            if uno_t.get("token") != token:
                return

            seconds = int(uno_t.get("seconds") or 10)

            up = state.get("uno_pending") or {}
            if not up.get("active") or up.get("resolved"):
                return

            if int(up.get("player_id", 0)) != int(uid):
                return

            if up.get("said"):
                clear_uno_state(state)
                try:
                    game.state = state
                    repo.save(game, expected_version=game.version, state=state)
                except OptimisticLockError:
                    s.rollback()
                return

            # не сказав UNO -> +2, і якщо це його хід — пропуск одразу
            skipped_now = svc.apply_penalty_and_skip_if_possible(
                state, uid, reason="UNO_TIMEOUT", cards=2
            )

            # могли кікнутися (ліміт карт)
            kicked_events = svc.pop_kick_events(state)

            clear_uno_state(state)

            # якщо після штрафу/кіка гра завершилась — не плануємо далі нічого
            if str(state.get("status") or "").lower() == "finished":
                t = state.setdefault("timers", {})
                t["turn"] = {}
                t["uno"] = {}
                state["timers"] = t
                game.state = state
                game.status = "finished"
                game_state = game.state
                level_ups_to_notify = apply_rewards_if_needed(s, state, Settings())
                if level_ups_to_notify and not state.get("level_ups_notified"):
                    state["level_ups_notified"] = True
                repo.save(
                    game,
                    expected_version=game.version,
                    state=game.state,
                    status=game.status,
                )
                finished_game = True
                next_uid = None
                next_token = None
                break

            if skipped_now:
                next_uid, next_token = prepare_turn_timer(svc, state, seconds=30)

            try:
                game.state = state
                game_state = game.state
                repo.save(game, expected_version=game.version, state=state)
                break
            except OptimisticLockError:
                s.rollback()
                continue
        else:
            return

    if next_uid is not None and next_token is not None:
        schedule_turn_timeout(chat_id, next_uid, next_token, seconds=30)

    if finished_game:
        # finish and announce results
        cancel_uno_timeout(chat_id, uid)
        cancel_turn_timeout(chat_id)
        try:
            _bot().send_message(
                chat_id,
                "\n".join(podium_lines(game_state)),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception:
            pass
        if level_ups_to_notify:
            send_level_up_notifications(_bot(), chat_id, level_ups_to_notify, game_state.get("player_meta", {}) or {})
        return

    if kicked_events:
        try:
            meta_now = game_state.get("player_meta", {}) or {}
            for ev in kicked_events:
                ku = int(ev.get("uid") or 0)
                cards = int(ev.get("cards") or 0)
                nm = meta_now.get(str(ku), {}).get("name") or str(ku)[-4:]
                _bot().send_message(
                    chat_id,
                    f"🚫 {mention(ku, nm)} вибув(ла) з гри — у руці стало <b>{cards}</b> карт (ліміт <b>{svc.MAX_HAND}</b>).",
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
        except Exception:
            pass

    # Хто ходить зараз? (зазвичай це НЕ uid, а поточний гравець після ходу)
    state_now = game_state
    cur_uid: int | None = None
    try:
        cur_uid = int(svc.current_player_id(state_now))
    except Exception:
        cur_uid = None

    meta = state_now.get("player_meta", {}) or {}
    name = meta.get(str(uid), {}).get("name") or str(uid)[-4:]
    cur_name = (
        meta.get(str(cur_uid), {}).get("name") or str(cur_uid)[-4:]
        if cur_uid is not None
        else "-"
    )

    extra = ", пропуск ходу" if skipped_now else ""

    # ---- повний статус столу ----
    settings = Settings()
    kb = Keyboards()

    top = state_now.get("top_card") or {}
    top_kind = str(top.get("kind") or "").lower()
    top_val = top.get("value")
    top_color_raw = str(top.get("color") or "").lower()

    # Верхня карта (людський вигляд)
    if top_kind == "num":
        top_pretty = str(top_val)
    else:
        # якщо у вас в settings.other_type_cards ключі "p2/p4/wild/skip/rev" — то ок
        top_pretty = settings.other_type_cards.get(top_kind, top_kind.upper())

    # Поточний колір: для wild/p4 беремо state["current_color"]
    color_key = None
    if top_kind in ("wild", "p4"):
        color_key = state_now.get("current_color")
    else:
        color_key = top_color_raw

    color_pretty = "-"
    try:
        if color_key:
            color_pretty = settings.colors.get(str(color_key), str(color_key))
    except Exception:
        color_pretty = str(color_key) if color_key else "-"

    # Хто ходить зараз
    turn_line = ""
    if cur_uid is not None:
        turn_line = f"➡️ <b>Тепер хід:</b> {mention(cur_uid, cur_name)}"

    _bot().send_message(
        chat_id,
        (
            f"⚠️ {mention(uid, name)} не сказав <b>UNO</b> за <b>{seconds}</b>с → <b>+2</b>{extra}.\n"
            f"🃏 <b>Верхня карта:</b> {top_pretty}\n"
            f"🎨 <b>Поточний колір:</b> {color_pretty}\n"
            f"{turn_line}\n\n"
        ),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=kb.game.get_cards_kb(chat_id),
    )


def clear_uno_timer(state: dict) -> None:
    # alias для старої назви
    clear_uno_state(state)
