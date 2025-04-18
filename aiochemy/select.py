import logging
from typing import TYPE_CHECKING, ClassVar, TypeVar

from sqlalchemy import ScalarResult
from sqlalchemy import Select as SaSelect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from .activerecord import ActiveRecord


logger = logging.getLogger(__name__)

TSelect = TypeVar("TSelect", bound="ActiveRecord")


class Select(SaSelect[tuple[TSelect]]):  # Inherit directly from SQLAlchemy's Select
    """
    Async-aware Select wrapper for ActiveRecord queries.

    Provides helper methods like `scalars()` for convenience.
    """

    # inherit_cache is a SQLAlchemy attribute, keep it if needed for specific caching behaviors
    inherit_cache: ClassVar[bool] = True

    # Store the target ORM class directly
    _orm_cls: type[TSelect]
    # _session: AsyncSession | None # Session is no longer stored here

    # # Need to override __init__ carefully to maintain Select's signature
    # # while adding our custom attributes. Using __new__ might be safer
    # but __init__ is often simpler if done right. Let's try __init__.

    # We cannot directly change the signature of __init__ as it breaks Select.
    # Instead, we'll add attributes *after* super().__init__ or use a factory method.

    # Let's use a factory method approach within ActiveRecord.select()
    # to keep this class cleaner and closer to SaSelect.

    # This helper method will be called internally.
    def set_context(self, cls: type[TSelect]):  # Remove session from context
        self._orm_cls = cls
        # self._session = session # Session no longer stored
        return self  # Return self for chaining

    async def scalars(self, session: AsyncSession) -> ScalarResult[TSelect]:  # Session is now required
        """
        Executes the query and returns a ScalarResult yielding ORM instances.

        Args:
            session: The AsyncSession to execute the query with.

        Returns:
            A ScalarResult object.

        Raises:
            SQLAlchemyError: If the database query fails.
            ValueError: If the session is invalid (though type hint enforces it).
            SQLAlchemyError: If the database query fails.
        """
        # execution_session = session or self._session # Session is now required
        # if not execution_session:
        #     # Try to get a session from the class if none was provided
        #     logger.debug(f"No explicit session for scalars(), getting session from {self._orm_cls.__name__}")
        #     execution_session = await self._orm_cls.get_session()  # Use class method to get session

        # if not execution_session:
        #     raise ValueError(f"Cannot execute query for {self._orm_cls.__name__}: No session provided or available.")

        if not session:  # Basic check, though type hint should prevent None
            raise ValueError(f"Cannot execute query for {self._orm_cls.__name__}: Session is required.")

        try:
            logger.debug(f"Executing query for {self._orm_cls.__name__} with session {session}")
            result = await session.execute(self)
            return result.scalars()
        except SQLAlchemyError as e:
            logger.error(f"Error executing scalars query for {self._orm_cls.__name__}: {e}", exc_info=True)
            raise e
