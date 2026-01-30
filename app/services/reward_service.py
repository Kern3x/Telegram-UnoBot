from __future__ import annotations

from math import ceil
from random import randint
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


def _rand_range(rng: tuple[int, int]) -> int:
    lo, hi = int(rng[0]), int(rng[1])
    if lo > hi:
        lo, hi = hi, lo
    return randint(lo, hi)


def apply_rewards(
    session: Session,
    placements: Iterable[int],
    *,
    top1: tuple[int, int],
    top2: tuple[int, int],
    top3: tuple[int, int],
    min_reward: tuple[int, int],
    top1_xp: tuple[int, int],
    top2_xp: tuple[int, int],
    top3_xp: tuple[int, int],
    min_xp: tuple[int, int],
) -> tuple[dict[int, dict], dict[int, dict]]:
    level_ups: dict[int, dict] = {}
    rewards: dict[int, dict] = {}
    for idx, uid in enumerate(placements):
        uid = int(uid)
        if idx == 0:
            coins = _rand_range(top1)
            xp = _rand_range(top1_xp)
        elif idx == 1:
            coins = _rand_range(top2)
            xp = _rand_range(top2_xp)
        elif idx == 2:
            coins = _rand_range(top3)
            xp = _rand_range(top3_xp)
        else:
            coins = _rand_range(min_reward)
            xp = _rand_range(min_xp)

        user = session.scalar(select(User).where(User.tg_id == uid))
        if not user:
            continue

        user.coins += int(coins)
        user.xp += int(xp)
        rewards[uid] = {"coins": int(coins), "xp": int(xp)}
        if idx == 0:
            user.wins += 1
        gained, new_level = _apply_level_up(user)
        if gained > 0:
            level_ups[uid] = {"gained": int(gained), "level": int(new_level)}
    return level_ups, rewards


def _apply_level_up(user: User) -> tuple[int, int]:
    gained = 0
    # Level up while XP threshold is reached; grow threshold by 1.2x each level.
    while int(user.xp) >= int(user.next_level_experience):
        user.xp -= int(user.next_level_experience)
        user.level += 1
        gained += 1
        next_req = int(ceil(float(user.next_level_experience) * 1.2))
        if next_req <= int(user.next_level_experience):
            next_req = int(user.next_level_experience) + 1
        user.next_level_experience = next_req
    return gained, int(user.level)


def apply_rewards_if_needed(session: Session, state: dict, settings) -> dict[int, dict]:
    if state.get("rewards_applied"):
        if state.get("level_ups_notified"):
            return {}
        return state.get("level_ups") or {}

    placements = state.get("placements") or []
    level_ups, rewards = apply_rewards(
        session,
        placements,
        top1=settings.REWARD_TOP1_COINS_RANGE,
        top2=settings.REWARD_TOP2_COINS_RANGE,
        top3=settings.REWARD_TOP3_COINS_RANGE,
        min_reward=settings.REWARD_MIN_COINS_RANGE,
        top1_xp=settings.REWARD_TOP1_XP_RANGE,
        top2_xp=settings.REWARD_TOP2_XP_RANGE,
        top3_xp=settings.REWARD_TOP3_XP_RANGE,
        min_xp=settings.REWARD_MIN_XP_RANGE,
    )
    state["rewards_applied"] = True
    state["level_ups"] = level_ups
    state["level_ups_notified"] = False
    state["rewards"] = rewards
    state["rewards_min_range"] = {
        "coins": tuple(settings.REWARD_MIN_COINS_RANGE),
        "xp": tuple(settings.REWARD_MIN_XP_RANGE),
    }
    return level_ups
