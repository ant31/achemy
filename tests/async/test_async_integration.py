"""
Integration tests for asynchronous ActiveAlchemy
"""

import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError

from achemy import BaseRepository
from achemy.demo.amodels import ACity, ACountry, AResident


# --- Repositories for Demo Models ---
class AResidentRepository(BaseRepository[AResident]):
    def __init__(self, session):
        super().__init__(session, AResident)


class ACityRepository(BaseRepository[ACity]):
    def __init__(self, session):
        super().__init__(session, ACity)


class ACountryRepository(BaseRepository[ACountry]):
    def __init__(self, session):
        super().__init__(session, ACountry)


@pytest.mark.asyncio
async def test_integration_create_retrieve_update_delete(async_engine, unique_id):
    """Test the full CRUD cycle in an integration test"""
    _db_engine, session_factory = async_engine.session()
    async with session_factory() as session:
        resident_repo = AResidentRepository(session)
        country_repo = ACountryRepository(session)
        city_repo = ACityRepository(session)

        user = AResident(name=f"intuser_{unique_id}", email=f"int_{unique_id}@example.com")
        await resident_repo.save(user, commit=True)
        user_id = user.id

        retrieved_user = await resident_repo.get(user_id)
        assert retrieved_user is not None
        assert retrieved_user.name == f"intuser_{unique_id}"
        assert retrieved_user.email == f"int_{unique_id}@example.com"

        c1 = await country_repo.save(ACountry(name="country1", code=f"c1_{unique_id}"), commit=True)
        await session.refresh(c1)
        assert c1.id != uuid.UUID("00000000-0000-0000-0000-000000000000")

        cities_to_add = [ACity(name=f"city{i}", country_id=c1.id) for i in range(3)]
        await city_repo.add_all(cities_to_add, commit=True)

        c1_new = await country_repo.get(c1.id)
        assert c1_new is not None
        assert len(await city_repo.all()) == 3
        assert len(await c1_new.awaitable_attrs.cities) == 3
        assert all(city.country_id == c1.id for city in await c1_new.awaitable_attrs.cities)

        code = f"c2_{unique_id}"
        c1_new.code = code
        c1_new = await country_repo.save(c1_new, commit=True)

        c1_new = await country_repo.get(c1.id)
        assert c1_new is not None
        assert c1_new.code == code

        new_cities_result = await city_repo.all(query=city_repo.where(ACity.country_id == c1.id))
        assert len(new_cities_result) == 3
        await country_repo.delete(c1_new, commit=True)
        c1_new = await country_repo.get(c1.id)
        assert c1_new is None

        new_cities_result_after_delete = await city_repo.all(query=city_repo.where(ACity.country_id == c1.id))
        assert len(new_cities_result_after_delete) == 0


@pytest.mark.asyncio
async def test_integration_first(async_engine, unique_id):
    """Test the repository .first() method."""
    _db_engine, session_factory = async_engine.session()
    async with session_factory() as session:
        repo = ACountryRepository(session)
        c1 = await repo.save(ACountry(name=f"Zimbabwe_{unique_id}", code=f"ZW_{unique_id}"), commit=True)
        c2 = await repo.save(ACountry(name=f"Albania_{unique_id}", code=f"AL_{unique_id}"), commit=True)
        c3 = await repo.save(ACountry(name=f"Canada_{unique_id}", code=f"CA_{unique_id}"), commit=True)

        first_by_pk = await repo.first()
        assert first_by_pk is not None
        assert isinstance(first_by_pk, ACountry)

        first_by_name_asc = await repo.first(order_by=ACountry.name.asc())
        assert first_by_name_asc is not None
        assert first_by_name_asc.id == c2.id

        first_by_name_desc = await repo.first(order_by=ACountry.name.desc())
        assert first_by_name_desc is not None
        assert first_by_name_desc.id == c1.id

        query = repo.where(ACountry.code == f"CA_{unique_id}")
        first_canada = await repo.first(query=query)
        assert first_canada is not None
        assert first_canada.id == c3.id

        query_ordered = repo.where(ACountry.name.like("%a%")).order_by(ACountry.name.asc())
        first_a_asc = await repo.first(query=query_ordered)
        assert first_a_asc is not None
        assert first_a_asc.id == c2.id

        query_none = repo.where(ACountry.code == "XX")
        first_none = await repo.first(query=query_none)
        assert first_none is None


@pytest.mark.asyncio
async def test_integration_add_all(async_engine, unique_id):
    """Test the repository .add_all() method."""
    _db_engine, session_factory = async_engine.session()
    countries_to_add_commit = [
        ACountry(name=f"Commit_{unique_id}_1", code=f"C{unique_id}1"),
        ACountry(name=f"Commit_{unique_id}_2", code=f"C{unique_id}2"),
    ]
    async with session_factory() as s:
        repo = ACountryRepository(s)
        added_countries_commit = await repo.add_all(countries_to_add_commit)
    assert len(added_countries_commit) == 2

    async with session_factory() as verify_session:
        repo = ACountryRepository(verify_session)
        found1 = await repo.find_by(code=f"C{unique_id}1")
        found2 = await repo.find_by(code=f"C{unique_id}2")
        assert found1 is not None
        assert found2 is not None

    async with session_factory() as session_no_commit:
        repo = ACountryRepository(session_no_commit)
        countries_to_add_no_commit = [
            ACountry(name=f"NoCommit_{unique_id}_1", code=f"NC{unique_id}1"),
        ]
        await repo.add_all(countries_to_add_no_commit, commit=False)

        async with session_factory() as verify_session_no_commit:
            repo_verify = ACountryRepository(verify_session_no_commit)
            assert await repo_verify.find_by(code=f"NC{unique_id}1") is None
        await session_no_commit.commit()

    async with session_factory() as verify_session_after_commit:
        repo = ACountryRepository(verify_session_after_commit)
        assert await repo.find_by(code=f"NC{unique_id}1") is not None

    async with session_factory() as s:
        repo = ACountryRepository(s)
        await repo.add_all([], s)

    async with session_factory() as session_flush_error:
        repo = ACountryRepository(session_flush_error)
        await repo.save(ACountry(name=f"Constraint_{unique_id}", code=f"CON{unique_id}"), commit=True)
        countries_violation = [
            ACountry(name=f"Duplicate_{unique_id}", code=f"CON{unique_id}"),
        ]
        with pytest.raises(SQLAlchemyError):
            await repo.add_all(countries_violation, commit=True)


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
