import logging
import uuid
from datetime import datetime
from typing import Self

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, MappedAsDataclass, declared_attr, mapped_column

logger = logging.getLogger(__name__)


class PKMixin(MappedAsDataclass):
    __abstract__ = True
    """
    Primary key mixin combined with AlchemyModel functionality.
    To be included in AlchemyModel subclasses only
    """

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
    async def find(cls, session: AsyncSession, pk_uuid: uuid.UUID) -> Self | None:
        """Return the instance with the given UUID primary key."""
        return await session.get(cls, pk_uuid)


class UpdateMixin(MappedAsDataclass):
    __abstract__ = True
    """
    Update/create timestamp tracking mixin combined with AlchemyModel functionality.
    To be included in AlchemyModel subclasses only
    """

    @declared_attr
    def created_at(cls) -> Mapped[datetime]:
        return mapped_column(server_default=func.now(), init=False)

    @declared_attr
    def updated_at(cls) -> Mapped[datetime]:
        return mapped_column(default=func.now(), onupdate=func.now(), init=False)

