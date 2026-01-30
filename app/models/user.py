# from sqlalchemy.types import ARRAY
from datetime import datetime

from sqlalchemy.types import JSON
from sqlalchemy import Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.utils.db_manager import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    games_played: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    next_level_experience: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # groups: Mapped[list] = mapped_column(ARRAY(Integer), nullable=True, default=list)
    groups: Mapped[dict] = mapped_column(JSON, nullable=True, default={"groups": []})
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
