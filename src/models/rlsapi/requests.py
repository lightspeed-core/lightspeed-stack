"""Models for rlsapi v1 REST API requests."""

from pydantic import Field, field_validator

from models.config import ConfigurationBase

# Character validation patterns for fields flowing into Splunk telemetry.
# Restrict the character set to prevent injection of control characters,
# HTML/script tags, or other malicious content into the telemetry pipeline.

# Alphanumeric, dots, underscores, spaces, and hyphens.
_SAFE_TEXT_PATTERN = r"^[a-zA-Z0-9._ \-]*$"

# Machine IDs: alphanumeric, dots, underscores, and hyphens (no spaces).
_MACHINE_ID_PATTERN = r"^[a-zA-Z0-9._\-]*$"

# NEVRA (Name-Epoch:Version-Release.Arch): also needs colons, plus, and tilde.
_NEVRA_PATTERN = r"^[a-zA-Z0-9._:+~\-]*$"

# Version strings share the same allowed set as machine IDs.
_VERSION_PATTERN = _MACHINE_ID_PATTERN


class RlsapiV1Attachment(ConfigurationBase):
    """Attachment data from rlsapi v1 context.

    Attributes:
        contents: The textual contents of the file read on the client machine.
        mimetype: The MIME type of the file.
    """

    contents: str = Field(
        default="",
        max_length=65_536,
        description="File contents read on client",
        examples=["# Configuration file\nkey=value"],
    )
    mimetype: str = Field(
        default="",
        description="MIME type of the file",
        examples=["text/plain", "application/json"],
    )


class RlsapiV1Terminal(ConfigurationBase):
    """Terminal output from rlsapi v1 context.

    Attributes:
        output: The textual contents of the terminal read on the client machine.
    """

    output: str = Field(
        default="",
        max_length=65_536,
        description="Terminal output from client",
        examples=["bash: command not found", "Permission denied"],
    )


class RlsapiV1SystemInfo(ConfigurationBase):
    """System information from rlsapi v1 context.

    Attributes:
        os: The operating system of the client machine.
        version: The version of the operating system.
        arch: The architecture of the client machine.
        system_id: The id of the client machine.
    """

    os: str = Field(
        default="",
        pattern=_SAFE_TEXT_PATTERN,
        description="Operating system name",
        examples=["RHEL"],
    )
    version: str = Field(
        default="",
        pattern=_SAFE_TEXT_PATTERN,
        description="Operating system version",
        examples=["9.3", "8.10"],
    )
    arch: str = Field(
        default="",
        pattern=_SAFE_TEXT_PATTERN,
        description="System architecture",
        examples=["x86_64", "aarch64"],
    )
    system_id: str = Field(
        default="",
        alias="id",
        pattern=_MACHINE_ID_PATTERN,
        description="Client machine ID",
        examples=["01JDKR8N7QW9ZMXVGK3PB5TQWZ"],
    )

    model_config = {"populate_by_name": True}


class RlsapiV1CLA(ConfigurationBase):
    """Command Line Assistant information from rlsapi v1 context.

    Attributes:
        nevra: The NEVRA (Name-Epoch-Version-Release-Architecture) of the CLA.
        version: The version of the command line assistant.
    """

    nevra: str = Field(
        default="",
        pattern=_NEVRA_PATTERN,
        description="CLA NEVRA identifier",
        examples=["command-line-assistant-0:0.2.0-1.el9.noarch"],
    )
    version: str = Field(
        default="",
        pattern=_VERSION_PATTERN,
        description="Command line assistant version",
        examples=["0.2.0"],
    )


class RlsapiV1Context(ConfigurationBase):
    """Context data for rlsapi v1 /infer request.

    Attributes:
        stdin: Redirect input read by command-line-assistant.
        attachments: Attachment object received by the client.
        terminal: Terminal object received by the client.
        systeminfo: System information object received by the client.
        cla: Command Line Assistant information.
    """

    stdin: str = Field(
        default="",
        max_length=65_536,
        description="Redirect input from stdin",
        examples=["piped input from previous command"],
    )
    attachments: RlsapiV1Attachment = Field(
        default_factory=RlsapiV1Attachment,
        description="File attachment data",
    )
    terminal: RlsapiV1Terminal = Field(
        default_factory=RlsapiV1Terminal,
        description="Terminal output context",
    )
    systeminfo: RlsapiV1SystemInfo = Field(
        default_factory=RlsapiV1SystemInfo,
        description="Client system information",
    )
    cla: RlsapiV1CLA = Field(
        default_factory=RlsapiV1CLA,
        description="Command line assistant metadata",
    )


class RlsapiV1InferRequest(ConfigurationBase):
    """RHEL Lightspeed rlsapi v1 /infer request.

    Attributes:
        question: User question string.
        context: Context with system info, terminal output, etc. (defaults provided).
        skip_rag: Reserved for future use. RAG retrieval is not yet implemented.

    Example:
        ```python
        request = RlsapiV1InferRequest(
            question="How do I list files?",
            context=RlsapiV1Context(
                systeminfo=RlsapiV1SystemInfo(os="RHEL", version="9.3"),
                terminal=RlsapiV1Terminal(output="bash: command not found"),
            ),
        )
        ```
    """

    question: str = Field(
        ...,
        min_length=1,
        max_length=10_240,
        description="User question",
        examples=["How do I list files?", "How do I configure SELinux?"],
    )
    context: RlsapiV1Context = Field(
        default_factory=RlsapiV1Context,
        description="Optional context (system info, terminal output, stdin, attachments)",
    )
    skip_rag: bool = Field(
        default=False,
        description="Reserved for future use. RAG retrieval is not yet implemented.",
        examples=[False, True],
    )

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        """Validate question is not empty or whitespace-only.

        Args:
            value: The question string to validate.

        Returns:
            The stripped question string.

        Raises:
            ValueError: If the question is empty or whitespace-only.
        """
        stripped = value.strip()
        if not stripped:
            raise ValueError("Question cannot be empty or whitespace-only")
        return stripped

    def get_input_source(self) -> str:
        """Combine all non-empty input sources into a single string.

        Joins question, stdin, attachment contents, and terminal output with double
        newlines, in priority order. Empty sources are omitted.

        Priority order:
            1. question
            2. stdin
            3. attachment contents
            4. terminal output

        Returns:
            The combined input string with sources separated by double newlines.
        """
        # pylint: disable=no-member  # Pydantic fields are dynamic
        parts = [
            self.question,
            self.context.stdin,
            self.context.attachments.contents,
            self.context.terminal.output,
        ]
        return "\n\n".join(part for part in parts if part)
