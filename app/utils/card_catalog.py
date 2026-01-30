from __future__ import annotations

from pathlib import Path


class CardCatalog:
    def __init__(self, cards_dir: Path):
        self.cards_dir = cards_dir
        self._map: dict[str, Path] = {}
        self._load()

    def _load(self) -> None:
        if not self.cards_dir.exists():
            return
        for p in self.cards_dir.glob("*.png"):
            key = self.key_from_filename(p.name)
            if key:
                self._map[key] = p

    @staticmethod
    def key_from_filename(name: str) -> str | None:
        # Supports:
        #  - {digit}_{color}.png -> num:{digit}:{color}
        #  - plus2_{color}.png -> p2:{color}
        #  - plus4.png -> p4
        #  - wild.png -> wild
        #  - skip_{color}.png -> skip:{color}
        #  - reverse_{color}.png -> rev:{color}
        stem = name[:-4].lower()
        if "_" in stem:
            a, b = stem.split("_", 1)
            if a.isdigit():
                return f"num:{int(a)}:{b}"
            if a in ("plus2", "p2"):
                return f"p2:{b}"
            if a in ("skip",):
                return f"skip:{b}"
            if a in ("reverse", "rev"):
                return f"rev:{b}"
        if stem in ("wild",):
            return "wild"
        if stem in ("plus4", "p4"):
            return "p4"
        return None

    @staticmethod
    def card_key(card: dict) -> str:
        kind = str(card.get("kind") or "").lower()
        val = card.get("value", None)
        col = str(card.get("color") or "").lower()

        if kind == "num":
            return f"num:{int(val)}:{col}"
        if kind in ("p2", "plus2"):
            return f"p2:{col}"
        if kind in ("skip",):
            return f"skip:{col}"
        if kind in ("rev", "reverse"):
            return f"rev:{col}"
        if kind in ("wild",):
            return "wild"
        if kind in ("p4", "plus4"):
            return "p4"

        return f"{kind}:{val}:{col}"

    def get(self, key: str) -> Path:
        p = self._map.get(key)
        if not p:
            raise FileNotFoundError(
                f"Card asset not found for key={key}. Put png into {self.cards_dir}"
            )
        return p
