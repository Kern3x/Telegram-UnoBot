from typing import Type
from sqlalchemy import select, func, update, delete

from app.utils.db_manager import get_session


class DataController:
    def add(self, model_cls: Type, **kwargs):
        with get_session() as s:
            obj = model_cls(**kwargs)
            s.add(obj)
            s.flush()
            return obj

    def get_first(self, model_cls: Type, **filters):
        with get_session() as s:
            stmt = select(model_cls).filter_by(**filters).limit(1)
            return s.scalars(stmt).first()

    def get_all(self, model_cls: Type, **filters) -> list:
        with get_session() as s:
            stmt = select(model_cls).filter_by(**filters)
            return list(s.scalars(stmt))

    def get_all_in(self, model_cls: Type, field, values: list):
        with get_session() as s:
            stmt = select(model_cls).where(field.in_(values))
            return list(s.scalars(stmt))

    def count(self, model_cls: Type, **filters) -> int:
        with get_session() as s:
            stmt = select(func.count()).select_from(model_cls).filter_by(**filters)
            return s.scalar(stmt) or 0

    def update_first(self, model_cls: Type, values: dict, **filters) -> int:
        with get_session() as s:
            obj = s.scalars(select(model_cls).filter_by(**filters).limit(1)).first()

            if not obj:
                return 0

            for k, v in values.items():
                setattr(obj, k, v)

            return 1

    def update_all(self, model_cls: Type, values: dict, **filters) -> int:
        with get_session() as s:
            res = s.execute(
                update(model_cls)
                .where(*[getattr(model_cls, k) == v for k, v in filters.items()])
                .values(**values)
            )

            return res.rowcount or 0

    def delete_first(self, model_cls: Type, **filters) -> int:
        with get_session() as s:
            obj = s.scalars(select(model_cls).filter_by(**filters).limit(1)).first()

            if not obj:
                return 0

            s.delete(obj)
            return 1

    def delete_all(self, model_cls: Type, **filters) -> int:
        with get_session() as s:
            res = s.execute(
                delete(model_cls).where(
                    *[getattr(model_cls, k) == v for k, v in filters.items()]
                )
            )

            return res.rowcount or 0
