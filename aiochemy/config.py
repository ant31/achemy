# pylint: disable=no-self-argument
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, aliases

logger: logging.Logger = logging.getLogger("aiochemy")


class BaseConfig(BaseModel):
    model_config = ConfigDict(extra="allow", validate_assignment=False)


class PostgreSQLConfigSchema(BaseConfig):
    """
    Placeholder for configuration schema.

    Expected Attributes:
        db (str): Database name identifier.
        default_schema (str): Default PostgreSQL schema.
        use_internal_pool (bool): Whether to use SQLAlchemy's pool.
        mode (Literal["sync", "async"]): Operation mode.
        connect_timeout (int): Connection timeout in seconds.
        debug (bool): Enable debug logging (e.g., SQL echo).
        async_driver (str): Async driver (e.g., 'asyncpg').
        params (dict): Dictionary of extra connection parameters.
        kwargs (dict): Extra kwargs for engine creation.

    Expected Methods:
        uri() -> str: Returns the synchronous DSN.
        async_uri() -> str: Returns the asynchronous DSN.
    """

    db: str = Field(default="aiochemy-dev")
    user: str = Field(default="aiochemy")
    port: int = Field(default=5432)
    password: str = Field(default="aiochemy")
    host: str = Field(default="localhost")
    params: dict[str, str | int] = Field(default={"sslmode": "disable"})
    driver: str = Field(default="asyncpg", validation_alias=aliases.AliasChoices("async_driver", "driver"))
    connect_timeout: int = Field(default=10)
    create_engine_kwargs: dict[str, Any] = Field(default_factory=dict)
    debug: bool = Field(default=False)
    default_schema: str = Field(default="public")
    kwargs: dict[str, Any] = Field(default_factory=dict)
    dsn: str | None = Field(default=None)

    def uri(self) -> str:
        return self.build_dsn()

    def build_dsn(self) -> str:
        if self.dsn:
            logger.debug("Using provided DSN: %s", self.dsn)
            return self.dsn
        params = self.params.copy()
        if "sslmode" in params and self.driver == "asyncpg":
            logger.debug("Adjusting 'sslmode' to 'ssl' in config params for asyncpg.")
            params["ssl"] = params.pop("sslmode")

        host = f"postgresql+{self.driver}://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"
        query_params = "&".join([f"{k}={v}" for k, v in params.items()])
        if params:
            host = f"{host}?{query_params}"
        return host
