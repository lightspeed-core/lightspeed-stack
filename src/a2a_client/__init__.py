"""A2A client module for discovering and delegating tasks to external agents."""

from a2a_client.capability import A2ADelegationCapability
from a2a_client.manager import A2AClientManager

__all__ = [
    "A2AClientManager",
    "A2ADelegationCapability",
]
