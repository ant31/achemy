import uuid

import pytest
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column

from achemy import ActiveRecord, UpdateMixin, UUIDPKMixin

# --- Mock Models and Fixtures for test_mixins.py ---


# Base class for mixin test models, following the pattern in demo models
class MockMixinBase(MappedAsDataclass, DeclarativeBase, ActiveRecord):
    pass

class MockPKModel(MockMixinBase, UUIDPKMixin):
    """Model using only UUIDPKMixin for testing."""
    __tablename__ = "mock_pk_models"
    name: Mapped[str] = mapped_column(init=True) # Add a data field

class MockUpdateModel(MockMixinBase, UpdateMixin):
    """Model using only UpdateMixin for testing."""
    __tablename__ = "mock_update_models"
    id: Mapped[int] = mapped_column(primary_key=True, init=False) # Need a PK
    name: Mapped[str] = mapped_column(init=True)

class MockCombinedModel(MockMixinBase, UUIDPKMixin, UpdateMixin):
    """Model using both UUIDPKMixin and UpdateMixin."""
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

