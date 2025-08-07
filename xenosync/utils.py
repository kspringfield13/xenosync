"""
Utility functions for Xenosync - Alien Synchronization Platform
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
import random


def setup_logging(level: str = "INFO"):
    """Setup logging configuration for Xenosync"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def print_banner():
    """Print Xenosync ASCII art banner with alien theme"""
    
    banners = [
        """
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│  ██╗  ██╗███████╗███╗   ██╗ ██████╗ ███████╗██╗   ██╗███╗   ██╗ ██████╗  │
│  ╚██╗██╔╝██╔════╝████╗  ██║██╔═══██╗██╔════╝╚██╗ ██╔╝████╗  ██║██╔════╝  │
│   ╚███╔╝ █████╗  ██╔██╗ ██║██║   ██║███████╗ ╚████╔╝ ██╔██╗ ██║██║       │
│   ██╔██╗ ██╔══╝  ██║╚██╗██║██║   ██║╚════██║  ╚██╔╝  ██║╚██╗██║██║       │
│  ██╔╝ ██╗███████╗██║ ╚████║╚██████╔╝███████║   ██║   ██║ ╚████║╚██████╗  │
│  ╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝ ╚═════╝ ╚══════╝   ╚═╝   ╚═╝  ╚═══╝ ╚═════╝  │
│                                                                          │
│                      Alien Synchronization Protocol                      │
│                      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                      │
└──────────────────────────────────────────────────────────────────────────┘
        """
    ]
    
    # Choose random banner
    banner = random.choice(banners)
    
    # Add color if terminal supports it
    if sys.stdout.isatty():
        # Alien green color
        banner = f"\033[92m{banner}\033[0m"
    
    print(banner)
    print()


def print_alien_message(message: str, style: str = "normal"):
    """Print a message with alien-themed styling"""
    
    if style == "success":
        prefix = "👽 [SYNC-SUCCESS]"
        color = "\033[92m"  # Green
    elif style == "warning":
        prefix = "⚠️  [HIVE-ALERT]"
        color = "\033[93m"  # Yellow
    elif style == "error":
        prefix = "❌ [SYNC-FAILURE]"
        color = "\033[91m"  # Red
    elif style == "info":
        prefix = "◉  [TRANSMISSION]"
        color = "\033[94m"  # Blue
    else:
        prefix = "◈  [XENOSYNC]"
        color = "\033[95m"  # Magenta
    
    if sys.stdout.isatty():
        print(f"{color}{prefix} {message}\033[0m")
    else:
        print(f"{prefix} {message}")


def format_alien_time(dt: datetime) -> str:
    """Format datetime in alien coordinate system"""
    # Use a fun alien time format
    earth_time = dt.strftime("%Y-%m-%d %H:%M:%S")
    alien_cycle = dt.timestamp() % 10000
    return f"{earth_time} [Cycle {alien_cycle:.0f}]"


def get_alien_greeting() -> str:
    """Get a random alien greeting"""
    greetings = [
        "Initiating otherworldly synchronization...",
        "Establishing alien hive connection...",
        "Synchronizing across dimensional barriers...",
        "Activating xenomorphic coordination protocol...",
        "Engaging multi-dimensional agent synthesis...",
        "Calibrating alien synchronization matrix...",
        "Opening interdimensional communication channels...",
        "Harmonizing with the cosmic collective...",
    ]
    return random.choice(greetings)


def get_completion_message() -> str:
    """Get a random completion message"""
    messages = [
        "Synchronization complete. The hive is pleased.",
        "Alien coordination successful. All agents harmonized.",
        "Interdimensional synthesis achieved.",
        "The collective consciousness has spoken.",
        "Xenosync protocol executed flawlessly.",
        "All alien agents report successful integration.",
        "Hive mind synchronization complete.",
        "Otherworldly orchestration concluded.",
    ]
    return random.choice(messages)


def create_session_id() -> str:
    """Create a unique session ID with alien theme"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    import hashlib
    import uuid
    
    # Create alien-themed prefix
    prefixes = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "theta", "omega"]
    prefix = random.choice(prefixes)
    
    # Generate unique suffix
    unique = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()[:6]
    
    return f"{prefix}_{timestamp}_{unique}"


def validate_agent_count(count: int) -> bool:
    """Validate agent count is within alien protocol limits"""
    MIN_AGENTS = 1
    MAX_AGENTS = 20  # Maximum hive size
    
    if count < MIN_AGENTS:
        print_alien_message(
            f"Insufficient agents. Minimum hive size is {MIN_AGENTS}.",
            "error"
        )
        return False
    
    if count > MAX_AGENTS:
        print_alien_message(
            f"Hive overload. Maximum supported agents is {MAX_AGENTS}.",
            "error"
        )
        return False
    
    return True


def display_hive_status(active_agents: int, total_agents: int, mode: str):
    """Display alien hive status"""
    status_art = f"""
    ╔═══════════════════════════════════════╗
    ║         XENOSYNC HIVE STATUS          ║
    ╠═══════════════════════════════════════╣
    ║  Active Aliens: {active_agents:2d}/{total_agents:2d}                 ║
    ║  Sync Mode: {mode:26s} ║
    ║  Hive Health: {"◉" * active_agents}{"○" * (total_agents - active_agents)}{" " * (20 - total_agents)} ║
    ╚═══════════════════════════════════════╝
    """
    print(status_art)