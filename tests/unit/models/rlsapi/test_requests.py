# pylint: disable=no-member
"""Unit tests for rlsapi v1 request models."""

from typing import Any, Optional

import pytest
from pydantic import BaseModel, ValidationError

from models.rlsapi.requests import (
    RlsapiV1Attachment,
    RlsapiV1CLA,
    RlsapiV1Context,
    RlsapiV1InferRequest,
    RlsapiV1SystemInfo,
    RlsapiV1Terminal,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(name="sample_systeminfo")
def sample_systeminfo_fixture() -> RlsapiV1SystemInfo:
    """Create a sample RlsapiV1SystemInfo for testing."""
    return RlsapiV1SystemInfo(os="RHEL", version="9.3", arch="x86_64")


@pytest.fixture(name="sample_context")
def sample_context_fixture(sample_systeminfo: RlsapiV1SystemInfo) -> RlsapiV1Context:
    """Create a sample RlsapiV1Context for testing."""
    return RlsapiV1Context(
        stdin="piped input",
        systeminfo=sample_systeminfo,
        terminal=RlsapiV1Terminal(output="bash: command not found"),
    )


@pytest.fixture(name="sample_request")
def sample_request_fixture(sample_context: RlsapiV1Context) -> RlsapiV1InferRequest:
    """Create a sample RlsapiV1InferRequest for testing."""
    return RlsapiV1InferRequest(
        question="How do I list files?",
        context=sample_context,
        skip_rag=True,
    )


# ---------------------------------------------------------------------------
# Parameterized tests for common patterns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model_class", "valid_kwargs"),
    [
        (RlsapiV1Attachment, {"contents": "test"}),
        (RlsapiV1Terminal, {"output": "test"}),
        (RlsapiV1SystemInfo, {"os": "RHEL"}),
        (RlsapiV1CLA, {"nevra": "test"}),
        (RlsapiV1Context, {"stdin": "test"}),
        (RlsapiV1InferRequest, {"question": "test"}),
    ],
    ids=[
        "Attachment",
        "Terminal",
        "SystemInfo",
        "CLA",
        "Context",
        "InferRequest",
    ],
)
def test_extra_fields_forbidden(
    model_class: type[BaseModel], valid_kwargs: dict[str, Any]
) -> None:
    """Test that extra fields are rejected for all models with extra='forbid'."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        model_class(**valid_kwargs, extra_field="not allowed")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("model_class", "expected_defaults"),
    [
        (RlsapiV1Attachment, {"contents": "", "mimetype": ""}),
        (RlsapiV1Terminal, {"output": ""}),
        (RlsapiV1CLA, {"nevra": "", "version": ""}),
    ],
    ids=["Attachment", "Terminal", "CLA"],
)
def test_simple_model_defaults(
    model_class: type[BaseModel], expected_defaults: dict[str, str]
) -> None:
    """Test that simple models have empty string defaults."""
    instance = model_class()
    for field_name, expected_value in expected_defaults.items():
        assert getattr(instance, field_name) == expected_value


# ---------------------------------------------------------------------------
# RlsapiV1Attachment tests
# ---------------------------------------------------------------------------


class TestRlsapiV1Attachment:  # pylint: disable=too-few-public-methods
    """Test cases for RlsapiV1Attachment model."""

    def test_constructor_with_values(self) -> None:
        """Test RlsapiV1Attachment with provided values."""
        attachment = RlsapiV1Attachment(
            contents="file contents here",
            mimetype="text/plain",
        )
        assert attachment.contents == "file contents here"
        assert attachment.mimetype == "text/plain"


# ---------------------------------------------------------------------------
# RlsapiV1Terminal tests
# ---------------------------------------------------------------------------


class TestRlsapiV1Terminal:  # pylint: disable=too-few-public-methods
    """Test cases for RlsapiV1Terminal model."""

    def test_constructor_with_values(self) -> None:
        """Test RlsapiV1Terminal with provided values."""
        terminal = RlsapiV1Terminal(output="bash: ls: command not found")
        assert terminal.output == "bash: ls: command not found"


# ---------------------------------------------------------------------------
# RlsapiV1SystemInfo tests
# ---------------------------------------------------------------------------


class TestRlsapiV1SystemInfo:
    """Test cases for RlsapiV1SystemInfo model."""

    def test_constructor_defaults(self) -> None:
        """Test RlsapiV1SystemInfo with default values."""
        sysinfo = RlsapiV1SystemInfo()
        assert sysinfo.os == ""
        assert sysinfo.version == ""
        assert sysinfo.arch == ""
        assert sysinfo.system_id == ""

    def test_constructor_with_values(self) -> None:
        """Test RlsapiV1SystemInfo with provided values."""
        sysinfo = RlsapiV1SystemInfo(
            os="RHEL",
            version="9.3",
            arch="x86_64",
            system_id="machine-001",  # pyright: ignore[reportCallIssue]
        )
        assert sysinfo.os == "RHEL"
        assert sysinfo.version == "9.3"
        assert sysinfo.arch == "x86_64"
        assert sysinfo.system_id == "machine-001"

    @pytest.mark.parametrize(
        ("kwargs", "expected_id"),
        [
            ({"id": "alias-machine-id"}, "alias-machine-id"),
            ({"system_id": "direct-machine-id"}, "direct-machine-id"),
        ],
        ids=["via_alias", "via_field_name"],
    )
    def test_system_id_population(
        self, kwargs: dict[str, str], expected_id: str
    ) -> None:
        """Test system_id can be set via alias 'id' or directly."""
        sysinfo = RlsapiV1SystemInfo(**kwargs)  # type: ignore[arg-type]
        assert sysinfo.system_id == expected_id


# ---------------------------------------------------------------------------
# RlsapiV1CLA tests
# ---------------------------------------------------------------------------


class TestRlsapiV1CLA:  # pylint: disable=too-few-public-methods
    """Test cases for RlsapiV1CLA model."""

    def test_constructor_with_values(self) -> None:
        """Test RlsapiV1CLA with provided values."""
        cla = RlsapiV1CLA(
            nevra="command-line-assistant-0.1.0-1.el9.noarch",
            version="0.1.0",
        )
        assert cla.nevra == "command-line-assistant-0.1.0-1.el9.noarch"
        assert cla.version == "0.1.0"


# ---------------------------------------------------------------------------
# RlsapiV1Context tests
# ---------------------------------------------------------------------------


class TestRlsapiV1Context:
    """Test cases for RlsapiV1Context model."""

    def test_constructor_defaults(self) -> None:
        """Test RlsapiV1Context with default values."""
        context = RlsapiV1Context()
        assert context.stdin == ""
        assert isinstance(context.attachments, RlsapiV1Attachment)
        assert isinstance(context.terminal, RlsapiV1Terminal)
        assert isinstance(context.systeminfo, RlsapiV1SystemInfo)
        assert isinstance(context.cla, RlsapiV1CLA)

    def test_constructor_with_nested_models(self) -> None:
        """Test RlsapiV1Context with nested model values."""
        context = RlsapiV1Context(
            stdin="piped input",
            attachments=RlsapiV1Attachment(
                contents="config file",
                mimetype="application/yaml",
            ),
            terminal=RlsapiV1Terminal(output="error output"),
            systeminfo=RlsapiV1SystemInfo(os="RHEL", version="9.3"),
            cla=RlsapiV1CLA(version="0.1.0"),
        )
        assert context.stdin == "piped input"
        assert context.attachments.contents == "config file"
        assert context.terminal.output == "error output"
        assert context.systeminfo.os == "RHEL"
        assert context.cla.version == "0.1.0"

    def test_constructor_with_dict_nested(self) -> None:
        """Test RlsapiV1Context with dict values for nested models."""
        context = RlsapiV1Context(
            terminal={"output": "from dict"},  # type: ignore[arg-type]
            systeminfo={"os": "RHEL", "version": "9.3"},  # type: ignore[arg-type]
        )
        assert context.terminal.output == "from dict"
        assert context.systeminfo.os == "RHEL"


# ---------------------------------------------------------------------------
# RlsapiV1InferRequest tests
# ---------------------------------------------------------------------------


class TestRlsapiV1InferRequest:
    """Test cases for RlsapiV1InferRequest model."""

    def test_constructor_minimal(self) -> None:
        """Test RlsapiV1InferRequest with only required field."""
        request = RlsapiV1InferRequest(question="How do I list files?")
        assert request.question == "How do I list files?"
        assert isinstance(request.context, RlsapiV1Context)
        assert request.skip_rag is False

    def test_constructor_full(self, sample_request: RlsapiV1InferRequest) -> None:
        """Test RlsapiV1InferRequest with all fields via fixture."""
        assert sample_request.question == "How do I list files?"
        assert sample_request.context.systeminfo.os == "RHEL"
        assert sample_request.context.terminal.output == "bash: command not found"
        assert sample_request.skip_rag is True

    @pytest.mark.parametrize(
        ("question", "error_match"),
        [
            pytest.param(None, "Field required", id="missing"),
            pytest.param("", "String should have at least 1 character", id="empty"),
            pytest.param(
                "   ", "Question cannot be empty or whitespace-only", id="whitespace"
            ),
        ],
    )
    def test_question_validation(
        self, question: Optional[str], error_match: str
    ) -> None:
        """Test question field validation for various invalid inputs."""
        with pytest.raises(ValidationError, match=error_match):
            if question is None:
                RlsapiV1InferRequest()  # type: ignore[call-arg]
            else:
                RlsapiV1InferRequest(question=question)

    def test_question_stripped(self) -> None:
        """Test that question is stripped of leading/trailing whitespace."""
        request = RlsapiV1InferRequest(question="  How do I list files?  ")
        assert request.question == "How do I list files?"

    def test_docstring_example(self) -> None:
        """Test the example from the docstring works correctly."""
        request = RlsapiV1InferRequest(
            question="How do I list files?",
            context=RlsapiV1Context(
                systeminfo=RlsapiV1SystemInfo(os="RHEL", version="9.3"),
                terminal=RlsapiV1Terminal(output="bash: command not found"),
            ),
        )
        assert request.question == "How do I list files?"
        assert request.context.systeminfo.os == "RHEL"
        assert request.context.systeminfo.version == "9.3"
        assert request.context.terminal.output == "bash: command not found"

    def test_serialization_roundtrip(
        self, sample_request: RlsapiV1InferRequest
    ) -> None:
        """Test that model can be serialized and deserialized."""
        json_data = sample_request.model_dump_json()
        restored = RlsapiV1InferRequest.model_validate_json(json_data)

        assert restored.question == sample_request.question
        assert restored.skip_rag == sample_request.skip_rag
        assert restored.context.systeminfo.os == sample_request.context.systeminfo.os


# ---------------------------------------------------------------------------
# get_input_source() tests
# ---------------------------------------------------------------------------


class TestGetInputSource:
    """Test cases for RlsapiV1InferRequest.get_input_source() method."""

    @pytest.fixture(name="make_request")
    def make_request_fixture(self) -> Any:
        """Factory fixture to build requests with specific context values."""

        class _RequestBuilder:  # pylint: disable=too-few-public-methods
            """Helper to construct requests with variable context."""

            @staticmethod
            def build(
                question: str = "q",
                stdin: str = "",
                attachment: str = "",
                terminal: str = "",
            ) -> RlsapiV1InferRequest:
                """Build an RlsapiV1InferRequest with specified context values."""
                return RlsapiV1InferRequest(
                    question=question,
                    context=RlsapiV1Context(
                        stdin=stdin,
                        attachments=RlsapiV1Attachment(contents=attachment),
                        terminal=RlsapiV1Terminal(output=terminal),
                    ),
                )

        return _RequestBuilder

    # -------------------------------------------------------------------------
    # Parameterized tests for input combinations
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize(
        ("question", "stdin", "attachment", "terminal", "expected"),
        [
            # All four sources present
            pytest.param(
                "question",
                "stdin",
                "attachment",
                "terminal",
                "question\n\nstdin\n\nattachment\n\nterminal",
                id="all_four_sources",
            ),
            # Three sources
            pytest.param(
                "question",
                "stdin",
                "attachment",
                "",
                "question\n\nstdin\n\nattachment",
                id="question_stdin_attachment",
            ),
            pytest.param(
                "question",
                "",
                "attachment",
                "terminal",
                "question\n\nattachment\n\nterminal",
                id="question_attachment_terminal",
            ),
            # Two sources
            pytest.param(
                "question",
                "stdin",
                "",
                "",
                "question\n\nstdin",
                id="question_stdin",
            ),
            pytest.param(
                "question",
                "",
                "attachment",
                "",
                "question\n\nattachment",
                id="question_attachment",
            ),
            pytest.param(
                "question",
                "",
                "",
                "terminal",
                "question\n\nterminal",
                id="question_terminal",
            ),
            # Question only
            pytest.param(
                "question",
                "",
                "",
                "",
                "question",
                id="question_only",
            ),
        ],
    )
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def test_input_combinations(
        self,
        make_request: Any,
        question: str,
        stdin: str,
        attachment: str,
        terminal: str,
        expected: str,
    ) -> None:
        """Test get_input_source() joins non-empty sources with double newlines."""
        request = make_request.build(
            question=question,
            stdin=stdin,
            attachment=attachment,
            terminal=terminal,
        )
        assert request.get_input_source() == expected

    # -------------------------------------------------------------------------
    # Edge cases
    # -------------------------------------------------------------------------

    def test_preserves_content_formatting(self, make_request: Any) -> None:
        """Test that content formatting (newlines, special chars) is preserved."""
        multiline_attachment = "line1\nline2\nline3"
        request = make_request.build(
            question="Explain this config",
            attachment=multiline_attachment,
        )
        result = request.get_input_source()
        assert "line1\nline2\nline3" in result

    def test_priority_order(self, make_request: Any) -> None:
        """Test that sources appear in priority order: question, stdin, attachment, terminal."""
        request = make_request.build(
            question="Q",
            stdin="S",
            attachment="A",
            terminal="T",
        )
        result = request.get_input_source()
        assert result == "Q\n\nS\n\nA\n\nT"
        # Verify order by checking positions
        assert (
            result.index("Q")
            < result.index("S")
            < result.index("A")
            < result.index("T")
        )
