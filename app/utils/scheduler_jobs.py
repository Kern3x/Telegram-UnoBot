# scheduler_jobs.py
from __future__ import annotations
import time
import uuid

from apscheduler.schedulers.background import BackgroundScheduler

from app.utils.db_manager import get_session
from app.utils.loks import chat_lock
from app.database.repos import GameRepo, OptimisticLockError
from app.services import GameService
from config import Settings

scheduler = BackgroundScheduler()
svc = GameService()
settings = Settings()


def _set_timer(state: dict, key: str, seconds: int) -> str:
    token = uuid.uuid4().hex
    state.setdefault("timers", {})
    state["timers"][key] = {
        "token": token,
        "until": time.time() + seconds,
    }
    return token


def schedule_turn_timeout(chat_id: int, game_id: int) -> None:
    token = uuid.uuid4().hex
    with get_session() as s:
        repo = GameRepo(s)
        g = repo.get_by_chat(chat_id)
        if not g or g.status != "playing":
            return
        st = g.state or {}
        st.setdefault("timers", {})
        st["timers"]["turn"] = {
            "token": token,
            "until": time.time() + settings.TURN_SECONDS,
        }
        try:
            repo.save(g, g.version, state=st)
        except OptimisticLockError:
            return

    scheduler.add_job(
        turn_timeout_job,
        trigger="date",
        run_date=time.time() + settings.TURN_SECONDS,
        args=[chat_id, game_id, token],
        replace_existing=False,
        id=f"turn:{chat_id}:{token}",
    )


def schedule_uno_timeout(chat_id: int, game_id: int, player_id: int) -> None:
    token = uuid.uuid4().hex
    with get_session() as s:
        repo = GameRepo(s)
        g = repo.get_by_chat(chat_id)
        if not g or g.status != "playing":
            return
        st = g.state or {}
        st.setdefault("timers", {})
        st["timers"]["uno"] = {
            "token": token,
            "until": time.time() + settings.UNO_SECONDS,
            "player_id": int(player_id),
            "said": False,
        }
        try:
            repo.save(g, g.version, state=st)
        except OptimisticLockError:
            return

    scheduler.add_job(
        uno_timeout_job,
        trigger="date",
        run_date=time.time() + settings.UNO_SECONDS,
        args=[chat_id, game_id, token],
        replace_existing=False,
        id=f"uno:{chat_id}:{token}",
    )


def turn_timeout_job(chat_id: int, game_id: int, token: str) -> None:
    # ВАЖЛИВО: тут нема bot.send_message — це робимо в bot.py через callback-хук, або просто лог
    # Але щоб було простіше, я поверну "need_notify" в state, а бот це прочитає.
    with chat_lock(chat_id):
        with get_session() as s:
            repo = GameRepo(s)
            g = repo.get_by_chat(chat_id)
            if not g or g.status != "playing":
                return

            st = g.state or {}
            t = (st.get("timers") or {}).get("turn") or {}
            if t.get("token") != token:
                return  # вже інший таймер актуальний

            cur = svc.current_player_id(st)
            if cur is not None:
                svc.auto_draw(st, cur)
                svc.next_turn(st)

            # помітка для бот-повідомлення
            st["last_event"] = {
                "type": "turn_timeout",
                "prev_player": cur,
                "ts": time.time(),
            }

            try:
                repo.save(g, g.version, state=st)
            except OptimisticLockError:
                return


def uno_timeout_job(chat_id: int, game_id: int, token: str) -> None:
    with chat_lock(chat_id):
        with get_session() as s:
            repo = GameRepo(s)
            g = repo.get_by_chat(chat_id)
            if not g or g.status != "playing":
                return

            st = g.state or {}
            t = (st.get("timers") or {}).get("uno") or {}
            if t.get("token") != token:
                return

            if t.get("said"):
                return  # гравець встиг

            st["last_event"] = {
                "type": "uno_timeout",
                "player_id": t.get("player_id"),
                "ts": time.time(),
            }
            try:
                repo.save(g, g.version, state=st)
            except OptimisticLockError:
                return
