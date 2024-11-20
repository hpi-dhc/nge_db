"""A module that contains the common Base of the ORM model."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Dynamic ORM base class."""

    pass
