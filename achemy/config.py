# pylint: disable=no-self-argument
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, aliases

logger: logging.Logger = logging.getLogger("achemy")


class BaseConfig(BaseModel):
    model_config = ConfigDict(extra="allow", validate_assignment=False)


class DatabaseConfig(BaseConfig):
    """
    Database configuration schema.

    Defines connection parameters for creating a SQLAlchemy engine DSN.
    """

    db: str = Field(default="achemy-dev")
    user: str = Field(default="achemy")
    port: int = Field(default=5432)
    password: str = Field(default="achemy")
    host: str = Field(default="localhost")
    params: dict[str, str | int] = Field(default_factory=dict)
    dialect: str = Field(default="postgresql")
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

        # Define dialect-specific default parameters
        default_params = {
            # asyncpg uses 'ssl' in the DSN query string
            "postgresql": {"ssl": "disable"},
        }

        # Start with defaults for the current dialect, if any
        final_params = default_params.get(self.dialect, {}).copy()
        # Merge user-provided params, which will override defaults
        final_params.update(self.params)

        host = f"{self.dialect}+{self.driver}://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"
        if final_params:
            query_params = "&".join([f"{k}={v}" for k, v in final_params.items()])
            host = f"{host}?{query_params}"
        return host
