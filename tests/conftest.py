import uuid

import pytest
from tests.models import MockCombinedModel, MockPKModel, MockUpdateModel

# --- Mock Models and Fixtures for test_mixins.py ---


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

