import logging
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Self

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, MappedAsDataclass, declared_attr, mapped_column

from .activerecord import ActiveRecord
from .select import Select

logger = logging.getLogger(__name__)


class PKMixin(MappedAsDataclass, ActiveRecord):
    """Primary key mixin combined with ActiveRecord functionality."""

    @declared_attr
    def id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            primary_key=True,
            default_factory=uuid.uuid4,
            server_default=func.gen_random_uuid(),
            kw_only=True,
            init=False,
        )

    @classmethod
    async def find(cls, pk_uuid: uuid.UUID, session: AsyncSession | None = None) -> Self | None:
        """Return the instance with the given UUID primary key."""
        # Uses the optimized session.get() method inherited via ActiveRecord.get
        return await cls.get(pk_uuid, session=session)


class UpdateMixin(MappedAsDataclass, ActiveRecord):
    """Update/create timestamp tracking mixin combined with ActiveRecord functionality."""

    @declared_attr
    def created_at(cls) -> Mapped[datetime]:
        return mapped_column(server_default=func.now(), init=False)

    @declared_attr
    def updated_at(cls) -> Mapped[datetime]:
        return mapped_column(default=func.now(), onupdate=func.now(), init=False)

    @classmethod
    async def last_modified(cls, session: AsyncSession | None = None) -> Self | None:
        """Returns the most recently updated instance."""
        logger.debug(f"Finding last modified record for {cls.__name__}")
        query = cls.select().order_by(cls.updated_at.desc())  # Removed session=session
        return await cls.first(query=query, session=session)  # Use first() with the query

    @classmethod
    async def last_created(cls, session: AsyncSession | None = None) -> Self | None:
        """Returns the most recently created instance."""
        logger.debug(f"Finding last created record for {cls.__name__}")
        query = cls.select().order_by(cls.created_at.desc())  # Removed session=session
        return await cls.first(query=query, session=session)

    @classmethod
    async def first_created(cls, session: AsyncSession | None = None) -> Self | None:
        """Returns the first created instance."""
        logger.debug(f"Finding first created record for {cls.__name__}")
        query = cls.select().order_by(cls.created_at.asc())  # Removed session=session
        return await cls.first(query=query, session=session)

    @classmethod
    async def get_since(
        cls, date: datetime, query: Select[Self] | None = None, session: AsyncSession | None = None
    ) -> Sequence[Self]:
        """
        Returns all instances modified since a given datetime.

        Args:
            date: The datetime threshold (exclusive).
            query: An optional base query to further filter.
            session: Optional session to execute with.

        Returns:
            A sequence of model instances modified after the specified date.
        """
        if query is None:
            query = cls.select()  # Removed session=session

        logger.debug(f"Finding {cls.__name__} records modified since {date}")
        # Apply the date filter and order by modification date
        filtered_query = query.where(cls.updated_at > date).order_by(cls.updated_at.desc())

        return await cls.all(query=filtered_query, session=session)
