"""
Custom exceptions for Xenosync - Alien Synchronization Platform
"""


class XenosyncError(Exception):
    """Base exception for Xenosync - when alien synchronization fails"""
    pass


class SyncError(XenosyncError):
    """Error during synchronization execution"""
    pass


class SyncInterrupted(XenosyncError):
    """Synchronization was interrupted by user"""
    pass


class SessionError(XenosyncError):
    """Error related to session management"""
    pass


class PromptError(XenosyncError):
    """Error related to prompt handling"""
    pass


class AgentError(XenosyncError):
    """Error related to agent management - alien disconnection"""
    pass


class ClaudeError(XenosyncError):
    """Error related to Claude interaction"""
    pass


class ConfigError(XenosyncError):
    """Error related to configuration"""
    pass


class TmuxError(XenosyncError):
    """Error related to tmux operations - visual sync failure"""
    pass


class TerminalError(XenosyncError):
    """Error related to terminal operations - display interface failure"""
    pass


class CoordinationError(XenosyncError):
    """Error related to agent coordination - hive mind disruption"""
    pass


class StrategyError(XenosyncError):
    """Error related to execution strategies"""
    pass


class AlienProtocolError(XenosyncError):
    """Error in alien communication protocol"""
    pass