from __future__ import annotations

import random
from app.domain.entities.card import Card, CardColor, CardKind

COLORS: tuple[CardColor, ...] = (
    CardColor.red,
    CardColor.green,
    CardColor.blue,
    CardColor.yellow,
)


class DeckService:
    def build_deck(self) -> list[Card]:
        deck: list[Card] = []

        for c in COLORS:
            deck.append(Card(kind=CardKind.num, value=0, color=c))

        for c in COLORS:
            for v in range(1, 10):
                deck.append(Card(kind=CardKind.num, value=v, color=c))
                deck.append(Card(kind=CardKind.num, value=v, color=c))

        for c in COLORS:
            for _ in range(2):
                deck.append(Card(kind=CardKind.skip, value=None, color=c))
                deck.append(Card(kind=CardKind.rev, value=None, color=c))
                deck.append(Card(kind=CardKind.p2, value=None, color=c))

        for _ in range(4):
            deck.append(Card(kind=CardKind.wild, value=None, color=CardColor.wild))
            deck.append(Card(kind=CardKind.p4, value=None, color=CardColor.wild))

        random.shuffle(deck)
        return deck

    def deal(
        self, deck: list[Card], players: list[int], hand_size: int = 7
    ) -> tuple[dict[int, list[Card]], list[Card]]:
        hands: dict[int, list[Card]] = {uid: [] for uid in players}

        for _ in range(hand_size):
            for uid in players:
                hands[uid].append(deck.pop())

        return hands, deck

    def draw_top_card(self, deck: list[Card]) -> tuple[Card, list[Card]]:
        return deck.pop(), deck
