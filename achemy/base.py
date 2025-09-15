from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass

from achemy.model import AlchemyModel


class Base(MappedAsDataclass, DeclarativeBase, AlchemyModel):
    __abstract__ = True
