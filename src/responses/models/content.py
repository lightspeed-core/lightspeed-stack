"""Input and output content parts, citations, and token log probabilities."""

from typing import Annotated, Literal, Optional, Self

from pydantic import BaseModel, Field, model_validator


class InputTextPart(BaseModel):
    """Text in an input message."""

    type: Literal["input_text"] = "input_text"
    text: str


class InputImagePart(BaseModel):
    """Image in an input message."""

    type: Literal["input_image"] = "input_image"
    file_id: Optional[str] = None
    image_url: Optional[str] = None


class InputFilePart(BaseModel):
    """File in an input message."""

    type: Literal["input_file"] = "input_file"
    file_data: Optional[str] = None
    file_id: Optional[str] = None
    file_url: Optional[str] = None
    filename: Optional[str] = None

    @model_validator(mode="after")
    def validate_file_source(self) -> Self:
        """Require a file payload, id, URL, or filename."""
        if not any([self.file_data, self.file_id, self.file_url, self.filename]):
            raise ValueError(
                "At least one of 'file_data', 'file_id', 'file_url', or "
                "'filename' must be provided for file content"
            )
        return self


InputMessageContent = Annotated[
    InputTextPart | InputImagePart | InputFilePart,
    Field(discriminator="type"),
]


class AnnotationFileCitation(BaseModel):
    """Citation of a file in output text."""

    type: Literal["file_citation"] = "file_citation"
    file_id: str
    filename: str
    index: int


class AnnotationUrlCitation(BaseModel):
    """Citation of a URL in output text."""

    type: Literal["url_citation"] = "url_citation"
    end_index: int
    start_index: int
    title: str
    url: str


class AnnotationContainerFileCitation(BaseModel):
    """Citation of a file stored in a container."""

    type: Literal["container_file_citation"] = "container_file_citation"
    container_id: str
    end_index: int
    file_id: str
    filename: str
    start_index: int


class AnnotationFilePath(BaseModel):
    """Path to a file referenced in output text."""

    type: Literal["file_path"] = "file_path"
    file_id: str
    index: int


ResponseAnnotation = Annotated[
    AnnotationFileCitation
    | AnnotationUrlCitation
    | AnnotationContainerFileCitation
    | AnnotationFilePath,
    Field(discriminator="type"),
]


class TopLogProb(BaseModel):
    """An alternative token and its log probability."""

    token: str
    logprob: float
    bytes: Optional[list[int]] = None


class TokenLogProb(BaseModel):
    """Log probability for one generated token."""

    token: str
    logprob: float
    bytes: Optional[list[int]] = None
    top_logprobs: Optional[list[TopLogProb]] = None


class OutputTextPart(BaseModel):
    """Text in an output message."""

    type: Literal["output_text"] = "output_text"
    text: str
    annotations: list[ResponseAnnotation] = Field(default_factory=list)
    logprobs: Optional[list[TokenLogProb]] = None


class RefusalPart(BaseModel):
    """Model refusal in an output message."""

    type: Literal["refusal"] = "refusal"
    refusal: str


OutputMessageContent = Annotated[
    OutputTextPart | RefusalPart,
    Field(discriminator="type"),
]


class StreamTextPart(BaseModel):
    """Text part in a streamed output item."""

    type: Literal["output_text"] = "output_text"
    text: str
    annotations: list[ResponseAnnotation] = Field(default_factory=list)
    logprobs: Optional[list[TokenLogProb]] = None


class StreamReasoningTextPart(BaseModel):
    """Reasoning text in a streamed output item."""

    type: Literal["reasoning_text"] = "reasoning_text"
    text: str


class StreamReasoningSummaryPart(BaseModel):
    """Reasoning summary in a streamed output item."""

    type: Literal["summary_text"] = "summary_text"
    text: str


StreamContentPart = Annotated[
    StreamTextPart | RefusalPart | StreamReasoningTextPart,
    Field(discriminator="type"),
]
