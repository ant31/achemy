import logging
from collections.abc import Sequence
from typing import Any, ClassVar, Self

import sqlalchemy as sa
from pydantic_core import to_jsonable_python
from sqlalchemy import FromClause, ScalarResult, func
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
from typing_extensions import deprecated

# Assuming ActiveEngine is imported from the refactored engine file
from aiochemy.engine import ActiveEngine
from aiochemy.schema import Schema
from aiochemy.select import Select

logger = logging.getLogger(__name__)


# Generic type for the model class

# --- ActiveRecord Core (Async) ---


class ActiveRecord(AsyncAttrs):
    """
    Async ActiveRecord-style base class using SQLAlchemy 2+ ORM.

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
        """Return the active engine associated with this class."""
        if not hasattr(cls, "__active_engine__") or cls.__active_engine__ is None:
            raise ValueError(f"No active engine configured for class {cls.__name__}")
        return cls.__active_engine__

    @classmethod
    def set_engine(cls, engine: ActiveEngine):
        """
        Set the ActiveEngine instance for this class and its subclasses.
        Also retrieves the session factory from the engine.
        """
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
        Raises ValueError if the engine/session factory hasn't been set.
        """
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
    @deprecated("use get_session() instead.")
    async def new_session(cls, session: AsyncSession | None = None) -> AsyncSession:
        """
        Deprecated: Use get_session() instead.
        Creates a new session or returns an existing one.
        """
        logger.warning("new_session() is deprecated. Use get_session() instead.")
        return await cls.get_session(session=session)

    @classmethod
    async def get_session(cls, session: AsyncSession | None = None) -> AsyncSession:
        """
        Gets an AsyncSession instance.

        If an existing session is provided, it's returned directly.
        Otherwise, a new session is created using the class's session factory.

        Args:
            session: An optional existing AsyncSession.

        Returns:
            An active AsyncSession.

        Raises:
            ValueError: If the session factory is not configured.
        """
        if session is not None:
            # If a session is passed, ensure it's active (or handle appropriately)
            # For now, we just return it, assuming it's managed externally if passed.
            logger.debug(f"Using provided session for {cls.__name__}: {session}")
            return session

        # Create a new session from the factory
        factory = cls.session_factory()  # Raises ValueError if not configured
        new_session = factory()
        logger.debug(f"Created new session for {cls.__name__}: {new_session}")
        return new_session

    def obj_session(self) -> AsyncSession | None:
        """Get the session associated with this specific object instance, if tracked."""
        return async_object_session(self)

    @classmethod
    async def _ensure_obj_session(cls, obj: Self, session: AsyncSession | None = None) -> tuple[AsyncSession, Self]:
        """
        Internal helper to ensure an object is associated with a session.

        Gets a session if not provided, merges the object into the session
        if it's not already persistent or detached within that session.

        Args:
            obj: The model instance.
            session: An optional existing session.

        Returns:
            A tuple containing the session and the (potentially merged) object.
        """
        if session is None:
            session = obj.obj_session()  # Check if already associated

        if session is None:
            # If still no session, get a default one
            session = await cls.get_session()
            logger.debug(f"Got default session {session} for object {obj}")
            # Merge the object into the new session to attach it
            logger.debug(f"Merging object {obj} into session {session}")
            obj = await session.merge(obj)
        elif obj not in session:
            # If session provided, but object not in it, merge it.
            logger.debug(f"Object {obj} not in provided session {session}, merging.")
            obj = await session.merge(obj)

        return session, obj

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
            # Fallback for non-mapped objects? Unlikely for ActiveRecord.
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
    async def add(cls, obj: Self, commit: bool = False, session: AsyncSession | None = None) -> Self:
        """Add this instance to the database."""
        if session:
            # Use provided session directly
            s = session
            try:
                s.add(obj)
                if commit:
                    await s.commit()
                    await s.refresh(obj)
                # No close/rollback needed for externally managed session
            except SQLAlchemyError as e:
                # Let caller handle rollback if session is external
                logger.error(f"Error adding {obj} with provided session {s}: {e}", exc_info=True)
                raise e
        else:
            # Manage session internally
            async with await cls.get_session() as s:
                try:
                    s.add(obj)
                    if commit:
                        await s.commit()
                        await s.refresh(obj)
                    else:
                        # Flush to get ID etc. if not committing
                        await s.flush([obj])
                        s.expire(obj)  # Expire to reflect potential DB defaults on next access
                except SQLAlchemyError as e:
                    # Rollback is handled by async with context manager on error
                    logger.error(f"Error adding {obj} with internal session {s}: {e}", exc_info=True)
                    raise e
        return obj

    async def save(self, commit: bool = False, session: AsyncSession | None = None) -> Self:
        """Add this instance to the database."""
        return await self.add(self, commit, session)

    @classmethod
    async def add_all(
        cls,
        objs: list[Self],
        commit: bool = True,
        session: AsyncSession | None = None,
    ) -> Sequence[Self]:
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

        s = await cls.get_session(session)
        try:
            # If session was provided, execute directly
            if session:
                return await cls._add_all_to_session(objs, s, commit)
            # Otherwise, use the session within its context manager
            else:
                async with s:  # type: ignore # s is AsyncSession when session is None
                    return await cls._add_all_to_session(objs, s, commit)
        except SQLAlchemyError as e:
            # Log the error originating from _add_all_to_session or session management
            logger.error(f"Error during add_all operation for {cls.__name__}: {e}", exc_info=True)
            # Rollback is handled by the context manager if session was internal,
            # or needs to be handled by the caller if session was provided.
            raise e
        # The return is handled within the try block

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
            await session.flush(objs)  # Flush if not committing
            for obj in objs:
                session.expire(obj)  # Expire after flush
        return objs

    @classmethod
    async def delete(cls, obj: Self, commit: bool = True, session: AsyncSession | None = None) -> None:
        """
        Deletes the instance from the database.

        Args:
            obj: The instance to delete.
            commit: If True, commit the session after deletion.
            session: Optional session to use.

        Raises:
            SQLAlchemyError: If database commit fails.
        """
        if session:
            # Use provided session
            s, obj_in_session = await cls._ensure_obj_session(obj, session)  # Ensure obj is in this session
            try:
                logger.debug(f"Deleting instance {obj_in_session} from provided session {s}")
                await s.delete(obj_in_session)
                if commit:
                    await s.commit()
                else:
                    await s.flush([obj_in_session])  # Flush if not committing
            except SQLAlchemyError as e:
                logger.error(f"Error deleting {obj_in_session} with provided session {s}: {e}", exc_info=True)
                # Let caller handle rollback
                raise e
        else:
            # Manage session internally
            async with await cls.get_session() as s:
                # Ensure object is attached to *this* internal session before delete
                obj_in_session = await s.merge(obj)  # Merge ensures it's attached
                try:
                    logger.debug(f"Deleting instance {obj_in_session} from internal session {s}")
                    await s.delete(obj_in_session)
                    if commit:
                        await s.commit()
                    else:
                        await s.flush([obj_in_session])  # Flush if not committing
                except SQLAlchemyError as e:
                    logger.error(f"Error deleting {obj_in_session} with internal session {s}: {e}", exc_info=True)
                    # Rollback handled by async with
                    raise e

    # --- Instance State Management ---

    async def refresh(self, attribute_names: Sequence[str] | None = None, session: AsyncSession | None = None) -> Self:
        """
        Refreshes the instance's attributes from the database.

        Args:
            attribute_names: Optional sequence of specific attribute names to refresh.
            session: Optional session to use.

        Returns:
            The refreshed instance itself.
        """
        s, obj_in_session = await self.__class__._ensure_obj_session(self, session)
        try:
            logger.debug(f"Refreshing attributes {attribute_names or 'all'} for {obj_in_session} in session {s}")
            await s.refresh(obj_in_session, attribute_names=attribute_names)
        except SQLAlchemyError as e:
            logger.error(f"Error refreshing instance {obj_in_session}: {e}", exc_info=True)
            # No rollback needed for refresh usually, but re-raise the error
            raise e
        return obj_in_session

    async def expire(self, attribute_names: Sequence[str] | None = None, session: AsyncSession | None = None) -> Self:
        """
        Expires the instance's attributes, causing them to be reloaded on next access.

        Args:
            attribute_names: Optional sequence of specific attribute names to expire.
            session: Optional session to use.

        Returns:
            The instance itself.
        """
        s, obj_in_session = await self.__class__._ensure_obj_session(self, session)
        logger.debug(f"Expiring attributes {attribute_names or 'all'} for {obj_in_session} in session {s}")
        s.expire(obj_in_session, attribute_names=attribute_names)
        return obj_in_session

    async def expunge(self, session: AsyncSession | None = None) -> Self:
        """
        Removes the instance from the session. The object becomes detached.

        Args:
            session: Optional session to use.

        Returns:
            The (now detached) instance itself.
        """
        s, obj_in_session = await self.__class__._ensure_obj_session(self, session)
        logger.debug(f"Expunging instance {obj_in_session} from session {s}")
        s.expunge(obj_in_session)
        return obj_in_session

    async def is_modified(self, session: AsyncSession | None = None) -> bool:
        """
        Checks if the instance has pending changes in the session.

        Args:
            session: Optional session to use.

        Returns:
            True if the object is considered modified within the session, False otherwise.
        """
        s, obj_in_session = await self.__class__._ensure_obj_session(self, session)
        # The session tracks modifications. Check the 'dirty' collection.
        is_dirty = obj_in_session in s.dirty
        logger.debug(f"Instance {obj_in_session} modified status in session {s}: {is_dirty}")
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
    def select(cls, *args, **kwargs) -> Select[Self]:  # Remove session argument
        """
        Creates a base SQLAlchemy Select statement targeting this class.

        Args:
            *args: Positional arguments passed to SQLAlchemy's select().
            **kwargs: Keyword arguments passed to SQLAlchemy's select().

        Returns:
            A Select object ready for filtering, ordering, etc.
        """
        # Create instance of our Select subclass
        query = Select(cls, *args, **kwargs)  # Pass the target class 'cls'
        # Set the context (target ORM class only)
        query.set_context(cls)

        logger.debug(f"Created Select query for {cls.__name__}")
        return query

    @classmethod
    def where(cls, *args, **kwargs) -> Select[Self]:  # Remove session argument
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
    async def _execute_query(cls, query: Select[Self], session: AsyncSession) -> ScalarResult[Self]:  # Session required
        """Internal helper to execute a Select query and return scalars."""
        # The Select object now requires the session in its scalars() method
        logger.debug(f"Executing query for {cls.__name__} with session {session}: {query}")
        # Pass the required session to scalars()
        return await query.scalars(session=session)

    @classmethod
    async def all(
        cls, query: Select[Self] | None = None, limit: int | None = None, session: AsyncSession | None = None
    ) -> Sequence[Self]:
        """
        Returns all instances matching the query.

        Args:
            query: An optional Select query object. If None, selects all.
            limit: Optional limit on the number of results.
            session: Optional session to execute with.

        Returns:
            A sequence of model instances.
        """
        q = query if query is not None else cls.select()  # No session here
        if limit is not None:
            q = q.limit(limit)

        logger.debug(f"Fetching all results for query on {cls.__name__} (limit: {limit})")
        # Manage session context if none provided
        if session:
            result = await cls._execute_query(q, session)
            return result.all()
        else:
            async with await cls.get_session() as s:
                result = await cls._execute_query(q, s)
                # Eagerly load results before session closes
                return result.all()

    @classmethod
    async def first(
        cls,
        query: Select[Self] | None = None,
        order_by: Any = None,  # ColumnElement or similar
        session: AsyncSession | None = None,
    ) -> Self | None:
        """
        Returns the first instance matching the query, optionally ordered.

        Args:
            query: An optional Select query object. If None, selects all.
            order_by: Optional column or ordering expression. Defaults to PK ascending.
            session: Optional session to execute with.

        Returns:
            The first matching model instance or None.
        """
        q = query if query is not None else cls.select()  # No session here

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
        # Manage session context if none provided
        if session:
            result = await cls._execute_query(q, session)
            return result.first()
        else:
            async with await cls.get_session() as s:
                result = await cls._execute_query(q, s)
                # Eagerly load result before session closes
                return result.first()

    @classmethod
    async def find_by(cls, *args, session: AsyncSession | None = None, **kwargs) -> Self | None:
        """
        Returns the first instance matching the given criteria.

        Combines `where()` and `first()`.

        Args:
            *args: Positional WHERE clause elements.
            session: Optional session to execute with.
            **kwargs: Keyword arguments for equality filters.

        Returns:
            The first matching model instance or None.
        """
        logger.debug(f"Finding first {cls.__name__} by criteria: args={args}, kwargs={kwargs}")
        query = cls.where(*args, **kwargs)  # No session here
        # Pass the session explicitly to first if provided here
        # first() will handle context if session is None
        return await cls.first(query=query, session=session)  # Default ordering by PK

    @classmethod
    async def get(cls, pk: Any, session: AsyncSession | None = None) -> Self | None:
        """
        Returns an instance by its primary key.

        Args:
            pk: The primary key value.
            session: Optional session to execute with.

        Returns:
            The model instance or None if not found.
        """
        # Manage session context if none provided
        if session:
            logger.debug(f"Getting {cls.__name__} by PK: {pk} using provided session {session}")
            try:
                return await session.get(cls, pk)
            except SQLAlchemyError as e:
                logger.error(f"Error getting {cls.__name__} by PK {pk} with provided session: {e}", exc_info=True)
                raise e
        else:
            async with await cls.get_session() as s:
                logger.debug(f"Getting {cls.__name__} by PK: {pk} using new session {s}")
                try:
                    # Use the context-managed session s
                    return await s.get(cls, pk)
                except SQLAlchemyError as e:
                    logger.error(f"Error getting {cls.__name__} by PK {pk} with new session: {e}", exc_info=True)
                    raise e  # Re-raise after logging

    @classmethod
    async def count(cls, query: Select[Self] | None = None, session: AsyncSession | None = None) -> int:
        """
        Returns the count of instances matching the query.

        Args:
            query: An optional Select query object. If None, counts all.
            session: Optional session to execute with.

        Returns:
            The total number of matching rows.
        """
        q = query if query is not None else cls.select()  # No session here

        # Construct a count query based on the original query's WHERE clause etc.
        # Reset limit/offset/order_by for count
        count_q = sa.select(func.count()).select_from(q.order_by(None).limit(None).offset(None).subquery())

        # Manage session context if none provided
        if session:
            logger.debug(f"Executing count query for {cls.__name__} with provided session {session}: {count_q}")
            try:
                result = await session.execute(count_q)
                count_scalar = result.scalar_one_or_none()
                return count_scalar if count_scalar is not None else 0
            except SQLAlchemyError as e:
                logger.error(
                    f"Error executing count query for {cls.__name__} with provided session: {e}", exc_info=True
                )
                raise e
        else:
            async with await cls.get_session() as s:
                logger.debug(f"Executing count query for {cls.__name__} with new session {s}: {count_q}")
                try:
                    result = await s.execute(count_q)
                    count_scalar = result.scalar_one_or_none()
                    return count_scalar if count_scalar is not None else 0
                except SQLAlchemyError as e:
                    logger.error(f"Error executing count query for {cls.__name__} with new session: {e}", exc_info=True)
                    raise e

    @classmethod
    def pydantic_schema(cls) -> type[Schema]:
        """Return the Pydantic schema for this model."""
        if not cls.__pydantic_initialized__:
            cls.__pydantic_schema__ = Schema[cls]
            # Initialize the Pydantic schema if not already done
            cls.__pydantic_schema__.add_fields(**cls.__columns__fields__())
            cls.__pydantic_initialized__ = True
        return cls.__pydantic_schema__

    def to_pydantic(self) -> Schema:
        return self.pydantic_schema()(**self.to_dict())
