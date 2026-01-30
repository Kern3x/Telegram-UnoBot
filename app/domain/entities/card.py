from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class CardColor(Enum):
    blue = "blue"
    green = "green"
    red = "red"
    yellow = "yellow"
    wild = "wild"


class CardKind(Enum):
    num = "num"
    skip = "skip"
    rev = "rev"
    p2 = "p2"
    wild = "wild"
    p4 = "p4"


@dataclass(frozen=True, slots=True)
class Card:
    kind: CardKind
    value: int | None
    color: CardColor

    def code(self) -> str:
        return f"{self.value}_{self.color.value}"
