from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass

from .activerecord import ActiveRecord


class Base(MappedAsDataclass, DeclarativeBase, ActiveRecord):
    pass
