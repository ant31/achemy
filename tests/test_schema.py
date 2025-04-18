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

def test_schema_add_fields_simple(mock_schema_class, mock_model_class):
    """Test dynamically adding fields with default values."""

    # Define a temporary schema inheriting from the fixture schema
    class TempSchemaSimple(mock_schema_class):
        pass # Inherits fields and config from mock_schema_class

    # Add fields *before* creating an instance of the temporary schema
    TempSchemaSimple.add_fields(
        extra_field_str="default_string",
        extra_field_int=99
    )

    # Verify fields exist on the temporary class
    assert "extra_field_str" in TempSchemaSimple.model_fields
    assert "extra_field_int" in TempSchemaSimple.model_fields
    # Verify base fields still exist
    assert "name" in TempSchemaSimple.model_fields

    # Create instance and check defaults
    schema_instance = TempSchemaSimple(name="Test Add Fields")
    assert schema_instance.extra_field_str == "default_string"
    assert schema_instance.extra_field_int == 99

    # Create instance overriding defaults
    schema_instance_override = TempSchemaSimple(
        name="Test Add Fields Override",
        extra_field_str="overridden",
        extra_field_int=100
    )
    assert schema_instance_override.extra_field_str == "overridden"
    assert schema_instance_override.extra_field_int == 100

    # No cleanup needed as TempSchemaSimple is local to this test


def test_schema_add_fields_typed(mock_schema_class, mock_model_class):
    """Test dynamically adding fields with type and default."""

    # Define a temporary schema inheriting from the fixture schema
    class TempSchemaTyped(mock_schema_class):
       pass # Inherits fields and config
    TempSchemaTyped.add_fields(
        typed_field=(str, "typed_default"),
        optional_typed_field=(bool | None, None)
    )

    assert "typed_field" in TempSchemaTyped.model_fields
    assert TempSchemaTyped.model_fields["typed_field"].annotation == str | None
    assert "optional_typed_field" in TempSchemaTyped.model_fields
    # Pydantic resolves Optional[bool] to Union[bool, None], check type compatibility
    # Compare against the expected pipe syntax type hint
    optional_field_annotation = TempSchemaTyped.model_fields["optional_typed_field"].annotation
    expected_annotation = bool | NoneType
    assert optional_field_annotation == expected_annotation # Use == for type equality check


    # Test instantiation and validation
    instance1 = TempSchemaTyped(name="Typed Fields")
    assert instance1.typed_field == "typed_default"
    assert instance1.optional_typed_field is None

    instance2 = TempSchemaTyped(
        name="Typed Fields Override",
        typed_field="override",
        optional_typed_field=True
    )
    assert instance2.typed_field == "override"
    assert instance2.optional_typed_field is True

    # Test type validation
    with pytest.raises(ValidationError):
        TempSchemaTyped(name="Bad Type", typed_field=123) # Expecting str

    with pytest.raises(ValidationError):
        TempSchemaTyped(name="Bad Optional Type", optional_typed_field="not a bool")


def test_schema_add_fields_invalid_definition(mock_schema_class, mock_model_class):
    """Test error handling for invalid field definitions in add_fields."""
    # Define a temporary schema inheriting from the fixture schema
    class InvalidDefSchema(mock_schema_class):
        pass

    with pytest.raises(ValueError, match="Field definitions should either be a tuple"):
        # Providing a tuple as the default value directly is ambiguous
        InvalidDefSchema.add_fields(bad_field=("tuple", "as", "default"))

    # Check tuple definition length
    with pytest.raises(ValueError, match="Field definitions should either be a tuple"):
        InvalidDefSchema.add_fields(bad_tuple_def=("just_type",)) # Too short

    with pytest.raises(ValueError, match="Field definitions should either be a tuple"):
        InvalidDefSchema.add_fields(bad_tuple_def=(str, "default", "extra")) # Too long


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


def test_schema_add_fields_existing_annotation(mock_schema_class):
    """Test add_fields when the field name exists in annotations but only default is provided."""

    # Define a temporary schema inheriting from the fixture schema
    class TempSchemaExisting(mock_schema_class):
        pass # Inherits fields and config

    # Add the 'value' field again, but only providing a default value.
    # The type annotation (int | None) should be picked up from the existing annotation.
    TempSchemaExisting.add_fields(
        value=999 # Provide only default, type should be inferred from existing annotation
    )

    # Verify the field still exists and its type annotation is correct
    assert "value" in TempSchemaExisting.model_fields
    assert TempSchemaExisting.model_fields["value"].annotation == (int | None)

    # Create an instance - the new default should apply if 'value' isn't provided
    instance_default = TempSchemaExisting(name="Test Existing Default")
    assert instance_default.value == 999

    # Create an instance providing the value
    instance_override = TempSchemaExisting(name="Test Existing Override", value=111)
    assert instance_override.value == 111

    # Test type validation still works based on original annotation
    with pytest.raises(ValidationError):
        TempSchemaExisting(name="Bad Type Existing", value="not a number")
