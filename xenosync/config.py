"""
Configuration management for Xenosync """

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional


@dataclass
class SyncProfile:
    """Build speed profile configuration"""
    name: str
    step_interval: int  # seconds between steps
    min_step_duration: int  # minimum seconds per step
    idle_check_interval: int  # seconds between idle checks
    idle_threshold: int  # seconds before considered idle
    idle_check_delay: int  # initial delay before checking


# Predefined profiles
PROFILES = {
    'fast': SyncProfile(
        name='fast',
        step_interval=300,  # 5 minutes
        min_step_duration=240,  # 4 minutes
        idle_check_interval=20,
        idle_threshold=40,
        idle_check_delay=30
    ),
    'normal': SyncProfile(
        name='normal',
        step_interval=600,  # 10 minutes
        min_step_duration=480,  # 8 minutes
        idle_check_interval=20,
        idle_threshold=40,
        idle_check_delay=60
    ),
    'careful': SyncProfile(
        name='careful',
        step_interval=1200,  # 20 minutes
        min_step_duration=900,  # 15 minutes
        idle_check_interval=30,
        idle_threshold=60,
        idle_check_delay=120
    )
}


class Config:
    """Xenosync configuration manager"""
    
    def __init__(self, config_dict: Optional[Dict[str, Any]] = None):
        self._config = config_dict or self._default_config()
        self._profile = PROFILES[self._config.get('default_profile', 'normal')]
    
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
        """Get default configuration"""
        return {
            # General settings
            'default_profile': 'normal',
            'use_tmux': True,
            'auto_continue': True,
            'log_level': 'INFO',
            
            # Paths
            'prompts_dir': 'prompts',
            'sessions_dir': 'xsync-sessions',
            'templates_dir': 'templates',
            
            # Session settings
            'session_name_prefix': 'build',
            'max_retries': 3,
            'retry_delay': 60,
            
            # Claude settings
            'claude_command': 'claude',
            'claude_args': ['--dangerously-skip-permissions'],
            'initial_wait': 3,  # seconds to wait after starting Claude
            
            # TODO detection settings
            'wait_for_todo': True,  # Whether to wait for TODO list
            'todo_wait_timeout': 90,  # Maximum seconds to wait for TODO
            'todo_patterns': [  # Patterns to detect TODO lists
                'todos', 'todo', 'task', 'steps', 'plan', 'ready',
                'update todos', 'todo list', 'task list', 'action items',
                'next steps', 'implementation plan', 'sync steps'
            ],
            'todo_capture_lines': 150,  # Lines to capture when checking for TODO
            
            # Database
            'database_path': 'xenosync.db',
            
            # Monitoring
            'enable_web_monitor': True,
            'monitor_port': 8080,
            'monitor_host': 'localhost',
            
            # Notifications
            'enable_notifications': False,
            'notification_webhook': None,
            
            # Advanced
            'capture_screenshots': False,
            'archive_completed': True,
            'compression': 'gzip',
            'max_log_size_mb': 100,
            'debug_output': False  # Enable debug output capture
        }
    
    def apply_profile(self, profile_name: str):
        """Apply a build profile"""
        if profile_name in PROFILES:
            self._profile = PROFILES[profile_name]
            self._config['current_profile'] = profile_name
        else:
            raise ValueError(f"Unknown profile: {profile_name}")
    
    @property
    def profile(self) -> SyncProfile:
        """Get current build profile"""
        return self._profile
    
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
    def database_path(self) -> Path:
        """Get database path"""
        return Path(self._config['database_path'])
    
    @property
    def use_tmux(self) -> bool:
        """Whether to use tmux"""
        return self._config.get('use_tmux', True)
    
    @property
    def auto_continue(self) -> bool:
        """Whether to auto-continue on idle"""
        return self._config.get('auto_continue', True)
    
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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            **self._config,
            'current_profile': asdict(self._profile)
        }