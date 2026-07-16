"""Base model for SQLAlchemy ORM classes."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):  # pylint: disable=too-few-public-methods
    """Base class for all SQLAlchemy ORM models."""
