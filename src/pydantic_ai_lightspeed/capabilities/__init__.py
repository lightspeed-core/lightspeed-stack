"""Pluggable capabilities for pydantic-ai agents in Lightspeed.

Provides safety, guardrail, and policy capabilities that hook into
pydantic-ai's AbstractCapability lifecycle to enforce constraints
before, during, or after agent runs.
"""

from pydantic_ai_lightspeed.capabilities.question_validity import QuestionValidity

__all__ = ["QuestionValidity"]
