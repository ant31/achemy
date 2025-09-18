"""
Tests for achemy/repository.py
"""
import uuid
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from tests.models import MockCombinedModel

from achemy import BaseRepository


# --- Repository for tests ---
class MockRepo(BaseRepository[MockCombinedModel]):
    def __init__(self, session):
        super().__init__(session, MockCombinedModel)


@pytest.mark.asyncio
class TestBaseRepository:
    @pytest.fixture
    def model_class(self):
        """Provides the model class for repository tests."""
        return MockCombinedModel

    async def test_add_and_get(self, async_engine, model_class, unique_id):
        """Test adding a new entity and retrieving it by primary key."""
        _db_engine, session_factory = async_engine.session()
        async with session_factory() as session:
            repo = MockRepo(session)
            name = f"get_test_{unique_id}"
            instance = model_class(name=name)
            await repo.add(instance, commit=True)

            retrieved = await repo.get(instance.id)
            assert retrieved is not None
            assert retrieved.id == instance.id
            assert retrieved.name == name

    async def test_find_by(self, async_engine, model_class, unique_id, caplog):
        """Test finding entities by attribute values."""
        _db_engine, session_factory = async_engine.session()
        name1 = f"find_A_{unique_id}"
        name2 = f"find_B_{unique_id}"
        async with session_factory() as session:
            repo = MockRepo(session)
            # Create test data
            inst1 = await repo.add(model_class(name=name1, value=10), commit=False)
            inst2 = await repo.add(model_class(name=name2, value=20), commit=True)

            # Test find by single attribute
            found_b = await repo.find_by(name=name2)
            assert found_b is not None
            assert found_b.id == inst2.id

            # Test find by multiple attributes
            found_a = await repo.find_by(name=name1, value=10)
            assert found_a is not None
            assert found_a.id == inst1.id

            # Test find with no result
            not_found = await repo.find_by(name=f"nonexistent_{unique_id}")
            assert not_found is None

            # Test find_by with non-mapped keys (should raise AttributeError)
            with pytest.raises(AttributeError, match=r"does not have attribute\(s\): non_existent_key"):
                await repo.find_by(non_existent_key="some_value")

            # Test find_by with no arguments
            with pytest.raises(ValueError, match=r"find_by\(\) requires at least one keyword argument"):
                await repo.find_by()

    async def test_all_and_count(self, async_engine, model_class, unique_id):
        """Test retrieving all entities and counting them."""
        _db_engine, session_factory = async_engine.session()
        base_name = f"all_count_{unique_id}"
        async with session_factory() as session:
            repo = MockRepo(session)
            await repo.add_all(
                [model_class(name=f"{base_name}_{i}", value=i) for i in range(3)],
                commit=True,
            )

            query = repo.where(model_class.name.like(f"{base_name}%"))

            # Test count
            count = await repo.count(query=query)
            assert count == 3

            # Test all
            all_results = await repo.all(query=query)
            assert len(all_results) == 3

            # Test all with limit
            limited_results = await repo.all(query=query, limit=2)
            assert len(limited_results) == 2

    async def test_delete(self, async_engine, model_class, unique_id):
        """Test deleting an entity."""
        _db_engine, session_factory = async_engine.session()
        async with session_factory() as session:
            repo = MockRepo(session)
            instance = model_class(name=f"delete_test_{unique_id}")
            await repo.add(instance, commit=True)
            instance_id = instance.id

            # Verify it exists
            assert await repo.get(instance_id) is not None

            # Delete and verify it's gone
            await repo.delete(instance, commit=True)
            assert await repo.get(instance_id) is None

    async def test_bulk_insert(self, async_engine, model_class, unique_id):
        """Test bulk insert operations, including conflict handling."""
        _db_engine, session_factory = async_engine.session()
        base_name = f"bulk_{unique_id}"

        async with session_factory() as session:
            repo = MockRepo(session)

            # Create a record that will cause a conflict
            await repo.add(model_class(name=f"{base_name}_conflict"), commit=True)

            # Test conflict: 'fail' (default)
            conflict_data = [{"name": f"{base_name}_conflict", "value": 99}]
            with pytest.raises(IntegrityError):
                await repo.bulk_insert(conflict_data, commit=True)

            # The session is now in a rolled-back state. We need to rollback.
            await session.rollback()

            # Test conflict: 'nothing'
            data = [
                {"name": f"{base_name}_1", "value": 1},
                {"name": f"{base_name}_conflict", "value": 98},  # This one should be skipped
                {"name": f"{base_name}_2", "value": 2},
            ]

            inserted_skipped = await repo.bulk_insert(
                data,
                commit=True,
                on_conflict="nothing",
                on_conflict_index_elements=["name"],
            )
            assert inserted_skipped is not None
            assert len(inserted_skipped) == 2  # _1 and _2

            # Verify final count: 1 initial + 2 new = 3
            assert await repo.count(repo.where(model_class.name.like(f"{base_name}%"))) == 3

    async def test_session_management(self, async_engine, model_class, unique_id):
        """Test session state management methods like refresh, expire, is_modified."""
        _db_engine, session_factory = async_engine.session()
        async with session_factory() as session:
            repo = MockRepo(session)
            name = f"session_mgmt_{unique_id}"
            instance = await repo.add(model_class(name=name, value=100), commit=True)

            # Test is_modified
            assert not await repo.is_modified(instance)
            instance.value = 200
            assert await repo.is_modified(instance)
            await session.commit()
            assert not await repo.is_modified(instance)

            # Test refresh
            instance.value = 300  # Change in memory
            assert instance.value == 300
            await repo.refresh(instance)
            assert instance.value == 200  # Should be back to the DB value

            # Test expire and expunge
            assert instance in session
            await repo.expire(instance)
            # In SQLAlchemy 2.0, check expiration via inspect()
            assert sa.inspect(instance).expired

            await repo.expunge(instance)
            assert instance not in session

    async def test_first_on_empty_result(self, async_engine, model_class, unique_id):
        """Test that .first() returns None when no records match."""
        _db_engine, session_factory = async_engine.session()
        async with session_factory() as session:
            repo = MockRepo(session)
            query = repo.where(model_class.name == f"non_existent_{unique_id}")
            result = await repo.first(query=query)
            assert result is None

    async def test_save_alias(self, async_engine, model_class, unique_id):
        """Test the save() method is an alias for add()."""
        _db_engine, session_factory = async_engine.session()
        async with session_factory() as session:
            repo = MockRepo(session)
            name = f"save_alias_{unique_id}"
            instance = model_class(name=name)
            await repo.save(instance, commit=True)

            retrieved = await repo.get(instance.id)
            assert retrieved is not None
            assert retrieved.name == name

    async def test_obj_session_and_ensure_session(self, async_engine, model_class, unique_id):
        """Test obj_session and that _ensure_obj_session merges detached instances."""
        _db_engine, session_factory = async_engine.session()
        instance = model_class(name=f"detached_{unique_id}")

        async with session_factory() as session1:
            repo1 = MockRepo(session1)
            await repo1.add(instance, commit=True)
            assert repo1.obj_session(instance) is session1

        # instance is now detached from session1
        assert sa.inspect(instance).detached

        async with session_factory() as session2:
            repo2 = MockRepo(session2)
            assert repo2.obj_session(instance) is None

            # _ensure_obj_session should merge it into session2
            merged_instance = await repo2._ensure_obj_session(instance)
            assert merged_instance == instance
            assert not sa.inspect(merged_instance).detached
            assert repo2.obj_session(merged_instance) is session2
            assert merged_instance in session2

    async def test_bulk_insert_update_on_conflict(self, async_engine, model_class, unique_id):
        """Test bulk insert with 'update' on conflict policy."""
        _db_engine, session_factory = async_engine.session()
        base_name = f"bulk_update_{unique_id}"
        conflict_name = f"{base_name}_conflict"

        async with session_factory() as session:
            repo = MockRepo(session)
            # Initial record to be updated
            initial_instance = await repo.add(model_class(name=conflict_name, value=1), commit=True)
            assert initial_instance.value == 1

            data_to_insert = [
                {"name": f"{base_name}_new", "value": 10},
                {"name": conflict_name, "value": 99},  # This should update
            ]

            results = await repo.bulk_insert(
                data_to_insert,
                on_conflict="update",
                on_conflict_index_elements=["name"],
                commit=True,
            )

            assert results is not None
            assert len(results) == 2

            # The ORM's identity map might hold a stale version of the object.
            # Expire it to ensure `find_by` re-fetches from the database.
            session.expire(initial_instance)

            # Verify the update
            updated_instance = await repo.find_by(name=conflict_name)
            assert updated_instance is not None
            assert updated_instance.id == initial_instance.id
            assert updated_instance.value == 99

            # Verify the new insert
            new_instance = await repo.find_by(name=f"{base_name}_new")
            assert new_instance is not None
            assert new_instance.value == 10

    async def test_bulk_insert_advanced(self, async_engine, model_class, unique_id):
        """Test advanced bulk insert features: empty list, no returning, and client-side PKs."""
        _db_engine, session_factory = async_engine.session()
        base_name = f"bulk_advanced_{unique_id}"

        async with session_factory() as session:
            repo = MockRepo(session)
            # Test with empty list
            result_empty = await repo.bulk_insert([])
            assert result_empty == []

            # Test with returning=False
            data = [{"name": f"{base_name}_1", "value": 1}]
            result_no_return = await repo.bulk_insert(data, returning=False, commit=True)
            assert result_no_return is None
            assert await repo.count(query=repo.where(model_class.name.like(f"{base_name}%"))) == 1

            # Test client-side PK generation (UUIDPKMixin)
            data_no_pk = [{"name": f"{base_name}_2", "value": 2}]
            result_with_pk = await repo.bulk_insert(data_no_pk, commit=True)
            assert result_with_pk is not None
            assert len(result_with_pk) == 1
            assert isinstance(result_with_pk[0].id, uuid.UUID)

    async def test_bulk_insert_errors(self, async_engine, model_class, unique_id):
        """Test error conditions for bulk_insert."""
        _db_engine, session_factory = async_engine.session()
        async with session_factory() as session:
            repo = MockRepo(session)
            data = [{"name": f"err_{unique_id}", "value": 1}]

            # Test ValueError for update without index_elements
            with pytest.raises(ValueError, match="must be provided for 'update' policy"):
                await repo.bulk_insert(data, on_conflict="update", on_conflict_index_elements=None)

            # Test ValueError for update with no columns to update
            with pytest.raises(ValueError, match="No columns specified to update"):
                await repo.bulk_insert(data, on_conflict="update", on_conflict_index_elements=["name", "value"])

            # Test NotImplementedError for unsupported on_conflict policy
            with pytest.raises(NotImplementedError, match="on_conflict='unsupported' is not supported"):
                await repo.bulk_insert(data, on_conflict="unsupported")

            # Test NotImplementedError for 'update' on non-postgresql dialect
            with patch.object(repo.session.bind.dialect, "name", "sqlite"), pytest.raises(NotImplementedError):
                await repo.bulk_insert(data, on_conflict="update")

    async def test_bulk_insert_type_error(self, async_engine):
        """Test bulk insert raises TypeError for class without __table__."""

        class NotAModel:
            pass

        _db_engine, session_factory = async_engine.session()
        async with session_factory() as session:
            repo = BaseRepository(session, NotAModel)
            with pytest.raises(TypeError):
                await repo.bulk_insert([{"foo": "bar"}])

    async def test_add_all_empty_and_refresh_error(self, async_engine, model_class, unique_id, caplog):
        """Test add_all with an empty list and handling of refresh errors."""
        _db_engine, session_factory = async_engine.session()
        async with session_factory() as session:
            repo = MockRepo(session)
            result = await repo.add_all([], commit=True)
            assert result == []

            # Test refresh error logging (by deleting object before refresh)
            instance = model_class(name=f"refresh_err_{unique_id}")
            with patch.object(session, "refresh", side_effect=Exception("Refresh failed")):
                objs = await repo.add_all([instance], commit=True)
                assert objs
                assert "Failed to refresh object" in caplog.text

    async def test_delete_transient_and_no_commit(self, async_engine, model_class, unique_id, caplog):
        """Test deleting transient object and using commit=False."""
        _db_engine, session_factory = async_engine.session()
        async with session_factory() as session:
            repo = MockRepo(session)

            # Test deleting a transient instance (should do nothing and log a warning)
            transient_instance = model_class(name=f"transient_{unique_id}")
            await repo.delete(transient_instance)
            assert f"Attempted to delete a transient instance {transient_instance}, ignoring." in caplog.text

            # Test delete with commit=False
            persistent_instance = await repo.add(model_class(name=f"no_commit_del_{unique_id}"), commit=True)
            instance_id = persistent_instance.id
            assert await repo.get(instance_id) is not None

            await repo.delete(persistent_instance, commit=False)

            # Should still be visible in another session because commit=False
            async with session_factory() as session2:
                repo2 = MockRepo(session2)
                assert await repo2.get(instance_id) is not None

            # After commit, it should be gone
            await session.commit()
            async with session_factory() as session3:
                repo3 = MockRepo(session3)
                assert await repo3.get(instance_id) is None

    async def test_state_management_with_attribute_names(self, async_engine, model_class, unique_id):
        """Test refresh and expire with specific attribute_names."""
        _db_engine, session_factory = async_engine.session()
        async with session_factory() as session:
            repo = MockRepo(session)
            instance = await repo.add(model_class(name=f"state_{unique_id}", value=10), commit=True)

            # Change values in memory
            instance.name = "new_name"
            instance.value = 20

            # Refresh only 'value'
            await repo.refresh(instance, attribute_names=["value"])
            assert instance.name == "new_name"  # Unchanged
            assert instance.value == 10  # Refreshed

            # Expire only 'name'
            await repo.expire(instance, attribute_names=["name"])
            insp = sa.inspect(instance)
            assert "name" in insp.expired_attributes
            assert "value" not in insp.expired_attributes

    async def test_first_with_ordering(self, async_engine, model_class, unique_id):
        """Test the first() method with explicit ordering."""
        _db_engine, session_factory = async_engine.session()
        base_name = f"first_order_{unique_id}"
        async with session_factory() as session:
            repo = MockRepo(session)
            await repo.add_all(
                [
                    model_class(name=f"{base_name}_C", value=3),
                    model_class(name=f"{base_name}_A", value=1),
                    model_class(name=f"{base_name}_B", value=2),
                ],
                commit=True,
            )

            query = repo.where(model_class.name.like(f"{base_name}%"))

            # Test order by value ascending
            first_by_val_asc = await repo.first(query=query, order_by=model_class.value.asc())
            assert first_by_val_asc is not None
            assert first_by_val_asc.value == 1

            # Test order by name descending
            first_by_name_desc = await repo.first(query=query, order_by=model_class.name.desc())
            assert first_by_name_desc is not None
            assert first_by_name_desc.name.endswith("_C")

    async def test_queries_with_no_args(self, async_engine, model_class, unique_id):
        """Test all(), count(), and where() with no specific query arguments."""
        _db_engine, session_factory = async_engine.session()
        async with session_factory() as session:
            repo = MockRepo(session)
            initial_count = await repo.count()

            await repo.add_all(
                [model_class(name=f"no_args_q_{unique_id}_{i}") for i in range(5)],
                commit=True,
            )

            total_count = initial_count + 5

            # where() with no args should be same as select()
            assert str(repo.where()) == str(repo.select())

            # all() with no query should return all repo's model objects
            all_no_query = await repo.all()
            assert len(all_no_query) == total_count

            # count() with no query should return total count of model's table
            assert await repo.count(query=None) == total_count

    async def test_error_handling(self, async_engine, model_class, unique_id, caplog):
        """Test logging and exception raising on DB errors."""
        _db_engine, session_factory = async_engine.session()
        async with session_factory() as session:
            repo = MockRepo(session)
            name = f"error_test_{unique_id}"
            instance = model_class(name=name)
            await repo.add(instance, commit=True)
            instance_id = instance.id

            # Test 'add' error (duplicate unique key)
            with pytest.raises(sa.exc.IntegrityError):
                await repo.add(model_class(name=name), commit=True)
            assert "Error adding" in caplog.text
            await session.rollback()  # Important after integrity error

            # Re-fetch the instance to ensure it's not in an expired state
            # before subsequent tests.
            instance = await repo.get(instance_id)
            assert instance is not None

            # Mock session methods for errors that are hard to reproduce
            with patch.object(session, "get", side_effect=sa.exc.SQLAlchemyError("DB down")):
                with pytest.raises(sa.exc.SQLAlchemyError):
                    await repo.get(instance_id)
                assert f"Error getting {model_class.__name__} by PK {instance_id}" in caplog.text

            with patch.object(session, "delete", side_effect=sa.exc.SQLAlchemyError("DB down")):
                with pytest.raises(sa.exc.SQLAlchemyError):
                    await repo.delete(instance)
                assert f"Error deleting {instance!r}" in caplog.text

            with patch.object(session, "refresh", side_effect=sa.exc.SQLAlchemyError("DB down")):
                with pytest.raises(sa.exc.SQLAlchemyError):
                    await repo.refresh(instance)
                assert f"Error refreshing instance {instance!r}" in caplog.text

            with patch.object(session, "execute", side_effect=sa.exc.SQLAlchemyError("DB down")):
                with pytest.raises(sa.exc.SQLAlchemyError):
                    await repo.count()
                assert f"Error executing count query for {model_class.__name__}" in caplog.text
