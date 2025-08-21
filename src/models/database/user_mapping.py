"""User ID anonymization mapping model."""

from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime, func, Index

from models.database.base import Base


class UserMapping(Base):  # pylint: disable=too-few-public-methods
    """Model for mapping real user IDs to anonymous UUIDs."""

    __tablename__ = "user_mapping"

    # Anonymous UUID used for all storage/analytics (primary key)
    anonymous_id: Mapped[str] = mapped_column(primary_key=True)

    # Original user ID from authentication (hashed for security)
    user_id_hash: Mapped[str] = mapped_column(index=True, unique=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # pylint: disable=not-callable
    )

    # Index for efficient lookups
    __table_args__ = (Index("ix_user_mapping_hash_lookup", "user_id_hash"),)
