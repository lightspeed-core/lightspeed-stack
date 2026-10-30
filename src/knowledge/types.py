"""Shared types for knowledge capability."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

KnowledgeReadinessStatus = Literal["ready", "degraded", "not_ready"]
"""Common readiness codes; backends may use additional `status` strings."""


@dataclass(frozen=True)
class KnowledgeMatch:
    """One scored knowledge-search result."""

    content: str
    """The matched chunk's text."""

    score: float
    """Similarity score for this match; higher is more relevant."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Unique identifier for this match."""

    source: Optional[str] = None
    """Optional citation identifier (e.g. a document URI), for grounding."""

    metadata: Mapping[str, Any] = field(default_factory=dict)
    """Optional backend-specific metadata carried alongside the match."""


@dataclass(frozen=True)
class KnowledgeReadiness:
    """Operational readiness of a knowledge source.

    ``status`` is an open-ended code: use ``"ready"``, ``"degraded"``, or
    ``"not_ready"``.
    """

    status: KnowledgeReadinessStatus
    """Readiness code; commonly one of ``KnowledgeReadinessStatus``."""

    message: str = ""
    """Human-readable summary for operators and logs."""

@dataclass(frozen=True)
class KnowledgeChunk:
    """A chunk of knowledge."""

    content: str
    """The chunk's text."""

    id: str
    """The chunk's unique identifier."""

    source: Optional[str] = None
    """The chunk's source."""

    metadata: Mapping[str, Any] = field(default_factory=dict)
    """Optional backend-specific metadata carried alongside the chunk."""