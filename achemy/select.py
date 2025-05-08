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


class Select[TSelect](SaSelect):  # Inherit directly from SQLAlchemy's Select
    """
    Async-aware Select wrapper for ActiveRecord queries.

    Provides helper methods like `scalars()` for convenience.
    """

    inherit_cache: ClassVar[bool] = True

    # Store the target ORM class directly
    _orm_cls: type[TSelect]

    def set_context(self, cls: type[TSelect]):  # Remove session from context
        self._orm_cls = cls
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
        if not session:
            raise ValueError(f"Cannot execute query for {self._orm_cls.__name__}: Session is required.")

        try:
            logger.debug(f"Executing query for {self._orm_cls.__name__} with session {session}")
            result = await session.execute(self)
            return result.scalars()
        except SQLAlchemyError as e:
            logger.error(f"Error executing scalars query for {self._orm_cls.__name__}: {e}", exc_info=True)
            raise e
