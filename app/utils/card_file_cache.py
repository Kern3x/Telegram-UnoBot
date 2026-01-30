from __future__ import annotations

import json
from pathlib import Path
from functools import lru_cache

from telebot import TeleBot


CACHE_PATH = Path("app/card_sticker_file_ids.json")

_cache_mem: dict[str, str] | None = None


def load_cache() -> dict[str, str]:
    global _cache_mem
    if _cache_mem is not None:
        return _cache_mem
    if CACHE_PATH.exists():
        _cache_mem = json.loads(CACHE_PATH.read_text("utf-8"))
    else:
        _cache_mem = {}
    return _cache_mem


def save_cache(data: dict[str, str]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def ensure_sticker_set_cached(bot: TeleBot, set_name: str) -> dict[str, str]:
    """
    Cache file_id from a sticker set by position order matched to asset filenames.
    NOTE: Telegram does not expose original filenames, so order must match assets.
    """
    cache = load_cache()

    try:
        st_set = bot.get_sticker_set(set_name)
    except Exception:
        return cache

    stickers = list(getattr(st_set, "stickers", []) or [])
    if not stickers:
        return cache

    save_cache(cache)
    reset_reverse_cache()
    return cache


@lru_cache(maxsize=1)
def _reverse_cache() -> dict[str, str]:
    """
    sticker_file_id -> card_key
    """
    cache = load_cache()
    return {v: k for k, v in cache.items() if v}


def sticker_file_id_to_card_key(sticker_file_id: str) -> str | None:
    return _reverse_cache().get(sticker_file_id)


def reset_reverse_cache() -> None:
    _reverse_cache.cache_clear()
