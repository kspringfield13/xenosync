#!/usr/bin/env python3
"""
Module: cli
Purpose: Command-line interface entry point for Xenosync multi-agent orchestration

This module provides the main CLI commands for interacting with Xenosync. It handles
command parsing, session management, configuration loading, and orchestration startup.
Supports both single and multi-agent modes with tmux visualization.

Key Classes:
    - XenosyncCLI: Main CLI application class

Key Functions:
    - cli(): Main CLI group
    - start(): Start a new multi-agent session
    - status(): Show active sessions
    - kill(): Terminate a session
    - attach(): Attach to tmux session
    - validate(): Validate configuration and prompts

Dependencies:
    - click: CLI framework
    - asyncio: Async execution
    - rich: Terminal formatting
    - orchestrator: Main execution engine
    - file_session_manager: Session persistence

Usage:
    xenosync start prompt.yaml --agents 4
    xenosync status
    xenosync attach --hive
    xenosync kill <session-id>
    
Author: Xenosync Team
Created: 2024-08-14
Modified: 2024-08-14
"""

import asyncio
import click
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Import our modules
from .config import Config
from .orchestrator import XenosyncOrchestrator
from .file_session_manager import SessionManager
from .prompt_manager import PromptManager
from .utils import setup_logging, print_banner

# Version
__version__ = "2.0.0"


@click.group()
@click.version_option(version=__version__)
@click.option('--config', '-c', type=click.Path(), help='Configuration file path')
@click.pass_context
def cli(ctx, config):
    """Xenosync - Alien Synchronization Platform"""
    ctx.ensure_object(dict)
    
    # Load configuration
    config_path = Path(config) if config else Path.home() / '.xenosync' / 'config.yaml'
    ctx.obj['config'] = Config.load(config_path)
    
    # Setup logging
    setup_logging(ctx.obj['config'].log_level)


@cli.command()
@click.argument('prompt_file', required=False)
@click.option('--agents', '-a', type=int, default=2, 
              help='Number of agents to run (2-20)')

@click.option('--resume', '-r', type=str, help='Resume a previous session')
@click.option('--dry-run', is_flag=True, help='Validate prompt without starting')
@click.option('--no-terminal', is_flag=True, help='Disable automatic terminal opening')
@click.pass_context
def start(ctx, prompt_file, agents, resume, dry_run, no_terminal):
    """Start a new multi-agent sync session
    
    Xenosync orchestrates multiple AI agents to work on tasks in parallel.
    Tasks are divided among agents upfront for efficient execution.
    """
    config = ctx.obj['config']
    
    # Validate agent count (minimum 2 for multi-agent platform)
    if agents < 2:
        click.echo("Error: Minimum 2 agents required for multi-agent execution", err=True)
        click.echo("Tip: Use --agents to specify number of agents (2-20)", err=True)
        sys.exit(1)
    
    if agents > 20:
        click.echo("Error: Maximum 20 agents supported", err=True)
        sys.exit(1)
    
    # Store settings in config
    config.set('num_agents', agents)
    config.set('auto_open_terminal', not no_terminal)
    
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
        click.echo(f"Agents: {agents}")
        
        # Start orchestrator
        orchestrator = XenosyncOrchestrator(config, session_manager, prompt_manager)
        
        # Run the build
        try:
            asyncio.run(orchestrator.run(session, prompt))
        except KeyboardInterrupt:
            # Handle interrupt gracefully with tmux cleanup
            click.echo("\n\n" + "=" * 60)
            click.echo("Shutting down agents...")
            click.echo("=" * 60)
            
            # Ensure tmux sessions are cleaned up
            try:
                from xenosync.tmux_manager import TmuxManager
                click.echo("Cleaning up tmux sessions...")
                TmuxManager.kill_xenosync_sessions()
                click.echo("Cleanup completed.")
            except Exception as e:
                click.echo(f"Warning: Failed to clean up tmux sessions: {e}", err=True)
        
    except KeyboardInterrupt:
        click.echo("\n\nBuild interrupted by user")
        
        # Update session status if exists
        if 'session' in locals():
            from xenosync.file_session_manager import SessionStatus
            session_manager.update_session_status(session.id, SessionStatus.INTERRUPTED)
        
        # Ensure tmux cleanup on outer interrupt as well
        try:
            from xenosync.tmux_manager import TmuxManager
            click.echo("Performing final cleanup...")
            TmuxManager.kill_xenosync_sessions()
        except Exception as e:
            click.echo(f"Warning: Failed to clean up tmux sessions: {e}", err=True)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        
        # Update session status if exists
        if 'session' in locals():
            from xenosync.file_session_manager import SessionStatus
            session_manager.update_session_status(session.id, SessionStatus.FAILED)
        
        # Cleanup tmux sessions on error as well
        try:
            from xenosync.tmux_manager import TmuxManager
            TmuxManager.kill_xenosync_sessions()
        except Exception:
            pass  # Don't mask the original error with cleanup errors
        
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
                # Look for xenosync-hive or other xenosync sessions
                all_xenosync_sessions = [s for s in result.stdout.splitlines() 
                                       if 'xenosync' in s.lower()]
                
                # Prefer xenosync-hive if it exists
                hive_session = next((s for s in all_xenosync_sessions if 'xenosync-hive' in s), None)
                if hive_session:
                    session_name = hive_session.split(':')[0]
                elif all_xenosync_sessions:
                    # Fall back to any xenosync session
                    session_name = all_xenosync_sessions[0].split(':')[0]
                else:
                    session_name = None
                
                if session_name:
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