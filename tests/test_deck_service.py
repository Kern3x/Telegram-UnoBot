from __future__ import annotations

import unittest
from collections import Counter
from unittest.mock import patch

from app.domain.entities.card import Card, CardColor, CardKind
from app.services.deck_service import DeckService


class DeckServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = DeckService()

    def test_build_deck_has_standard_uno_composition(self) -> None:
        with patch("app.services.deck_service.random.shuffle"):
            deck = self.service.build_deck()

        self.assertEqual(len(deck), 108)

        kinds = Counter(card.kind for card in deck)
        self.assertEqual(kinds[CardKind.num], 76)
        self.assertEqual(kinds[CardKind.skip], 8)
        self.assertEqual(kinds[CardKind.rev], 8)
        self.assertEqual(kinds[CardKind.p2], 8)
        self.assertEqual(kinds[CardKind.wild], 4)
        self.assertEqual(kinds[CardKind.p4], 4)

        for color in (
            CardColor.red,
            CardColor.green,
            CardColor.blue,
            CardColor.yellow,
        ):
            colored_cards = [card for card in deck if card.color == color]
            self.assertEqual(len(colored_cards), 25)
            self.assertEqual(
                sum(card.kind == CardKind.num and card.value == 0 for card in deck),
                4,
            )

        wild_cards = [
            card
            for card in deck
            if card.kind in (CardKind.wild, CardKind.p4)
        ]
        self.assertTrue(all(card.color == CardColor.wild for card in wild_cards))

    def test_deal_distributes_cards_and_mutates_the_same_deck(self) -> None:
        deck = [
            Card(CardKind.num, value, CardColor.red)
            for value in range(6)
        ]

        hands, remaining = self.service.deal(deck, players=[10, 20], hand_size=2)

        self.assertIs(remaining, deck)
        self.assertEqual(len(remaining), 2)
        self.assertEqual(len(hands[10]), 2)
        self.assertEqual(len(hands[20]), 2)
        self.assertEqual(
            len(remaining) + sum(len(hand) for hand in hands.values()),
            6,
        )

    def test_draw_top_card_removes_last_card(self) -> None:
        first = Card(CardKind.num, 1, CardColor.red)
        top = Card(CardKind.skip, None, CardColor.blue)
        deck = [first, top]

        drawn, remaining = self.service.draw_top_card(deck)

        self.assertIs(drawn, top)
        self.assertIs(remaining, deck)
        self.assertEqual(remaining, [first])


if __name__ == "__main__":
    unittest.main()
