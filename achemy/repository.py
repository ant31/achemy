import logging
from collections.abc import Sequence
from typing import Any, Literal, TypeVar

import sqlalchemy as sa
from sqlalchemy import FromClause, ScalarResult, Select, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_object_session
from sqlalchemy.orm import Mapper

from achemy.model import AlchemyModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=AlchemyModel)


class BaseRepository[T]:
    """
    A generic repository class providing common data access patterns.
    """

    _model_cls: type[T]
    session: AsyncSession

    def __init__(self, session: AsyncSession, model_cls: type[T]):
        self.session = session
        self._model_cls = model_cls

    @property
    def __table__(self) -> FromClause:
        return self._model_cls.__table__

    @property
    def __mapper__(self) -> Mapper[Any]:
        return self._model_cls.__mapper__

    # --- Instance & Session Helpers ---
    def obj_session(self, obj: T) -> AsyncSession | None:
        return async_object_session(obj)

    async def _ensure_obj_session(self, obj: T) -> T:
        if obj not in self.session:
            return await self.session.merge(obj)
        return obj

    # --- Basic CRUD Operations ---
    async def add(self, obj: T, commit: bool = False) -> T:
        try:
            self.session.add(obj)
            if commit:
                await self.session.commit()
                await self.session.refresh(obj)
        except SQLAlchemyError as e:
            logger.error(f"Error adding {obj}: {e}", exc_info=True)
            raise e
        return obj

    async def save(self, obj: T, commit: bool = False) -> T:
        return await self.add(obj, commit)

    async def bulk_insert(
        self,
        objs: list[T],
        commit: bool = True,
        on_conflict: Literal["fail", "nothing"] = "fail",
        on_conflict_index_elements: list[str] | None = None,
        fields: set[str] | None = None,
        returning: bool = True,
    ) -> Sequence[T] | None:
        if not hasattr(self._model_cls, "__table__"):
            raise TypeError(f"Class {self._model_cls.__name__} does not have a __table__ defined.")

        if not objs:
            return [] if returning else None

        values = [o.dump_model(with_meta=False, fields=fields) for o in objs]
        stmt = sa.insert(self._model_cls)

        if on_conflict == "nothing":
            # This works for dialects that support it (e.g., PostgreSQL, SQLite)
            stmt = stmt.on_conflict_do_nothing(index_elements=on_conflict_index_elements)
        elif on_conflict != "fail":
            dialect = self.session.bind.dialect.name if self.session.bind else "unknown"
            raise NotImplementedError(f"on_conflict='{on_conflict}' is not supported for dialect '{dialect}'.")

        insert_stmt = stmt.values(values)
        if returning:
            insert_stmt = insert_stmt.returning(self._model_cls)

        try:
            result = await self._execute_and_commit_bulk_statement(insert_stmt, commit)
            res = result.scalars().all() if returning and result else None
            return res
        except SQLAlchemyError as e:
            logger.error(f"Error during bulk_insert for {self._model_cls.__name__}: {e}", exc_info=True)
            raise e

    async def _execute_and_commit_bulk_statement(self, stmt: Any, commit_flag: bool) -> Any:
        result = await self.session.execute(stmt)
        if commit_flag:
            await self.session.commit()
        return result

    async def add_all(self, objs: list[T], commit: bool = True) -> Sequence[T]:
        if not objs:
            return []
        try:
            self.session.add_all(objs)
            if commit:
                await self.session.commit()
                for obj in objs:
                    try:
                        await self.session.refresh(obj)
                    except Exception as refresh_err:
                        logger.warning(f"Failed to refresh object {obj} after commit: {refresh_err}")
            return objs
        except SQLAlchemyError as e:
            logger.error(f"Error during add_all for {self._model_cls.__name__}: {e}", exc_info=True)
            raise e

    async def delete(self, obj: T, commit: bool = True) -> None:
        try:
            obj_in_session = await self._ensure_obj_session(obj)
            await self.session.delete(obj_in_session)
            if commit:
                await self.session.commit()
            else:
                await self.session.flush([obj_in_session])
        except SQLAlchemyError as e:
            logger.error(f"Error deleting {obj}: {e}", exc_info=True)
            raise e

    # --- Instance State Management ---
    async def refresh(self, obj: T, attribute_names: Sequence[str] | None = None) -> T:
        obj_in_session = await self._ensure_obj_session(obj)
        try:
            await self.session.refresh(obj_in_session, attribute_names=attribute_names)
        except SQLAlchemyError as e:
            logger.error(f"Error refreshing instance {obj_in_session}: {e}", exc_info=True)
            raise e
        return obj_in_session

    async def expire(self, obj: T, attribute_names: Sequence[str] | None = None) -> T:
        obj_in_session = await self._ensure_obj_session(obj)
        self.session.expire(obj_in_session, attribute_names=attribute_names)
        return obj_in_session

    async def expunge(self, obj: T) -> T:
        obj_in_session = await self._ensure_obj_session(obj)
        self.session.expunge(obj_in_session)
        return obj_in_session

    async def is_modified(self, obj: T) -> bool:
        obj_in_session = await self._ensure_obj_session(obj)
        return obj_in_session in self.session.dirty

    # --- Querying Methods ---
    def select(self, *args: Any, **kwargs: Any) -> Select[tuple[T]]:
        return sa.select(self._model_cls, *args, **kwargs)

    def where(self, *args: Any) -> Select[tuple[T]]:
        """
        Builds a query with a WHERE clause using SQLAlchemy expressions.

        This method encourages explicit, type-safe query construction by accepting
        any number of SQLAlchemy binary expressions.

        Args:
            *args: SQLAlchemy binary expressions (e.g., `self._model_cls.name == 'Alice'`).

        Returns:
            A new Select object with the WHERE clause applied.

        Example:
            # Find users named 'Alice' who are active
            active_alice_query = repo.where(User.name == 'Alice', User.is_active == True)
        """
        query = self.select()
        if args:
            query = query.where(*args)
        return query

    async def _execute_query(self, query: Select[tuple[T]]) -> ScalarResult[T]:
        result = await self.session.execute(query)
        return result.scalars()

    async def all(self, query: Select[tuple[T]] | None = None, limit: int | None = None) -> Sequence[T]:
        q = query if query is not None else self.select()
        if limit is not None:
            q = q.limit(limit)
        result = await self._execute_query(q)
        return result.all()

    async def first(self, query: Select[tuple[T]] | None = None, order_by: Any = None) -> T | None:
        q = query if query is not None else self.select()
        if order_by is None:
            try:
                pk_col = self.__table__.primary_key.columns.values()[0]
                q = q.order_by(pk_col.asc())
            except (AttributeError, IndexError):
                pass
        else:
            q = q.order_by(order_by)
        q = q.limit(1)
        result = await self._execute_query(q)
        return result.first()

    async def find_by(self, **kwargs: Any) -> T | None:
        """
        Finds the first record matching simple equality criteria.

        This is a convenience method for simple key-value lookups. For more
        complex queries (e.g., using inequalities, LIKE, etc.), use the `where()`
        method with explicit SQLAlchemy expressions and `await self.first(query)`.

        Args:
            **kwargs: Field-value pairs to match for equality.

        Returns:
            The first matching model instance or None.
        """
        mapper_props = {p.key for p in self.__mapper__.iterate_properties}

        # Warn about keys that are not mapped properties
        unknown_keys = set(kwargs.keys()) - mapper_props
        if unknown_keys:
            logger.warning(
                "find_by called with keys that are not mapped properties and will be ignored: %s",
                sorted(list(unknown_keys)),
            )

        filters = [getattr(self._model_cls, key) == value for key, value in kwargs.items() if key in mapper_props]

        if not filters:
            logger.warning(
                "find_by() called with no valid filtering criteria. "
                "This will return the first record in the table."
            )
            return await self.first()

        query = self.select().where(*filters)
        return await self.first(query=query)

    async def get(self, pk: Any) -> T | None:
        try:
            return await self.session.get(self._model_cls, pk)
        except SQLAlchemyError as e:
            logger.error(f"Error getting {self._model_cls.__name__} by PK {pk}: {e}", exc_info=True)
            raise e

    async def count(self, query: Select[T] | None = None) -> int:
        q = query if query is not None else self.select()
        count_q = sa.select(func.count()).select_from(q.order_by(None).limit(None).offset(None).subquery())
        try:
            result = await self.session.execute(count_q)
            count_scalar = result.scalar_one_or_none()
            return count_scalar if count_scalar is not None else 0
        except SQLAlchemyError as e:
            logger.error(f"Error executing count query for {self._model_cls.__name__}: {e}", exc_info=True)
            raise e
