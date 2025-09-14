import logging
import warnings
from collections.abc import Sequence
from typing import Any, ClassVar, Literal, Self

import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as sa_pg
from pydantic_core import to_jsonable_python
from sqlalchemy import FromClause, ScalarResult, Select, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_object_session,
    async_sessionmaker,
)
from sqlalchemy.orm import (
    ColumnProperty,
    Mapper,
)

# Assuming ActiveEngine is imported from the refactored engine file
from achemy.engine import ActiveEngine
from achemy.schema import Schema

logger = logging.getLogger(__name__)


# Generic type for the model class

# --- AlchemyModel Core (Async) ---


class AlchemyModel(AsyncAttrs):
    """
    Base model class with query helpers using SQLAlchemy 2+ ORM.

    Provides convenience methods for database operations (CRUD, queries)
    directly on the model class or instances.
    """

    # --- Class Attributes ---

    __tablename__: ClassVar[str]  # Must be defined by subclasses
    __schema__: ClassVar[str] = "public"  # Default schema
    __table__: ClassVar[FromClause]  # Populated by SQLAlchemy mapper
    __mapper__: ClassVar[Mapper[Any]]  # Populated by SQLAlchemy mapper
    __pydantic_schema__: ClassVar[type[Schema]]  # Pydantic schema class for serialization
    __pydantic_initialized__: ClassVar[bool] = False  # Flag for Pydantic schema initialization
    # Direct reference to the configured ActiveEngine instance
    __active_engine__: ClassVar[ActiveEngine]
    # Session factory associated with this class (set via engine)
    _session_factory: ClassVar[async_sessionmaker[AsyncSession] | None] = None

    # --- Engine Management ---
    @classmethod
    def engine(cls) -> ActiveEngine:
        """
        Return the active engine associated with this class.

        .. deprecated:: 0.4.0
            This method is deprecated. Manage the ``ActiveEngine`` instance directly
            in your application's context instead of accessing it via the model class.
        """
        warnings.warn(
            (
                "AlchemyModel.engine() is deprecated and will be removed in a future version. "
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
        """
        Set the ActiveEngine instance for this class and its subclasses.

        .. deprecated:: 0.4.0
            This method is deprecated. Instantiate ``ActiveEngine`` and get sessions
            from it directly, rather than attaching it globally to models.
        """
        warnings.warn(
            (
                "AlchemyModel.set_engine() is deprecated and will be removed in a future version. "
                "Instantiate ActiveEngine and get sessions from it directly."
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        if not isinstance(engine, ActiveEngine):
            raise TypeError("Engine must be an instance of ActiveEngine")
        cls.__active_engine__ = engine
        # Retrieve and store the session factory for this class's default schema/db
        _, session_factory = engine.session(schema=cls.__schema__)  # Use class schema
        cls._session_factory = session_factory
        logger.info(f"ActiveEngine and session factory set for {cls.__name__}")

    # dispose_engines was removed as fork management is gone.
    # Direct disposal can be done via `ActiveRecord.engine().dispose_engines()` if needed.

    # --- Session Management ---
    @classmethod
    def session_factory(cls) -> async_sessionmaker[AsyncSession]:
        """
        Return the session factory associated with this class.

        .. deprecated:: 0.4.0
            This method is deprecated. Get a session factory directly from your
            ``ActiveEngine`` instance via ``engine.session()``.
        """
        warnings.warn(
            (
                "AlchemyModel.session_factory() is deprecated and will be removed in a future version. "
                "Get a session factory directly from your ActiveEngine instance."
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        if cls._session_factory is None:
            # Attempt to set it if engine exists but factory wasn't retrieved?
            if hasattr(cls, "__active_engine__") and cls.__active_engine__:
                logger.warning(f"Session factory not set for {cls.__name__}, attempting retrieval from engine.")
                cls.set_engine(cls.__active_engine__)  # This will set _session_factory
                if cls._session_factory:
                    return cls._session_factory
            raise ValueError(f"Session factory not configured for {cls.__name__}. Call set_engine first.")
        return cls._session_factory

    @classmethod
    def get_session(cls) -> AsyncSession:
        """
        Gets a new AsyncSession instance from the class's session factory.

        .. deprecated:: 0.4.0
            This method is deprecated. Get a session directly from a session factory
            obtained from your ``ActiveEngine`` instance. Example:
            ``_, session_factory = engine.session()``
            ``async with session_factory() as session: ...``
        """
        warnings.warn(
            (
                "AlchemyModel.get_session() is deprecated and will be removed in a future version. "
                "Get a session directly from a session factory obtained from your ActiveEngine instance."
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        # Create a new session from the factory
        factory = cls.session_factory()  # Raises ValueError if not configured
        new_session = factory()
        logger.debug(f"Created new session for {cls.__name__}: {new_session}")
        return new_session

    def obj_session(self) -> AsyncSession | None:
        """Get the session associated with this specific object instance, if tracked."""
        return async_object_session(self)

    @classmethod
    async def _ensure_obj_session(cls, obj: Self, session: AsyncSession) -> Self:
        """
        Internal helper to ensure an object is associated with a given session.

        Merges the object into the session if it's not already persistent
        or part of that session's identity map.

        Args:
            obj: The model instance.
            session: The session to associate the object with.

        Returns:
            The (potentially merged) object instance.
        """
        if obj not in session:
            # If session provided, but object not in it, merge it.
            logger.debug(f"Object {obj} not in provided session {session}, merging.")
            return await session.merge(obj)
        return obj

    # --- Instance Representation & Data Handling (Merged from BaseActiveRecord) ---
    def __str__(self):
        """Return a string representation, including primary key if available."""
        pk = getattr(self, "id", "id?")  # Assumes 'id' is the PK attribute
        return f"{self.__class__.__name__}({pk})"  # Use class name for clarity

    def __repr__(self) -> str:
        """Return a technical representation, same as __str__."""
        return str(self)

    def printn(self):
        """Helper method to print instance attributes (excluding SQLAlchemy state)."""
        print(f"Attributes for {self}:")
        attrs = {k: v for k, v in self.__dict__.items() if not k.startswith("_sa_")}
        for k, v in attrs.items():
            print(f"  {k}: {v}")

    def id_key(self) -> str:
        """Return a unique key string for this instance (Class:id)."""
        pk = getattr(self, "id", None)
        if pk is None:
            # Handle case where object might be transient (no ID yet)
            return f"{self.__class__.__name__}:transient_{id(self)}"
            # Or raise error: raise AttributeError(f"{self.__class__.__name__} instance has no 'id' attribute set.")
        return f"{self.__class__.__name__}:{pk}"

    @classmethod
    def __columns__fields__(cls) -> dict[str, tuple[type | None, Any]]:
        """
        Inspects the SQLAlchemy mapped columns for the class.

        Returns:
            A dictionary where keys are column names and values are tuples
            of (python_type, default_value). Returns None for python_type
            if it cannot be determined.
        """
        if not hasattr(cls, "__table__") or cls.__table__ is None:
            raise ValueError(f"No table associated with class {cls.__name__}")

        field_data = {}
        try:
            for col in cls.__table__.columns:
                py_type = None
                try:
                    # Attempt to get the Python type from the column type
                    py_type = col.type.python_type
                except NotImplementedError:
                    logger.warning(f"Could not determine Python type for column '{col.name}' of type {col.type}")

                default_val = col.default.arg if col.default else None
                field_data[col.name] = (py_type, default_val)
        except Exception as e:
            logger.error(f"Error inspecting columns for {cls.__name__}: {e}", exc_info=True)
            raise  # Or return partial data: return field_data
        return field_data

    def to_dict(self, with_meta: bool = False, fields: set[str] | None = None) -> dict[str, Any]:
        """
        Generate a dictionary representation of the model instance's mapped attributes.

        Args:
            with_meta: If True, include a '__metadata__' key with class/table info.
            fields: An optional set of attribute names to include. If None, includes all mapped columns.

        Returns:
            A dictionary containing the instance's data.
        """
        data = {}
        if hasattr(self, "__mapper__"):
            # Get names of attributes corresponding to mapped columns
            col_prop_keys = {p.key for p in self.__mapper__.iterate_properties if isinstance(p, ColumnProperty)}

            # Filter keys if 'fields' is specified
            keys_to_include = col_prop_keys
            if fields is not None:
                keys_to_include = col_prop_keys.intersection(fields)
                # Warn if requested fields are not mapped columns?
                # unknown_fields = fields - col_prop_keys
                # if unknown_fields: logger.warning(...)

            # Populate data dictionary, handling potential deferred loading issues
            for key in keys_to_include:
                try:
                    # Accessing the attribute might trigger loading if deferred
                    data[key] = getattr(self, key)
                except Exception as e:
                    logger.warning(f"Could not retrieve attribute '{key}' for {self}: {e}")
                    data[key] = None  # Or some other placeholder
        else:
            # Fallback for non-mapped objects? Unlikely for AlchemyModel.
            logger.warning(f"Instance {self} does not seem to be mapped by SQLAlchemy.")
            # Simple __dict__ might include SQLAlchemy state (_sa_...)
            # data = {k: v for k, v in self.__dict__.items() if not k.startswith('_sa_')}
            return {}  # Or raise error

        if with_meta:
            classname = f"{self.__class__.__module__}:{self.__class__.__name__}"
            data["__metadata__"] = {
                "model": classname,
                "table": getattr(self, "__tablename__", "unknown"),
                "schema": getattr(self, "__schema__", "unknown"),
            }

        return data

    def dump_model(self, with_meta: bool = False, fields: set[str] | None = None) -> dict[str, Any]:
        """
        Return a JSON-serializable dict representation of the instance.

        Uses `to_dict` and then `pydantic_core.to_jsonable_python` for compatibility.

        Args:
            with_meta: Passed to `to_dict`.
            fields: Passed to `to_dict`.

        Returns:
            A JSON-serializable dictionary.
        """
        plain_dict = self.to_dict(with_meta=with_meta, fields=fields)
        try:
            # Convert types like UUID, datetime to JSON-friendly formats
            return to_jsonable_python(plain_dict)
        except Exception as e:
            logger.error(f"Error making dictionary for {self} JSON-serializable: {e}", exc_info=True)
            # Fallback: return the plain dict, might cause issues downstream
            return plain_dict

    @classmethod
    def load(cls, data: dict[str, Any]) -> Self:
        """
        Load an instance from a dictionary, setting only mapped attributes.

        Args:
            data: The dictionary containing data to load.

        Returns:
            A new instance of the class populated with data.

        Raises:
            ValueError: If the class is not mapped or data is not a dict.
        """
        if not isinstance(data, dict):
            raise ValueError("Input 'data' must be a dictionary.")

        if not hasattr(cls, "__mapper__"):
            raise ValueError(f"Cannot load data: Class {cls.__name__} is not mapped by SQLAlchemy.")

        obj = cls()  # Create a new instance

        # Get names of mapped column attributes
        col_prop_keys = {p.key for p in cls.__mapper__.iterate_properties if isinstance(p, ColumnProperty)}

        loaded_keys = set()
        for key, value in data.items():
            if key in col_prop_keys:
                try:
                    setattr(obj, key, value)
                    loaded_keys.add(key)
                except Exception as e:
                    logger.warning(f"Failed to set attribute '{key}' on {cls.__name__} instance: {e}")
            # else: ignore keys in the data dict that don't correspond to mapped columns

        logger.debug(f"Loaded {len(loaded_keys)} attributes onto new {cls.__name__} instance: {loaded_keys}")
        return obj

    # --- Basic CRUD Operations ---

    @classmethod
    async def add(cls, obj: Self, session: AsyncSession, commit: bool = False) -> Self:
        """
        Add an instance to the session and optionally commit.

        Args:
            obj: The model instance to add.
            session: The active AsyncSession.
            commit: If True, commit the transaction. It is recommended to manage
                    commits at the session level instead.

        Returns:
            The added instance.
        """
        try:
            session.add(obj)
            if commit:
                await session.commit()
                await session.refresh(obj)
            else:
                # Flush to get ID etc. if not committing.
                # This is now the caller's responsibility when managing a session.
                pass
        except SQLAlchemyError as e:
            logger.error(f"Error adding {obj} with provided session {session}: {e}", exc_info=True)
            raise e
        return obj

    async def save(self, session: AsyncSession, commit: bool = False) -> Self:
        """Add this instance to the database via the provided session."""
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
        """
        Performs a bulk INSERT operation with conflict handling.

        Handles conflicts based on the 'on_conflict' parameter. This feature
        is currently only supported for the PostgreSQL dialect.

        Args:
            objs: A list of model instances to insert.
            session: The active AsyncSession.
            commit: If True, commit the session after the insert.
            on_conflict: Strategy for handling conflicts (PostgreSQL only):
                         - "fail": Standard INSERT behavior; will raise IntegrityError on conflict.
                         - "nothing": Use ON CONFLICT DO NOTHING; skips rows with conflicts.
            on_conflict_index_elements: Optional list of column names for the conflict target
                                        when on_conflict is "nothing". If None, the primary
                                        key or a unique constraint is used implicitly.
            fields: Optional set of field names to include in the insert values.
            returning: Whether to return the inserted model instances.

        Returns:
            A sequence of the inserted model instances if returning is True,
            otherwise None. Returns an empty list if returning is True and objs is empty.
            Note: When using ON CONFLICT DO NOTHING, returning() only returns
            the rows that were *actually inserted*, not the ones that were skipped.

        Raises:
            SQLAlchemyError: If a database error occurs.
            NotImplementedError: If on_conflict is used with a non-PostgreSQL dialect.
            TypeError: If the model class does not have a __table__ defined.
        """
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
                raise NotImplementedError(
                    f"on_conflict='{on_conflict}' is only supported for 'postgresql', "
                    f"not for the current '{dialect}' dialect."
                )
            stmt = sa.insert(cls)

        insert_stmt = stmt.values(values)

        if returning:
            # NOTE: `returning` support can vary between backends, but is
            # common enough for core support (PostgreSQL, SQLite, etc.)
            insert_stmt = insert_stmt.returning(cls)

        try:
            result = await cls._execute_and_commit_bulk_statement(session, insert_stmt, commit)
            res = result.scalars().all() if returning and result else None
            return res
        except SQLAlchemyError as e:
            logger.error(
                f"Error during bulk_insert for {cls.__name__} with on_conflict='{on_conflict}': {e}",
                exc_info=True,
            )
            raise e

    @staticmethod
    async def _execute_and_commit_bulk_statement(
        s: AsyncSession, stmt: Any, commit_flag: bool
    ) -> Any:  # Returns SA's Result object
        result = await s.execute(stmt)
        if commit_flag:
            await s.commit()
        return result

    @classmethod
    async def add_all(cls, objs: list[Self], session: AsyncSession, commit: bool = True) -> Sequence[Self]:
        """
        Adds multiple instances to the session and optionally commits.

        Args:
            objs: A list of model instances to add.
            commit: If True, commit the session after adding all objects.
            session: Optional session to use. If None, gets a default session.

        Returns:
            The sequence of added instances (potentially refreshed after commit).

        Raises:
            SQLAlchemyError: If database commit fails.
        """
        if not objs:
            return []

        try:
            return await cls._add_all_to_session(objs, session, commit)
        except SQLAlchemyError as e:
            logger.error(f"Error during add_all operation for {cls.__name__}: {e}", exc_info=True)
            # Rollback needs to be handled by the caller.
            raise e

    @classmethod
    async def _add_all_to_session(cls, objs: list[Self], session: AsyncSession, commit: bool) -> Sequence[Self]:
        """Helper to add objects within a specific session."""
        logger.debug(f"Adding {len(objs)} instances of {cls.__name__} to session {session}")
        session.add_all(objs)
        if commit:
            await session.commit()
            for obj in objs:
                # Refresh might fail if the object was deleted concurrently,
                # but commit succeeded. Handle appropriately if needed.
                try:
                    await session.refresh(obj)
                except Exception as refresh_err:
                    logger.warning(f"Failed to refresh object {obj} after commit: {refresh_err}")
        else:
            # Flushing is now the caller's responsibility when not committing.
            pass
        return objs

    @classmethod
    async def delete(cls, obj: Self, session: AsyncSession, commit: bool = True) -> None:
        """
        Deletes the instance from the database using the provided session.

        Args:
            obj: The instance to delete.
            session: The active AsyncSession.
            commit: If True, commit the transaction. It is recommended to manage
                    commits at the session level instead.

        Raises:
            SQLAlchemyError: If database commit fails.
        """
        try:
            obj_in_session = await cls._ensure_obj_session(obj, session)
            logger.debug(f"Deleting instance {obj_in_session} from session {session}")
            await session.delete(obj_in_session)
            if commit:
                await session.commit()
            else:
                await session.flush([obj_in_session])  # Flush if not committing
        except SQLAlchemyError as e:
            logger.error(f"Error deleting {obj} with session {session}: {e}", exc_info=True)
            raise e

    # --- Instance State Management ---

    async def refresh(self, session: AsyncSession, attribute_names: Sequence[str] | None = None) -> Self:
        """
        Refreshes the instance's attributes from the database.

        Args:
            session: The active AsyncSession.
            attribute_names: Optional sequence of specific attribute names to refresh.

        Returns:
            The refreshed instance itself.
        """
        obj_in_session = await self.__class__._ensure_obj_session(self, session)
        try:
            logger.debug(f"Refreshing attributes {attribute_names or 'all'} for {obj_in_session} in session {session}")
            await session.refresh(obj_in_session, attribute_names=attribute_names)
        except SQLAlchemyError as e:
            logger.error(f"Error refreshing instance {obj_in_session}: {e}", exc_info=True)
            raise e
        return obj_in_session

    async def expire(self, session: AsyncSession, attribute_names: Sequence[str] | None = None) -> Self:
        """
        Expires the instance's attributes, causing them to be reloaded on next access.

        Args:
            session: The active AsyncSession.
            attribute_names: Optional sequence of specific attribute names to expire.

        Returns:
            The instance itself.
        """
        obj_in_session = await self.__class__._ensure_obj_session(self, session)
        logger.debug(f"Expiring attributes {attribute_names or 'all'} for {obj_in_session} in session {session}")
        session.expire(obj_in_session, attribute_names=attribute_names)
        return obj_in_session

    async def expunge(self, session: AsyncSession) -> Self:
        """
        Removes the instance from the session. The object becomes detached.

        Args:
            session: The active AsyncSession.

        Returns:
            The (now detached) instance itself.
        """
        obj_in_session = await self.__class__._ensure_obj_session(self, session)
        logger.debug(f"Expunging instance {obj_in_session} from session {session}")
        session.expunge(obj_in_session)
        return obj_in_session

    async def is_modified(self, session: AsyncSession) -> bool:
        """
        Checks if the instance has pending changes in the session.

        Args:
            session: The active AsyncSession.

        Returns:
            True if the object is considered modified within the session, False otherwise.
        """
        obj_in_session = await self.__class__._ensure_obj_session(self, session)
        # The session tracks modifications. Check the 'dirty' collection.
        is_dirty = obj_in_session in session.dirty
        logger.debug(f"Instance {obj_in_session} modified status in session {session}: {is_dirty}")
        return is_dirty

    # --- Session Commit/Rollback (Class-level convenience) ---
    # These might be less common in ActiveRecord pattern but can be useful.

    @classmethod
    async def commit(cls, session: AsyncSession) -> None:
        """Commits the provided session."""
        if session is None:
            raise ValueError("A session instance must be provided to commit.")
        try:
            logger.debug(f"Committing provided session {session}")
            await session.commit()
        except SQLAlchemyError as e:
            logger.error(f"Error committing session {session}: {e}", exc_info=True)
            logger.debug(f"Rolling back session {session} after commit error")
            await session.rollback()  # Rollback on commit error
            raise e

    @classmethod
    async def rollback(cls, session: AsyncSession) -> None:
        """Rolls back the provided session."""
        if session is None:
            raise ValueError("A session instance must be provided to rollback.")
        try:
            logger.debug(f"Rolling back provided session {session}")
            await session.rollback()
        except SQLAlchemyError as e:
            # Rollback itself failing is less common but possible
            logger.error(f"Error rolling back session {session}: {e}", exc_info=True)
            raise e

    # --- Querying Methods ---

    @classmethod
    def select(cls, *args: Any, **kwargs: Any) -> Select[tuple[Self]]:
        """
        Creates a base SQLAlchemy Select statement targeting this class.

        Args:
            *args: Positional arguments passed to SQLAlchemy's select().
            **kwargs: Keyword arguments passed to SQLAlchemy's select().

        Returns:
            A SQLAlchemy Select object ready for filtering, ordering, etc.
        """
        query = sa.select(cls, *args, **kwargs)
        logger.debug(f"Created Select query for {cls.__name__}")
        return query

    @classmethod
    def where(cls, *args: Any, **kwargs: Any) -> Select[tuple[Self]]:
        """
        Creates a Select statement with WHERE criteria applied.

        Args:
            *args: Positional WHERE clause elements (e.g., cls.column == value).
            **kwargs: Keyword arguments treated as equality filters (e.g., name="value").

        Returns:
            A Select object with the WHERE clause.
        """
        query = cls.select()  # No session passed here

        # Handle keyword arguments as equality conditions
        # Ensure kwargs match actual column names/attributes
        mapper_props = {p.key for p in cls.__mapper__.iterate_properties}
        filters = []
        for key, value in kwargs.items():
            if key in mapper_props:
                filters.append(getattr(cls, key) == value)
            else:
                logger.warning(
                    f"Ignoring keyword argument '{key}' in where() for {cls.__name__} as it's not a mapped attribute."
                )

        # Combine positional and keyword filters
        all_filters = list(args) + filters
        if all_filters:
            query = query.where(*all_filters)
            logger.debug(f"Applied WHERE clause to {cls.__name__} query: {all_filters}")

        return query

    @classmethod
    async def _execute_query(cls, query: Select[tuple[Self]], session: AsyncSession) -> ScalarResult[Self]:
        """Internal helper to execute a Select query and return scalars."""
        logger.debug(f"Executing query for {cls.__name__} with session {session}: {query}")
        result = await session.execute(query)
        return result.scalars()

    @classmethod
    async def all(
        cls, session: AsyncSession, query: Select[tuple[Self]] | None = None, limit: int | None = None
    ) -> Sequence[Self]:
        """
        Returns all instances matching the query.

        Args:
            session: The active AsyncSession to execute with.
            query: An optional Select query object. If None, selects all.
            limit: Optional limit on the number of results.

        Returns:
            A sequence of model instances.
        """
        q = query if query is not None else cls.select()
        if limit is not None:
            q = q.limit(limit)

        logger.debug(f"Fetching all results for query on {cls.__name__} (limit: {limit})")
        result = await cls._execute_query(q, session)
        return result.all()

    @classmethod
    async def first(
        cls,
        session: AsyncSession,
        query: Select[tuple[Self]] | None = None,
        order_by: Any = None,  # ColumnElement or similar
    ) -> Self | None:
        """
        Returns the first instance matching the query, optionally ordered.

        Args:
            session: The active AsyncSession to execute with.
            query: An optional Select query object. If None, selects all.
            order_by: Optional column or ordering expression. Defaults to PK ascending.

        Returns:
            The first matching model instance or None.
        """
        q = query if query is not None else cls.select()

        if order_by is None:
            # Default order by primary key ascending if possible
            try:
                pk_col = cls.__table__.primary_key.columns.values()[0]
                q = q.order_by(pk_col.asc())
                logger.debug(f"Defaulting order_by to PK: {pk_col.name} asc")
            except (AttributeError, IndexError):
                logger.warning(f"Could not determine default PK for ordering in first() for {cls.__name__}")
                # Proceed without ordering if PK cannot be found
        else:
            q = q.order_by(order_by)

        q = q.limit(1)
        logger.debug(f"Fetching first result for query on {cls.__name__}")
        result = await cls._execute_query(q, session)
        return result.first()

    @classmethod
    async def find_by(cls, session: AsyncSession, *args, **kwargs) -> Self | None:
        """
        Returns the first instance matching the given criteria.

        Combines `where()` and `first()`.

        Args:
            session: The active AsyncSession to execute with.
            *args: Positional WHERE clause elements.
            **kwargs: Keyword arguments for equality filters.

        Returns:
            The first matching model instance or None.
        """
        logger.debug(f"Finding first {cls.__name__} by criteria: args={args}, kwargs={kwargs}")
        query = cls.where(*args, **kwargs)
        return await cls.first(session=session, query=query)  # Default ordering by PK

    @classmethod
    async def get(cls, session: AsyncSession, pk: Any) -> Self | None:
        """
        Returns an instance by its primary key using the provided session.

        Args:
            session: The active AsyncSession.
            pk: The primary key value.

        Returns:
            The model instance or None if not found.
        """
        logger.debug(f"Getting {cls.__name__} by PK: {pk} using session {session}")
        try:
            return await session.get(cls, pk)
        except SQLAlchemyError as e:
            logger.error(f"Error getting {cls.__name__} by PK {pk} with session {session}: {e}", exc_info=True)
            raise e

    @classmethod
    async def count(cls, session: AsyncSession, query: Select[Self] | None = None) -> int:
        """
        Returns the count of instances matching the query.

        Args:
            session: The active AsyncSession.
            query: An optional Select query object. If None, counts all.

        Returns:
            The total number of matching rows.
        """
        q = query if query is not None else cls.select()

        # Construct a count query based on the original query's WHERE clause etc.
        # Reset limit/offset/order_by for count
        count_q = sa.select(func.count()).select_from(q.order_by(None).limit(None).offset(None).subquery())

        logger.debug(f"Executing count query for {cls.__name__} with session {session}: {count_q}")
        try:
            result = await session.execute(count_q)
            count_scalar = result.scalar_one_or_none()
            return count_scalar if count_scalar is not None else 0
        except SQLAlchemyError as e:
            logger.error(f"Error executing count query for {cls.__name__} with session {session}: {e}", exc_info=True)
            raise e

    @classmethod
    def pydantic_schema(cls) -> type[Schema]:
        """
        Return the Pydantic schema for this model.

        Note:
            This method generates a Pydantic model at runtime, which cannot be
            understood by static type checkers like Mypy. For type-safe applications,
            it is strongly recommended to define Pydantic schemas manually.
        """
        if not cls.__pydantic_initialized__:
            cls.__pydantic_schema__ = Schema[cls]
            # Initialize the Pydantic schema if not already done
            cls.__pydantic_schema__.add_fields(**cls.__columns__fields__())
            cls.__pydantic_initialized__ = True
        return cls.__pydantic_schema__

    def to_pydantic(self) -> Schema:
        """
        Converts the model instance to its dynamically generated Pydantic schema instance.

        Note:
            This method uses a Pydantic model generated at runtime, which cannot be
            understood by static type checkers like Mypy. For type-safe applications,
            it is strongly recommended to define Pydantic schemas manually and use
            `YourSchema.model_validate(self)` for conversion.
        """
        return self.pydantic_schema()(**self.to_dict())
