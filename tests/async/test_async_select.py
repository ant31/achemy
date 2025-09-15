"""
Unit tests for query construction via the Repository pattern.
"""
# Note: Tests rely on unique_id for isolation instead of table cleaning.
import pytest
from sqlalchemy import Select as SaSelect

from achemy import BaseRepository


class TestModelRepository(BaseRepository):
    """Repository for TestModel used in select tests."""

    def __init__(self, session, model_cls):
        super().__init__(session, model_cls)


@pytest.mark.asyncio
async def test_select_init(setup_select, test_model, async_engine):
    """Test that repo.select() returns a SQLAlchemy Select object."""
    _db_engine, session_factory = async_engine.session()
    async with session_factory() as session:
        repo = TestModelRepository(session, test_model)
        select_obj = repo.select()
        assert isinstance(select_obj, SaSelect)


@pytest.mark.asyncio
async def test_select_chaining_and_execution(setup_select, test_model, unique_id, async_engine):
    """Test that query objects from repo.select() and repo.where() can be executed."""
    TestModel = test_model
    target_name = f"Where Target {unique_id}"
    name_c = f"Order C {unique_id}"
    name_a = f"Order A {unique_id}"

    _db_engine, session_factory = async_engine.session()
    async with session_factory() as session:
        repo = TestModelRepository(session, TestModel)
        # Create data
        await repo.add(TestModel(id=f"d_{unique_id}_1", name=target_name), commit=False)
        await repo.add(TestModel(id=f"d_{unique_id}_2", name=name_c), commit=False)
        await repo.add(TestModel(id=f"d_{unique_id}_3", name=name_a), commit=False)
        await session.commit()

        # 1. Test .where()
        query_where = repo.where(TestModel.name == target_name)
        results_where = (await session.execute(query_where)).scalars().all()
        assert len(results_where) == 1
        assert results_where[0].name == target_name

        # 2. Test chaining .order_by() and .limit()
        query_ordered = (
            repo.select().where(TestModel.name.like(f"%_{unique_id}")).order_by(TestModel.name.asc()).limit(2)
        )
        results_ordered = (await session.execute(query_ordered)).scalars().all()
        assert len(results_ordered) == 2
        assert results_ordered[0].name == name_a
        assert results_ordered[1].name == name_c

