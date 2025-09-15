import os

import pytest
import pytest_asyncio
import sqlalchemy
from sqlalchemy import String, text
from sqlalchemy.orm import Mapped, mapped_column

from achemy import AchemyEngine, Base, DatabaseConfig


# Database configuration for tests
@pytest.fixture(scope="session")
def db_config():
    """Get database configuration from environment variables or use defaults"""
    return DatabaseConfig(
        user=os.environ.get("TEST_DB_USER", "activealchemy"),
        password=os.environ.get("TEST_DB_PASSWORD", "activealchemy"),
        host=os.environ.get("TEST_DB_HOST", "localhost"),
        port=int(os.environ.get("TEST_DB_PORT", "5434")),
        db=os.environ.get("TEST_DB", "pythonapp-test"),
        debug=os.environ.get("TEST_DB_DEBUG", "false").lower() == "true",
        driver="asyncpg"
    )


# Async fixtures
@pytest_asyncio.fixture(scope="session")
async def async_engine(db_config):
    """Create an async engine once per test session""" # Updated docstring
    db_config.driver = "asyncpg"
    db_config.params = {"ssl": "disable", "timeout": 5}
    print("Creating async engine...")
    engine = AchemyEngine(db_config)
    # ActiveRecord has been removed; the engine is now passed to tests
    # via the 'async_engine' fixture where needed.
    yield engine

    print("\nDisposing async engines...") # Add print for debugging test runs
    await engine.dispose_engines()
    print("Async engines disposed.")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def acreate_tables(async_engine):
    """Create all tables defined in Base.metadata once per session."""
    print("acreate_tables: Creating all tables...")
    async with async_engine.engine().begin() as conn:
        # Drop and create all tables associated with the Base metadata
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("acreate_tables: All tables created.")
    yield # Let the session run
    # Optional: Drop tables after session if needed, but cleaning might be sufficient
    # print("acreate_tables: Dropping all tables post-session...")
    # async with async_engine.engine().begin() as conn:
    #     await conn.run_sync(Base.metadata.drop_all)
    # print("acreate_tables: All tables dropped.")


class TestModel(Base):
    """Test model for select tests"""
    # Note: Removed aclean_tables fixture. Tests now rely on unique_id
    # for isolation. Ensure all test data creation and queries use unique_id.
    __tablename__ = "test_select_models"

    id: Mapped[str] = mapped_column(primary_key=True, init=True)
    name: Mapped[str] = mapped_column(String, nullable=False, init=True)

@pytest.fixture(scope="session")
def test_model():
    """Provide the TestModel class for tests"""
    return TestModel

@pytest_asyncio.fixture
async def setup_select(async_engine, test_model): # Removed aclean_tables
    """Set up select tests"""
    print("setup_select")
    # TestModel.set_engine(async_engine)  # No longer needed with repository pattern

    # Clean up
    async with async_engine.engine().begin() as conn:
        # Pass the specific model's metadata
        # Ensure table exists (create_all is idempotent)
        await conn.run_sync(test_model.metadata.create_all)

    # Data creation moved to individual tests
    print("setup_select: Table ensured.")

@pytest_asyncio.fixture
async def setup_mixin_tests(async_engine, # Removed aclean_tables
                            mock_pk_model_class, mock_update_model_class, mock_combined_model_class):
    """Set up engine and tables for mixin tests."""
    models = [mock_pk_model_class, mock_update_model_class, mock_combined_model_class]
    # Create tables
    print("setup_mixin_tests")
    async with async_engine.engine().begin() as conn:
        print("Creating tables...")
        for model in models:
            print(f"Creating table: {model.__tablename__}")
            await conn.run_sync(model.metadata.create_all)


@pytest_asyncio.fixture(scope="session",autouse=True)
async def aclean_tables(async_engine, acreate_tables): # Depend on acreate_tables
    """Clean all tables before and after tests"""
    # Ensure all known tables, including the one for SimpleModel, are listed
    tables = ["simple_models_activerecord",
              "test_select_models", "mock_pk_models", "mock_update_models",
              "mock_combined_models", "resident_city", "resident", "city","country", ]
    print("aclean: Cleaning tables before session...")
    # Use the engine manager provided by the fixture
    # Get a session using the globally set engine manager
    _db_engine, session_factory = async_engine.session()
    async with session_factory() as session:
        print("Cleaning tables...")
        async with session.begin(): # Use a transaction for cleanup
            print("Cleaning tables in transaction...")
            for table in tables: # Truncate in reverse dependency order
                print(f"Truncating table: {table}") # Debug print
                # Suppress errors if table doesn't exist
                try:
                    await session.execute(text(f'DELETE FROM "{table}"'))
                    print(f"Truncated table: {table}")
                except sqlalchemy.exc.SQLAlchemyError as e:
                    # This might happen if the table doesn't exist yet on the first run
                    print(f"Error deleting from table {table}: {e}")
        # No explicit commit needed with session.begin()

    yield # Let the session run

    # Add cleanup *after* the session as well to ensure clean state
    print("aclean: Cleaning tables post-session...")
    _db_engine, session_factory = async_engine.session()
    async with session_factory() as session:
        print("Cleaning tables post-session...")
        async with session.begin():
            print("Cleaning tables post-session in transaction...")
            # Iterate in reverse to handle potential foreign key dependencies if any exist
            for table in reversed(tables):
                print(f"Deleting from table post-session: {table}")
                try:
                    # Use DELETE instead of TRUNCATE for potentially better compatibility
                    # and to avoid issues if tables were dropped/recreated differently.
                    await session.execute(text(f'DELETE FROM "{table}"'))
                    print(f"Deleted from table post-session: {table}")
                except sqlalchemy.exc.SQLAlchemyError as e:
                    # Log errors but continue cleaning other tables
                    print(f"Error deleting post-session from table {table}: {e}")
