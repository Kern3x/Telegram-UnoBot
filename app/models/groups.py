from __future__ import annotations

from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, BigInteger, String

from app.utils.db_manager import Base


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    settings: Mapped[dict] = mapped_column(
        JSON, nullable=True, default={"settings": {}}
    )
