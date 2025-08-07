#!/usr/bin/env python3
"""
Xenosync - Alien Synchronization Platform
Setup and installation configuration
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_path = Path(__file__).parent / "README.md"
if readme_path.exists():
    long_description = readme_path.read_text()
else:
    long_description = "Xenosync - Alien Synchronization Platform for Multi-Agent AI Orchestration"

setup(
    name="xenosync",
    version="3.0.0",
    author="Xenosync Collective",
    author_email="contact@xenosync.ai",
    description="Alien synchronization platform for orchestrating multiple AI agents",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/xenosync/xenosync",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "click>=8.0",
        "pyyaml>=6.0",
        "aiohttp>=3.8",
        "asyncio>=3.4",
        "dataclasses>=0.6",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-asyncio>=0.21",
            "black>=22.0",
            "mypy>=1.0",
            "flake8>=5.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "xenosync=xenosync.cli:cli",
            "xsync=xenosync.cli:cli",  # Short alias
        ],
    },
    include_package_data=True,
    package_data={
        "xenosync": [
            "templates/*.yaml",
        ],
    },
)
