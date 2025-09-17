import logging
import uuid
from datetime import datetime

from sqlalchemy import Integer, Uuid, func
from sqlalchemy.orm import Mapped, MappedAsDataclass, declared_attr, mapped_column

logger = logging.getLogger(__name__)


class UUIDPKMixin(MappedAsDataclass):
    __abstract__ = True
    """
    Provides a standard, portable UUID primary key column named `id`.

    This mixin uses a client-side `uuid.uuid4` default factory and is
    compatible with any database backend.
    """

    @declared_attr
    def id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            Uuid,
            primary_key=True,
            default_factory=uuid.uuid4,
            kw_only=True,
        )


class PGUUIDPKMixin(MappedAsDataclass):
    __abstract__ = True
    """
    Provides a UUID primary key with a PostgreSQL-specific server-side default.

    This should be used in place of `UUIDPKMixin` for models that will be
    used with a PostgreSQL database to leverage its native UUID generation.
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


class IntPKMixin(MappedAsDataclass):
    __abstract__ = True
    """
    Provides a standard auto-incrementing integer primary key column named `id`.
    """

    @declared_attr
    def id(cls) -> Mapped[int]:
        return mapped_column(Integer, primary_key=True, init=False)


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
