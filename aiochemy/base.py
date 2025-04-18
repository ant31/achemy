from sqlalchemy.orm import DeclarativeBase

from .activerecord import ActiveRecord


class Base(DeclarativeBase, ActiveRecord):
    pass
