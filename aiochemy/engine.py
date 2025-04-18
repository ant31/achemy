"""
Provides the asynchronous SQLAlchemy engine manager for ActiveAlchemy.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from aiochemy.config import PostgreSQLConfigSchema

logger = logging.getLogger(__name__)


class ActiveEngine:
    """
    Manages asynchronous SQLAlchemy engines and sessions for ActiveAlchemy.

    This class handles the creation and configuration of AsyncEngine and
    async_sessionmaker based on a provided configuration schema.
    """

    config: PostgreSQLConfigSchema
    engine_kwargs: dict[str, Any]
    sessions: dict[str, dict[str, async_sessionmaker[AsyncSession]]]
    engines: dict[str, dict[str, AsyncEngine]]

    def __init__(self, config: PostgreSQLConfigSchema, **kwargs: Any):
        """
        Initializes the ActiveEngine.

        Args:
            config: The configuration object (e.g., PostgreSQLConfigSchema).
            **kwargs: Additional keyword arguments to pass to the engine creator.
        """
        if not isinstance(config, PostgreSQLConfigSchema):
            raise TypeError("config must be an instance of PostgreSQLConfigSchema")
        self.config = config
        logger.debug(f"Initializing ActiveEngine with config: {config}")
        self.engine_kwargs = self._prep_engine_arguments(kwargs)
        self.sessions = {}
        self.engines = {}
        # Fork handling is removed as it's less relevant for pure async

    def _prep_engine_arguments(self, incoming_kwargs: dict[str, Any]) -> dict[str, Any]:
        """
        Prepare the keyword arguments for SQLAlchemy async engine creation.

        Merges default arguments derived from the `self.config` object with
        any explicitly provided `incoming_kwargs`. Handles specific adjustments
        for async mode and the asyncpg driver.

        Args:
            incoming_kwargs: Keyword arguments passed during engine initialization.

        Returns:
            A dictionary of processed arguments ready for `create_async_engine`.
        """
        # Work on a copy to avoid modifying the original dictionary
        kwargs = incoming_kwargs.copy()

        # --- Merge Additional Config Kwargs ---
        if self.config.kwargs:
            logger.debug(f"Merging additional kwargs from config: {self.config.kwargs}")
            kwargs.update(self.config.kwargs)

        logger.debug(f"Preparing engine arguments from config and initial kwargs: {kwargs}")

        # Always use NullPool for async engines as connection pooling
        # is often handled by the driver (like asyncpg) itself.
        kwargs["poolclass"] = NullPool

        # --- Connection Arguments ---
        if "connect_args" not in kwargs:
            kwargs["connect_args"] = {}  # Initialize if not present

        # Ensure connect_args is a dictionary before proceeding
        connect_args_val = kwargs.get("connect_args")
        if not isinstance(connect_args_val, dict):
            logger.warning(
                f"Expected 'connect_args' to be a dict, but got {type(connect_args_val)}. Resetting to empty dict."
            )
            kwargs["connect_args"] = {}

        # Set default connect_timeout if not provided within connect_args
        if "connect_timeout" not in kwargs["connect_args"]:
            kwargs["connect_args"]["connect_timeout"] = self.config.connect_timeout
            logger.debug(f"Setting default connect_timeout in connect_args: {kwargs['connect_args']}")

        # --- Echo SQL ---
        if "echo" not in kwargs:
            kwargs["echo"] = self.config.debug
            logger.debug(f"Setting echo={kwargs['echo']} based on config.debug")

        # Adjust connect_timeout -> timeout within connect_args for asyncpg driver
        if self.config.driver == "asyncpg":
            logger.debug("Applying asyncpg-specific argument adjustments for connect_args.")
            if (
                "connect_args" in kwargs
                and isinstance(kwargs["connect_args"], dict)
                and "connect_timeout" in kwargs["connect_args"]
                # Only add 'timeout' if it's not already explicitly set
                and "timeout" not in kwargs["connect_args"]
            ):
                timeout = kwargs["connect_args"].pop("connect_timeout")
                kwargs["connect_args"]["timeout"] = timeout
                logger.debug(
                    "Adjusted 'connect_timeout' to 'timeout' in connect_args for asyncpg: %s",
                    kwargs["connect_args"],
                )

        logger.debug(f"Final prepared engine arguments: {kwargs}")
        return kwargs

    def engine(
        self,
        schema: str | None = None,
        database: str | None = None,
        isolation_level: str | None = None,
        **kwargs: Any,
    ) -> AsyncEngine:
        """
        Retrieves or creates an AsyncEngine for the specified configuration.

        Args:
            schema: The database schema to use. Defaults to config schema.
            database: The database name to connect to. Defaults to config database.
            isolation_level: The transaction isolation level for the engine.
            **kwargs: Additional kwargs to override/add to engine creation.

        Returns:
            An instance of AsyncEngine.
        """
        schema = schema or self.config.default_schema
        database = database or self.config.db

        # Create a unique key for this engine configuration
        engine_key = f"{database}_{schema}_{isolation_level or 'default'}"
        engine_conf_key = str(sorted(kwargs.items()))  # Key based on extra kwargs
        if engine_key not in self.engines:
            self.engines[engine_key] = {}

        if engine_conf_key not in self.engines[engine_key]:
            logger.info(f"Creating new async engine for key: {engine_key} with kwargs: {kwargs}")
            # Build DSN using potentially overridden database
            temp_config = self.config.model_copy(update={"database": database})
            dsn = temp_config.uri()

            # Merge base kwargs, specific kwargs, and isolation level
            final_kwargs = self.engine_kwargs.copy()
            if isolation_level:
                final_kwargs["isolation_level"] = isolation_level
            final_kwargs.update(kwargs)  # Apply specific overrides last

            logger.debug(f"Creating async engine with DSN: {dsn} and final kwargs: {final_kwargs}")
            try:
                engine = create_async_engine(dsn, **final_kwargs)
                self.engines[engine_key][engine_conf_key] = engine
            except Exception as e:
                logger.error(f"Failed to create async engine for {dsn}: {e}", exc_info=True)
                raise
        else:
            logger.debug(f"Reusing existing async engine for key: {engine_key} with kwargs: {kwargs}")

        return self.engines[engine_key][engine_conf_key]

    def session(
        self,
        schema: str | None = None,
        database: str | None = None,
        isolation_level: str | None = None,
        session_kwargs: dict | None = None,
        engine_kwargs: dict | None = None,
    ) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
        """
        Retrieves or creates an engine and associated sessionmaker.

        Args:
            schema: The database schema. Defaults to config schema.
            database: The database name. Defaults to config database.
            isolation_level: Transaction isolation level for the engine.
            session_kwargs: Keyword arguments for the async_sessionmaker.
            engine_kwargs: Keyword arguments for the get_engine call.

        Returns:
            A tuple containing the AsyncEngine and the async_sessionmaker.
        """
        schema = schema or self.config.default_schema
        database = database or self.config.db
        session_kwargs = session_kwargs or {}
        engine_kwargs = engine_kwargs or {}

        # Use same keying logic as get_engine for consistency
        engine_key = f"{database}_{schema}_{isolation_level or 'default'}"
        engine_conf_key = str(sorted(engine_kwargs.items()))  # Key based on engine kwargs
        session_conf_key = str(sorted(session_kwargs.items()))  # Key based on session kwargs

        # Ensure outer dictionary exists
        if engine_key not in self.sessions:
            self.sessions[engine_key] = {}

        # Combine engine and session kwargs for session key uniqueness
        session_key = f"{engine_conf_key}_{session_conf_key}"
        engine = self.engine(
            schema=schema,
            database=database,
            isolation_level=isolation_level,
            **engine_kwargs,
        )

        if session_key not in self.sessions[engine_key]:
            logger.info(f"Creating new sessionmaker for key: {engine_key} / {session_key}")
            # Get or create the engine first
            # Default sessionmaker settings
            final_session_kwargs = {
                "expire_on_commit": False,  # Common default for async
                "class_": AsyncSession,
            }
            final_session_kwargs.update(session_kwargs)  # Apply user overrides

            logger.debug(f"Creating async_sessionmaker bound to engine {engine} with kwargs: {final_session_kwargs}")
            try:
                session_factory = async_sessionmaker(bind=engine, **final_session_kwargs)
                self.sessions[engine_key][session_key] = session_factory
            except Exception as e:
                logger.error(f"Failed to create async_sessionmaker: {e}", exc_info=True)
                raise
        else:
            logger.debug(f"Reusing existing sessionmaker for key: {engine_key} / {session_key}")

        return engine, self.sessions[engine_key][session_key]

    async def dispose_engines(self) -> None:
        """
        Dispose all managed engines.
        """
        logger.info("Disposing all managed async engines...")
        disposed_count = 0
        for engine_key, engine_configs in self.engines.items():
            for conf_key, engine in engine_configs.items():
                logger.debug(f"Disposing engine for key: {engine_key} / {conf_key}")
                await engine.dispose()
                disposed_count += 1
        # Clear dictionaries after disposal
        self.engines.clear()
        self.sessions.clear()
        logger.info(f"Disposed {disposed_count} engine(s).")
