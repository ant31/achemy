"""
Unit tests for the async Select class
"""
# Note: Tests rely on unique_id for isolation instead of table cleaning.
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError


@pytest.mark.asyncio
async def test_select_init(setup_select, test_model): # setup_select no longer depends on aclean_tables
    """Test Select class initialization"""
    # Test initialization (session is no longer stored in Select)

    TestModel = test_model
    select = TestModel.select() # No session passed here
    # assert select._session is None # _session attribute removed
    assert select._orm_cls == TestModel

    # Test initialization without session (same as above now)
    # select = Select[TestModel](TestModel) # Select() takes entities directly
    # select.set_context(cls=TestModel) # No session in set_context
    # assert select._session is None
    # assert select._orm_cls == TestModel


@pytest.mark.asyncio
async def test_select_scalars(async_engine, setup_select, test_model, unique_id):
    """Test Select.scalars method"""
    TestModel = test_model
    # Create unique data for this test
    async with TestModel.get_session() as session:
        await TestModel(id=f"s_{unique_id}_1", name=f"Scalar 1 {unique_id}").save(session, commit=False)
        await TestModel(id=f"s_{unique_id}_2", name=f"Scalar 2 {unique_id}").save(session, commit=False)
        await TestModel(id=f"s_{unique_id}_3", name=f"Scalar 3 {unique_id}").save(session, commit=False)
        await session.commit()

        # Session must be provided to scalars()
        select = TestModel.select().where(TestModel.id.like(f"s_{unique_id}%")) # Filter for this test's data
        result = await select.scalars(session=session) # Pass session here
        items = list(result)
        assert len(items) == 3
        assert all(isinstance(item, TestModel) for item in items)
        assert {item.id for item in items} == {f"s_{unique_id}_1", f"s_{unique_id}_2", f"s_{unique_id}_3"}

    # Test calling via ActiveRecord.all (which handles session internally)
    # Need to create data again or use a different approach if relying on .all() without filter
    async with TestModel.get_session() as session_all:
        await TestModel(id=f"sa_{unique_id}_1", name=f"Scalar All 1 {unique_id}").save(session_all, commit=True)
        await TestModel(id=f"sa_{unique_id}_2", name=f"Scalar All 2 {unique_id}").save(session_all, commit=True)

        # Use a query with .all() to isolate data
        query_all = TestModel.select().where(TestModel.id.like(f"sa_{unique_id}%"))
        result_all = await TestModel.all(session_all, query=query_all)  # Pass session and query
        items_all = list(result_all)
        assert len(items_all) == 2
        assert {item.id for item in items_all} == {f"sa_{unique_id}_1", f"sa_{unique_id}_2"}


@pytest.mark.asyncio
async def test_select_where(setup_select, test_model, unique_id):
    """Test Select with where clause"""
    TestModel = test_model
    target_name = f"Where Target {unique_id}"
    async with TestModel.get_session() as session:
        # Create unique data
        await TestModel(id=f"w_{unique_id}_1", name=f"Where Other {unique_id}").save(session, commit=False)
        await TestModel(id=f"w_{unique_id}_2", name=target_name).save(session, commit=False)
        await TestModel(id=f"w_{unique_id}_3", name=f"Where Else {unique_id}").save(session, commit=False)
        await session.commit()

        select = TestModel.select().where(TestModel.name == target_name) # No session in select()
        result = await select.scalars(session=session) # Pass session here
        items = list(result)
        assert len(items) == 1
        assert items[0].name == target_name
        assert items[0].id == f"w_{unique_id}_2"


@pytest.mark.asyncio
async def test_select_order_by(setup_select, test_model, unique_id):
    """Test Select with order_by clause"""
    TestModel = test_model
    name1 = f"Order C {unique_id}"
    name2 = f"Order A {unique_id}"
    name3 = f"Order B {unique_id}"
    async with TestModel.get_session() as session:
        # Create unique data
        await TestModel(id=f"o_{unique_id}_1", name=name1).save(session, commit=False)  # C
        await TestModel(id=f"o_{unique_id}_2", name=name2).save(session, commit=False)  # A
        await TestModel(id=f"o_{unique_id}_3", name=name3).save(session, commit=False)  # B
        await session.commit()

        # Filter for this test's data
        select = (
            TestModel.select()
            .where(TestModel.id.like(f"o_{unique_id}%"))
            .order_by(TestModel.name.desc()) # No session in select()
        )
        result = await select.scalars(session=session) # Pass session here
        items = list(result)
        assert len(items) == 3
        assert items[0].name == name1 # C (desc)
        assert items[1].name == name3 # B
        assert items[2].name == name2 # A

        select_asc = (
            TestModel.select()
            .where(TestModel.id.like(f"o_{unique_id}%"))
            .order_by(TestModel.name.asc())
        )
        result_asc = await select_asc.scalars(session=session)
        items_asc = list(result_asc)
        assert len(items_asc) == 3
        assert items_asc[0].name == name2 # A (asc)
        assert items_asc[1].name == name3 # B
        assert items_asc[2].name == name1 # C


@pytest.mark.asyncio
async def test_select_limit(setup_select, test_model, unique_id):
    """Test Select with limit clause"""
    TestModel = test_model
    async with TestModel.get_session() as session:
        # Create unique data
        await TestModel(id=f"l_{unique_id}_1", name=f"Limit 1 {unique_id}").save(session, commit=False)
        await TestModel(id=f"l_{unique_id}_2", name=f"Limit 2 {unique_id}").save(session, commit=False)
        await TestModel(id=f"l_{unique_id}_3", name=f"Limit 3 {unique_id}").save(session, commit=False)
        await session.commit()

        # Filter for this test's data and apply limit
        select = (
            TestModel.select()
            .where(TestModel.id.like(f"l_{unique_id}%"))
            .order_by(TestModel.name)
            .limit(2) # No session in select()
        )
        result = await select.scalars(session=session) # Pass session here
        items = list(result)
        assert len(items) == 2
        # Verify the correct items based on ordering
        assert items[0].name == f"Limit 1 {unique_id}"
        assert items[1].name == f"Limit 2 {unique_id}"


@pytest.mark.asyncio
async def test_select_scalars_no_session(setup_select, test_model):
    """Test Select.scalars raises ValueError if session is None."""
    TestModel = test_model
    select = TestModel.select()
    with pytest.raises(ValueError, match="Session is required"):
        # Explicitly pass None, although type hints should prevent this in real code
        await select.scalars(session=None) # type: ignore


@pytest.mark.asyncio
async def test_select_scalars_db_error(setup_select, test_model):
    """Test Select.scalars raises SQLAlchemyError on execution failure."""
    TestModel = test_model
    select = TestModel.select()

    # Mock the session's execute method to raise an error
    mock_session = AsyncMock()
    mock_session.execute.side_effect = SQLAlchemyError("Database connection failed")

    with pytest.raises(SQLAlchemyError, match="Database connection failed"):
        await select.scalars(session=mock_session)

    mock_session.execute.assert_awaited_once()

