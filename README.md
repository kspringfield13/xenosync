![Xenosync](assets/xenosync-hero.png)

# Xenosync
### Multi-Agent AI Orchestration Platform

[![Version](https://img.shields.io/badge/version-2.1.0-maroon.svg)](https://github.com/xenosync/xenosync)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

## What is Xenosync?

Xenosync orchestrates multiple Claude Code AI agents to work together on complex software development tasks. Run 2-20 agents in parallel to build applications, refactor code, and solve engineering challenges faster.

**Version 2.1** introduces enhanced completion detection, project-based workspaces, and intelligent timing controls for more reliable multi-agent coordination.

## Prerequisites

- Python 3.8+
- [Claude CLI](https://claude.ai/code) installed and configured
- Tmux (for visual monitoring)

## Installation

```bash
# Clone the repository
git clone https://github.com/xenosync/xenosync.git
cd xenosync

# Install Xenosync
pip install -e .

# Initialize configuration
xenosync init
```

## Quick Start

```bash
# Start with interactive prompt selection (minimum 2 agents)
xenosync start --agents 4

# Run a specific prompt file
xenosync start my_prompt.yaml --agents 3
```

## How It Works

Xenosync uses **project-based parallel execution** to distribute tasks among agents upfront. Each agent works in an isolated project workspace, allowing them to build, test, and iterate independently before final project merging.

### Key Features (v2.1)

- **Enhanced Completion Detection**: Multi-signal analysis using pattern detection, file activity monitoring, and semantic verification
- **Project-Based Workspaces**: Each agent works in `~/agent-N/project/` for isolated development
- **Intelligent Timing**: Minimum 10-minute work duration prevents premature completion
- **Quality Validation**: Ensures substantial work before allowing project merges
- **Manual Merge Triggers**: Manual override capabilities for stuck situations

**Best for**: Building separate components, parallel development, independent tasks

```bash
xenosync start prompt.yaml --agents 4
```

## Demo Example - Retro Game Build

Experience xenosync's power by building a complete Pac-Man style arcade game. This demo serves as our primary performance benchmark:

```bash
# Agents divide game components (graphics, AI, controls, sound) and work in parallel
xenosync start prompts/demos/retro-game.yaml --agents 4
```

This builds a fully playable retro arcade game with:
- 8-bit pixel art graphics and animations
- Ghost AI with different personality patterns
- Power-ups and scoring system
- Retro sound effects and music
- Responsive controls and collision detection

Watch as multiple agents collaborate to create a complex, interactive game in minutes!

## Commands Reference

### Starting Sessions
```bash
xenosync start                          # Interactive prompt selection
xenosync start prompt.yaml --agents 4   # Run specific prompt
xenosync start --resume <session-id>    # Resume previous session
```

### Managing Sessions
```bash
xenosync status                         # Show active sessions
xenosync list                           # List all sessions
xenosync attach --hive                  # Attach to tmux session
xenosync kill <session-id>              # Terminate a session
```

### Manual Project Merging
```bash
# Trigger immediate merge (if agents appear stuck)
kill -USR1 <orchestrator-pid>           # Send signal to orchestrator
# or
touch .xenosync_merge_now               # Create trigger file in project root
```

### Working with Prompts
```bash
xenosync prompt list                    # List available prompts
xenosync prompt validate file.yaml      # Validate prompt syntax
```

## Creating Prompts

Create YAML files defining your tasks:

```yaml
name: "Build Feature X"
description: "Create a new feature with tests"
initial_prompt: |
  You are part of a development team building Feature X.
  Work together to create high-quality, tested code.

steps:
  - number: 1
    content: "Set up the project structure and dependencies"
    
  - number: 2
    content: "Implement the core feature logic"
    
  - number: 3
    content: "Add comprehensive tests"
    
  - number: 4
    content: "Create documentation"
```

## Configuration

Configuration lives in `~/.xenosync/config.yaml`:

```yaml
# Core settings
log_level: INFO
sessions_dir: xsync-sessions
prompts_dir: prompts

# Claude settings
claude_command: claude
claude_args: ['--dangerously-skip-permissions']

# Multi-agent defaults
num_agents: 2                # Minimum 2 agents required

# Timing (optimized for Claude Code)
agent_monitor_interval: 30   # Check agents every 30 seconds
message_grace_period: 60     # Wait after sending work

# Enhanced completion detection (v2.1)
minimum_work_duration_minutes: 10        # Minimum work time before completion
require_completion_confidence: true      # Use enhanced detection vs basic patterns
completion_confidence_threshold: 0.7     # Confidence needed for completion
project_quality_threshold: 3             # Minimum files per project
project_substantial_work_threshold: 500  # Minimum characters in project files

# Completion verification
completion_verification_enabled: true    # Proactive completion verification
completion_verification_interval: 300    # Verify every 5 minutes
file_activity_timeout: 10               # No activity timeout (minutes)
```

## Visual Monitoring

Xenosync automatically opens a tmux session showing all agents:

- **Orchestrator window**: Main control and logging
- **Agent panes**: Individual agent outputs
- **Color coding**: Green (working), Yellow (idle), Red (error)

Attach to running session:
```bash
xenosync attach --hive
# or directly with tmux
tmux attach -t xenosync-hive
```

## Troubleshooting

### "Minimum 2 agents required"
Xenosync is a multi-agent platform. Always specify at least 2 agents:
```bash
xenosync start prompt.yaml --agents 2  # Minimum
```

### Tmux session persists after Ctrl+C
Clean up manually if needed:
```bash
xenosync kill all
# or
tmux kill-session -t xenosync-hive
```

### Agents marked idle too quickly
This is normal - agents alternate between working and idle states. The system has 60-second grace periods to avoid premature idle detection.

### File coordination conflicts
The file-based coordination system prevents conflicts automatically. If you see conflict warnings, they typically self-resolve within seconds.

### Project completion too early (v2.1)
The enhanced completion detection now enforces:
- Minimum 10-minute work duration per agent
- Quality validation (minimum 3 files, 500+ characters)
- Multi-signal confidence scoring before completion

### Agents appear stuck but working
Use manual merge triggers if agents seem finished but system hasn't detected completion:
```bash
kill -USR1 <orchestrator-pid>  # Send signal
# or
touch .xenosync_merge_now      # Create trigger file
```

### Enhanced completion detection issues
Disable enhanced detection and use basic patterns:
```yaml
require_completion_confidence: false
```

## Tips for Best Results

1. **Start with 3-4 agents** - Good balance of parallelism and efficiency
2. **Break large tasks into smaller steps** in your YAML prompts
3. **Let agents run** - They work best with minimal intervention
4. **Structure tasks clearly** - Well-defined tasks lead to better parallel execution

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black xenosync/

# Type checking
mypy xenosync/
```

## Architecture Highlights

- **Project-based workspaces**: Each agent works in isolated `~/agent-N/project/` directories
- **Enhanced completion detection**: Multi-signal analysis with pattern detection, file monitoring, and semantic verification
- **File-based coordination**: No database needed, uses JSON files for state
- **Conflict-free design**: Automatic work claim system prevents overlaps
- **Intelligent timing**: Minimum work duration and quality validation prevent premature completion
- **Resilient agents**: Automatic recovery from API errors with proactive verification
- **Visual feedback**: Real-time tmux monitoring with shortened path displays
- **Manual override**: Signal-based and file-based merge triggers for stuck situations

## Contributing

We welcome contributions! Focus areas:
- Enhanced completion detection algorithms
- Project workspace optimization
- Execution strategy improvements
- Agent coordination enhancements
- Prompt templates for common tasks

## License

MIT License - see [LICENSE](LICENSE) file.

---

**Xenosync** - Orchestrate AI agents to build software faster