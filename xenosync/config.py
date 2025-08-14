"""
Configuration management for Xenosync - Simplified single-profile system
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class Config:
    """Xenosync configuration manager - streamlined for simplicity"""
    
    def __init__(self, config_dict: Optional[Dict[str, Any]] = None):
        self._config = config_dict or self._default_config()
    
    @classmethod
    def load(cls, config_path: Path) -> 'Config':
        """Load configuration from file"""
        if config_path.exists():
            with open(config_path, 'r') as f:
                config_dict = yaml.safe_load(f)
            return cls(config_dict)
        else:
            # Create default config if not exists
            config = cls()
            config.save(config_path)
            return config
    
    def save(self, config_path: Path):
        """Save configuration to file"""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump(self._config, f, default_flow_style=False)
    
    @classmethod
    def create_default(cls, config_path: Path):
        """Create default configuration file"""
        config = cls()
        config.save(config_path)
    
    def _default_config(self) -> Dict[str, Any]:
        """Get default configuration - only essential settings"""
        return {
            # Core settings
            'log_level': 'INFO',
            'sessions_dir': 'xsync-sessions',
            'prompts_dir': 'prompts',
            
            # Claude settings
            'claude_command': 'claude',
            'claude_args': ['--dangerously-skip-permissions'],
            'initial_wait': 5,  # Seconds to wait after starting Claude
            
            # Multi-agent settings
            'num_agents': 2,  # Default number of agents (minimum 2)
            'agent_launch_delay': 3,  # Seconds between agent launches
            
            # Tmux settings
            'use_tmux': True,
            'auto_open_terminal': True,
            'preferred_terminal': None,  # Auto-detect if None
            
            # Timing settings (optimized for Claude Code)
            'agent_monitor_interval': 30,  # Check agents every 30 seconds
            'message_grace_period': 60,  # Wait 60 seconds after sending message
            'wait_check_interval': 5,  # Check interval when waiting for agents
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self._config.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set configuration value"""
        self._config[key] = value
    
    @property
    def prompts_dir(self) -> Path:
        """Get prompts directory path"""
        return Path(self._config['prompts_dir'])
    
    @property
    def sessions_dir(self) -> Path:
        """Get sessions directory path"""
        return Path(self._config['sessions_dir'])
    
    @property
    def use_tmux(self) -> bool:
        """Whether to use tmux"""
        return self._config.get('use_tmux', True)
    
    @property
    def log_level(self) -> str:
        """Get log level"""
        return self._config.get('log_level', 'INFO')
    
    @property
    def claude_command(self) -> list:
        """Get full Claude command"""
        cmd = [self._config['claude_command']]
        cmd.extend(self._config.get('claude_args', []))
        return cmd
    
    @property
    def agent_monitor_interval(self) -> int:
        """Get agent monitoring interval in seconds"""
        return self._config.get('agent_monitor_interval', 30)
    
    @property
    def message_grace_period(self) -> int:
        """Get grace period after sending message in seconds"""
        return self._config.get('message_grace_period', 60)
    
    @property
    def wait_check_interval(self) -> int:
        """Get check interval when waiting for agents"""
        return self._config.get('wait_check_interval', 5)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return self._config.copy()