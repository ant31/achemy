from aiochemy.config import PostgreSQLConfigSchema


def test_config():
    PostgresConfig = PostgreSQLConfigSchema(db="aiochemy-test", port=5434)
    assert PostgresConfig.db == "aiochemy-test"
    assert PostgresConfig.user == "aiochemy"
    assert PostgresConfig.port == 5434
    assert PostgresConfig.password == "aiochemy"
    assert PostgresConfig.host == "localhost"
    assert PostgresConfig.params == {"sslmode": "disable"}
    assert PostgresConfig.driver == "asyncpg"
    #``assert PostgresConfig.async_driver == "asyncpg"
    assert PostgresConfig.connect_timeout == 10
    assert PostgresConfig.create_engine_kwargs == {}
    assert PostgresConfig.debug is False
    assert PostgresConfig.default_schema == "public"


    assert PostgresConfig.uri() == "postgresql+asyncpg://aiochemy:aiochemy@localhost:5434/aiochemy-test?ssl=disable"

    PostgresConfig.port = 5435
    assert PostgresConfig.uri() == "postgresql+asyncpg://aiochemy:aiochemy@localhost:5435/aiochemy-test?ssl=disable"
    PostgresConfig. params = {"sslmode": "require"}
    assert PostgresConfig.uri() == "postgresql+asyncpg://aiochemy:aiochemy@localhost:5435/aiochemy-test?ssl=require"
    PostgresConfig.driver = "asyncpg-other"
    assert PostgresConfig.uri() == "postgresql+asyncpg-other://aiochemy:aiochemy@localhost:5435/aiochemy-test?sslmode=require"
