import logging
from typing import TYPE_CHECKING, ClassVar, TypeVar

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from .base import Base
    from .model import AlchemyModel

logger = logging.getLogger(__name__)


# Generic TypeVar for AlchemyModel subclasses used in Schema definition
T = TypeVar("T", bound="Base")


class Schema[T: "AlchemyModel"](BaseModel):
    """
    Base schema class for serialization/deserialization using Pydantic.
    Designed to work with AlchemyModel models.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,  # Allow creating schema from model attributes
        extra="allow",  # Allow extra fields (e.g., metadata) if needed
    )

    def to_model(self, modelcls: type[T]) -> T:
        """
        Converts the Pydantic schema instance into an AlchemyModel model instance.

        Args:
            modelcls: The AlchemyModel class to instantiate.

        Returns:
            An instance of the AlchemyModel model populated with schema data.
        """
        # Create an instance using the model's __init__
        # model_dump() provides the data suitable for ORM initialization
        model_instance = modelcls(**self.model_dump(exclude_unset=True))
        return model_instance

