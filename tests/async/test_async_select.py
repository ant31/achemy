"""
Unit tests for query construction via ActiveRecord.
"""
# Note: Tests rely on unique_id for isolation instead of table cleaning.
import pytest
from sqlalchemy import Select as SaSelect


@pytest.mark.asyncio
async def test_select_init(setup_select, test_model):  # setup_select no longer depends on aclean_tables
    """Test that ActiveRecord.select() returns a SQLAlchemy Select object."""
    TestModel = test_model
    select_obj = TestModel.select()
    assert isinstance(select_obj, SaSelect)


@pytest.mark.asyncio
async def test_select_chaining_and_execution(setup_select, test_model, unique_id):
    """Test that query objects from .select() and .where() can be executed."""
    TestModel = test_model
    target_name = f"Where Target {unique_id}"
    name_c = f"Order C {unique_id}"
    name_a = f"Order A {unique_id}"

    async with TestModel.get_session() as session:
        # Create data
        await TestModel(id=f"d_{unique_id}_1", name=target_name).save(session, commit=False)
        await TestModel(id=f"d_{unique_id}_2", name=name_c).save(session, commit=False)
        await TestModel(id=f"d_{unique_id}_3", name=name_a).save(session, commit=False)
        await session.commit()

        # 1. Test .where()
        query_where = TestModel.where(TestModel.name == target_name)
        results_where = (await session.execute(query_where)).scalars().all()
        assert len(results_where) == 1
        assert results_where[0].name == target_name

        # 2. Test chaining .order_by() and .limit()
        query_ordered = (
            TestModel.select().where(TestModel.name.like(f"%_{unique_id}")).order_by(TestModel.name.asc()).limit(2)
        )
        results_ordered = (await session.execute(query_ordered)).scalars().all()
        assert len(results_ordered) == 2
        assert results_ordered[0].name == name_a
        assert results_ordered[1].name == name_c

