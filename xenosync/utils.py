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