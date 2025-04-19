import uuid

import pytest
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column

from achemy import ActiveRecord, Base, PKMixin, Schema, UpdateMixin

# --- Mock Model and Schema for test_schema.py ---

class MockModel(Base):
    """A simple mock ActiveRecord model for testing schemas."""
    __tablename__ = "mock_models" # Required by Base/ActiveRecord

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    value: Mapped[int | None] = mapped_column(default=None)

    # Add __init__ if not using MappedAsDataclass or similar helpers
    # Base doesn't inherit MappedAsDataclass by default
    def __init__(self, name: str, value: int | None = None, **kw):
        super().__init__(**kw) # Pass extra kwargs to SQLAlchemy internals if needed
        self.name = name
        self.value = value


class MockSchema(Schema[MockModel]):
    """Schema corresponding to MockModel."""
    name: str
    value: int | None = None
    # We don't include 'id' here typically, as it's often DB-generated


@pytest.fixture(scope="session") # Use session scope as the class definition doesn't change
def mock_model_class():
    """Provides the MockModel class."""
    return MockModel

@pytest.fixture(scope="session") # Use session scope as the base class definition doesn't change
def mock_schema_class():
    """Provides the MockSchema class."""
    # Return a fresh copy or the class itself.
    # Be mindful if tests modify the class directly.
    return MockSchema


# --- Mock Models and Fixtures for test_mixins.py ---


# Base class for mixin test models, following the pattern in demo models
class MockMixinBase(MappedAsDataclass, DeclarativeBase, ActiveRecord):
    pass

class MockPKModel(MockMixinBase, PKMixin):
    """Model using only PKMixin for testing."""
    __tablename__ = "mock_pk_models"
    name: Mapped[str] = mapped_column(init=True) # Add a data field

class MockUpdateModel(MockMixinBase, UpdateMixin):
    """Model using only UpdateMixin for testing."""
    __tablename__ = "mock_update_models"
    id: Mapped[int] = mapped_column(primary_key=True, init=False) # Need a PK
    name: Mapped[str] = mapped_column(init=True)

class MockCombinedModel(MockMixinBase, PKMixin, UpdateMixin):
    """Model using both PKMixin and UpdateMixin."""
    __tablename__ = "mock_combined_models"
    name: Mapped[str] = mapped_column(init=True)


@pytest.fixture(scope="session")
def mock_pk_model_class():
    """Provides the MockPKModel class."""
    return MockPKModel

@pytest.fixture(scope="session")
def mock_update_model_class():
    """Provides the MockUpdateModel class."""
    return MockUpdateModel

@pytest.fixture(scope="session")
def mock_combined_model_class():
    """Provides the MockCombinedModel class."""
    return MockCombinedModel


# --- Other Utility fixtures ---
@pytest.fixture(scope="function")
def unique_id():
    """Generate a unique ID for test data"""
    return str(uuid.uuid4())

