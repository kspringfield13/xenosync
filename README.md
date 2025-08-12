# Xenosync
### Multi-Agent AI Orchestration Platform

[![Version](https://img.shields.io/badge/version-2.0.0-maroon.svg)](https://github.com/xenosync/xenosync)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

## What is Xenosync?

Xenosync orchestrates multiple Claude Code AI agents to work together on complex software development tasks. Run 2-20 agents in parallel or collaborative mode to build applications, refactor code, and solve engineering challenges faster.

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

# Use collaborative mode for interdependent tasks
xenosync start prompt.yaml --agents 4 --mode collaborative
```

## Execution Modes

### Parallel Mode (Default)
Tasks are pre-distributed among agents. Each agent works independently on their assigned tasks.

**Use when**: Tasks are independent, building separate components, parallel development

```bash
xenosync start prompt.yaml --agents 4 --mode parallel
```

### Collaborative Mode  
Agents dynamically claim tasks from a shared pool and can build on each other's work.

**Use when**: Tasks are interdependent, need coordination, complex systems

```bash
xenosync start prompt.yaml --agents 3 --mode collaborative
```

## Demo Example - Retro Game Build

Experience xenosync's power by building a complete Pac-Man style arcade game. This demo serves as our primary performance benchmark:

```bash
# Parallel mode - Agents divide game components (graphics, AI, controls, sound)
xenosync start prompts/demos/retro-game.yaml --agents 4 --mode parallel

# Collaborative mode - Agents coordinate on interdependent game systems
xenosync start prompts/demos/retro-game.yaml --agents 4 --mode collaborative
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
execution_mode: parallel     # parallel or collaborative

# Timing (optimized for Claude Code)
agent_monitor_interval: 30   # Check agents every 30 seconds
message_grace_period: 60     # Wait after sending work
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

## Tips for Best Results

1. **Start with 3-4 agents** - Good balance of parallelism and coordination
2. **Use parallel mode** for independent tasks like building separate features
3. **Use collaborative mode** for complex, interconnected work
4. **Break large tasks into smaller steps** in your YAML prompts
5. **Let agents run** - They work best with minimal intervention

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

- **File-based coordination**: No database needed, uses JSON files for state
- **Conflict-free design**: Automatic work claim system prevents overlaps
- **Resilient agents**: Automatic recovery from API errors
- **Visual feedback**: Real-time tmux monitoring of all agents

## Contributing

We welcome contributions! Focus areas:
- Execution strategy improvements
- Agent coordination enhancements
- Prompt templates for common tasks

## License

MIT License - see [LICENSE](LICENSE) file.

---

**Xenosync** - Orchestrate AI agents to build software faster