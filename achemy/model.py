import logging
from typing import Any, ClassVar, Self

from pydantic import BaseModel, create_model
from pydantic_core import to_jsonable_python
from sqlalchemy import FromClause
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import ColumnProperty, Mapper

logger = logging.getLogger(__name__)


# --- AlchemyModel Core (Async) ---


class AlchemyModel(AsyncAttrs):
    """
    Base model class with data handling and serialization helpers.

    Provides convenience methods for data conversion (`to_dict`, `dump_model`, etc.)
    and Pydantic schema generation. Does not include database interaction
    methods; for that, see `achemy.repository.BaseRepository`.
    """

    # --- Class Attributes ---

    __tablename__: ClassVar[str]  # Must be defined by subclasses
    __schema__: ClassVar[str] = "public"  # Default schema
    __table__: ClassVar[FromClause]  # Populated by SQLAlchemy mapper
    __mapper__: ClassVar[Mapper[Any]]  # Populated by SQLAlchemy mapper

    # --- Instance Representation & Data Handling ---
    def __str__(self):
        """Return a string representation, including primary key if available."""
        pk = getattr(self, "id", "id?")  # Assumes 'id' is the PK attribute
        return f"{self.__class__.__name__}({pk})"  # Use class name for clarity

    def __repr__(self) -> str:
        """Return a technical representation, same as __str__."""
        return str(self)

    def printn(self):
        """Helper method to print instance attributes (excluding SQLAlchemy state)."""
        print(f"Attributes for {self}:")
        attrs = {k: v for k, v in self.__dict__.items() if not k.startswith("_sa_")}
        for k, v in attrs.items():
            print(f"  {k}: {v}")

    def id_key(self) -> str:
        """Return a unique key string for this instance (Class:id)."""
        pk = getattr(self, "id", None)
        if pk is None:
            # Handle case where object might be transient (no ID yet)
            return f"{self.__class__.__name__}:transient_{id(self)}"
            # Or raise error: raise AttributeError(f"{self.__class__.__name__} instance has no 'id' attribute set.")
        return f"{self.__class__.__name__}:{pk}"

    @classmethod
    def __columns__fields__(cls) -> dict[str, tuple[type | None, Any]]:
        """
        Inspects the SQLAlchemy mapped columns for the class.

        Returns:
            A dictionary where keys are column names and values are tuples
            of (python_type, default_value). Returns None for python_type
            if it cannot be determined.
        """
        if not hasattr(cls, "__table__") or cls.__table__ is None:
            raise ValueError(f"No table associated with class {cls.__name__}")

        field_data = {}
        try:
            for col in cls.__table__.columns:
                py_type = None
                try:
                    # Attempt to get the Python type from the column type
                    py_type = col.type.python_type
                except NotImplementedError:
                    logger.warning(f"Could not determine Python type for column '{col.name}' of type {col.type}")

                default_val = col.default.arg if col.default else None
                field_data[col.name] = (py_type, default_val)
        except Exception as e:
            logger.error(f"Error inspecting columns for {cls.__name__}: {e}", exc_info=True)
            raise  # Or return partial data: return field_data
        return field_data

    def to_dict(self, with_meta: bool = False, fields: set[str] | None = None) -> dict[str, Any]:
        """
        Generate a dictionary representation of the model instance's mapped attributes.

        Args:
            with_meta: If True, include a '__metadata__' key with class/table info.
            fields: An optional set of attribute names to include. If None, includes all mapped columns.

        Returns:
            A dictionary containing the instance's data.
        """
        data = {}
        if hasattr(self, "__mapper__"):
            # Get names of attributes corresponding to mapped columns
            col_prop_keys = {p.key for p in self.__mapper__.iterate_properties if isinstance(p, ColumnProperty)}

            # Filter keys if 'fields' is specified
            keys_to_include = col_prop_keys
            if fields is not None:
                keys_to_include = col_prop_keys.intersection(fields)
                # Warn if requested fields are not mapped columns?
                # unknown_fields = fields - col_prop_keys
                # if unknown_fields: logger.warning(...)

            # Populate data dictionary, handling potential deferred loading issues
            for key in keys_to_include:
                try:
                    # Accessing the attribute might trigger loading if deferred
                    data[key] = getattr(self, key)
                except Exception as e:
                    logger.warning(f"Could not retrieve attribute '{key}' for {self}: {e}")
                    data[key] = None  # Or some other placeholder
        else:
            # Fallback for non-mapped objects? Unlikely for AlchemyModel.
            logger.warning(f"Instance {self} does not seem to be mapped by SQLAlchemy.")
            # Simple __dict__ might include SQLAlchemy state (_sa_...)
            # data = {k: v for k, v in self.__dict__.items() if not k.startswith('_sa_')}
            return {}  # Or raise error

        if with_meta:
            classname = f"{self.__class__.__module__}:{self.__class__.__name__}"
            data["__metadata__"] = {
                "model": classname,
                "table": getattr(self, "__tablename__", "unknown"),
                "schema": getattr(self, "__schema__", "unknown"),
            }

        return data

    def dump_model(self, with_meta: bool = False, fields: set[str] | None = None) -> dict[str, Any]:
        """
        Return a JSON-serializable dict representation of the instance.

        Uses `to_dict` and then `pydantic_core.to_jsonable_python` for compatibility.

        Args:
            with_meta: Passed to `to_dict`.
            fields: Passed to `to_dict`.

        Returns:
            A JSON-serializable dictionary.
        """
        plain_dict = self.to_dict(with_meta=with_meta, fields=fields)
        try:
            # Convert types like UUID, datetime to JSON-friendly formats
            return to_jsonable_python(plain_dict)
        except Exception as e:
            logger.error(f"Error making dictionary for {self} JSON-serializable: {e}", exc_info=True)
            # Fallback: return the plain dict, might cause issues downstream
            return plain_dict

    @classmethod
    def load(cls, data: dict[str, Any]) -> Self:
        """
        Load an instance from a dictionary by passing valid attributes to the constructor.

        This method filters the input dictionary to include only keys that correspond
        to mapped SQLAlchemy column properties, then instantiates the class with them.

        Args:
            data: The dictionary containing data to load.

        Returns:
            A new instance of the class populated with data.

        Raises:
            ValueError: If the class is not mapped or data is not a dict.
            TypeError: If instantiation fails due to missing required arguments or
                       other constructor-related issues.
        """
        if not isinstance(data, dict):
            raise ValueError("Input 'data' must be a dictionary.")

        if not hasattr(cls, "__mapper__"):
            raise ValueError(f"Cannot load data: Class {cls.__name__} is not mapped by SQLAlchemy.")

        # Get names of mapped column attributes to ensure only valid fields are passed
        col_prop_keys = {p.key for p in cls.__mapper__.iterate_properties if isinstance(p, ColumnProperty)}

        # Filter the input data to only include keys that are mapped columns
        filtered_data = {key: value for key, value in data.items() if key in col_prop_keys}

        # For debugging, it can be useful to know which keys were ignored
        ignored_keys = set(data.keys()) - set(filtered_data.keys())
        if ignored_keys:
            logger.debug(f"Ignored non-mapped keys when loading {cls.__name__}: {sorted(list(ignored_keys))}")

        try:
            # Instantiate the class using the filtered data
            return cls(**filtered_data)
        except TypeError as e:
            logger.error(f"Failed to instantiate {cls.__name__} from data: {e}", exc_info=True)
            # Re-raise to signal that instantiation failed, which is a critical error.
            raise

    @classmethod
    def pydantic_schema(cls) -> type[BaseModel]:
        """
        Dynamically creates a Pydantic schema from the SQLAlchemy model.

        This method inspects the model's columns and generates a Pydantic
        model that can be used for serialization (a "read" schema).

        Returns:
            A Pydantic BaseModel class representing the schema.
        """
        if not hasattr(cls, "__mapper__"):
            raise ValueError(f"Cannot create schema: Class {cls.__name__} is not mapped by SQLAlchemy.")

        fields = {}
        # Use mapper to iterate over all mapped columns, including those from mixins
        for prop in cls.__mapper__.iterate_properties:
            if isinstance(prop, ColumnProperty):
                # A ColumnProperty can have multiple columns (e.g., composite keys)
                # but we'll focus on the first/primary one for simplicity.
                if not prop.columns:
                    continue
                col = prop.columns[0]

                # Get python type
                py_type: Any = Any
                try:
                    py_type = col.type.python_type
                except NotImplementedError:
                    logger.warning(
                        f"Could not determine Python type for column '{col.name}' of type {col.type}, using Any."
                    )

                # Handle optionality
                field_type = py_type
                if col.nullable:
                    field_type = py_type | None

                # Handle default value
                default_value = ...  # Pydantic's marker for required
                if col.default is not None and hasattr(col.default, "arg"):
                    # Only use scalar defaults that are representable
                    if col.default.is_scalar:
                        default_value = col.default.arg
                elif col.nullable:
                    default_value = None

                fields[prop.key] = (field_type, default_value)

        schema_name = f"{cls.__name__}Schema"
        # Create the Pydantic model dynamically
        return create_model(schema_name, **fields)

