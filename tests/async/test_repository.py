"""
Tests for achemy/repository.py
"""
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
