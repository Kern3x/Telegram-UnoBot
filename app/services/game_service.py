from __future__ import annotations

from enum import Enum
from typing import Any
import time

from app.services.deck_service import DeckService
from config import Settings


class GameService:
    TURN_PENALTY_CARDS = 2
    UNO_PENALTY_CARDS = 2
    MAX_HAND = 25

    def __init__(self) -> None:
        self.deck = DeckService()

    @staticmethod
    def _jsonable(v: Any) -> Any:
        if isinstance(v, Enum):
            return v.value
        return v

    @classmethod
    def card_to_dict(cls, c) -> dict[str, Any]:
        return {
            "kind": cls._jsonable(getattr(c, "kind", None)),
            "value": cls._jsonable(getattr(c, "value", None)),
            "color": cls._jsonable(getattr(c, "color", None)),
        }

    def start_game_state(self, player_ids: list[int]) -> dict[str, Any]:
        deck = self.deck.build_deck()
        hands_by_uid, deck = self.deck.deal(deck, players=player_ids, hand_size=7)

        hands: dict[str, list[dict[str, Any]]] = {}
        for uid in player_ids:
            hands[str(uid)] = [
                self.card_to_dict(c) for c in (hands_by_uid.get(uid) or [])
            ]

        return {
            "players": player_ids,
            "status": "playing",
            "turn_idx": 0,
            "direction": 1,
            "top_card": None,
            "current_color": None,
            "deck": [self.card_to_dict(c) for c in deck],
            "discard": [],
            "hands": hands,
            "timers": {},
            "pending_color": {"active": False, "resolved": True},
            "uno_pending": {"active": False, "resolved": True},
            "penalties": {},
            "turn_flags": {},
            "kicked": {},
            "placements": [],
            "finished_meta": {},
            "rewards_applied": False,
            "level_ups": {},
            "level_ups_notified": False,
            "events": [],
        }

    # -------------------- helpers --------------------

    @classmethod
    def current_player_id(cls, state: dict[str, Any]) -> int:
        """Return current active player id.

        If turn_idx currently points at a kicked player, normalize turn_idx to the
        next active player (in current direction).
        """
        players = state.get("players") or []
        if not players:
            raise ValueError("No players")

        idx0 = int(state.get("turn_idx", 0) or 0) % len(players)
        direction = int(state.get("direction", 1) or 1)
        idx = cls._find_next_active_index(state, start_idx=idx0, direction=direction)
        if idx is None:
            raise ValueError("No active players")
        if idx != idx0:
            state["turn_idx"] = idx
        return int(players[idx])

    @staticmethod
    def _has_pending_color(state: dict[str, Any]) -> bool:
        pc = state.get("pending_color")
        return bool(pc and pc.get("active") and not pc.get("resolved"))

    @staticmethod
    def _set_pending_color(state: dict[str, Any], uid: int, kind: str) -> None:
        state["pending_color"] = {
            "active": True,
            "resolved": False,
            "player_id": int(uid),
            "kind": kind,  # "wild" | "p4"
        }

    @staticmethod
    def _clear_pending_color(state: dict[str, Any]) -> None:
        pc = state.get("pending_color") or {}
        pc["active"] = False
        pc["resolved"] = True
        state["pending_color"] = pc

    @classmethod
    def _next_player_id(cls, state: dict[str, Any]) -> int:
        players = state.get("players") or []
        if not players:
            raise ValueError("No players")
        idx0 = int(state.get("turn_idx", 0) or 0) % len(players)
        direction = int(state.get("direction", 1) or 1)
        idx = cls._find_next_active_index(state, start_idx=(idx0 + direction) % len(players), direction=direction)
        if idx is None:
            raise ValueError("No active players")
        return int(players[idx])

    @classmethod
    def _advance_turn(cls, state: dict[str, Any], steps: int = 1) -> None:
        players = state.get("players") or []
        if not players:
            return

        direction = int(state.get("direction", 1) or 1)
        # advance by "active" steps
        for _ in range(max(1, int(steps))):
            idx0 = int(state.get("turn_idx", 0) or 0) % len(players)
            idx = cls._find_next_active_index(
                state,
                start_idx=(idx0 + direction) % len(players),
                direction=direction,
            )
            if idx is None:
                return
            state["turn_idx"] = idx

    @classmethod
    def draw_one(cls, state: dict[str, Any], uid: int) -> None:
        # kicked player can no longer receive cards
        if cls.is_kicked(state, uid):
            return
        deck = state.get("deck") or []
        if not deck:
            return
        card = deck.pop()
        state.setdefault("hands", {}).setdefault(str(uid), []).append(card)
        cls.enforce_hand_limit(state, uid)

    # -------------------- kicked / limits --------------------

    @staticmethod
    def now_ts() -> float:
        return time.time()

    @classmethod
    def is_kicked(cls, state: dict, uid: int) -> bool:
        return str(uid) in (state.get("kicked") or {})

    @classmethod
    def active_players(cls, state: dict) -> list[int]:
        players = state.get("players") or []
        kicked = state.get("kicked") or {}
        return [int(uid) for uid in players if str(uid) not in kicked]

    @classmethod
    def hand_size(cls, state: dict, uid: int) -> int:
        hands = state.get("hands") or {}
        return len(hands.get(str(uid), []) or [])

    @classmethod
    def _find_next_active_index(
        cls, state: dict, start_idx: int, direction: int
    ) -> int | None:
        players = state.get("players") or []
        if not players:
            return None
        kicked = state.get("kicked") or {}
        n = len(players)
        idx = int(start_idx) % n
        step = 1 if int(direction) >= 0 else -1

        for _ in range(n):
            uid = players[idx]
            if str(uid) not in kicked:
                return idx
            idx = (idx + step) % n
        return None

    @classmethod
    def _normalize_turn_idx(cls, state: dict) -> None:
        """If turn_idx points to kicked user, shift to next active."""
        players = state.get("players") or []
        if not players:
            return
        idx0 = int(state.get("turn_idx", 0) or 0) % len(players)
        direction = int(state.get("direction", 1) or 1)
        idx = cls._find_next_active_index(state, start_idx=idx0, direction=direction)
        if idx is not None:
            state["turn_idx"] = idx

    @classmethod
    def clear_uno_for_uid(cls, state: dict, uid: int) -> None:
        up = state.get("uno_pending") or {}
        if up.get("active") and not up.get("resolved") and int(up.get("player_id", 0)) == int(uid):
            up["active"] = False
            up["resolved"] = True
            state["uno_pending"] = up
            state.setdefault("timers", {})["uno"] = {}

    @classmethod
    def _record_kick_event(cls, state: dict, uid: int, cards: int) -> None:
        ev = {
            "type": "KICK",
            "uid": int(uid),
            "cards": int(cards),
            "ts": cls.now_ts(),
        }
        state.setdefault("events", []).append(ev)

    @classmethod
    def pop_kick_events(cls, state: dict) -> list[dict]:
        events = state.get("events") or []
        kicks = [e for e in events if e.get("type") == "KICK"]
        if kicks:
            state["events"] = [e for e in events if e.get("type") != "KICK"]
        return kicks

    @classmethod
    def kick_player(cls, state: dict, uid: int, reason: str, *, cards_at_kick: int | None = None) -> None:
        kicked = state.get("kicked") or {}
        if str(uid) in kicked:
            state["kicked"] = kicked
            return

        if cards_at_kick is None:
            cards_at_kick = cls.hand_size(state, uid)

        # Remove player from the active rotation (players/hands) immediately.
        # We still keep them in state["kicked"] so they cannot re-join until game end.
        players = state.get("players") or []
        old_n = len(players)
        idx_kick = None
        try:
            idx_kick = players.index(int(uid))
        except ValueError:
            idx_kick = None

        # Drop hand so they no longer appear with card count / can open hand.
        hands = state.get("hands") or {}
        hands.pop(str(uid), None)
        state["hands"] = hands

        # Also drop any per-player flags/penalties for cleanliness.
        (state.get("penalties") or {}).pop(str(uid), None)
        (state.get("turn_flags") or {}).pop(str(uid), None)

        if idx_kick is not None:
            # Adjust turn_idx to keep the same "next" player semantics.
            # If current turn was after removed index -> shift left by 1.
            cur_idx = int(state.get("turn_idx", 0) or 0)
            if old_n > 0:
                cur_idx = cur_idx % old_n

            # Remove from players.
            players = [p for p in players if int(p) != int(uid)]
            state["players"] = players

            if players:
                if idx_kick < cur_idx:
                    cur_idx -= 1
                # if idx_kick == cur_idx -> keep cur_idx as-is (it now points to next player)
                state["turn_idx"] = cur_idx % len(players)
            else:
                state["turn_idx"] = 0

        kicked[str(uid)] = {
            "reason": reason,
            "cards": int(cards_at_kick),
            "ts": cls.now_ts(),
        }
        state["kicked"] = kicked

        # cleanup UNO if needed
        cls.clear_uno_for_uid(state, uid)

        # If pending_color belonged to the kicked player (rare), clear it so the game cannot get stuck.
        pc = state.get("pending_color") or {}
        if pc.get("active") and not pc.get("resolved") and int(pc.get("player_id", 0) or 0) == int(uid):
            cls._clear_pending_color(state)

        cls.finish_player(state, uid, reason=reason)
        cls._maybe_finish_game(state)

    @classmethod
    def enforce_hand_limit(cls, state: dict, uid: int) -> bool:
        """Return True if player was newly kicked due to hand limit."""
        if cls.is_kicked(state, uid):
            return False
        cards_now = cls.hand_size(state, uid)
        if cards_now > int(cls.MAX_HAND):
            # record BEFORE we remove them from players/hands
            cls._record_kick_event(state, uid, cards=cards_now)
            cls.kick_player(state, uid, reason="hand_limit", cards_at_kick=cards_now)
            return True
        return False

    @classmethod
    def finish_player(cls, state: dict, uid: int, reason: str) -> None:
        placements = state.setdefault("placements", [])
        if int(uid) not in placements:
            placements.append(int(uid))
            state["placements"] = placements

        players = state.get("players") or []
        if int(uid) in players:
            old_n = len(players)
            idx_finish = players.index(int(uid))
            cur_idx = int(state.get("turn_idx", 0) or 0)
            if old_n > 0:
                cur_idx = cur_idx % old_n

            players = [p for p in players if int(p) != int(uid)]
            state["players"] = players

            if players:
                if idx_finish < cur_idx:
                    cur_idx -= 1
                state["turn_idx"] = cur_idx % len(players)
            else:
                state["turn_idx"] = 0

        hands = state.get("hands") or {}
        hands.pop(str(uid), None)
        state["hands"] = hands

        state.setdefault("finished_meta", {})[str(uid)] = {"reason": reason}

    @classmethod
    def _maybe_finish_game(cls, state: dict) -> None:
        players = state.get("players") or []
        if len(players) <= 1:
            if players:
                cls.finish_player(state, int(players[0]), reason="last_player")
            state["status"] = "finished"

    # -------------------- rules --------------------

    @staticmethod
    def can_play(
        card: dict[str, Any], top: dict[str, Any] | None, current_color: str | None
    ) -> bool:
        if not top:
            return True

        kind = card.get("kind")
        top_kind = top.get("kind")

        if kind in ("wild", "p4"):
            return True

        if current_color and card.get("color") == current_color:
            return True

        if kind == "num" and top_kind == "num":
            return card.get("value") == top.get("value")

        if kind in ("skip", "rev", "p2") and top_kind == kind:
            return True

        return False

    # -------------------- main: play_card --------------------

    @classmethod
    def play_card(
        cls, state: dict[str, Any], uid: int, card_index: int
    ) -> tuple[bool, str]:
        if cls.is_kicked(state, uid):
            return False, "Ти вибув(ла) з цієї гри до завершення (ліміт карт)."

        if cls._has_pending_color(state):
            pc = state.get("pending_color") or {}
            if int(pc.get("player_id", 0)) == int(uid):
                return False, "Спочатку обери колір для Wild/+4."
            return False, "Очікуємо вибір кольору іншим гравцем."

        if cls.current_player_id(state) != uid:
            return False, "Зараз не твій хід."

        hands = state.get("hands") or {}
        hand = hands.get(str(uid)) or []
        if card_index < 0 or card_index >= len(hand):
            return False, "Карта не знайдена."

        card = hand[card_index]
        top = state.get("top_card")
        current_color = state.get("current_color")

        if not cls.can_play(card, top, current_color):
            return False, "Цю карту не можна зіграти."

        kind = card.get("kind")

        # зіграли карту
        hand.pop(card_index)
        state.setdefault("discard", []).append(card)
        state["top_card"] = card

        if kind not in ("wild", "p4"):
            state["current_color"] = card.get("color")

        # перемога
        if len(hand) == 0:
            cls.finish_player(state, uid, reason="empty_hand")
            cls._clear_pending_color(state)
            cls._maybe_finish_game(state)
            return True, "WIN"

        # UNO pending (можеш лишити, а таймери вже піднімеш у хендлері)
        if len(hand) == 1:
            state["uno_pending"] = {
                "active": True,
                "resolved": False,
                "player_id": int(uid),
                "expires_at": time.time() + 10,
                "said": False,
            }
        else:
            up = state.get("uno_pending") or {}
            if up.get("active") and not up.get("resolved"):
                up["active"] = False
                up["resolved"] = True
                state["uno_pending"] = up

        # спец-логіка
        if kind in ("wild", "p4"):
            cls._set_pending_color(state, uid=uid, kind=kind)
            return True, "PENDING_COLOR"

        if kind == "skip":
            cls._advance_turn(state, steps=2)
            return True, "OK"

        if kind == "rev":
            state["direction"] = -int(state.get("direction", 1) or 1)
            if len(state.get("players") or []) == 2:
                cls._advance_turn(state, steps=2)
            else:
                cls._advance_turn(state, steps=1)
            return True, "OK"

        if kind == "p2":
            victim = cls._next_player_id(state)
            plus2 = getattr(Settings(), "PLUS2_CARDS", 2)
            for _ in range(int(plus2)):
                cls.draw_one(state, uid=victim)

            # ✅ ПІСЛЯ +2 хід має бути у victim, а не пропускати його.
            cls._advance_turn(state, steps=1)
            return True, "OK"

        cls._advance_turn(state, steps=1)
        return True, "OK"

    # -------------------- choose_color --------------------

    @classmethod
    def choose_color(cls, state: dict[str, Any], uid: int, color: str) -> tuple[bool, str]:
        if cls.is_kicked(state, uid):
            return False, "Ти вибув(ла) з цієї гри до завершення (ліміт карт)."

        pc = state.get("pending_color") or {}
        if not pc.get("active") or pc.get("resolved"):
            return False, "Немає активного вибору кольору."

        if int(pc.get("player_id", 0)) != int(uid):
            return False, "Колір має обрати гравець, який зіграв Wild/+4."

        state["current_color"] = color
        kind = pc.get("kind")
        stack = int(pc.get("stack") or 1)
        cls._clear_pending_color(state)

        if kind == "p4":
            victim = cls._next_player_id(state)
            plus4 = int(getattr(Settings(), "PLUS4_CARDS", 4))

            for _ in range(stack * plus4):
                cls.draw_one(state, uid=victim)

            # ✅ victim ходить (НЕ пропускає)
            cls._advance_turn(state, steps=1)
            return True, "OK"

        # wild: просто передаємо хід наступному
        cls._advance_turn(state, steps=1)
        return True, "OK"


    # -------------------- draw --------------------

    @classmethod
    def draw_card_and_pass(cls, state: dict, uid: int) -> tuple[bool, str]:
        if cls._has_pending_color(state):
            return False, "Очікуємо вибір кольору."

        if cls.is_kicked(state, uid):
            return False, "Ти вибув(ла) з цієї гри до завершення (ліміт карт)."

        if cls.current_player_id(state) != uid:
            return False, "Зараз не твій хід."

        cls.draw_one(state, uid=uid)

        # якщо після добору гравця кікнуло (25+ карт) — його хід закінчився
        if cls.is_kicked(state, uid):
            cls._advance_turn(state, steps=1)
            return True, "KICKED"
        state.setdefault("turn_flags", {})["drew"] = {
            "uid": int(uid),
            "ts": time.time(),
        }
        return True, "OK"

    # -------------------- penalties / skips --------------------

    def apply_penalty(self, state: dict, uid: int, reason: str, cards: int = 2) -> None:
        for _ in range(cards):
            self.draw_one(state, uid)
        state.setdefault("last_penalty", {})[str(uid)] = {
            "reason": reason,
            "ts": time.time(),
        }

    def apply_penalty_and_skip_if_possible(
        self, state: dict, uid: int, reason: str, cards: int = 2
    ) -> bool:
        self.apply_penalty(state, uid, reason, cards=cards)

        # якщо кікнуло під час штрафу — не ставимо skip_next_turn, просто не даємо ходити
        if self.is_kicked(state, uid):
            if int(self.current_player_id(state)) == int(uid):
                self._advance_turn(state, steps=1)
                return True
            return False

        if int(self.current_player_id(state)) == int(uid):
            self._advance_turn(state, steps=1)
            return True

        pen = state.setdefault("penalties", {}).setdefault(str(uid), {})
        pen["skip_next_turn"] = True
        state["penalties"][str(uid)] = pen
        return False

    def consume_skip_if_marked(self, state: dict) -> bool:
        uid = self.current_player_id(state)
        pen = (state.get("penalties") or {}).get(str(uid)) or {}
        if pen.get("skip_next_turn"):
            pen["skip_next_turn"] = False
            state.setdefault("penalties", {})[str(uid)] = pen
            self._advance_turn(state, steps=1)
            return True
        return False

    @staticmethod
    def group_key(card: dict[str, Any]) -> str:
        kind = str(card.get("kind") or "").lower()
        if kind == "num":
            return f"num:{int(card.get('value') or 0)}"  # ✅ група по значенню
        if kind in ("skip", "rev", "p2", "wild", "p4"):
            return kind
        # fallback
        return kind

    @classmethod
    def play_group_dump(cls, state: dict[str, Any], uid: int, group: str) -> tuple[bool, str]:
        if cls.is_kicked(state, uid):
            return False, "Ти вибув(ла) з цієї гри до завершення (ліміт карт)."

        # pending_color блокує будь-що
        if cls._has_pending_color(state):
            pc = state.get("pending_color") or {}
            if int(pc.get("player_id", 0)) == int(uid):
                return False, "Спочатку обери колір для Wild/+4."
            return False, "Очікуємо вибір кольору іншим гравцем."

        if cls.current_player_id(state) != uid:
            return False, "Зараз не твій хід."

        hands = state.get("hands") or {}
        hand: list[dict[str, Any]] = hands.get(str(uid)) or []
        if not hand:
            return False, "В тебе немає карт."

        idxs = [i for i, c in enumerate(hand) if cls.group_key(c) == group]
        if len(idxs) < 2:
            return False, "Немає 2+ карт цього типу."

        # Перша карта має бути зіграбельна
        first_card = hand[idxs[0]]
        top = state.get("top_card")
        current_color = state.get("current_color")
        if not cls.can_play(first_card, top, current_color):
            return False, "Першу з цих карт зараз не можна зіграти."

        # Скидаємо всі карти групи
        to_play = [hand[i] for i in idxs]
        for i in sorted(idxs, reverse=True):
            hand.pop(i)

        state.setdefault("discard", []).extend(to_play)
        last = to_play[-1]
        kind = str(last.get("kind") or "").lower()
        state["top_card"] = last

        if kind not in ("wild", "p4"):
            state["current_color"] = last.get("color")

        # win?
        if len(hand) == 0:
            cls.finish_player(state, uid, reason="empty_hand")
            cls._clear_pending_color(state)
            cls._maybe_finish_game(state)
            return True, "WIN"

        # UNO pending
        if len(hand) == 1:
            state["uno_pending"] = {
                "active": True,
                "resolved": False,
                "player_id": int(uid),
                "expires_at": time.time() + 10,
                "said": False,
            }
        else:
            up = state.get("uno_pending") or {}
            if up.get("active") and not up.get("resolved"):
                up["active"] = False
                up["resolved"] = True
                state["uno_pending"] = up

        n = len(to_play)

        # ---- ефекти ----
        if kind in ("wild", "p4"):
            state["pending_color"] = {
                "active": True,
                "resolved": False,
                "player_id": int(uid),
                "kind": kind,      # wild | p4
                "stack": int(n),   # ✅ для p4: скільки карт p4 скинули
            }
            return True, "PENDING_COLOR"

        if kind == "skip":
            cls._advance_turn(state, steps=2)
            return True, "OK"

        if kind == "rev":
            if n % 2 == 1:
                state["direction"] = -int(state.get("direction", 1) or 1)

            if len(state.get("players") or []) == 2:
                cls._advance_turn(state, steps=2)
            else:
                cls._advance_turn(state, steps=1)
            return True, "OK"

        if kind == "p2":
            victim = cls._next_player_id(state)
            plus2 = int(getattr(Settings(), "PLUS2_CARDS", 2))
            for _ in range(n * plus2):
                cls.draw_one(state, uid=victim)

            # ✅ victim ходить (НЕ пропускає)
            cls._advance_turn(state, steps=1)
            return True, "OK"

        # num група
        cls._advance_turn(state, steps=1)
        return True, "OK"
