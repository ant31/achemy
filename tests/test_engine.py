"""
Tests for achemy/engine.py
"""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.pool import NullPool

from achemy import AchemyEngine, DatabaseConfig
from achemy.engine import _generate_cache_key

# --- Fixtures ---

@pytest.fixture
def minimal_config():
    """Provides a minimal valid DatabaseConfig."""
    return DatabaseConfig(db="testdb", user="testuser", password="pw", host="localhost")


@pytest.fixture
def engine_manager(minimal_config):
    """Provides an AchemyEngine instance initialized with minimal config."""
    return AchemyEngine(config=minimal_config)


# --- Test Cases ---

def test_engine_initialization(minimal_config):
    """Test AchemyEngine initialization with valid config."""
    engine = AchemyEngine(config=minimal_config, pool_size=5) # Pass extra kwarg
    assert engine.config == minimal_config
    assert engine.engines == {}
    assert engine.sessions == {}
    # Check if _prep_engine_arguments processed the kwargs correctly
    assert engine.engine_kwargs["poolclass"] is NullPool # Should always be NullPool for async
    assert engine.engine_kwargs["echo"] is False # Default from config
    assert engine.engine_kwargs["connect_args"]["timeout"] == 10 # Default from config, adjusted for asyncpg
    # Check that the extra kwarg *is* present in the prepared arguments
    assert "pool_size" in engine.engine_kwargs
    assert engine.engine_kwargs["pool_size"] == 5


def test_engine_initialization_invalid_config():
    """Test AchemyEngine initialization with invalid config type."""
    with pytest.raises(TypeError, match="config must be an instance of DatabaseConfig"):
        AchemyEngine(config={"db": "wrong_type"})


def test_prep_engine_arguments_defaults(minimal_config):
    """Test _prep_engine_arguments applies defaults correctly."""
    engine = AchemyEngine(config=minimal_config)
    kwargs = engine._prep_engine_arguments({})
    assert kwargs["poolclass"] is NullPool
    assert kwargs["echo"] is False
    assert "timeout" in kwargs["connect_args"]
    assert kwargs["connect_args"]["timeout"] == minimal_config.connect_timeout
    assert "connect_timeout" not in kwargs["connect_args"] # Should be renamed


def test_prep_engine_arguments_overrides(minimal_config):
    """Test _prep_engine_arguments respects explicit overrides."""
    engine = AchemyEngine(
        config=minimal_config,
        echo=True, # Override echo
        connect_args={"timeout": 5, "server_settings": {"application_name": "test_app"}} # Override timeout
    )
    # _prep_engine_arguments is called during __init__
    kwargs = engine.engine_kwargs
    assert kwargs["poolclass"] is NullPool
    assert kwargs["echo"] is True # Explicit override
    assert "timeout" in kwargs["connect_args"]
    assert kwargs["connect_args"]["timeout"] == 5 # Explicit override
    # Because 'timeout' was explicitly provided, the default 'connect_timeout' remains
    assert "connect_timeout" in kwargs["connect_args"]
    assert kwargs["connect_args"]["connect_timeout"] == 10 # Default value remained
    assert kwargs["connect_args"]["server_settings"]["application_name"] == "test_app"


def test_prep_engine_arguments_merges_config_kwargs(minimal_config):
    """Test _prep_engine_arguments merges kwargs from config object."""
    minimal_config.kwargs = {"pool_recycle": 3600} # Add kwarg to config
    engine = AchemyEngine(config=minimal_config)
    kwargs = engine.engine_kwargs
    assert kwargs["pool_recycle"] == 3600


def test_prep_engine_arguments_invalid_connect_args(minimal_config, caplog):
    """Test _prep_engine_arguments handles non-dict connect_args."""
    engine = AchemyEngine(config=minimal_config, connect_args="not_a_dict")
    # Check that connect_args was reset to {} and default timeout applied
    assert isinstance(engine.engine_kwargs["connect_args"], dict)
    assert engine.engine_kwargs["connect_args"]["timeout"] == 10
    # Check for the warning log message
    assert "Expected 'connect_args' to be a dict" in caplog.text


def test_get_engine_creation_and_caching(engine_manager):
    """Test engine() creates and caches engines correctly."""
    # First call - creates engine
    engine1 = engine_manager.engine()
    assert isinstance(engine1, AsyncEngine)
    default_conf_key = _generate_cache_key({})
    assert engine_manager.engines["testdb_public_default"][default_conf_key] is engine1

    # Second call with same params - reuses engine
    engine2 = engine_manager.engine()
    assert engine1 is engine2
    assert len(engine_manager.engines) == 1
    assert len(engine_manager.engines["testdb_public_default"]) == 1

    # Call with different database - creates new engine
    engine3 = engine_manager.engine(database="otherdb")
    assert isinstance(engine3, AsyncEngine)
    assert engine1 is not engine3
    default_conf_key = _generate_cache_key({})
    assert engine_manager.engines["otherdb_public_default"][default_conf_key] is engine3
    assert len(engine_manager.engines) == 2

    # Call with different schema - creates new engine
    engine4 = engine_manager.engine(schema="otherschema")
    assert isinstance(engine4, AsyncEngine)
    assert engine1 is not engine4
    assert engine3 is not engine4
    default_conf_key = _generate_cache_key({})
    assert engine_manager.engines["testdb_otherschema_default"][default_conf_key] is engine4
    assert len(engine_manager.engines) == 3

    # Call with different isolation level - creates new engine
    engine5 = engine_manager.engine(isolation_level="READ_COMMITTED")
    assert isinstance(engine5, AsyncEngine)
    assert engine1 is not engine5
    default_conf_key = _generate_cache_key({})
    assert engine_manager.engines["testdb_public_READ_COMMITTED"][default_conf_key] is engine5
    assert len(engine_manager.engines) == 4

    # Call with different engine kwargs - creates new sub-entry
    engine6 = engine_manager.engine(pool_pre_ping=True)
    assert isinstance(engine6, AsyncEngine)
    assert engine1 is not engine6
    engine_conf_key = _generate_cache_key({"pool_pre_ping": True})
    assert engine_manager.engines["testdb_public_default"][engine_conf_key] is engine6
    assert len(engine_manager.engines["testdb_public_default"]) == 2 # Now two configs for this key


def test_engine_creation_failure(engine_manager):
    """Test that engine creation errors are propagated."""
    with patch(
        'achemy.engine.create_async_engine',
        side_effect=RuntimeError("DB connection failed")
    ) as mock_create:
        with pytest.raises(RuntimeError, match="DB connection failed"):
            engine_manager.engine(database="faildb") # Trigger creation
        mock_create.assert_called_once() # Ensure the mock was called


def test_get_session_creation_and_caching(engine_manager):
    """Test session() creates and caches engines and sessionmakers correctly."""
    # First call - creates engine and sessionmaker
    engine1, sm1 = engine_manager.session()
    assert isinstance(engine1, AsyncEngine)
    assert isinstance(sm1, async_sessionmaker)
    default_engine_conf_key = _generate_cache_key({})
    default_session_conf_key = _generate_cache_key({})
    assert engine_manager.engines["testdb_public_default"][default_engine_conf_key] is engine1
    session_key = f"{default_engine_conf_key}_{default_session_conf_key}"
    assert engine_manager.sessions["testdb_public_default"][session_key] is sm1

    # Second call with same params - reuses both
    engine2, sm2 = engine_manager.session()
    assert engine1 is engine2
    assert sm1 is sm2
    assert len(engine_manager.engines["testdb_public_default"]) == 1
    assert len(engine_manager.sessions["testdb_public_default"]) == 1

    # Call with different session kwargs - reuses engine, new sessionmaker
    engine3, sm3 = engine_manager.session(session_kwargs={"expire_on_commit": True})
    assert engine1 is engine3 # Engine reused
    assert sm1 is not sm3 # New sessionmaker
    assert isinstance(sm3, async_sessionmaker)
    default_engine_conf_key = _generate_cache_key({})
    session_conf_key = _generate_cache_key({"expire_on_commit": True})
    new_session_key = f"{default_engine_conf_key}_{session_conf_key}"
    assert engine_manager.sessions["testdb_public_default"][new_session_key] is sm3
    assert len(engine_manager.sessions["testdb_public_default"]) == 2

    # Call with different engine kwargs - new engine, new sessionmaker
    engine4, sm4 = engine_manager.session(engine_kwargs={"pool_pre_ping": True})
    assert engine1 is not engine4 # New engine
    assert sm1 is not sm4 # New sessionmaker
    assert sm3 is not sm4
    engine_conf_key = _generate_cache_key({"pool_pre_ping": True})
    default_session_conf_key = _generate_cache_key({})
    new_engine_key = "testdb_public_default" # Base key remains the same
    new_session_key_engine = f"{engine_conf_key}_{default_session_conf_key}"
    assert engine_manager.engines[new_engine_key][engine_conf_key] is engine4
    assert engine_manager.sessions[new_engine_key][new_session_key_engine] is sm4
    assert len(engine_manager.engines[new_engine_key]) == 2
    assert len(engine_manager.sessions[new_engine_key]) == 3 # Original, session_kwarg diff, engine_kwarg diff


@pytest.mark.asyncio
async def test_dispose_engines(engine_manager):
    """Test that dispose_engines clears internal caches and calls dispose."""
    # Create a couple of engines and sessions
    _engine1, _sm1 = engine_manager.session()
    _engine2, _sm2 = engine_manager.session(database="otherdb")

    assert len(engine_manager.engines) == 2
    assert len(engine_manager.sessions) == 2

    # Patch the dispose method on the AsyncEngine class itself
    # Target the actual location of the class method
    with patch('sqlalchemy.ext.asyncio.AsyncEngine.dispose', new_callable=AsyncMock) as mock_dispose:
        await engine_manager.dispose_engines()

        # Assertions
        # Check that dispose was awaited twice (once for each engine)
        assert mock_dispose.await_count == 2, (
            f"Expected dispose to be called twice, "
            f"but was called {mock_dispose.await_count} times."
        )
        assert engine_manager.engines == {}, "Engines dictionary not cleared"
        assert engine_manager.sessions == {}, "Sessions dictionary not cleared"


def test_session_creation_failure(engine_manager):
    """Test that sessionmaker creation errors are propagated."""
    # First call to engine() is fine
    engine_manager.engine()

    # Mock sessionmaker to raise an error
    with patch('achemy.engine.async_sessionmaker', side_effect=TypeError("Invalid session args")) as mock_create:
        with pytest.raises(TypeError, match="Invalid session args"):
            # Trigger sessionmaker creation with specific kwargs to ensure it's a new one
            engine_manager.session(session_kwargs={"autoflush": False})
        mock_create.assert_called_once() # Ensure the mock was called
