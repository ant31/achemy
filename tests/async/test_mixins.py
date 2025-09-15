"""
Tests for achemy/mixins.py
"""
import asyncio
import uuid
from datetime import datetime, timedelta

import pytest

# Use the setup fixture defined in async/conftest.py
# pytestmark = pytest.mark.usefixtures("setup_mixin_tests")
# Note: Tests rely on unique_id for isolation instead of table cleaning.
from achemy import BaseRepository


# --- Repositories for Mock Models ---
class MockPKRepository(BaseRepository):
    def __init__(self, session, model_cls):
        super().__init__(session, model_cls)


class MockUpdateRepository(BaseRepository):
    def __init__(self, session, model_cls):
        super().__init__(session, model_cls)


class MockCombinedRepository(BaseRepository):
    def __init__(self, session, model_cls):
        super().__init__(session, model_cls)


@pytest.mark.asyncio
async def test_pkmixin_id_creation(setup_mixin_tests, mock_pk_model_class, unique_id, async_engine):
    """Test that UUIDPKMixin creates a UUID id."""
    instance = mock_pk_model_class(name=f"pk_test_{unique_id}")
    assert isinstance(instance.id, uuid.UUID)

    _db_engine, session_factory = async_engine.session()
    async with session_factory() as s:
        repo = MockPKRepository(s, mock_pk_model_class)
        await repo.save(instance, commit=True)
    assert isinstance(instance.id, uuid.UUID)


@pytest.mark.asyncio
async def test_pkmixin_find(setup_mixin_tests, mock_pk_model_class, unique_id, async_engine):
    """Test finding a record by its primary key using the repository."""
    instance_name = f"find_test_{unique_id}"
    _db_engine, session_factory = async_engine.session()
    async with session_factory() as s:
        repo = MockPKRepository(s, mock_pk_model_class)
        instance = await repo.save(mock_pk_model_class(name=instance_name), commit=True)
        found_instance = await repo.get(instance.id)
        assert found_instance is not None
        assert found_instance.id == instance.id
        assert found_instance.name == instance_name

        non_existent_uuid = uuid.uuid4()
        not_found_instance = await repo.get(non_existent_uuid)
        assert not_found_instance is None


@pytest.mark.asyncio
async def test_updatemixin_timestamps(setup_mixin_tests, mock_combined_model_class, unique_id, async_engine):
    """Test that UpdateMixin adds and manages timestamps."""
    await asyncio.sleep(0.01)
    instance = mock_combined_model_class(name=f"timestamp_test_{unique_id}")

    _db_engine, session_factory = async_engine.session()
    async with session_factory() as session:
        repo = MockCombinedRepository(session, mock_combined_model_class)
        instance = await repo.save(instance, commit=True)
        await asyncio.sleep(0.01)

        assert isinstance(instance.created_at, datetime)
        assert isinstance(instance.updated_at, datetime)
        assert abs(instance.updated_at - instance.created_at) < timedelta(seconds=1)

        created_at_before_update = instance.created_at
        updated_at_before_update = instance.updated_at
        await asyncio.sleep(0.05)
        instance.name = f"timestamp_test_updated_{unique_id}"
        instance = await repo.save(instance, commit=True)

        assert instance.created_at == created_at_before_update
        assert instance.updated_at > updated_at_before_update


@pytest.mark.asyncio
async def test_updatemixin_queries(setup_mixin_tests, mock_combined_model_class, unique_id, async_engine):
    """Test querying based on UpdateMixin's timestamp columns."""
    Model = mock_combined_model_class
    _db_engine, session_factory = async_engine.session()
    async with session_factory() as session:
        repo = MockCombinedRepository(session, Model)
        instance1 = await repo.save(Model(name=f"q_old_{unique_id}"), commit=True)
        instance2 = await repo.save(Model(name=f"q_mid_{unique_id}"), commit=True)
        instance3 = await repo.save(Model(name=f"q_new_{unique_id}"), commit=True)

        instance2.name = f"q_mid_updated_{unique_id}"
        instance2 = await repo.save(instance2, commit=True)

        query_scope = repo.where(Model.name.like(f"%_{unique_id}"))

        last_created = await repo.first(query=query_scope, order_by=Model.created_at.desc())
        assert last_created is not None
        assert last_created.id == instance3.id

        first_created = await repo.first(query=query_scope, order_by=Model.created_at.asc())
        assert first_created is not None
        assert first_created.id == instance1.id

        last_modified = await repo.first(query=query_scope, order_by=Model.updated_at.desc())
        assert last_modified is not None
        assert last_modified.id == instance2.id

        since_time1 = instance1.updated_at
        since_query = query_scope.where(Model.updated_at > since_time1)
        modified_since_1 = await repo.all(query=since_query)
        assert len(modified_since_1) == 2
