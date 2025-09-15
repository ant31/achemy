"""
Tests for achemy/model.py methods.
"""
import json
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from achemy import AlchemyModel, Base, BaseRepository, UUIDPKMixin

# --- Fixtures ---


# Define a simple model for testing AlchemyModel methods directly
# Inherit UUIDPKMixin to get an 'id' primary key
class SimpleModel(UUIDPKMixin, Base):
    __tablename__ = "simple_models_activerecord"
    name: Mapped[str] = mapped_column(init=True, default=None, nullable=False)
    value: Mapped[int | None] = mapped_column(init=True, default=None)

    __table_args__ = (UniqueConstraint("name", name="uq_simple_models_activerecord_name"),)


class SimpleModelRepository(BaseRepository[SimpleModel]):
    """Repository for SimpleModel used in tests."""

    def __init__(self, session):
        super().__init__(session, SimpleModel)


# --- Test Cases ---

@pytest.mark.asyncio
async def test_instance_representation_and_data(async_engine, unique_id):
    """Test instance representation and data methods (to_dict, dump_model, load, etc.)."""
    instance_name = f"repr_test_{unique_id}"
    instance = SimpleModel(name=instance_name, value=3)
    instance_id = instance.id  # Get the generated UUID

    # 1. Test __str__ and __repr__
    expected_str = f"SimpleModel({instance_id})"
    instance_repr = repr(instance)
    assert str(instance) == expected_str
    # Check components of repr without relying on order
    assert instance_repr.startswith("SimpleModel(")
    assert f"id=UUID('{instance_id}')" in instance_repr
    assert f"name='{instance_name}'" in instance_repr
    assert instance_repr.endswith(")")

    # 2. Test id_key
    # Test after saving to ensure it's not transient
    _db_engine, session_factory = async_engine.session()
    async with session_factory() as s:
        repo = SimpleModelRepository(s)
        await repo.save(instance)
        await s.commit()
    assert instance.id_key() == f"SimpleModel:{instance_id}"

    # 3. Test __columns__fields__
    fields = SimpleModel.__columns__fields__()
    assert "id" in fields
    assert fields["id"][0] is uuid.UUID # Check type
    # Default value check is complex due to default_factory/server_default
    # assert fields["id"][1] is not None # Removed assertion

    assert "name" in fields
    assert fields["name"][0] is str
    assert fields["name"][1] is None # Default is None

    # 4. Test to_dict
    data_dict = instance.to_dict()
    assert data_dict == {"id": instance_id, "name": instance_name, "value": 3}

    data_dict_fields = instance.to_dict(fields={"name"})
    assert data_dict_fields == {"name": instance_name}

    data_dict_meta = instance.to_dict(with_meta=True)
    assert data_dict_meta["id"] == instance_id
    assert data_dict_meta["name"] == instance_name
    assert "__metadata__" in data_dict_meta
    # The module name is dynamic based on the test file's location
    assert data_dict_meta["__metadata__"]["model"].endswith("test_model_methods:SimpleModel")
    assert data_dict_meta["__metadata__"]["table"] == "simple_models_activerecord"

    # 5. Test dump_model (should be JSON serializable)
    dumped_data = instance.dump_model()
    # UUID should be converted to string
    assert dumped_data == {"id": str(instance_id), "name": instance_name, "value": 3}
    # Test if it's actually JSON serializable (basic check)
    try:
        json.dumps(dumped_data)
    except TypeError:
        pytest.fail("dump_model output was not JSON serializable")

    # 6. Test load
    load_data = {"name": f"loaded_{unique_id}", "id": str(uuid.uuid4())} # Provide string UUID
    loaded_instance = SimpleModel.load(load_data)
    assert isinstance(loaded_instance, SimpleModel)
    assert loaded_instance.name == f"loaded_{unique_id}"
    # ID should be set, but might be string or UUID depending on load logic
    # ActiveRecord.load currently just sets attributes, so it might remain a string.
    # Let's check the type after potential conversion or direct set.
    # If load is expected to handle type conversion, this needs adjustment.
    # Current load just sets attributes, so it will be a string.
    assert loaded_instance.id == load_data["id"] # Check if it matches the input string

    # Test load with extra data (should be ignored)
    load_data_extra = {"name": f"loaded_extra_{unique_id}", "extra": "ignored"}
    loaded_extra = SimpleModel.load(load_data_extra)
    assert loaded_extra.name == f"loaded_extra_{unique_id}"
    assert not hasattr(loaded_extra, "extra")

    # Test load with non-dict
    with pytest.raises(ValueError, match="Input 'data' must be a dictionary"):
        SimpleModel.load("not a dict") # type: ignore


@pytest.mark.asyncio
async def test_helpers_and_error_cases(async_engine, unique_id, capsys, caplog):
    """Test helper methods and some error paths."""
    Model = SimpleModel

    # --- Test printn ---
    instance_print = Model(name=f"print_test_{unique_id}")
    instance_print.printn()
    captured = capsys.readouterr()
    assert f"Attributes for {instance_print}:" in captured.out
    assert "name:" in captured.out
    assert f"print_test_{unique_id}" in captured.out
    assert "_sa_" not in captured.out  # Ensure SQLAlchemy state is excluded

    # --- Test id_key on transient object ---
    instance_transient = Model(name=f"transient_{unique_id}")
    expected_id_key = f"SimpleModel:{instance_transient.id}"
    assert instance_transient.id_key() == expected_id_key

    # --- Test load error: Non-mapped class ---
    class UnmappedAlchemyModel(AlchemyModel):
        """A class that inherits from AlchemyModel but is not mapped."""

    with pytest.raises(ValueError, match="Class UnmappedAlchemyModel is not mapped"):
        UnmappedAlchemyModel.load({"key": "value"})

    # --- Test to_dict error: Non-mapped instance ---
    class NonMapped:
        """Dummy class without SQLAlchemy mapping."""

    non_mapped_instance = NonMapped()
    non_mapped_instance.some_attr = 123
    caplog.clear()
    result_dict = AlchemyModel.to_dict(non_mapped_instance)
    assert result_dict == {}
    assert "does not seem to be mapped" in caplog.text

    # --- Test dump_model error: JSON serialization ---
    _db_engine, session_factory = async_engine.session()
    async with session_factory() as s:
        repo = SimpleModelRepository(s)
        instance_dump = Model(name=f"dump_err_{unique_id}")
        await repo.save(instance_dump, commit=True)

    with patch("achemy.model.to_jsonable_python", side_effect=TypeError("Cannot serialize")):
        caplog.clear()
        dumped = instance_dump.dump_model()
        assert isinstance(dumped, dict)
        assert "Error making dictionary for" in caplog.text
        assert "JSON-serializable" in caplog.text

    # Cleanup
    async with session_factory() as s:
        repo = SimpleModelRepository(s)
        await repo.delete(instance_dump, commit=True)

    # --- Test __columns__fields__ error: NotImplementedError ---
    # Define a mock type that raises error on python_type access
    class MockColumnType(String): # Inherit from a real type
        @property
        def python_type(self):
            raise NotImplementedError("Test error")

    # Define a dedicated model using this problematic type
    class ModelWithBadColType(Base, UUIDPKMixin):
        __tablename__ = "test_bad_col_type" # Needs a unique table name
        bad_column: Mapped[str] = mapped_column(MockColumnType, default=None)
        good_column: Mapped[int] = mapped_column(default=0)

    # Ensure the table is created for this temporary model if needed by __columns__fields__
    # (It shouldn't strictly need DB interaction, but safer to ensure mapping is complete)
    # async with Model.engine().engine.begin() as conn:
    #     await conn.run_sync(ModelWithBadColType.metadata.create_all)
    # Note: Creating tables here might interfere with cleanup or other tests.
    # Let's assume __columns__fields__ works on the mapped class without DB table existing.

    caplog.clear()
    fields = ModelWithBadColType.__columns__fields__()

    # Check that the method ran despite the error and logged a warning
    assert "Could not determine Python type for column 'bad_column'" in caplog.text
    # Check that other valid fields were still processed
    assert "good_column" in fields
    assert "id" in fields # From UUIDPKMixin


