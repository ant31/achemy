from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass

from .activerecord import AlchemyModel


class Base(MappedAsDataclass, DeclarativeBase, AlchemyModel):
    pass
