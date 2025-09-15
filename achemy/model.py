import inspect
import logging
from typing import Any, ClassVar, ForwardRef, Self

from pydantic import BaseModel, create_model
from pydantic_core import to_jsonable_python
from sqlalchemy import FromClause
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import ColumnProperty, Mapper, RelationshipProperty
from sqlalchemy.sql.expression import ClauseElement

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

            # Identify columns with server-side defaults to handle them specially for new instances
            server_defaulted_keys = {c.key for c in self.__mapper__.columns if c.server_default is not None}

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
                    value = getattr(self, key)

                    # For new objects, if a server-defaulted column is None,
                    # don't include it in the dict. This allows the database
                    # to apply its default value during bulk inserts.
                    if key in server_defaulted_keys and value is None:
                        continue

                    # Accessing the attribute might trigger loading if deferred
                    data[key] = value
                except AttributeError:
                    # If attribute is not present (e.g., a server-defaulted column
                    # on a new instance), skip it so the DB can apply the default.
                    continue
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

        # Filter out values that are SQLAlchemy constructs (like func.now())
        # as they are not JSON-serializable and are meant for the DB.
        serializable_dict = {k: v for k, v in plain_dict.items() if not isinstance(v, ClauseElement)}

        try:
            # Convert types like UUID, datetime to JSON-friendly formats
            return to_jsonable_python(serializable_dict)
        except Exception as e:
            logger.error(f"Error making dictionary for {self} JSON-serializable: {e}", exc_info=True)
            # Fallback: return the plain dict, might cause issues downstream
            return serializable_dict

    @classmethod
    def load(cls, data: dict[str, Any]) -> Self:
        """
        Load an instance from a dictionary.

        This method filters the input dictionary to include only keys that correspond
        to mapped SQLAlchemy column properties. It then instantiates the class using
        attributes that are part of the constructor, and sets the remaining attributes
        after instantiation.

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
            # Separate data for constructor and for setting after instantiation
            init_param_keys = inspect.signature(cls).parameters.keys()

            init_data = {k: v for k, v in filtered_data.items() if k in init_param_keys}
            non_init_data = {k: v for k, v in filtered_data.items() if k not in init_param_keys}

            # Instantiate the class using the constructor data
            instance = cls(**init_data)

            # Set the remaining attributes on the instance
            for key, value in non_init_data.items():
                setattr(instance, key, value)

            return instance
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
        # Use mapper to iterate over all mapped columns and relationships
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

            elif isinstance(prop, RelationshipProperty):
                related_class = prop.mapper.class_
                related_schema_name = f"{related_class.__name__}Schema"
                forward_ref = ForwardRef(related_schema_name)

                field_type: Any
                if prop.uselist:
                    field_type = list[forward_ref] | None
                else:
                    field_type = forward_ref | None

                # Relationships are made optional in the schema by default
                fields[prop.key] = (field_type, None)

        schema_name = f"{cls.__name__}Schema"
        # Create the Pydantic model dynamically
        return create_model(schema_name, **fields)
