"""
Integration tests for asynchronous ActiveAlchemy
"""

import asyncio
import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError  # Import necessary exceptions

from achemy.demo.amodels import ACity, ACountry, AResident


@pytest.mark.asyncio
async def test_integration_create_retrieve_update_delete(async_engine, unique_id): # Removed aclean_tables
    """Test the full CRUD cycle in an integration test"""
    # Note: Relies on unique_id for isolation instead of table cleaning.
    async with ACountry.get_session() as session:

        user = AResident(name=f"intuser_{unique_id}", email=f"int_{unique_id}@example.com")
        await user.save(session, commit=True)
        user_id = user.id

        # Retrieve the user
        retrieved_user = await AResident.get(session, user_id)
        assert retrieved_user is not None
        assert retrieved_user.name == f"intuser_{unique_id}"
        assert retrieved_user.email == f"int_{unique_id}@example.com"

        c1 = await ACountry(name="country1", code=f"c1_{unique_id}").save(session, commit=True)
        # await c1.refresh_me()
        await session.refresh(c1)
        assert c1.id != uuid.UUID("00000000-0000-0000-0000-000000000000")

        # Create items for the user
        queries = []
        for i in range(3):
            queries.append(ACity(name=f"city{i}", country_id=c1.id).save(session, commit=False))
        cities = await asyncio.gather(*queries)
        await session.commit()
        assert len(cities) == 3
        c1_new = await ACountry.get(session, c1.id)
        assert c1_new is not None
        assert len(await ACity.all(session)) == 3
        assert len(await c1_new.awaitable_attrs.cities) == 3
        assert all(city.country_id == c1.id for city in cities)

        # Update the user
        code = f"c2_{unique_id}"
        c1_new.code = code
        c1_new = await c1_new.save(session, commit=True)

        #     # verify update
        c1_new = await ACountry.find(session, c1.id)
        assert c1_new is not None
        assert c1_new.code == code

        # Pass session to scalars()
        new_cities_result = await ACity.where(ACity.country_id == c1.id).scalars(session=session)
        new_cities = new_cities_result.all()
        assert len(new_cities) == 3
        await ACountry.delete(c1_new, session)
        await session.commit()
        c1_new = await ACountry.find(session, c1.id)
        assert c1_new is None

        # Pass session to scalars()
        new_cities_result = await ACity.where(ACity.country_id == c1.id).scalars(session=session)
        new_cities = new_cities_result.all()
        assert len(new_cities) == 0


@pytest.mark.asyncio
async def test_integration_first(async_engine, unique_id): # Removed aclean_tables
    """Test the ActiveRecord.first() method."""
    # Note: Relies on unique_id for isolation instead of table cleaning.
    async with ACountry.get_session() as session:
        # Create some data with predictable order
        # Removed sleeps - rely on transaction order/PK uniqueness
        c1 = await ACountry(name=f"Zimbabwe_{unique_id}", code=f"ZW_{unique_id}").save(session, commit=True)
        # Should be last alphabetically
        c2 = await ACountry(name=f"Albania_{unique_id}", code=f"AL_{unique_id}").save(session, commit=True)
        # Should be first alphabetically
        c3 = await ACountry(name=f"Canada_{unique_id}", code=f"CA_{unique_id}").save(session, commit=True)

        # 1. Test first() without arguments (default order by PK)
        # The actual order depends on UUID generation, so we can't reliably assert which one is first by PK.
        # Instead, we'll just check that *a* record is returned.
        first_by_pk = await ACountry.first(session)
        assert first_by_pk is not None
        assert isinstance(first_by_pk, ACountry)

        # 2. Test first() with explicit order_by (name ascending)
        first_by_name_asc = await ACountry.first(session, order_by=ACountry.name.asc())
        assert first_by_name_asc is not None
        assert first_by_name_asc.id == c2.id
        assert first_by_name_asc.name == f"Albania_{unique_id}"

        # 3. Test first() with explicit order_by (name descending)
        first_by_name_desc = await ACountry.first(session, order_by=ACountry.name.desc())
        assert first_by_name_desc is not None
        assert first_by_name_desc.id == c1.id
        assert first_by_name_desc.name == f"Zimbabwe_{unique_id}"

        # 4. Test first() with a query (where clause)
        query = ACountry.select().where(ACountry.code == f"CA_{unique_id}")
        first_canada = await ACountry.first(session, query=query)
        assert first_canada is not None
        assert first_canada.id == c3.id
        assert first_canada.code == f"CA_{unique_id}"

        # 5. Test first() with a query and order_by
        query_ordered = ACountry.select().where(ACountry.name.like("%a%")).order_by(ACountry.name.asc())
        # Albania, Canada, Zimbabwe -> Albania
        first_a_asc = await ACountry.first(session, query=query_ordered)
        assert first_a_asc is not None
        assert first_a_asc.id == c2.id  # Albania

        query_ordered_desc = ACountry.select().where(ACountry.name.like("%a%")).order_by(ACountry.name.desc())
        # Zimbabwe, Canada, Albania -> Zimbabwe
        first_a_desc = await ACountry.first(session, query=query_ordered_desc)
        assert first_a_desc is not None
        assert first_a_desc.id == c1.id  # Zimbabwe

        # 6. Test first() when no records match
        query_none = ACountry.select().where(ACountry.code == "XX")
        first_none = await ACountry.first(session, query=query_none)
        assert first_none is None

        # 7. Test first() using an externally provided session
        # Create a new session
        async with ACountry.get_session() as external_session:
            first_external_session = await ACountry.first(external_session, order_by=ACountry.name.asc())
            assert first_external_session is not None
            assert first_external_session.id == c2.id  # Should still find Albania


@pytest.mark.asyncio
async def test_integration_add_all(async_engine, unique_id): # Removed aclean_tables
    """Test the ActiveRecord.add_all() method."""
    # Note: Relies on unique_id for isolation instead of table cleaning.
    # 1. Test add_all with commit=True (default)
    countries_to_add_commit = [
        ACountry(name=f"Commit_{unique_id}_1", code=f"C{unique_id}1"),
        ACountry(name=f"Commit_{unique_id}_2", code=f"C{unique_id}2"),
    ]
    async with ACountry.get_session() as s:
        added_countries_commit = await ACountry.add_all(countries_to_add_commit, s)

    assert len(added_countries_commit) == 2
    assert all(c.id is not None for c in added_countries_commit)  # Should have IDs after commit
    # Verify they are in the DB using a new session
    async with ACountry.get_session() as verify_session:
        found1 = await ACountry.find_by(verify_session, code=f"C{unique_id}1")
        found2 = await ACountry.find_by(verify_session, code=f"C{unique_id}2")
        assert found1 is not None
        assert found2 is not None
        assert found1.name == f"Commit_{unique_id}_1"
        assert found2.name == f"Commit_{unique_id}_2"

    # 2. Test add_all with commit=False
    async with ACountry.get_session() as session_no_commit:
        countries_to_add_no_commit = [
            ACountry(name=f"NoCommit_{unique_id}_1", code=f"NC{unique_id}1"),
            ACountry(name=f"NoCommit_{unique_id}_2", code=f"NC{unique_id}2"),
        ]
        # Add within the session context, but don't commit yet
        added_countries_no_commit = await ACountry.add_all(
            countries_to_add_no_commit, session_no_commit, commit=False
        )

        assert len(added_countries_no_commit) == 2
        # Should have IDs after flush (which happens in add_all when commit=False)
        ids = await asyncio.gather(*[c.awaitable_attrs.id for c in added_countries_no_commit])
        assert all(c is not None for c in ids)
        # Verify they are NOT YET in the DB using a separate session
        async with ACountry.get_session() as verify_session_no_commit:
            found_nc1_before = await ACountry.find_by(verify_session_no_commit, code=f"NC{unique_id}1")
            found_nc2_before = await ACountry.find_by(verify_session_no_commit, code=f"NC{unique_id}2")
            assert found_nc1_before is None
            assert found_nc2_before is None

        # Now commit the original session
        await session_no_commit.commit()

        # Verify they ARE NOW in the DB using a new session
        async with ACountry.get_session() as verify_session_after_commit:
            found_nc1_after = await ACountry.find_by(verify_session_after_commit, code=f"NC{unique_id}1")
            found_nc2_after = await ACountry.find_by(verify_session_after_commit, code=f"NC{unique_id}2")
            assert found_nc1_after is not None
            assert found_nc2_after is not None
            assert found_nc1_after.name == f"NoCommit_{unique_id}_1"
            assert found_nc2_after.name == f"NoCommit_{unique_id}_2"

    # 3. Test add_all with explicit session (commit=True)
    async with ACountry.get_session() as explicit_session:
        countries_explicit = [
            ACountry(name=f"Explicit_{unique_id}_1", code=f"EX{unique_id}1"),
        ]
        await ACountry.add_all(countries_explicit, explicit_session)  # Commit=True is default
        # Verify within the same session (already committed)
        found_ex1 = await ACountry.find_by(explicit_session, code=f"EX{unique_id}1")
        assert found_ex1 is not None

    # 4. Test add_all with empty list
    async with ACountry.get_session() as s:
        added_empty = await ACountry.add_all([], s)
        assert added_empty == []

    # 5. Test add_all error handling (commit error) - Mocking needed
    # This requires mocking the session.commit() to raise an error
    # We'll skip the direct implementation here as it needs more mocking setup,
    # but the principle is to ensure rollback occurs.

    # 6. Test add_all error handling (flush error - e.g., constraint)
    async with ACountry.get_session() as session_flush_error:
        # Create a country first to cause a unique constraint violation
        # Removed unused variable assignment and fixed line length
        await ACountry(name=f"Constraint_{unique_id}", code=f"CON{unique_id}").save(
            session_flush_error, commit=True
        )

        countries_violation = [
            ACountry(name=f"Valid_{unique_id}", code=f"VALID{unique_id}"),
            ACountry(name=f"Duplicate_{unique_id}", code=f"CON{unique_id}"),  # Duplicate code
        ]
        # Catch a more specific SQLAlchemy error, likely IntegrityError for unique constraint
        with pytest.raises(SQLAlchemyError):
            # Use the same session, commit=False to trigger flush error
            await ACountry.add_all(countries_violation, session_flush_error, commit=False)

        # Verify the valid one wasn't added either due to rollback within the context manager
        # (Note: add_all itself doesn't explicitly rollback on flush error,
        # the session context manager does if an error propagates out)
        async with ACountry.get_session() as verify_session_flush:
            found_valid = await ACountry.find_by(verify_session_flush, code=f"VALID{unique_id}")
            assert found_valid is None


# @pytest.mark.asyncio
# async def test_integration_querying(engine_and_models, unique_id):
#     """Test complex querying functionality"""
#     # Create multiple users
#     users = []
#     for i in range(5):
#         user = AsyncTestUser(
#             username=f"quser_{i}_{unique_id}",
#             email=f"q_{i}_{unique_id}@example.com",
#             is_active=(i % 2 == 0)  # Some active, some inactive
#         )
#         await user.save(commit=True)
#         users.append(user)

#         # Create items for each user
#         for j in range(i + 1):  # Each user has a different number of items
#             item = AsyncTestItem(
#                 name=f"Item {j} for User {i}_{unique_id}",
#                 description=f"Description {j}",
#                 user_id=user.id
#             )
#             await item.save(commit=True)

#     # Query active users
#     active_users = await AsyncTestUser.all(AsyncTestUser.where(
#         AsyncTestUser.is_active == True,
#         AsyncTestUser.username.like(f"quser_%_{unique_id}")
#     ))
#     assert len(active_users) == 3  # Users 0, 2, 4 are active

#     # Query users with at least 3 items
#     users_with_many_items = []
#     all_query_users = await AsyncTestUser.all(AsyncTestUser.where(
#         AsyncTestUser.username.like(f"quser_%_{unique_id}")
#     ))
#     for user in all_query_users:
#         await AsyncTestUser.refresh(user)
#         if len(user.items) >= 3:
#             users_with_many_items.append(user)

#     assert len(users_with_many_items) == 3  # Users 2, 3, 4 have 3+ items

#     # Clean up
#     for user in users:
#         await user.delete_me()
#         await user.commit_me()


# @pytest.mark.asyncio
# async def test_integration_transactions(engine_and_models, unique_id):
#     """Test transaction handling"""
#     # Create a session
#     async with engine_and_models.session_factory() as session:
#         # Start a transaction
#         async with session.begin():
#             # Create a user within the transaction
#             user = AsyncTestUser(
#                 username=f"txuser_{unique_id}",
#                 email=f"tx_{unique_id}@example.com"
#             )
#             session.add(user)
#             await session.flush()  # Flush but don't commit

#             user_id = user.id

#             # Create an item
#             item = AsyncTestItem(
#                 name=f"Transaction item for {unique_id}",
#                 description="This item is in a transaction",
#                 user_id=user_id
#             )
#             session.add(item)

#             # Rollback manually (simulating an error)
#             # We use a nested session to rollback within our test
#             await session.rollback()

#     # After rollback, user shouldn't exist
#     found_user = await AsyncTestUser.get(user_id)
#     assert found_user is None

#     # Create a successful transaction
#     user = AsyncTestUser(
#         username=f"txuser2_{unique_id}",
#         email=f"tx2_{unique_id}@example.com"
#     )
#     await user.save(commit=False)  # Don't commit yet

#     item = AsyncTestItem(
#         name=f"Successful transaction item for {unique_id}",
#         description="This item will be committed",
#         user_id=user.id
#     )
#     await item.save(commit=False)  # Don't commit yet

#     # Now commit both changes at once
#     await user.commit_me()

#     # Verify both were saved
#     retrieved_user = await AsyncTestUser.get(user.id)
#     assert retrieved_user is not None

#     await AsyncTestUser.refresh(retrieved_user)
#     assert len(retrieved_user.items) == 1
#     assert retrieved_user.items[0].name == f"Successful transaction item for {unique_id}"

#     # Clean up
#     await user.delete_me()
#     await user.commit_me()


# @pytest.mark.asyncio
# async def test_integration_concurrency(engine_and_models, unique_id):
#     """Test concurrent operations"""
#     # Create a base user to attach items to
#     base_user = AsyncTestUser(
#         username=f"concurrent_user_{unique_id}",
#         email=f"concurrent_{unique_id}@example.com"
#     )
#     await base_user.save(commit=True)

#     # Function to create items asynchronously
#     async def create_item(i):
#         item = AsyncTestItem(
#             name=f"Concurrent Item {i} for {unique_id}",
#             description=f"Created concurrently {i}",
#             user_id=base_user.id
#         )
#         await item.save(commit=True)
#         return item.id

#     # Create multiple items concurrently
#     item_ids = await asyncio.gather(*[create_item(i) for i in range(10)])

#     # Verify all items were created
#     assert len(item_ids) == 10

#     # Retrieve the user and verify items
#     retrieved_user = await AsyncTestUser.get(base_user.id)
#     await AsyncTestUser.refresh(retrieved_user)

#     assert len(retrieved_user.items) == 10

#     # Function to update items asynchronously
#     async def update_item(item_id, i):
#         item = await AsyncTestItem.get(item_id)
#         item.description = f"Updated concurrently {i}"
#         await item.save(commit=True)

#     # Update all items concurrently
#     await asyncio.gather(*[update_item(item_id, i) for i, item_id in enumerate(item_ids)])

#     # Verify updates
#     for i, item_id in enumerate(item_ids):
#         item = await AsyncTestItem.get(item_id)
#         assert item.description == f"Updated concurrently {i}"

#     # Clean up
#     await base_user.delete_me()
#     await base_user.commit_me()
