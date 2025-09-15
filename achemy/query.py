import logging
import warnings
from collections.abc import Sequence
from typing import Any, ClassVar, Literal, Self

import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as sa_pg
from sqlalchemy import FromClause, ScalarResult, Select, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_object_session,
    async_sessionmaker,
)
from sqlalchemy.orm import Mapper

from achemy.engine import ActiveEngine

logger = logging.getLogger(__name__)


class QueryMixin:
    """
    An opt-in mixin that provides ActiveRecord-like query and CRUD methods.
    """

    # --- Class Attributes ---
    __table__: ClassVar[FromClause]  # Populated by SQLAlchemy mapper
    __mapper__: ClassVar[Mapper[Any]]  # Populated by SQLAlchemy mapper
    __active_engine__: ClassVar[ActiveEngine]
    _session_factory: ClassVar[async_sessionmaker[AsyncSession] | None] = None

    # --- Engine & Session Management (DEPRECATED) ---
    @classmethod
    def engine(cls) -> ActiveEngine:
        warnings.warn(
            (
                "QueryMixin.engine() is deprecated. "
                "Manage the ActiveEngine instance directly in your application."
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        if not hasattr(cls, "__active_engine__") or cls.__active_engine__ is None:
            raise ValueError(f"No active engine configured for class {cls.__name__}")
        return cls.__active_engine__

    @classmethod
    def set_engine(cls, engine: ActiveEngine):
        warnings.warn(
            (
                "QueryMixin.set_engine() is deprecated. "
                "Instantiate ActiveEngine and get sessions from it directly."
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        if not isinstance(engine, ActiveEngine):
            raise TypeError("Engine must be an instance of ActiveEngine")
        cls.__active_engine__ = engine
        _, session_factory = engine.session(schema=getattr(cls, "__schema__", "public"))
        cls._session_factory = session_factory
        logger.info(f"ActiveEngine and session factory set for {cls.__name__}")

    @classmethod
    def session_factory(cls) -> async_sessionmaker[AsyncSession]:
        warnings.warn(
            ("QueryMixin.session_factory() is deprecated."),
            DeprecationWarning,
            stacklevel=2,
        )
        if cls._session_factory is None:
            if hasattr(cls, "__active_engine__") and cls.__active_engine__:
                cls.set_engine(cls.__active_engine__)
                if cls._session_factory:
                    return cls._session_factory
            raise ValueError(f"Session factory not configured for {cls.__name__}.")
        return cls._session_factory

    @classmethod
    def get_session(cls) -> AsyncSession:
        warnings.warn(
            ("QueryMixin.get_session() is deprecated."),
            DeprecationWarning,
            stacklevel=2,
        )
        factory = cls.session_factory()
        return factory()

    # --- Instance & Session Helpers ---
    def obj_session(self) -> AsyncSession | None:
        return async_object_session(self)

    @classmethod
    async def _ensure_obj_session(cls, obj: Self, session: AsyncSession) -> Self:
        if obj not in session:
            return await session.merge(obj)
        return obj

    # --- Basic CRUD Operations ---
    @classmethod
    async def add(cls, obj: Self, session: AsyncSession, commit: bool = False) -> Self:
        try:
            session.add(obj)
            if commit:
                await session.commit()
                await session.refresh(obj)
        except SQLAlchemyError as e:
            logger.error(f"Error adding {obj}: {e}", exc_info=True)
            raise e
        return obj

    async def save(self, session: AsyncSession, commit: bool = False) -> Self:
        return await self.add(self, session, commit)

    @classmethod
    async def bulk_insert(
        cls: type[Self],
        objs: list[Self],
        session: AsyncSession,
        commit: bool = True,
        on_conflict: Literal["fail", "nothing"] = "fail",
        on_conflict_index_elements: list[str] | None = None,
        fields: set[str] | None = None,
        returning: bool = True,
    ) -> Sequence[Self] | None:
        if not hasattr(cls, "__table__"):
            raise TypeError(f"Class {cls.__name__} does not have a __table__ defined.")

        if not objs:
            return [] if returning else None

        values = [o.dump_model(with_meta=False, fields=fields) for o in objs]
        dialect = session.bind.dialect.name if session.bind else "unknown"

        if dialect == "postgresql":
            stmt = sa_pg.insert(cls)
            if on_conflict == "nothing":
                stmt = stmt.on_conflict_do_nothing(index_elements=on_conflict_index_elements)
            elif on_conflict != "fail":
                raise ValueError(f"Invalid on_conflict strategy '{on_conflict}' for PostgreSQL.")
        else:
            if on_conflict != "fail":
                raise NotImplementedError(f"on_conflict='{on_conflict}' is not supported for '{dialect}'.")
            stmt = sa.insert(cls)

        insert_stmt = stmt.values(values)
        if returning:
            insert_stmt = insert_stmt.returning(cls)

        try:
            result = await cls._execute_and_commit_bulk_statement(session, insert_stmt, commit)
            res = result.scalars().all() if returning and result else None
            return res
        except SQLAlchemyError as e:
            logger.error(f"Error during bulk_insert for {cls.__name__}: {e}", exc_info=True)
            raise e

    @staticmethod
    async def _execute_and_commit_bulk_statement(s: AsyncSession, stmt: Any, commit_flag: bool) -> Any:
        result = await s.execute(stmt)
        if commit_flag:
            await s.commit()
        return result

    @classmethod
    async def add_all(cls, objs: list[Self], session: AsyncSession, commit: bool = True) -> Sequence[Self]:
        if not objs:
            return []
        try:
            session.add_all(objs)
            if commit:
                await session.commit()
                for obj in objs:
                    try:
                        await session.refresh(obj)
                    except Exception as refresh_err:
                        logger.warning(f"Failed to refresh object {obj} after commit: {refresh_err}")
            return objs
        except SQLAlchemyError as e:
            logger.error(f"Error during add_all for {cls.__name__}: {e}", exc_info=True)
            raise e

    @classmethod
    async def delete(cls, obj: Self, session: AsyncSession, commit: bool = True) -> None:
        try:
            obj_in_session = await cls._ensure_obj_session(obj, session)
            await session.delete(obj_in_session)
            if commit:
                await session.commit()
            else:
                await session.flush([obj_in_session])
        except SQLAlchemyError as e:
            logger.error(f"Error deleting {obj}: {e}", exc_info=True)
            raise e

    # --- Instance State Management ---
    async def refresh(self, session: AsyncSession, attribute_names: Sequence[str] | None = None) -> Self:
        obj_in_session = await self.__class__._ensure_obj_session(self, session)
        try:
            await session.refresh(obj_in_session, attribute_names=attribute_names)
        except SQLAlchemyError as e:
            logger.error(f"Error refreshing instance {obj_in_session}: {e}", exc_info=True)
            raise e
        return obj_in_session

    async def expire(self, session: AsyncSession, attribute_names: Sequence[str] | None = None) -> Self:
        obj_in_session = await self.__class__._ensure_obj_session(self, session)
        session.expire(obj_in_session, attribute_names=attribute_names)
        return obj_in_session

    async def expunge(self, session: AsyncSession) -> Self:
        obj_in_session = await self.__class__._ensure_obj_session(self, session)
        session.expunge(obj_in_session)
        return obj_in_session

    async def is_modified(self, session: AsyncSession) -> bool:
        obj_in_session = await self.__class__._ensure_obj_session(self, session)
        return obj_in_session in session.dirty

    # --- Querying Methods ---
    @classmethod
    def select(cls, *args: Any, **kwargs: Any) -> Select[tuple[Self]]:
        return sa.select(cls, *args, **kwargs)

    @classmethod
    def where(cls, *args: Any, **kwargs: Any) -> Select[tuple[Self]]:
        query = cls.select()
        mapper_props = {p.key for p in cls.__mapper__.iterate_properties}
        filters = [getattr(cls, key) == value for key, value in kwargs.items() if key in mapper_props]
        all_filters = list(args) + filters
        if all_filters:
            query = query.where(*all_filters)
        return query

    @classmethod
    async def _execute_query(cls, query: Select[tuple[Self]], session: AsyncSession) -> ScalarResult[Self]:
        result = await session.execute(query)
        return result.scalars()

    @classmethod
    async def all(
        cls, session: AsyncSession, query: Select[tuple[Self]] | None = None, limit: int | None = None
    ) -> Sequence[Self]:
        q = query if query is not None else cls.select()
        if limit is not None:
            q = q.limit(limit)
        result = await cls._execute_query(q, session)
        return result.all()

    @classmethod
    async def first(
        cls, session: AsyncSession, query: Select[tuple[Self]] | None = None, order_by: Any = None
    ) -> Self | None:
        q = query if query is not None else cls.select()
        if order_by is None:
            try:
                pk_col = cls.__table__.primary_key.columns.values()[0]
                q = q.order_by(pk_col.asc())
            except (AttributeError, IndexError):
                pass
        else:
            q = q.order_by(order_by)
        q = q.limit(1)
        result = await cls._execute_query(q, session)
        return result.first()

    @classmethod
    async def find_by(cls, session: AsyncSession, *args, **kwargs) -> Self | None:
        query = cls.where(*args, **kwargs)
        return await cls.first(session=session, query=query)

    @classmethod
    async def get(cls, session: AsyncSession, pk: Any) -> Self | None:
        try:
            return await session.get(cls, pk)
        except SQLAlchemyError as e:
            logger.error(f"Error getting {cls.__name__} by PK {pk}: {e}", exc_info=True)
            raise e

    @classmethod
    async def count(cls, session: AsyncSession, query: Select[Self] | None = None) -> int:
        q = query if query is not None else cls.select()
        count_q = sa.select(func.count()).select_from(q.order_by(None).limit(None).offset(None).subquery())
        try:
            result = await session.execute(count_q)
            count_scalar = result.scalar_one_or_none()
            return count_scalar if count_scalar is not None else 0
        except SQLAlchemyError as e:
            logger.error(f"Error executing count query for {cls.__name__}: {e}", exc_info=True)
            raise e
