"""Database benchmarks implementations."""

from typing import Optional
from sqlalchemy.orm import Session
from datetime import UTC, datetime
from pytest_benchmark.fixture import BenchmarkFixture

from app.database import get_session
from utils.suid import get_suid

from models.database.conversations import UserConversation

from .data_generators import (
    generate_provider,
    generate_model_for_provider,
    generate_topic_summary,
)


def store_new_user_conversation(
    session: Session, id: Optional[str] = None, user_id: Optional[str] = None
) -> None:
    """Store the new user conversation into database.

    This helper constructs a UserConversation structure with randomized
    provider/model and topic summary values and commits it into the provided
    session.

    Parameters:
        session (Session): SQLAlchemy session used to persist the record.
        id (Optional[str]): Optional explicit ID to assign to the new conversation.
            If not provided, a generated suid will be used.
        user_id (Optional[str]): Optional explicit user ID to assign to the new
            conversation. If not provided, a generated suid will be used.

    Returns:
        None
    """
    provider = generate_provider()
    model = generate_model_for_provider(provider)
    topic_summary = generate_topic_summary()
    conversation = UserConversation(
        id=id or get_suid(),
        user_id=user_id or get_suid(),
        last_used_model=model,
        last_used_provider=provider,
        topic_summary=topic_summary,
        last_message_at=datetime.now(UTC),
        message_count=1,
    )
    session.add(conversation)
    session.commit()


def update_user_conversation(session: Session, id: str) -> None:
    """Update existing conversation in the database.

    This helper constructs a UserConversation structure with randomized
    provider/model and topic summary values and commits it into the provided
    session.

    Parameters:
        session (Session): SQLAlchemy session used to persist the record.
        id (str): Explicit ID to assign to the new conversation.

    Returns:
        None
    """
    provider = generate_provider()
    model = generate_model_for_provider(provider)
    topic_summary = generate_topic_summary()

    existing_conversation = session.query(UserConversation).filter_by(id=id).first()
    assert existing_conversation is not None

    existing_conversation.last_used_model = model
    existing_conversation.last_used_provider = provider
    existing_conversation.last_message_at = datetime.now(UTC)
    existing_conversation.message_count += 1
    existing_conversation.topic_summary = topic_summary
    session.commit()


def list_conversation_for_all_users(session: Session) -> None:
    """Query and assert retrieval of all user conversations.

    This helper queries all UserConversation records and asserts that the
    result is a list (possibly empty). It is intended for use in a benchmark
    that measures the listing performance.

    Parameters:
        session (Session): SQLAlchemy session used to query conversations.

    Returns:
        None
    """
    query = session.query(UserConversation)

    user_conversations = query.all()
    assert user_conversations is not None
    assert len(user_conversations) >= 0


def retrieve_conversation(
    session: Session, conversation_id: str, should_be_none: bool
) -> None:
    """Query and assert retrieval of one conversation.

    This helper function retrieves one given conversation from a database. It
    is intended for use in a benchmark that measures the listing performance.

    Parameters:
        session (Session): SQLAlchemy session used to query conversations.

    Returns:
        None
    """
    query = session.query(UserConversation).filter_by(id=conversation_id)

    conversation = query.first()
    if should_be_none:
        assert conversation is None
    else:
        assert conversation is not None


def retrieve_conversation_for_one_user(
    session: Session, user_id: str, conversation_id: str, should_be_none: bool
) -> None:
    """Query and assert retrieval of one conversation.

    This helper function retrieves one given conversation from a database. It
    is intended for use in a benchmark that measures the listing performance.

    Parameters:
        session (Session): SQLAlchemy session used to query conversations.

    Returns:
        None
    """
    query = session.query(UserConversation).filter_by(
        id=conversation_id, user_id=user_id
    )

    conversation = query.first()
    if should_be_none:
        assert conversation is None
    else:
        assert conversation is not None


def list_conversation_for_one_user(session: Session, user_id: str) -> None:
    """Query and assert retrieval of one user conversation.

    This helper queries all UserConversation records and asserts that the
    result is a list (possibly empty). It is intended for use in a benchmark
    that measures the listing performance.

    Parameters:
        session (Session): SQLAlchemy session used to query conversations.

    Returns:
        None
    """
    query = session.query(UserConversation).filter_by(user_id=user_id)

    user_conversations = query.all()
    assert user_conversations is not None
    assert len(user_conversations) >= 0


def benchmark_store_new_user_conversations(
    benchmark: BenchmarkFixture, records_to_insert: int
) -> None:
    """Prepare DB and benchmark storing a single new conversation.

    The database is pre-populated with ``records_to_insert`` records, then the
    benchmark task stores one more conversation (using the helper above).

    Parameters:
        benchmark (BenchmarkFixture): pytest-benchmark fixture to run the measurement.
        records_to_insert (int): Number of records to pre-populate before benchmarking.

    Returns:
        None
    """
    with get_session() as session:
        # store bunch of conversations first
        for id in range(records_to_insert):
            store_new_user_conversation(session, str(id))
        # then perform the benchmark
        benchmark(store_new_user_conversation, session)


def benchmark_update_user_conversation(
    benchmark: BenchmarkFixture, records_to_insert: int
) -> None:
    """Prepare DB and benchmark updating a single existing conversation.

    The database is pre-populated with ``records_to_insert`` records. Ensures
    that a record with id "1234" exists (inserting it explicitly when needed)
    and then benchmarks updating that conversation.

    Parameters:
        benchmark (BenchmarkFixture): pytest-benchmark fixture to run the measurement.
        records_to_insert (int): Number of records to pre-populate before benchmarking.

    Returns:
        None
    """
    with get_session() as session:
        # store bunch of conversations first
        # Ensure record "1234" exists for the update benchmark.
        # if records_to_insert <= 1234, range() won't include 1234, so insert it explicitly.
        if records_to_insert <= 1234:
            store_new_user_conversation(session, "1234")

        # pre-populate database with records
        for id in range(records_to_insert):
            store_new_user_conversation(session, str(id))

        # then perform the benchmark
        benchmark(update_user_conversation, session, "1234")


def benchmark_list_conversations_for_all_users(
    benchmark: BenchmarkFixture, records_to_insert: int
) -> None:
    """Prepare DB and benchmark listing all conversations.

    Pre-populates the DB with ``records_to_insert`` entries and benchmarks
    the performance of querying and retrieving all UserConversation rows.

    Parameters:
        benchmark (BenchmarkFixture): pytest-benchmark fixture to run the measurement.
        records_to_insert (int): Number of records to pre-populate before benchmarking.

    Returns:
        None
    """
    with get_session() as session:
        # store bunch of conversations first
        for id in range(records_to_insert):
            store_new_user_conversation(session, str(id))
        # then perform the benchmark
        benchmark(list_conversation_for_all_users, session)


def benchmark_list_conversations_for_one_user(
    benchmark: BenchmarkFixture, records_to_insert: int
) -> None:
    """Prepare DB and benchmark listing all conversations.

    Pre-populates the DB with ``records_to_insert`` entries and benchmarks
    the performance of querying and retrieving all UserConversation rows.

    Parameters:
        benchmark (BenchmarkFixture): pytest-benchmark fixture to run the measurement.
        records_to_insert (int): Number of records to pre-populate before benchmarking.

    Returns:
        None
    """
    with get_session() as session:
        # store bunch of conversations first
        for id in range(records_to_insert):
            # use explicit conversation ID and also user ID
            store_new_user_conversation(session, str(id), str(id))
        # user ID somewhere in the middle of database
        user_id = str(records_to_insert / 2)
        # then perform the benchmark
        benchmark(list_conversation_for_one_user, session, user_id)


def benchmark_retrieve_conversation(
    benchmark: BenchmarkFixture, records_to_insert: int
) -> None:
    """Prepare DB and benchmark retrieving one conversation.

    Pre-populates the DB with ``records_to_insert`` entries and benchmarks
    the performance of querying and retrieving one UserConversation record.

    Parameters:
        benchmark (BenchmarkFixture): pytest-benchmark fixture to run the measurement.
        records_to_insert (int): Number of records to pre-populate before benchmarking.

    Returns:
        None
    """
    with get_session() as session:
        # store bunch of conversations first
        for id in range(records_to_insert):
            # use explicit conversation ID and also user ID
            store_new_user_conversation(session, str(id), str(id))
        # user ID somewhere in the middle of database
        conversation_id = str(records_to_insert // 2)
        # then perform the benchmark
        benchmark(
            retrieve_conversation, session, conversation_id, records_to_insert == 0
        )


def benchmark_retrieve_conversation_for_one_user(
    benchmark: BenchmarkFixture, records_to_insert: int
) -> None:
    """Prepare DB and benchmark retrieving one conversation.

    Pre-populates the DB with ``records_to_insert`` entries and benchmarks
    the performance of querying and retrieving one UserConversation record.

    Parameters:
        benchmark (BenchmarkFixture): pytest-benchmark fixture to run the measurement.
        records_to_insert (int): Number of records to pre-populate before benchmarking.

    Returns:
        None
    """
    with get_session() as session:
        # store bunch of conversations first
        for id in range(records_to_insert):
            # use explicit conversation ID and also user ID
            store_new_user_conversation(session, str(id), str(id))
        # user ID somewhere in the middle of database
        user_id = str(records_to_insert // 2)
        conversation_id = str(records_to_insert // 2)
        # then perform the benchmark
        benchmark(
            retrieve_conversation_for_one_user,
            session,
            user_id,
            conversation_id,
            records_to_insert == 0,  # a flag whether records should be read
        )
