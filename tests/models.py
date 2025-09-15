"""
Shared models for tests.
"""

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from achemy import Base, UpdateMixin, UUIDPKMixin


# Base class for mixin test models, following the pattern in demo models
class MockMixinBase(Base):
    __abstract__ = True


class MockPKModel(MockMixinBase, UUIDPKMixin):
    """Model using only UUIDPKMixin for testing."""

    __tablename__ = "mock_pk_models"
    name: Mapped[str] = mapped_column(init=True)  # Add a data field


class MockUpdateModel(MockMixinBase, UpdateMixin):
    """Model using only UpdateMixin for testing."""

    __tablename__ = "mock_update_models"
    id: Mapped[int] = mapped_column(primary_key=True, init=False)  # Need a PK
    name: Mapped[str] = mapped_column(init=True)


class MockCombinedModel(MockMixinBase, UUIDPKMixin, UpdateMixin):
    """Model using both UUIDPKMixin and UpdateMixin."""

    __tablename__ = "mock_combined_models"
    name: Mapped[str] = mapped_column(init=True)
    value: Mapped[int | None] = mapped_column(default=None, init=True)

    __table_args__ = (UniqueConstraint("name", name="uq_mock_combined_models_name"),)
