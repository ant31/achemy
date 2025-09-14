"""
Tests for achemy/activerecord.py
"""
import asyncio
import json  # For dump_model test
import uuid  # Import uuid for tests
from unittest.mock import patch  # For mocking

import pytest
from sqlalchemy import String, UniqueConstraint  # Import String for MockColumnType
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column  # Import Mapped and mapped_column

from achemy import ActiveEngine, ActiveRecord, Base, PKMixin, PostgreSQLConfigSchema

# --- Fixtures ---

# Use the async_engine fixture from tests/async/conftest.py
# It sets the engine globally via ActiveRecord.set_engine

# Define a simple model for testing ActiveRecord methods directly
# Inherit PKMixin to get an 'id' primary key
class SimpleModel(PKMixin, Base):
    __tablename__ = "simple_models_activerecord"
    # Add a field required by MappedAsDataclass (inherited via PKMixin)
    name: Mapped[str] = mapped_column(init=True, default=None, nullable=False) # Made non-nullable for unique constraint
    value: Mapped[int | None] = mapped_column(init=True, default=None) # Add another field for testing `fields`
    # Inherits engine and session factory from Base/ActiveRecord

    __table_args__ = (UniqueConstraint("name", name="uq_simple_models_activerecord_name"),)


# --- Test Cases ---

@pytest.mark.asyncio
async def test_engine_management(async_engine, db_config):
    """Test set_engine and engine methods."""
    # 1. Test that engine is set correctly by the fixture
    assert ActiveRecord.engine() is async_engine
    assert SimpleModel.engine() is async_engine

    # 2. Test setting a different engine
    # Create a dummy config and engine
    dummy_config = PostgreSQLConfigSchema(db="dummy", user="dummy", password="dummy", host="dummy")
    dummy_engine = ActiveEngine(dummy_config)

    # Set the dummy engine on the specific class
    SimpleModel.set_engine(dummy_engine)
    assert SimpleModel.engine() is dummy_engine
    # Verify ActiveRecord base still has the original engine
    assert ActiveRecord.engine() is async_engine

    # 3. Test error when engine is not set
    class UnconfiguredModel(ActiveRecord): # Don't inherit from Base which might have engine set
        __tablename__ = "unconfigured_activerecord"
        # No set_engine called

    # Explicitly remove the inherited engine for this test case
    UnconfiguredModel.__active_engine__ = None

    with pytest.raises(ValueError, match="No active engine configured"):
        UnconfiguredModel.engine()

    # 4. Test set_engine with invalid type
    with pytest.raises(TypeError, match="Engine must be an instance of ActiveEngine"):
        SimpleModel.set_engine("not an engine") # type: ignore

    # Reset engine for SimpleModel to avoid affecting other tests
    SimpleModel.set_engine(async_engine)
    assert SimpleModel.engine() is async_engine


@pytest.mark.asyncio
async def test_session_management(async_engine, unique_id):
    """Test session_factory, get_session, and obj_session methods."""
    # 1. Test session_factory returns the correct factory
    factory = SimpleModel.session_factory()
    assert factory is not None
    # Check if it's the factory associated with the default engine config
    _, expected_factory = async_engine.session() # Get the default factory
    assert factory is expected_factory

    # 2. Test get_session creates a new session
    async with SimpleModel.get_session() as session1:
        assert session1 is not None
        assert session1.is_active

    # 3. Test session_factory error when not configured
    class UnconfiguredModel(ActiveRecord):
        __tablename__ = "unconfigured_session_test"
        # No engine set

    UnconfiguredModel.__active_engine__ = None # Ensure no inherited engine
    UnconfiguredModel._session_factory = None # Ensure no inherited factory

    with pytest.raises(ValueError, match="Session factory not configured"):
        UnconfiguredModel.session_factory()

    # 4. Test obj_session
    instance = SimpleModel(name=f"session_test_{unique_id}")
    assert instance.obj_session() is None # Transient object has no session

    async with SimpleModel.get_session() as s:
        # Add instance to session
        s.add(instance)
        await s.flush([instance]) # Flush to make it persistent in this session
        # Now the object should be associated with the session
        assert instance.obj_session() is s

        # Test obj_session after commit and refresh
        await s.commit()
        await s.refresh(instance)
        assert instance.obj_session() is s

    # Test obj_session after session is closed (should be None or detached state)
    # Accessing obj_session after close might be undefined or raise, depending on impl.
    # Let's check it's not the closed session.
    assert instance.obj_session() is not s # Session 's' is closed now
    # It might be None or associated with a new session if accessed later.
    # For now, just ensure it's not the closed one.

    # Reset engine for SimpleModel (done in test_engine_management teardown implicitly if needed)
    # SimpleModel.set_engine(async_engine)


@pytest.mark.asyncio
async def test_session_factory_retry(async_engine, caplog):
    """Test session_factory retries getting factory if engine exists but factory is None."""
    class RetryModel(Base, PKMixin):
        __tablename__ = "retry_model_test"
        name: Mapped[str] = mapped_column(init=True, default=None)

    # Ensure engine is set, but manually unset the factory
    RetryModel.set_engine(async_engine)
    original_factory = RetryModel._session_factory
    RetryModel._session_factory = None
    assert RetryModel._session_factory is None # Verify it's unset

    caplog.clear()
    # Calling session_factory should trigger the warning and re-fetch
    retrieved_factory = RetryModel.session_factory()

    assert "Session factory not set for RetryModel, attempting retrieval from engine." in caplog.text
    assert retrieved_factory is not None
    assert retrieved_factory is original_factory # Should retrieve the correct one
    assert RetryModel._session_factory is original_factory # Should be set back on the class

    # Clean up - reset engine/factory if necessary, though test isolation should handle this.
    # RetryModel.set_engine(async_engine) # Re-set to be sure


@pytest.mark.asyncio
async def test_ensure_obj_session_merges_object(unique_id):
    """Test that _ensure_obj_session merges the object if not in the provided session."""
    Model = SimpleModel
    instance_name = f"ensure_merge_{unique_id}"
    # Create and save instance in one session to make it persistent
    async with Model.get_session() as s:
        instance = await Model(name=instance_name).save(s, commit=True)
    # After the session closes, the instance is detached.
    assert instance.obj_session() is None

    # Create a new session
    async with Model.get_session() as session2:
        # Instance is not initially in session2
        assert instance not in session2

        # Mock session2.merge to check if it's called
        with patch.object(session2, 'merge', wraps=session2.merge) as mock_merge:
            # Call a method that uses _ensure_obj_session with the new session
            refreshed_instance = await instance.refresh(session2)

            # Assert merge was called with the instance
            mock_merge.assert_awaited_once_with(instance)

            # Assert the instance is now associated with session2
            assert refreshed_instance in session2
            assert refreshed_instance.obj_session() is session2


@pytest.mark.asyncio
async def test_instance_representation_and_data(unique_id):
    """Test instance representation (__str__, __repr__) and data methods (to_dict, dump_model, load, etc.)."""
    instance_name = f"repr_test_{unique_id}"
    instance = SimpleModel(name=instance_name, value=3)
    instance_id = instance.id # Get the generated UUID

    # 1. Test __str__ and __repr__
    expected_str = f"SimpleModel({instance_id})"
    # Dataclass repr includes init fields
    # expected_repr = f"SimpleModel(id=UUID('{instance_id}'), name='{instance_name}')" # Kept for reference
    instance_repr = repr(instance)
    assert str(instance) == expected_str
    # Check components of repr without relying on order
    assert instance_repr.startswith("SimpleModel(")
    assert f"id=UUID('{instance_id}')" in instance_repr
    assert f"name='{instance_name}'" in instance_repr
    assert instance_repr.endswith(")")


    # 2. Test id_key
    # Transient object id_key might vary, let's test after save
    # assert instance.id_key() == f"SimpleModel:transient_{id(instance)}" # Less reliable
    async with SimpleModel.get_session() as s:
        await instance.save(s, commit=True)
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
    # Adjust assertion to match observed module path
    assert data_dict_meta["__metadata__"]["model"] == "test_activerecord:SimpleModel"
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
async def test_crud_add_save(unique_id):
    """Test ActiveRecord.add() and instance.save() methods."""
    # 1. Save with commit=True (using internal session)
    instance1_name = f"crud_add1_{unique_id}"
    instance_to_save = SimpleModel(name=instance1_name)
    instance1_id = None # Initialize id

    # Use an explicit session for the save operation with async with
    async with SimpleModel.get_session() as save_session1:
        instance1 = await instance_to_save.save(save_session1, commit=True)
        instance1_id = instance1.id # ID should be loaded after save commits
        # Session is automatically closed/committed here by async with

    # Allow potential background tasks from session close to run
    await asyncio.sleep(0.01) # Use a slightly longer sleep after session close

    # Verify it's in the DB using another explicit session
    async with SimpleModel.get_session() as verify_session1:
        found1 = await SimpleModel.get(verify_session1, instance1_id)
        assert found1 is not None
        assert found1.name == instance1_name

    # 2. Add with commit=False
    instance2_name = f"crud_add2_{unique_id}"
    instance2 = SimpleModel(name=instance2_name)
    async with SimpleModel.get_session() as session_no_commit:
        # Use add directly with commit=False
        added_instance2 = await SimpleModel.add(instance2, session_no_commit, commit=False)
        assert added_instance2 is instance2
        assert added_instance2.id is not None # ID should be assigned after flush
        instance2_id = added_instance2.id

        # Verify it's NOT YET in the DB via another explicit session
        async with SimpleModel.get_session() as verify_session2_before:
            found2_before_commit = await SimpleModel.get(verify_session2_before, instance2_id)
            assert found2_before_commit is None

        # Commit the session
        await session_no_commit.commit()

    # Verify it IS NOW in the DB using another explicit session
    async with SimpleModel.get_session() as verify_session2_after:
        found2_after_commit = await SimpleModel.get(verify_session2_after, instance2_id)
        assert found2_after_commit is not None
        assert found2_after_commit.name == instance2_name

    # 3. Add with provided session (commit=True)
    instance3_name = f"crud_add3_{unique_id}"
    instance3 = SimpleModel(name=instance3_name)
    async with SimpleModel.get_session() as provided_session:
        added_instance3 = await SimpleModel.add(instance3, provided_session, commit=True)
        instance3_id = added_instance3.id
        # Verify within the same session (already committed)
        found3_in_session = await SimpleModel.get(provided_session, instance3_id)
        assert found3_in_session is not None

    # Verify in a new explicit session
    async with SimpleModel.get_session() as verify_session3_new:
        found3_new_session = await SimpleModel.get(verify_session3_new, instance3_id)
        assert found3_new_session is not None


@pytest.mark.asyncio
async def test_crud_add_all(unique_id):
    """Test ActiveRecord.add_all() method."""
    # (add_all tests are also covered in test_async_integration.py)
    instance4_name = f"crud_add_all1_{unique_id}"
    instance5_name = f"crud_add_all2_{unique_id}"
    instances_to_add = [SimpleModel(name=instance4_name), SimpleModel(name=instance5_name)]
    async with SimpleModel.get_session() as s:
        added_all_instances = await SimpleModel.add_all(instances_to_add, s)  # commit=True default
        assert len(added_all_instances) == 2
        instance4_id = added_all_instances[0].id
        instance5_id = added_all_instances[1].id
        assert await SimpleModel.get(s, instance4_id) is not None
        assert await SimpleModel.get(s, instance5_id) is not None


@pytest.mark.asyncio
async def test_crud_delete(unique_id):
    """Test ActiveRecord.delete() method."""
    # Setup: Create instances to delete
    async with SimpleModel.get_session() as s:
        inst1 = await SimpleModel(name=f"del1_{unique_id}").save(s, commit=True)
        inst2 = await SimpleModel(name=f"del2_{unique_id}").save(s, commit=True)
        inst3 = await SimpleModel(name=f"del3_{unique_id}").save(s, commit=True)

    # 1. Delete with commit=True (default)
    async with SimpleModel.get_session() as s:
        await SimpleModel.delete(inst1, s)
    async with SimpleModel.get_session() as s:
        assert await SimpleModel.get(s, inst1.id) is None

    # 2. Delete with commit=False
    async with SimpleModel.get_session() as session_del_no_commit:
        # Retrieve instance 2 again within this session context
        instance2_to_delete = await SimpleModel.get(session_del_no_commit, inst2.id)
        assert instance2_to_delete is not None
        await SimpleModel.delete(instance2_to_delete, session_del_no_commit, commit=False)

        # Verify it's STILL in the DB via another session
        async with SimpleModel.get_session() as s2:
            found2_before_del_commit = await SimpleModel.get(s2, inst2.id)
            assert found2_before_del_commit is not None

        # Commit the delete
        await session_del_no_commit.commit()

    # Verify it's NOW deleted
    async with SimpleModel.get_session() as s2:
        assert await SimpleModel.get(s2, inst2.id) is None

    # 3. Delete with provided session (commit=True)
    async with SimpleModel.get_session() as provided_del_session:
        instance3_to_delete = await SimpleModel.get(provided_del_session, inst3.id)
        assert instance3_to_delete is not None
        await SimpleModel.delete(instance3_to_delete, provided_del_session, commit=True)
        # Verify deleted within the same session
        assert await SimpleModel.get(provided_del_session, inst3.id) is None

    # Verify deleted in a new session
    async with SimpleModel.get_session() as s:
        assert await SimpleModel.get(s, inst3.id) is None


@pytest.mark.asyncio
async def test_instance_state_management(unique_id):
    """Test instance state methods: refresh, expire, expunge, is_modified."""
    Model = SimpleModel
    instance_name = f"state_test_{unique_id}"
    async with Model.get_session() as s:
        instance = await Model(name=instance_name).save(s, commit=True)
    instance_id = instance.id

    # --- Test refresh ---
    async with Model.get_session() as session1:
        # Load the instance into session1 FIRST
        instance_in_s1 = await Model.get(session1, instance_id)
        assert instance_in_s1.name == instance_name  # Check initial state

        # Modify data in DB using a different instance/session
        async with Model.get_session() as session2:
            instance_alt = await Model.get(session2, instance_id)
            instance_alt.name = f"state_test_updated_{unique_id}"
            await instance_alt.save(session2, commit=True)

        # Verify instance in session1 STILL has the old name (due to session cache)
        assert instance_in_s1.name == instance_name

        # Refresh the instance in session1
        refreshed_instance = await instance_in_s1.refresh(session1)
        assert refreshed_instance is instance_in_s1  # Should return the same instance
        # Now it should have the updated name
        assert refreshed_instance.name == f"state_test_updated_{unique_id}"

    # --- Test expire ---
    async with Model.get_session() as session3:
        instance_in_s3 = await Model.get(session3, instance_id)
        # Ensure name is the updated one
        assert instance_in_s3.name == f"state_test_updated_{unique_id}"

        # Manually change the attribute in the object (without saving)
        instance_in_s3.name = "state_test_expired_local"

        # Expire the instance (or specific attributes)
        expired_instance = await instance_in_s3.expire(session3)
        # Explicitly refresh the attribute instead of relying on lazy load after expire,
        # as implicit load seems to cause MissingGreenlet error here.
        await session3.refresh(expired_instance, attribute_names=["name"])
        # Accessing the attribute should now work without triggering implicit load
        assert expired_instance.name == f"state_test_updated_{unique_id}"

    # --- Test is_modified ---
    async with Model.get_session() as session4:
        instance_in_s4 = await Model.get(session4, instance_id)
        # Initially, not modified
        assert not await instance_in_s4.is_modified(session4)

        # Modify the instance
        instance_in_s4.name = "state_test_modified_check"
        # Now it should be marked as modified (dirty)
        assert await instance_in_s4.is_modified(session4)

        # Commit the change
        await session4.commit()
        # After commit, it should no longer be modified
        assert not await instance_in_s4.is_modified(session4)

    # --- Test expunge ---
    async with Model.get_session() as session5:
        instance_in_s5 = await Model.get(session5, instance_id)
        assert instance_in_s5 in session5  # Should be in the session

        # Expunge the instance
        expunged_instance = await instance_in_s5.expunge(session5)
        assert expunged_instance is instance_in_s5
        # Now it should be detached
        assert instance_in_s5 not in session5
        # Accessing attributes might still work if loaded, but it's detached.
        assert expunged_instance.name == "state_test_modified_check"


@pytest.mark.asyncio
async def test_querying_methods(unique_id, caplog):
    """Test querying methods: where, first, get, count."""
    Model = SimpleModel
    # Setup: Create some data
    async with Model.get_session() as s:
        inst1 = await Model(name=f"query_A_{unique_id}").save(s, commit=True)
        inst2 = await Model(name=f"query_B_{unique_id}").save(s, commit=True)
        inst3 = await Model(name=f"query_C_{unique_id}").save(s, commit=True)

    # --- Test where ---
    # 1. Where with keyword argument
    async with Model.get_session() as s:
        query_kw = Model.where(name=inst2.name)
        results_kw = await query_kw.scalars(session=s)
        items_kw = results_kw.all()
        assert len(items_kw) == 1
        assert items_kw[0].id == inst2.id

    # 2. Where with positional argument
    async with Model.get_session() as s:
        query_pos = Model.where(Model.name == inst3.name)
        results_pos = await query_pos.scalars(session=s)
        items_pos = results_pos.all()
        assert len(items_pos) == 1
        assert items_pos[0].id == inst3.id

    # 3. Where with non-mapped attribute (should log warning)
    caplog.clear()
    query_warn = Model.where(non_existent_attr="value")
    assert "Ignoring keyword argument 'non_existent_attr'" in caplog.text
    # Check that the query still works but ignores the bad kwarg
    async with Model.get_session() as s:
        # This query should return all 3 items created in this test
        results_warn = await query_warn.scalars(session=s)
        items_warn = results_warn.all()
        # Filter results to only those created in this test run
        test_ids = {inst1.id, inst2.id, inst3.id}
        filtered_items_warn = [item for item in items_warn if item.id in test_ids]
        assert len(filtered_items_warn) == 3

    # --- Test first ---
    async with Model.get_session() as s:
        # 1. First with default order (PK) - difficult to assert exact order, just check one is returned
        first_default = await Model.first(s)
        assert first_default is not None
        assert isinstance(first_default, Model)

        # 2. First when no results match
        first_none = await Model.first(s, query=Model.where(Model.name == "non_existent"))
        assert first_none is None

    # --- Test get ---
    # (get success is covered in other tests)
    # 1. Get non-existent PK
    non_existent_pk = uuid.uuid4()
    async with Model.get_session() as s:
        get_none = await Model.get(s, non_existent_pk)
        assert get_none is None

    # --- Test count ---
    async with Model.get_session() as s:
        # 1. Count all (may include data from other tests, filter if needed)
        total_count = await Model.count(s)
        assert total_count >= 3  # Should be at least the 3 we created

        # 2. Count with a query
        query_count = Model.where(Model.name.like(f"query_%_{unique_id}"))
        count_filtered = await Model.count(s, query=query_count)
        assert count_filtered == 3

        # 3. Count with query yielding no results
        query_count_none = Model.where(Model.name == "non_existent")
        count_none = await Model.count(s, query=query_count_none)
        assert count_none == 0

    # Cleanup
    async with Model.get_session() as s:
        await Model.delete(inst1, s)
        await Model.delete(inst2, s)
        await Model.delete(inst3, s)
        await s.commit()


@pytest.mark.asyncio
async def test_helpers_and_error_cases(unique_id, capsys, caplog):
    """Test helper methods (printn, id_key) and some error paths."""
    Model = SimpleModel

    # --- Test printn ---
    instance_print = Model(name=f"print_test_{unique_id}")
    instance_print.printn()
    captured = capsys.readouterr()
    assert f"Attributes for {instance_print}:" in captured.out
    assert "name:" in captured.out
    assert f"print_test_{unique_id}" in captured.out
    assert "_sa_" not in captured.out # Ensure SQLAlchemy state is excluded

    # --- Test id_key on transient object ---
    instance_transient = Model(name=f"transient_{unique_id}")
    # Since PKMixin provides a default_factory, the ID exists even when transient.
    # id_key() should return the standard format.
    expected_id_key = f"SimpleModel:{instance_transient.id}"
    assert instance_transient.id_key() == expected_id_key

    # --- Test load error: Non-mapped class ---
    class UnmappedActiveRecord(ActiveRecord):
        # Inherits ActiveRecord but lacks __tablename__ or mapped columns,
        # so SQLAlchemy won't generate a __mapper__ for it.
        pass

    with pytest.raises(ValueError, match="Class UnmappedActiveRecord is not mapped"):
        # Call load on the unmapped class
        UnmappedActiveRecord.load({"key": "value"})

    # --- Test to_dict error: Non-mapped instance ---
    # Define NonMapped class here for the next test section
    class NonMapped: # Dummy class without SQLAlchemy mapping
        pass
    non_mapped_instance = NonMapped()
    # Add __dict__ to simulate attributes if needed, though to_dict checks __mapper__
    non_mapped_instance.some_attr = 123
    caplog.clear()
    result_dict = ActiveRecord.to_dict(non_mapped_instance) # type: ignore
    assert result_dict == {} # Should return empty dict for non-mapped
    assert "does not seem to be mapped" in caplog.text

    # --- Test dump_model error: JSON serialization ---
    # Mock to_jsonable_python to raise an error
    async with Model.get_session() as s:
        instance_dump = await Model(name=f"dump_err_{unique_id}").save(s, commit=True)
    with patch('achemy.activerecord.to_jsonable_python', side_effect=TypeError("Cannot serialize")):
        caplog.clear()
        # dump_model should catch the error and log it
        dumped = instance_dump.dump_model()
        # It might return the original dict or an empty one depending on error handling goal
        # Current implementation returns the plain dict.
        assert isinstance(dumped, dict)
        assert "Error making dictionary for" in caplog.text
        assert "JSON-serializable" in caplog.text

    # Cleanup instance from dump_model test
    async with Model.get_session() as s:
        await Model.delete(instance_dump, s)

    # --- Test __columns__fields__ error: NotImplementedError ---
    # Define a mock type that raises error on python_type access
    class MockColumnType(String): # Inherit from a real type
        @property
        def python_type(self):
            raise NotImplementedError("Test error")

    # Define a dedicated model using this problematic type
    class ModelWithBadColType(Base, PKMixin):
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
    assert "id" in fields # From PKMixin


# --- Test Cases for bulk_insert ---

@pytest.mark.asyncio
async def test_bulk_insert_simple(unique_id):
    """Test basic bulk_insert functionality."""
    Model = SimpleModel
    name1 = f"bulk_simple1_{unique_id}"
    name2 = f"bulk_simple2_{unique_id}"
    objs_to_insert = [Model(name=name1, value=10), Model(name=name2, value=20)]

    async with Model.get_session() as s:
        inserted_objs = await Model.bulk_insert(objs_to_insert, s)
    assert inserted_objs is not None
    assert len(inserted_objs) == 2
    assert all(isinstance(obj, Model) for obj in inserted_objs)
    assert {obj.name for obj in inserted_objs} == {name1, name2}
    assert {obj.value for obj in inserted_objs} == {10, 20}

    # Verify in DB
    async with Model.get_session() as s:
        db_obj1 = await Model.find_by(s, name=name1)
        db_obj2 = await Model.find_by(s, name=name2)
        assert db_obj1 is not None
        assert db_obj2 is not None
        assert db_obj1.value == 10
        assert db_obj2.value == 20

        # Cleanup
        await Model.delete(db_obj1, s)
        await Model.delete(db_obj2, s)
        await s.commit()


@pytest.mark.asyncio
async def test_bulk_insert_no_commit_and_explicit_session(unique_id):
    """Test bulk_insert with commit=False and then committing an explicit session."""
    Model = SimpleModel
    name1 = f"bulk_nocommit1_{unique_id}"
    name2 = f"bulk_nocommit2_{unique_id}"
    objs_to_insert = [Model(name=name1), Model(name=name2)]

    async with await Model.get_session() as s:
        inserted_objs = await Model.bulk_insert(objs_to_insert, s, commit=False)
        assert inserted_objs is not None
        assert len(inserted_objs) == 2

        # Verify NOT in DB yet (via a different session)
        async with Model.get_session() as s2:
            assert await Model.find_by(s2, name=name1) is None
            assert await Model.find_by(s2, name=name2) is None

        # Verify they are in the original session's pending state (optional check)
        # This check is a bit more involved as they are not full objects yet.
        # For simplicity, we'll rely on the "not in DB" check above and "in DB after commit" below.

        await s.commit()  # Commit the explicit session

    # Verify in DB now
    async with Model.get_session() as s2:
        db_obj1 = await Model.find_by(s2, name=name1)
        db_obj2 = await Model.find_by(s2, name=name2)
        assert db_obj1 is not None
        assert db_obj2 is not None

        # Cleanup
        await Model.delete(db_obj1, s2)
        await Model.delete(db_obj2, s2)
        await s2.commit()


@pytest.mark.asyncio
async def test_bulk_insert_no_returning(unique_id):
    """Test bulk_insert with returning=False."""
    Model = SimpleModel
    name1 = f"bulk_noreturn_{unique_id}"
    objs_to_insert = [Model(name=name1)]

    async with Model.get_session() as s:
        inserted_objs = await Model.bulk_insert(objs_to_insert, s, returning=False)
        assert inserted_objs is None

        # Verify in DB
        db_obj1 = await Model.find_by(s, name=name1)
        assert db_obj1 is not None

        # Cleanup
        await Model.delete(db_obj1, s)
        await s.commit()


@pytest.mark.asyncio
async def test_bulk_insert_empty_list():
    """Test bulk_insert with an empty list of objects."""
    Model = SimpleModel
    async with Model.get_session() as s:
        inserted_objs = await Model.bulk_insert([], s)
        assert inserted_objs == []

        inserted_objs_no_return = await Model.bulk_insert([], s, returning=False)
        assert inserted_objs_no_return is None


@pytest.mark.asyncio
async def test_bulk_insert_on_conflict_fail(unique_id):
    """Test bulk_insert with on_conflict='fail' (default)."""
    Model = SimpleModel
    name_conflict = f"bulk_conflict_fail_{unique_id}"

    # Insert initial record
    async with Model.get_session() as s:
        initial_obj = await Model(name=name_conflict, value=1).save(s, commit=True)
    assert initial_obj is not None

    objs_to_insert = [
        Model(name=name_conflict, value=2), # This will conflict
        Model(name=f"bulk_conflict_fail_ok_{unique_id}", value=3)
    ]

    with pytest.raises(IntegrityError):  # Or the specific DB driver error
        async with Model.get_session() as s:
            await Model.bulk_insert(objs_to_insert, s, on_conflict="fail")

    # Verify the non-conflicting record was NOT inserted due to transaction rollback
    async with Model.get_session() as s:
        assert await Model.find_by(s, name=f"bulk_conflict_fail_ok_{unique_id}") is None
        # Verify initial object still exists with original value
        db_initial = await Model.get(s, initial_obj.id)
        assert db_initial is not None
        assert db_initial.value == 1

        # Cleanup
        await Model.delete(db_initial, s)
        await s.commit()


@pytest.mark.asyncio
async def test_bulk_insert_on_conflict_nothing(unique_id):
    """Test bulk_insert with on_conflict='nothing'."""
    Model = SimpleModel
    name_conflict = f"bulk_conflict_nothing_{unique_id}"
    name_ok = f"bulk_conflict_nothing_ok_{unique_id}"

    # Insert initial record
    async with Model.get_session() as s:
        initial_obj = await Model(name=name_conflict, value=100).save(s, commit=True)
    assert initial_obj is not None

    objs_to_insert = [
        Model(name=name_conflict, value=200), # This will conflict and be skipped
        Model(name=name_ok, value=300)      # This should be inserted
    ]

    # Use default index_elements (PK or unique constraint on 'name')
    async with Model.get_session() as s:
        inserted_objs = await Model.bulk_insert(objs_to_insert, s, on_conflict="nothing")

    assert inserted_objs is not None
    assert len(inserted_objs) == 1 # Only the non-conflicting one is returned
    assert inserted_objs[0].name == name_ok
    assert inserted_objs[0].value == 300

    # Verify in DB
    async with Model.get_session() as s:
        db_initial = await Model.get(s, initial_obj.id)
        assert db_initial is not None
        assert db_initial.name == name_conflict
        assert db_initial.value == 100  # Original value should remain

        db_ok = await Model.find_by(s, name=name_ok)
        assert db_ok is not None
        assert db_ok.value == 300

        # Cleanup
        await Model.delete(db_initial, s)
        await Model.delete(db_ok, s)
        await s.commit()


@pytest.mark.asyncio
async def test_bulk_insert_on_conflict_nothing_specific_index(unique_id):
    """Test bulk_insert with on_conflict='nothing' and specific index_elements."""
    Model = SimpleModel
    name_conflict_idx = f"bulk_conflict_idx_{unique_id}"
    name_ok_idx = f"bulk_conflict_idx_ok_{unique_id}"

    # Insert initial record
    async with Model.get_session() as s:
        initial_obj = await Model(name=name_conflict_idx, value=50).save(s, commit=True)
    assert initial_obj is not None

    objs_to_insert = [
        Model(name=name_conflict_idx, value=55), # Conflicts on 'name'
        Model(name=name_ok_idx, value=65)
    ]

    # Specify the unique constraint on 'name'
    async with Model.get_session() as s:
        inserted_objs = await Model.bulk_insert(
            objs_to_insert, s, on_conflict="nothing", on_conflict_index_elements=["name"]
        )

    assert inserted_objs is not None
    assert len(inserted_objs) == 1
    assert inserted_objs[0].name == name_ok_idx
    assert inserted_objs[0].value == 65

    # Verify in DB
    async with Model.get_session() as s:
        db_initial = await Model.get(s, initial_obj.id)
        assert db_initial is not None
        assert db_initial.value == 50  # Unchanged

        db_ok = await Model.find_by(s, name=name_ok_idx)
        assert db_ok is not None
        assert db_ok.value == 65

        # Cleanup
        await Model.delete(db_initial, s)
        if db_ok:
            await Model.delete(db_ok, s)
        await s.commit()


@pytest.mark.asyncio
async def test_bulk_insert_with_fields(unique_id):
    """Test bulk_insert using the 'fields' parameter."""
    Model = SimpleModel
    name1 = f"bulk_fields1_{unique_id}"
    name2 = f"bulk_fields2_{unique_id}"

    # Create full model instances, but only 'name' should be inserted
    # 'value' has a default of None in the model, but we are not providing it via 'fields'
    objs_to_insert = [
        Model(name=name1, value=1000),  # value should be ignored
        Model(name=name2, value=2000),  # value should be ignored
    ]
    async with Model.get_session() as s:
        inserted_objs = await Model.bulk_insert(objs_to_insert, s, fields={"id", "name"})
    # Note: 'id' is often auto-generated by DB or SQLAlchemy before insert if not provided.
    # If 'id' is part of 'fields', its pre-generated value from the Python side would be used.
    # If PKMixin's default_factory is client-side, 'id' will be in dump_model().

    assert inserted_objs is not None
    assert len(inserted_objs) == 2
    assert {obj.name for obj in inserted_objs} == {name1, name2}

    # Verify in DB
    async with Model.get_session() as s:
        db_obj1 = await Model.find_by(s, name=name1)
        db_obj2 = await Model.find_by(s, name=name2)

        assert db_obj1 is not None
        assert db_obj1.value is None  # Value should be its default (None) as it wasn't in 'fields'

        assert db_obj2 is not None
        assert db_obj2.value is None  # Value should be its default (None)

        # Cleanup
        await Model.delete(db_obj1, s)
        await Model.delete(db_obj2, s)
        await s.commit()


@pytest.mark.asyncio
async def test_bulk_insert_invalid_on_conflict_value(unique_id):
    """Test bulk_insert raises ValueError for invalid on_conflict."""
    Model = SimpleModel
    objs_to_insert = [Model(name=f"invalid_conflict_{unique_id}")]

    with pytest.raises(ValueError, match="Invalid on_conflict_strategy value: bogus_value"):
        async with Model.get_session() as s:
            await Model.bulk_insert(objs_to_insert, s, on_conflict="bogus_value")  # type: ignore
