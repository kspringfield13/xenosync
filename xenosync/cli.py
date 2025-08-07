#!/usr/bin/env python3
"""
Xenosync - Unified Alien Synchronization Platform

A simplified, powerful system for managing sequential Claude sessions
to execute complex, multi-step synchronization processes.
"""

import asyncio
import click
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Import our modules
from .config import Config, SyncProfile
from .orchestrator import XenosyncOrchestrator
from .session_manager import SessionManager
from .prompt_manager import PromptManager
from .monitor import XenosyncMonitor
from .utils import setup_logging, print_banner

# Version
__version__ = "2.0.0"


@click.group()
@click.version_option(version=__version__)
@click.option('--config', '-c', type=click.Path(), help='Configuration file path')
@click.option('--profile', '-p', type=str, help='Build profile (fast/normal/careful)')
@click.pass_context
def cli(ctx, config, profile):
    """Xenosync - Alien Synchronization Platform"""
    ctx.ensure_object(dict)
    
    # Load configuration
    config_path = Path(config) if config else Path.home() / '.xenosync' / 'config.yaml'
    ctx.obj['config'] = Config.load(config_path)
    
    # Apply profile if specified
    if profile:
        ctx.obj['config'].apply_profile(profile)
    
    # Setup logging
    setup_logging(ctx.obj['config'].log_level)


@cli.command()
@click.argument('prompt_file', required=False)
@click.option('--speed', '-s', type=click.Choice(['fast', 'normal', 'careful']), 
              default='normal', help='Build speed profile')
@click.option('--agents', '-a', type=int, default=1, 
              help='Number of agents to run (1-20)')
@click.option('--mode', '-m', type=click.Choice(['sequential', 'parallel', 'collaborative', 'distributed', 'hybrid']), 
              default='sequential', help='Execution mode for multi-agent runs')
@click.option('--resume', '-r', type=str, help='Resume a previous session')
@click.option('--dry-run', is_flag=True, help='Validate prompt without starting build')
@click.pass_context
def start(ctx, prompt_file, speed, agents, mode, resume, dry_run):
    """Start a new sync session"""
    config = ctx.obj['config']
    config.apply_profile(speed)
    
    # Validate agent count
    if agents < 1 or agents > 20:
        click.echo("Error: Number of agents must be between 1 and 20", err=True)
        sys.exit(1)
    
    # If multiple agents requested but mode is sequential, warn user
    if agents > 1 and mode == 'sequential':
        click.echo("Warning: Sequential mode with multiple agents will run agents one at a time")
    
    # Store multi-agent settings in config
    config.set('multi_agent_enabled', agents > 1)
    config.set('num_agents', agents)
    config.set('execution_mode', mode)
    
    # Initialize managers
    session_manager = SessionManager(config)
    prompt_manager = PromptManager(config)
    
    try:
        if resume:
            # Resume existing session
            session = session_manager.resume_session(resume)
            if not session:
                click.echo(f"Session {resume} not found or cannot be resumed", err=True)
                sys.exit(1)
            prompt = prompt_manager.load_prompt(session.prompt_file)
        else:
            # Load or select prompt
            if prompt_file:
                prompt = prompt_manager.load_prompt(prompt_file)
            else:
                prompt = prompt_manager.select_prompt()
            
            if dry_run:
                # Validate and display prompt info
                click.echo(f"Prompt: {prompt.name}")
                click.echo(f"Total steps: {len(prompt.steps)}")
                click.echo(f"Estimated time: {prompt.estimated_time(config)}")
                return
            
            # Create new session
            session = session_manager.create_session(prompt)
        
        # Print session info
        print_banner()
        click.echo(f"Session ID: {session.id}")
        click.echo(f"Project: {prompt.name}")
        click.echo(f"Steps: {len(prompt.steps)}")
        click.echo(f"Speed: {speed}")
        if agents > 1:
            click.echo(f"Agents: {agents}")
            click.echo(f"Mode: {mode}")
        
        # Start orchestrator
        orchestrator = XenosyncOrchestrator(config, session_manager, prompt_manager)
        
        # Run the build
        try:
            asyncio.run(orchestrator.run(session, prompt))
        except KeyboardInterrupt:
            # Handle interrupt gracefully
            click.echo("\n\n" + "=" * 60)
            click.echo("Shutting down agents...")
            orchestrator.interrupt()
            click.echo("=" * 60)
        
    except KeyboardInterrupt:
        click.echo("\n\nBuild interrupted by user")
        if 'session' in locals():
            from xenosync.session_manager import SessionStatus
            session_manager.update_session_status(session.id, SessionStatus.INTERRUPTED)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        if 'session' in locals():
            from xenosync.session_manager import SessionStatus
            session_manager.update_session_status(session.id, SessionStatus.FAILED)
        sys.exit(1)


@cli.command()
@click.option('--session', '-s', help='Specific session ID')
@click.option('--detailed', '-d', is_flag=True, help='Show detailed information')
@click.pass_context
def status(ctx, session, detailed):
    """Show sync session status"""
    config = ctx.obj['config']
    session_manager = SessionManager(config)
    
    if session:
        # Show specific session
        session_info = session_manager.get_session(session)
        if not session_info:
            click.echo(f"Session {session} not found", err=True)
            return
        
        session_manager.display_session_status(session_info, detailed)
    else:
        # Show all active sessions
        active_sessions = session_manager.get_active_sessions()
        if not active_sessions:
            click.echo("No active sessions")
            return
        
        click.echo("Active Sessions:")
        for sess in active_sessions:
            session_manager.display_session_summary(sess)


@cli.command()
@click.option('--port', '-p', type=int, default=8080, help='Port for web interface')
@click.option('--host', '-h', type=str, default='localhost', help='Host to bind to')
@click.pass_context
def monitor(ctx, port, host):
    """Start the web-based monitoring dashboard"""
    config = ctx.obj['config']
    monitor = XenosyncMonitor(config)
    
    click.echo(f"Starting monitoring dashboard at http://{host}:{port}")
    monitor.start(host, port)


@cli.command()
@click.argument('session_id', required=False)
@click.option('--hive', is_flag=True, help='Attach to multi-agent hive session')
@click.pass_context
def attach(ctx, session_id, hive):
    """Attach to a running sync session
    
    Use --hive to attach to the multi-agent tmux session
    """
    config = ctx.obj['config']
    
    if hive:
        # Attach to multi-agent hive session
        import subprocess
        if subprocess.run(['which', 'tmux'], capture_output=True).returncode == 0:
            # Check for xenosync hive sessions
            result = subprocess.run(['tmux', 'list-sessions'], capture_output=True, text=True)
            if result.returncode == 0:
                # Look for xenosync-hive or xenosync_collective sessions
                hive_sessions = [s for s in result.stdout.splitlines() 
                               if 'xenosync' in s.lower() and ('hive' in s or 'collective' in s)]
                if hive_sessions:
                    # Get the most recent hive session
                    session_name = hive_sessions[0].split(':')[0]
                    click.echo(f"Attaching to hive session: {session_name}")
                    click.echo("Navigation: Ctrl+B,1 for agents | Ctrl+B,d to detach")
                    subprocess.run(['tmux', 'attach-session', '-t', session_name])
                else:
                    click.echo("No active hive sessions found", err=True)
                    click.echo("Start a multi-agent session with: xenosync start <prompt> --agents N")
            else:
                click.echo("No tmux sessions found", err=True)
        else:
            click.echo("tmux not available", err=True)
        return
    
    if not session_id:
        click.echo("Please provide a session ID or use --hive for multi-agent sessions", err=True)
        return
    
    session_manager = SessionManager(config)
    session = session_manager.get_session(session_id)
    if not session or session.status != 'active':
        click.echo(f"No active session found: {session_id}", err=True)
        return
    
    # Use tmux attach if available, otherwise show logs
    if config.use_tmux:
        import subprocess
        subprocess.run(['tmux', 'attach-session', '-t', f'xsync-{session_id[:8]}'])
    else:
        # Stream logs
        session_manager.stream_logs(session_id)


@cli.command()
@click.argument('session_id')
@click.option('--force', '-f', is_flag=True, help='Force kill without confirmation')
@click.pass_context
def kill(ctx, session_id, force):
    """Kill a running sync session"""
    config = ctx.obj['config']
    session_manager = SessionManager(config)
    
    if not force:
        click.confirm(f"Are you sure you want to kill session {session_id}?", abort=True)
    
    if session_manager.kill_session(session_id):
        click.echo(f"Session {session_id} killed")
    else:
        click.echo(f"Failed to kill session {session_id}", err=True)


@cli.command()
@click.option('--all', '-a', is_flag=True, help='List all sessions (not just active)')
@click.option('--limit', '-l', type=int, default=10, help='Number of sessions to show')
@click.pass_context
def list(ctx, all, limit):
    """List sync sessions"""
    config = ctx.obj['config']
    session_manager = SessionManager(config)
    
    if all:
        sessions = session_manager.get_all_sessions(limit=limit)
        click.echo(f"All Sessions (showing {len(sessions)} of {session_manager.count_sessions()}):")
    else:
        sessions = session_manager.get_active_sessions()
        click.echo(f"Active Sessions ({len(sessions)}):")
    
    if not sessions:
        click.echo("No sessions found")
        return
    
    for session in sessions:
        session_manager.display_session_summary(session)


@cli.command()
@click.argument('session_id')
@click.option('--format', '-f', type=click.Choice(['markdown', 'json', 'html']), 
              default='markdown', help='Output format')
@click.option('--output', '-o', type=click.Path(), help='Output file path')
@click.pass_context
def summary(ctx, session_id, format, output):
    """Generate a session summary report"""
    config = ctx.obj['config']
    session_manager = SessionManager(config)
    
    summary = session_manager.generate_summary(session_id, format)
    if not summary:
        click.echo(f"Could not generate summary for session {session_id}", err=True)
        return
    
    if output:
        Path(output).write_text(summary)
        click.echo(f"Summary written to {output}")
    else:
        click.echo(summary)


@cli.command()
@click.option('--days', '-d', type=int, default=30, help='Number of days to analyze')
@click.pass_context
def stats(ctx, days):
    """Show build statistics"""
    config = ctx.obj['config']
    session_manager = SessionManager(config)
    
    stats = session_manager.get_statistics(days)
    session_manager.display_statistics(stats)


@cli.group()
def prompt():
    """Manage build prompts"""
    pass


@prompt.command('list')
@click.pass_context
def prompt_list(ctx):
    """List available prompts"""
    config = ctx.obj['config']
    prompt_manager = PromptManager(config)
    
    prompts = prompt_manager.list_prompts()
    if not prompts:
        click.echo("No prompts found")
        return
    
    click.echo("Available Prompts:")
    for p in prompts:
        click.echo(f"  {p.name} - {len(p.steps)} steps")
        if p.description:
            click.echo(f"    {p.description}")


@prompt.command('validate')
@click.argument('prompt_file')
@click.pass_context
def prompt_validate(ctx, prompt_file):
    """Validate a prompt file"""
    config = ctx.obj['config']
    prompt_manager = PromptManager(config)
    
    try:
        prompt = prompt_manager.load_prompt(prompt_file)
        click.echo(f"✓ Prompt is valid: {prompt.name}")
        click.echo(f"  Steps: {len(prompt.steps)}")
        click.echo(f"  Format: {prompt.format}")
    except Exception as e:
        click.echo(f"✗ Invalid prompt: {e}", err=True)
        sys.exit(1)


@prompt.command('convert')
@click.argument('input_file')
@click.argument('output_file')
@click.pass_context
def prompt_convert(ctx, input_file, output_file):
    """Convert prompt between formats (txt <-> yaml)"""
    config = ctx.obj['config']
    prompt_manager = PromptManager(config)
    
    try:
        prompt_manager.convert_prompt(input_file, output_file)
        click.echo(f"Converted {input_file} to {output_file}")
    except Exception as e:
        click.echo(f"Conversion failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('agent_id', type=int)
@click.option('--session', '-s', help='Session ID to find agent in')
@click.pass_context
def recover(ctx, agent_id, session):
    """Force recovery attempt for a stuck agent
    
    Use this command to manually trigger error recovery for an agent
    that appears to be stuck with API errors.
    """
    config = ctx.obj['config']
    
    click.echo(f"🔄 Manual recovery requested for agent {agent_id}")
    if session:
        click.echo(f"Session: {session}")
    
    click.echo("\nTo use this feature:")
    click.echo("1. Attach to the hive session: xenosync attach --hive")
    click.echo("2. Identify stuck agents by monitoring their output")
    click.echo("3. The system will automatically attempt recovery")
    click.echo("\nFor immediate help:")
    click.echo("- Send '--continue' to the agent manually in tmux")
    click.echo("- Or send 'Please retry and continue with your work'")


@cli.command()
@click.pass_context
def init(ctx):
    """Initialize Xenosync configuration"""
    config_dir = Path.home() / '.xenosync'
    config_dir.mkdir(exist_ok=True)
    
    config_file = config_dir / 'config.yaml'
    if config_file.exists():
        click.confirm("Configuration already exists. Overwrite?", abort=True)
    
    # Create default configuration
    Config.create_default(config_file)
    click.echo(f"Created configuration at {config_file}")
    
    # Create directories
    for dir_name in ['prompts', 'sessions', 'logs', 'templates']:
        (config_dir / dir_name).mkdir(exist_ok=True)
    
    click.echo("Xenosync initialized successfully!")


if __name__ == '__main__':
    cli()