"""Unit tests for token counter utilities."""

from utils.token_counter import TokenCounter
from llama_stack_client.types import UserMessage, CompletionMessage
from configuration import AppConfig


config_dict = {
    "name": "foo",
    "service": {
        "host": "localhost",
        "port": 8080,
        "auth_enabled": False,
        "workers": 1,
        "color_log": True,
        "access_log": True,
    },
    "llama_stack": {
        "api_key": "xyzzy",
        "url": "http://x.y.com:1234",
        "use_as_library_client": False,
    },
    "user_data_collection": {
        "feedback_disabled": True,
    },
}


class TestTokenCounter:
    """Test cases for TokenCounter class."""

    def setup_class(self):
        cfg = AppConfig()
        cfg.init_from_dict(config_dict)

    def test_count_tokens_empty_string(self):
        """Test counting tokens for empty message list."""
        counter = TokenCounter("gpt-4")
        assert counter.count_tokens("") == 0

    def test_count_tokens_simple(self):
        counter = TokenCounter("llama3.2:1b")
        assert counter.count_tokens("Hello World!") == 3

    def test_count_message_tokens_simple(self):
        """Test counting tokens for simple messages."""
        counter = TokenCounter("llama3.2:1b")

        messages = [
            UserMessage(role="user", content="Hello"),
            CompletionMessage(
                role="assistant", content="Hi there", stop_reason="end_of_turn"
            ),
        ]

        result = counter.count_message_tokens(messages)

        # 3 tokens worth of content + 4 role overhead per message + 4 conversation overhead
        expected = 3 + (4 * 2) + 4
        assert result == expected

    def test_count_message_tokens_empty_messages(self):
        """Test counting tokens for empty message list."""
        counter = TokenCounter("llama3.2:1b")
        result = counter.count_message_tokens([])
        assert result == 0

    def test_count_conversation_turn_tokens(self):
        """Test cumulative token tracking across conversation turns."""
        counter = TokenCounter("llama3.2:1b")

        # First conversation should accumulate tokens
        result1 = counter.count_conversation_turn_tokens(
            "conv1", "System", "Hello", "Hi"
        )
        assert result1["input_tokens"] == 14
        result2 = counter.count_conversation_turn_tokens(
            "conv1", "System", "How are you?", "Good"
        )
        assert result2["input_tokens"] == 31
        result3 = counter.count_conversation_turn_tokens(
            "conv1", "System", "Fantastic", "Yup"
        )
        assert result3["input_tokens"] == 45

        # Second conversation should be independent of the first
        result4 = counter.count_conversation_turn_tokens(
            "conv2", "System", "Hello", "Hi"
        )
        assert result4["input_tokens"] == 14
