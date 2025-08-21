"""User ID anonymization utilities."""

import hashlib
import hmac
import logging
import os
from typing import Optional

from sqlalchemy.exc import IntegrityError

from models.database.user_mapping import UserMapping
from app.database import get_session
from utils.suid import get_suid

logger = logging.getLogger("utils.user_anonymization")

# Load HMAC pepper from environment - fail at startup if missing
try:
    _USER_ANON_PEPPER = os.environ["USER_ANON_PEPPER"].encode("utf-8")
except KeyError as e:
    raise RuntimeError(
        "USER_ANON_PEPPER environment variable is required for user anonymization. "
        "Set a secure random value (e.g., 'export USER_ANON_PEPPER=<your-secret-key>')"
    ) from e


def _hash_user_id(user_id: str) -> str:
    """
    Create a consistent hash of the user ID for mapping purposes.

    Uses HMAC-SHA256 with a server-secret pepper to ensure consistent hashing
    while preventing rainbow table attacks and providing cryptographic security.
    """
    # Normalize user ID: trim whitespace and lowercase
    normalized_user_id = user_id.strip().lower()

    # Use HMAC-SHA256 with secret pepper
    return hmac.new(
        _USER_ANON_PEPPER, normalized_user_id.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def get_anonymous_user_id(auth_user_id: str) -> str:
    """
    Get or create an anonymous UUID for a user ID from authentication.

    This function:
    1. Hashes the original user ID for secure storage
    2. Looks up existing anonymous mapping
    3. Creates new anonymous UUID if none exists
    4. Returns the anonymous UUID for use in storage/analytics

    Args:
        auth_user_id: The original user ID from authentication

    Returns:
        Anonymous UUID string for this user
    """
    user_id_hash = _hash_user_id(auth_user_id)

    with get_session() as session:
        # Try to find existing mapping
        existing_mapping = (
            session.query(UserMapping).filter_by(user_id_hash=user_id_hash).first()
        )

        if existing_mapping:
            logger.debug(
                "Found existing anonymous ID for user hash %s", user_id_hash[:8] + "..."
            )
            return existing_mapping.anonymous_id

        # Create new anonymous mapping
        anonymous_id = get_suid()
        new_mapping = UserMapping(anonymous_id=anonymous_id, user_id_hash=user_id_hash)

        try:
            session.add(new_mapping)
            session.commit()
            logger.info(
                "Created new anonymous ID %s for user hash %s",
                anonymous_id,
                user_id_hash[:8] + "...",
            )
            return anonymous_id

        except IntegrityError as e:
            session.rollback()
            # Race condition - another thread created the mapping
            logger.warning("Race condition creating user mapping: %s", e)

            # Try to fetch the mapping created by the other thread
            existing_mapping = (
                session.query(UserMapping).filter_by(user_id_hash=user_id_hash).first()
            )

            if existing_mapping:
                return existing_mapping.anonymous_id

            # If we still can't find it, something is wrong
            logger.error(
                "Failed to create or retrieve user mapping for hash %s",
                user_id_hash[:8] + "...",
            )
            raise RuntimeError("Unable to create or retrieve anonymous user ID") from e


def get_user_count() -> int:
    """
    Get the total number of unique users in the system.

    Returns:
        Total count of unique anonymous users
    """
    with get_session() as session:
        return session.query(UserMapping).count()


def find_anonymous_user_id(auth_user_id: str) -> Optional[str]:
    """
    Find existing anonymous ID for a user without creating a new one.

    Args:
        auth_user_id: The original user ID from authentication

    Returns:
        Anonymous UUID if found, None otherwise
    """
    user_id_hash = _hash_user_id(auth_user_id)

    with get_session() as session:
        existing_mapping = (
            session.query(UserMapping).filter_by(user_id_hash=user_id_hash).first()
        )

        return existing_mapping.anonymous_id if existing_mapping else None
