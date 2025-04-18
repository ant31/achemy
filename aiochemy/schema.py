import logging
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.fields import FieldInfo

if TYPE_CHECKING:
    from .activerecord import ActiveRecord
    from .base import Base

logger = logging.getLogger(__name__)


# Generic TypeVar for ActiveRecord subclasses used in Schema definition
T = TypeVar("T", bound="Base")


class Schema[T: "ActiveRecord"](BaseModel):
    """
    Base schema class for serialization/deserialization using Pydantic.
    Designed to work with ActiveRecord models.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,  # Allow creating schema from model attributes
        extra="allow",  # Allow extra fields (e.g., metadata) if needed
    )

    def to_model(self, modelcls: type[T]) -> T:
        """
        Converts the Pydantic schema instance into an ActiveRecord model instance.

        Args:
            modelcls: The ActiveRecord class to instantiate.

        Returns:
            An instance of the ActiveRecord model populated with schema data.
        """
        # Create an instance using the model's __init__
        # model_dump() provides the data suitable for ORM initialization
        model_instance = modelcls(**self.model_dump(exclude_unset=True))
        return model_instance

    # Source: https://github.com/pydantic/pydantic/issues/1937#issuecomment-695313040
    # Note: Dynamically adding fields can sometimes obscure type checking. Use carefully.
    @classmethod
    def add_fields(cls, **field_definitions: Any):
        """
        Dynamically adds fields to the Pydantic schema.

        Args:
            **field_definitions: Keyword arguments where keys are field names
                                and values are either (<type>, <default>) tuples
                                or just default values.
        """
        new_fields: dict[str, FieldInfo] = {}
        # current_annotations = cls.__annotations__ # Removed unused variable

        for f_name, f_def in field_definitions.items():
            f_annotation: Any = None
            f_value: Any = ...  # Pydantic's way of saying 'required' initially

            if isinstance(f_def, tuple):
                try:
                    f_annotation, f_value = f_def
                except ValueError as e:
                    raise ValueError(
                        "Field definitions should either be a tuple of (<type>, <default>) "
                        "or just a default value. tuples as default values are not directly allowed this way."
                    ) from e
            else:
                # If only a value is provided, it's the default.
                f_value = f_def
                # Check if the field already exists (inherited or defined) in the model's fields
                if f_name in cls.model_fields:
                    # Preserve the existing annotation from the FieldInfo object
                    f_annotation = cls.model_fields[f_name].annotation
                else:
                    # If it's a truly new field and only default is given, default to Any
                    # This maintains the previous behavior for brand new fields.
                    f_annotation = Any

            # Use FieldInfo constructor directly for Pydantic v2 compatibility
            # Ensure the retrieved annotation is used
            new_fields[f_name] = FieldInfo(annotation=f_annotation | None, default=f_value)
            # Update annotations directly for Pydantic v2 rebuild
            cls.__annotations__[f_name] = f_annotation

        # Update model_fields which stores FieldInfo objects
        cls.model_fields.update(new_fields)
        # Rebuild the model to incorporate new fields and annotations
        cls.model_rebuild(force=True)
        logger.debug(f"Rebuilt schema {cls.__name__} with added fields: {list(new_fields.keys())}")
