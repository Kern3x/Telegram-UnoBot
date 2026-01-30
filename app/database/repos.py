from __future__ import annotations
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Game, User, Group


class OptimisticLockError(Exception): ...


class GameRepo:
    def __init__(self, s: Session):
        self.s = s

    def get_by_chat(self, chat_id: int) -> Game | None:
        return self.s.scalar(select(Game).where(Game.chat_id == chat_id))

    def create_lobby(self, chat_id: int, title: str) -> Game:
        g = Game(
            chat_id=chat_id,
            status="lobby",
            state={
                "title": title,
                "players": [],
                "turn_idx": 0,
                "hands": {},
                "top_card": None,
                "current_color": None,
                "timers": {},
                "assets_chat_id": None,
            },
        )
        self.s.add(g)
        self.s.commit()
        self.s.refresh(g)
        return g

    def delete_lobby(self, game: Game) -> None:
        self.s.delete(game)
        self.s.commit()

    def save(
        self,
        game: Game,
        expected_version: int,
        *,
        status: str | None = None,
        state: dict | None = None,
    ) -> None:
        new_status = status if status is not None else game.status
        new_state = state if state is not None else game.state

        res = self.s.execute(
            update(Game)
            .where(Game.id == game.id, Game.version == expected_version)
            .values(status=new_status, state=new_state, version=expected_version + 1)
        )
        if res.rowcount != 1:
            self.s.rollback()
            raise OptimisticLockError()
        self.s.commit()

    def add_player(self, game: Game, user_id: int) -> Game:
        state = game.state or {}
        players = state.get("players") or []
        if user_id not in players:
            players.append(user_id)
        state["players"] = players
        game.state = state
        return game

    def remove_player(self, game: Game, user_id: int) -> Game:
        state = game.state or {}
        players = state.get("players") or []
        players = [x for x in players if int(x) != int(user_id)]
        state["players"] = players
        # ще можна прибрати руку
        hands = state.get("hands") or {}
        hands.pop(str(user_id), None)
        state["hands"] = hands
        game.state = state
        return game

    def get_top_players_by(
        self, limit: int = 10, group_id: int = None, by: str = "coins"
    ) -> list[User]:
        stmt = select(User).order_by(getattr(User, by).desc()).limit(limit)

        if group_id:
            stmt = stmt.where(User.groups["groups"].contains([group_id]))

        return self.s.scalars(stmt).all()

    def get_group(self, chat_id: int) -> Group | None:
        return self.s.scalar(select(Group).where(Group.chat_id == chat_id))
    
    def create_group(self, chat_id: int, title: str) -> Group:
        group = Group(
            chat_id=chat_id,
            title=title,
        )
        self.s.add(group)
        self.s.commit()
        self.s.refresh(group)
        return group