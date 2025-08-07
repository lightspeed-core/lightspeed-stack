"""Authorization configuration models."""

from enum import Enum
from typing import Any
from pydantic import BaseModel


class JsonPathOperator(str, Enum):
    """Supported operators for JSONPath evaluation."""

    EQUALS = "equals"
    CONTAINS = "contains"
    IN = "in"
    NOT_EQUALS = "not_equals"
    NOT_CONTAINS = "not_contains"
    NOT_IN = "not_in"


class RoleRule(BaseModel):
    """Rule for extracting roles from JWT claims."""

    jsonpath: str  # JSONPath expression to evaluate
    operator: JsonPathOperator  # Comparison operator
    value: Any  # Value to compare against
    roles: list[str]  # Roles to assign if rule matches


class Action(str, Enum):
    """Available actions in the system."""

    QUERY = "query"
    STREAMING_QUERY = "streaming_query"
    GET_CONVERSATION = "get_conversation"
    DELETE_CONVERSATION = "delete_conversation"
    FEEDBACK = "feedback"
    GET_MODELS = "get_models"
    GET_METRICS = "get_metrics"
    GET_CONFIG = "get_config"


class AccessRule(BaseModel):
    """Rule defining what actions a role can perform."""

    role: str  # Role name
    actions: list[Action]  # Allowed actions for this role


class AuthorizationConfiguration(BaseModel):
    """Authorization configuration for JWK authentication."""

    role_rules: list[RoleRule] = []  # Rules for extracting roles from JWT
    access_rules: list[AccessRule] = []  # Rules for role-based access control
