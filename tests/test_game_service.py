from __future__ import annotations

import unittest
from typing import Any

from app.services.game_service import GameService


def card(kind: str, color: str, value: int | None = None) -> dict[str, Any]:
    return {"kind": kind, "color": color, "value": value}


def game_state(
    *,
    players: list[int] | None = None,
    hands: dict[str, list[dict[str, Any]]] | None = None,
    deck: list[dict[str, Any]] | None = None,
    top_card: dict[str, Any] | None = None,
    current_color: str | None = None,
) -> dict[str, Any]:
    resolved_players = players or [1, 2, 3]
    return {
        "players": resolved_players,
        "status": "playing",
        "turn_idx": 0,
        "direction": 1,
        "top_card": top_card,
        "current_color": current_color,
        "deck": list(deck or []),
        "discard": [],
        "hands": hands
        or {str(uid): [card("num", "red", uid)] for uid in resolved_players},
        "timers": {},
        "pending_color": {"active": False, "resolved": True},
        "uno_pending": {"active": False, "resolved": True},
        "penalties": {},
        "turn_flags": {},
        "kicked": {},
        "placements": [],
        "finished_meta": {},
        "events": [],
    }


class GameServiceRuleTests(unittest.TestCase):
    def test_can_play_matches_color_value_kind_or_wild(self) -> None:
        top = card("num", "red", 5)

        self.assertTrue(GameService.can_play(card("skip", "red"), top, "red"))
        self.assertTrue(GameService.can_play(card("num", "blue", 5), top, "red"))
        self.assertTrue(GameService.can_play(card("wild", "wild"), top, "red"))
        self.assertFalse(GameService.can_play(card("num", "blue", 7), top, "red"))

        action_top = card("skip", "red")
        self.assertTrue(
            GameService.can_play(card("skip", "blue"), action_top, "yellow")
        )

    def test_skip_advances_over_next_player(self) -> None:
        state = game_state(
            hands={
                "1": [card("skip", "red"), card("num", "blue", 2)],
                "2": [card("num", "green", 3)],
                "3": [card("num", "yellow", 4)],
            },
            top_card=card("num", "red", 8),
            current_color="red",
        )

        played, result = GameService.play_card(state, uid=1, card_index=0)

        self.assertTrue(played)
        self.assertEqual(result, "OK")
        self.assertEqual(GameService.current_player_id(state), 3)
        self.assertEqual(state["top_card"]["kind"], "skip")
        self.assertTrue(state["uno_pending"]["active"])

    def test_reverse_changes_direction_and_moves_backwards(self) -> None:
        state = game_state(
            hands={
                "1": [card("rev", "red"), card("num", "blue", 2)],
                "2": [card("num", "green", 3)],
                "3": [card("num", "yellow", 4)],
            },
            top_card=card("num", "red", 8),
            current_color="red",
        )

        played, result = GameService.play_card(state, uid=1, card_index=0)

        self.assertTrue(played)
        self.assertEqual(result, "OK")
        self.assertEqual(state["direction"], -1)
        self.assertEqual(GameService.current_player_id(state), 3)

    def test_wild_draw_four_requires_owner_choice_and_draws_four(self) -> None:
        draw_cards = [card("num", "yellow", value) for value in range(6)]
        state = game_state(
            players=[1, 2],
            hands={
                "1": [card("p4", "wild"), card("num", "red", 2)],
                "2": [card("num", "green", 3)],
            },
            deck=draw_cards,
            top_card=card("num", "red", 8),
            current_color="red",
        )

        played, result = GameService.play_card(state, uid=1, card_index=0)
        self.assertTrue(played)
        self.assertEqual(result, "PENDING_COLOR")

        chosen, message = GameService.choose_color(state, uid=2, color="green")
        self.assertFalse(chosen)
        self.assertIn("гравець", message)

        chosen, result = GameService.choose_color(state, uid=1, color="green")
        self.assertTrue(chosen)
        self.assertEqual(result, "OK")
        self.assertEqual(state["current_color"], "green")
        self.assertEqual(len(state["hands"]["2"]), 5)
        self.assertEqual(len(state["deck"]), 2)
        self.assertEqual(GameService.current_player_id(state), 2)
        self.assertTrue(state["pending_color"]["resolved"])

    def test_group_dump_stacks_draw_two_cards(self) -> None:
        state = game_state(
            hands={
                "1": [
                    card("p2", "red"),
                    card("p2", "blue"),
                    card("num", "green", 7),
                ],
                "2": [card("num", "green", 3)],
                "3": [card("num", "yellow", 4)],
            },
            deck=[card("num", "yellow", value) for value in range(8)],
            top_card=card("num", "red", 8),
            current_color="red",
        )

        played, result = GameService.play_group_dump(state, uid=1, group="p2")

        self.assertTrue(played)
        self.assertEqual(result, "OK")
        self.assertEqual(len(state["discard"]), 2)
        self.assertEqual(len(state["hands"]["1"]), 1)
        self.assertEqual(len(state["hands"]["2"]), 5)
        self.assertEqual(GameService.current_player_id(state), 2)

    def test_draw_marks_turn_without_advancing_it(self) -> None:
        state = game_state(
            deck=[card("num", "blue", 9)],
            top_card=card("num", "red", 8),
            current_color="red",
        )

        drawn, result = GameService.draw_card_and_pass(state, uid=1)

        self.assertTrue(drawn)
        self.assertEqual(result, "OK")
        self.assertEqual(len(state["hands"]["1"]), 2)
        self.assertEqual(state["turn_flags"]["drew"]["uid"], 1)
        self.assertEqual(GameService.current_player_id(state), 1)

    def test_drawing_above_hand_limit_kicks_player_and_records_event(self) -> None:
        state = game_state(
            hands={
                "1": [card("num", "red", value % 10) for value in range(25)],
                "2": [card("num", "green", 3)],
                "3": [card("num", "yellow", 4)],
            },
            deck=[card("num", "blue", 9)],
        )

        GameService.draw_one(state, uid=1)

        self.assertTrue(GameService.is_kicked(state, 1))
        self.assertNotIn(1, state["players"])
        self.assertNotIn("1", state["hands"])
        self.assertEqual(state["placements"], [1])
        self.assertEqual(state["kicked"]["1"]["reason"], "hand_limit")

        events = GameService.pop_kick_events(state)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["uid"], 1)
        self.assertEqual(events[0]["cards"], 26)
        self.assertEqual(state["events"], [])


if __name__ == "__main__":
    unittest.main()
