from achemy.config import DatabaseConfig


def test_config():
    PostgresConfig = DatabaseConfig(db="achemy-test", port=5434)
    assert PostgresConfig.db == "achemy-test"
    assert PostgresConfig.user == "achemy"
    assert PostgresConfig.port == 5434
    assert PostgresConfig.password == "achemy"
    assert PostgresConfig.host == "localhost"
    assert PostgresConfig.params == {}
    assert PostgresConfig.driver == "asyncpg"
    #``assert PostgresConfig.async_driver == "asyncpg"
    assert PostgresConfig.connect_timeout == 10
    assert PostgresConfig.create_engine_kwargs == {}
    assert PostgresConfig.debug is False
    assert PostgresConfig.default_schema == "public"


    assert PostgresConfig.uri() == "postgresql+asyncpg://achemy:achemy@localhost:5434/achemy-test?ssl=disable"

    PostgresConfig.port = 5435
    assert PostgresConfig.uri() == "postgresql+asyncpg://achemy:achemy@localhost:5435/achemy-test?ssl=disable"
    PostgresConfig. params = {"ssl": "require"}
    assert PostgresConfig.uri() == "postgresql+asyncpg://achemy:achemy@localhost:5435/achemy-test?ssl=require"
    PostgresConfig.driver = "asyncpg-other"
    assert PostgresConfig.uri() == "postgresql+asyncpg-other://achemy:achemy@localhost:5435/achemy-test?ssl=require"
