from __future__ import annotations

from sqlalchemy.types import JSON
from sqlalchemy import Integer, BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.utils.db_manager import Base


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )

    status: Mapped[str] = mapped_column(nullable=False, default="lobby")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # В SQLite це буде TEXT, в Postgres буде JSONB (але ти не залежиш від цього)
    state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
