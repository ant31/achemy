from types import NoneType  # Import NoneType

import pytest
from pydantic import ValidationError

# --- Test Cases ---

def test_schema_initialization(mock_schema_class):
    """Test creating a schema instance."""
    data = {"name": "Test Name", "value": 123}
    schema_instance = mock_schema_class(**data)
    assert schema_instance.name == "Test Name"
    assert schema_instance.value == 123

def test_schema_validation(mock_schema_class):
    """Test Pydantic validation within the schema."""
    # Missing required field 'name'
    with pytest.raises(ValidationError):
        mock_schema_class(value=456)

    # Incorrect type for 'value'
    with pytest.raises(ValidationError):
        mock_schema_class(name="Test Name", value="not a number")

def test_schema_to_model(mock_schema_class, mock_model_class):
    """Test converting a schema instance to a model instance."""
    schema_instance = mock_schema_class(name="Schema to Model", value=789)
    model_instance = schema_instance.to_model(mock_model_class)

    assert isinstance(model_instance, mock_model_class)
    assert model_instance.name == "Schema to Model"
    assert model_instance.value == 789
    # 'id' will not be set as it's not in the schema

def test_schema_from_model(mock_schema_class, mock_model_class):
    """Test creating a schema instance from a model instance."""
    model_instance = mock_model_class(name="Model to Schema", value=101)
    # Simulate adding an ID as if it came from DB
    model_instance.id = 1

    schema_instance = mock_schema_class.model_validate(model_instance)

    assert schema_instance.name == "Model to Schema"
    assert schema_instance.value == 101
    # 'id' should not be included by default unless explicitly added to schema

def test_schema_extra_fields_allowed(mock_schema_class):
    """Test that extra fields are allowed by default config."""
    data = {"name": "Test Name", "value": 123, "unexpected_field": "some_value"}
    # Should not raise validation error if extra='allow'
    try:
        schema_instance = mock_schema_class(**data)
        assert schema_instance.name == "Test Name"
        assert schema_instance.value == 123
        # Check if the extra field is accessible (depends on Pydantic version/config)
        # In Pydantic v2 with extra='allow', it's often stored in __pydantic_extra__
        assert getattr(schema_instance, 'unexpected_field', None) == "some_value" or \
               schema_instance.__pydantic_extra__.get('unexpected_field') == "some_value"

    except ValidationError as e:
        pytest.fail(f"Schema validation failed unexpectedly with extra='allow': {e}")


