"""
Xenosync - Alien Synchronization Platform for Multi-Agent Orchestration

An otherworldly coordination system that synchronizes multiple AI agents
to work in perfect harmony, like an alien hive mind building software.
"""

__version__ = "3.0.0"
__author__ = "Xenosync Collective"
__description__ = "Alien synchronization for multi-agent AI orchestration"

from .exceptions import (
    XenosyncError,
    SyncError,
    SyncInterrupted,
    SessionError,
    PromptError,
    AgentError,
    CoordinationError,
    StrategyError,
)

__all__ = [
    "XenosyncError",
    "SyncError", 
    "SyncInterrupted",
    "SessionError",
    "PromptError",
    "AgentError",
    "CoordinationError",
    "StrategyError",
]