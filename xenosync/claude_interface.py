"""
Module: claude_interface
Purpose: Asynchronous wrapper for Claude CLI interactions

This module provides an interface to interact with Claude through the command-line
interface. It supports both direct process management and tmux-based sessions,
enabling multiple Claude instances to run in parallel with proper isolation.

Key Classes:
    - ClaudeInterface: Main interface for Claude CLI interaction

Key Functions:
    - start(): Initialize Claude session
    - send_message(): Send input to Claude
    - get_recent_output(): Retrieve Claude's output
    - _start_in_tmux_pane(): Start Claude in tmux pane
    - _start_direct_session(): Start Claude as subprocess

Dependencies:
    - asyncio: Asynchronous subprocess management
    - tmux: Terminal multiplexer (optional)
    - pathlib: Path operations
    - subprocess: Process execution

Usage:
    interface = ClaudeInterface(config)
    interface.working_directory = '/path/to/project'
    await interface.start(session_id, agent_uid)
    await interface.send_message("Hello Claude")
    
Author: Xenosync Team
Created: 2024-08-14
Modified: 2024-08-14
"""

import asyncio
import logging
import subprocess
from typing import Optional, List
from pathlib import Path

from .config import Config
from .exceptions import ClaudeError


logger = logging.getLogger(__name__)


class ClaudeInterface:
    """Interface for interacting with Claude CLI"""
    
    def __init__(self, config: Config):
        self.config = config
        self.process: Optional[asyncio.subprocess.Process] = None
        self.session_id: Optional[str] = None
        self.agent_uid: Optional[str] = None
        self.output_buffer = []
        self.max_buffer_size = 10000
        
        # Tmux integration if enabled
        self.use_tmux = config.use_tmux
        self.tmux_session = None
        
        # Tmux pane mode for multi-agent
        self.tmux_pane_mode = False
        self.tmux_shared_session = None
        self.tmux_pane_id = None
        
        # Working directory for git worktree support
        self.working_directory: Optional[str] = None
    
    def set_tmux_pane_mode(self, session_name: str, pane_id: int):
        """Configure to use a specific tmux pane in a shared session"""
        self.tmux_pane_mode = True
        self.tmux_shared_session = session_name
        self.tmux_pane_id = pane_id
    
    async def start(self, session_id: str, agent_uid: Optional[str] = None):
        """Start Claude CLI session"""
        self.session_id = session_id
        self.agent_uid = agent_uid
        
        # Set up coordination environment if multi-agent
        if agent_uid:
            await self._setup_coordination_environment()
        
        if self.tmux_pane_mode:
            # Use existing tmux pane in shared session
            await self._start_in_tmux_pane()
        elif self.use_tmux:
            # Create separate tmux session
            await self._start_tmux_session()
        else:
            # Start directly without tmux
            await self._start_direct_session()
        
        # Wait for Claude to initialize
        await asyncio.sleep(self.config.get('initial_wait', 3))
        
        logger.info(f"Claude session started for {session_id}")
    
    async def _setup_coordination_environment(self):
        """Set up environment and files for agent coordination"""
        try:
            # Create session file for coordination
            session_file = Path.cwd() / ".xenosync_session"
            session_file.write_text(self.session_id)
            
            # Create coordination directory
            coord_dir = Path.cwd() / ".xenosync_coordination"
            coord_dir.mkdir(exist_ok=True)
            
            # Write agent info file
            agent_info = {
                "agent_uid": self.agent_uid,
                "session_id": self.session_id,
                "started_at": str(asyncio.get_event_loop().time())
            }
            
            import json
            agent_file = coord_dir / f"agent_{self.agent_uid}.json"
            agent_file.write_text(json.dumps(agent_info))
            
            logger.debug(f"Set up coordination environment for {self.agent_uid}")
            
        except Exception as e:
            logger.warning(f"Failed to set up coordination environment: {e}")
    
    async def _start_in_tmux_pane(self):
        """Start Claude in a specific tmux pane (multi-agent mode)"""
        # Target pane in shared session
        target_pane = f"{self.tmux_shared_session}:agents.{self.tmux_pane_id}"
        
        # Change to working directory first if specified
        if self.working_directory:
            # Validate directory exists
            if Path(self.working_directory).exists():
                cd_cmd = f"cd '{self.working_directory}'"
                await self._run_command([
                    'tmux', 'send-keys', '-t', target_pane,
                    cd_cmd, 'Enter'
                ])
                # Small delay to ensure cd completes
                await asyncio.sleep(0.5)
                logger.debug(f"Changed to working directory: {self.working_directory}")
            else:
                logger.warning(f"Working directory does not exist: {self.working_directory}")
        
        # Set environment variables for coordination in the tmux session itself
        if self.agent_uid:
            # Set environment variables at session level first
            session_env_cmds = [
                ['tmux', 'set-environment', '-t', self.tmux_shared_session, 
                 'XENOSYNC_SESSION_ID', self.session_id],
                ['tmux', 'set-environment', '-t', self.tmux_shared_session,
                 'XENOSYNC_AGENT_UID', self.agent_uid]
            ]
            
            for env_cmd in session_env_cmds:
                await self._run_command(env_cmd)
            
            # Also export in the pane shell environment
            pane_env_cmds = [
                f"export XENOSYNC_SESSION_ID='{self.session_id}'",
                f"export XENOSYNC_AGENT_UID='{self.agent_uid}'",
                f"export XENOSYNC_PROJECT_ROOT='{Path(__file__).parent.parent}'",
                "echo 'Coordination environment set up for agent'"
            ]
            
            # Add working directory to environment if set
            if self.working_directory:
                pane_env_cmds.insert(2, f"export XENOSYNC_WORKTREE_PATH='{self.working_directory}'")
            
            for env_cmd in pane_env_cmds:
                await self._run_command([
                    'tmux', 'send-keys', '-t', target_pane, 
                    env_cmd, 'Enter'
                ])
            
            # Small delay to ensure environment is set
            await asyncio.sleep(1)
        
        # Start Claude in the pane
        claude_cmd = ' '.join(self.config.claude_command)
        
        # Send command to the specific pane
        send_cmd = [
            'tmux', 'send-keys', '-t', target_pane,
            claude_cmd, 'Enter'
        ]
        await self._run_command(send_cmd)
        
        # Store pane reference for later use
        self.tmux_session = self.tmux_shared_session
        self.tmux_window = f"agents.{self.tmux_pane_id}"
        
        logger.info(f"Started Claude in pane {self.tmux_pane_id} of session {self.tmux_shared_session}")
    
    async def _start_tmux_session(self):
        """Start Claude in a tmux session"""
        # For multi-agent, session_id includes agent suffix, use full ID for uniqueness
        # Truncate if too long for tmux session name (max ~80 chars)
        if '_agent_' in self.session_id:
            # Multi-agent mode: use shortened base + agent number
            parts = self.session_id.split('_agent_')
            short_base = parts[0][:8]
            agent_num = parts[1] if len(parts) > 1 else '0'
            self.tmux_session = f"xsync-{short_base}-a{agent_num}"
        else:
            # Single agent mode: use first 8 chars
            short_id = self.session_id[:8]
            self.tmux_session = f"xsync-{short_id}"
        
        # Create tmux session
        create_cmd = [
            'tmux', 'new-session', '-d', '-s', self.tmux_session,
            '-n', 'Orchestrator'
        ]
        await self._run_command(create_cmd)
        
        # Create Claude window
        new_window_cmd = [
            'tmux', 'new-window', '-t', self.tmux_session,
            '-n', 'Claude'
        ]
        await self._run_command(new_window_cmd)
        
        # Change to working directory if specified
        if self.working_directory:
            # Validate directory exists
            if Path(self.working_directory).exists():
                cd_cmd = f"cd '{self.working_directory}'"
                await self._run_command([
                    'tmux', 'send-keys', '-t', f"{self.tmux_session}:Claude",
                    cd_cmd, 'Enter'
                ])
                # Small delay to ensure cd completes
                await asyncio.sleep(0.5)
                logger.debug(f"Changed to working directory: {self.working_directory}")
            else:
                logger.warning(f"Working directory does not exist: {self.working_directory}")
        
        # Start Claude in the window
        claude_cmd = ' '.join(self.config.claude_command)
        send_cmd = [
            'tmux', 'send-keys', '-t', f"{self.tmux_session}:Claude",
            claude_cmd, 'Enter'
        ]
        await self._run_command(send_cmd)
    
    async def _start_direct_session(self):
        """Start Claude process directly"""
        cmd = self.config.claude_command
        
        # Set working directory if specified
        cwd = self.working_directory if self.working_directory else None
        
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )
        
        # Start output monitoring
        asyncio.create_task(self._monitor_output())
    
    async def _monitor_output(self):
        """Monitor Claude output (for direct mode)"""
        if not self.process:
            return
        
        while True:
            try:
                line = await self.process.stdout.readline()
                if not line:
                    break
                
                decoded_line = line.decode('utf-8', errors='ignore')
                self.output_buffer.append(decoded_line)
                
                # Maintain buffer size
                if len(self.output_buffer) > self.max_buffer_size:
                    self.output_buffer = self.output_buffer[-self.max_buffer_size:]
                
            except Exception as e:
                logger.error(f"Error monitoring output: {e}")
                break
    
    async def send_message(self, message: str):
        """Send a message to Claude"""
        if self.use_tmux:
            await self._send_tmux_message(message)
        else:
            await self._send_direct_message(message)
    
    async def _send_tmux_message(self, message: str):
        """Send message via tmux"""
        # Escape special characters
        escaped_message = message.replace('"', '\\"').replace('\n', ' ')
        
        # Determine target based on mode
        if self.tmux_pane_mode:
            target = f"{self.tmux_session}:{self.tmux_window}"
        else:
            target = f"{self.tmux_session}:{self.tmux_window}"
        
        send_cmd = [
            'tmux', 'send-keys', '-t', target,
            f'"{escaped_message}"'
        ]
        await self._run_command(send_cmd)
        
        # Wait for UI
        await asyncio.sleep(0.5)
        
        # Send Enter
        enter_cmd = [
            'tmux', 'send-keys', '-t', target,
            'Enter'
        ]
        await self._run_command(enter_cmd)
    
    async def _send_direct_message(self, message: str):
        """Send message directly to process"""
        if not self.process or not self.process.stdin:
            raise ClaudeError("Claude process not running")
        
        self.process.stdin.write(f"{message}\n".encode())
        await self.process.stdin.drain()
    
    async def get_recent_output(self, lines: int = 50, offset: int = 0) -> str:
        """Get recent output from Claude"""
        if self.use_tmux:
            return await self._get_tmux_output(lines, offset)
        else:
            return await self._get_direct_output(lines, offset)
    
    async def _get_tmux_output(self, lines: int, offset: int) -> str:
        """Get output from tmux pane"""
        # Determine target based on mode
        if self.tmux_pane_mode:
            target = f"{self.tmux_session}:{self.tmux_window}"
        else:
            target = f"{self.tmux_session}:{self.tmux_window}"
        
        cmd = [
            'tmux', 'capture-pane', '-t', target,
            '-p', '-S', f"-{lines + offset}", '-E', f"-{offset}"
        ]
        
        result = await self._run_command(cmd, capture_output=True)
        return result.stdout.decode('utf-8', errors='ignore')
    
    async def _get_direct_output(self, lines: int, offset: int) -> str:
        """Get output from buffer"""
        start_idx = max(0, len(self.output_buffer) - lines - offset)
        end_idx = len(self.output_buffer) - offset if offset > 0 else len(self.output_buffer)
        
        return ''.join(self.output_buffer[start_idx:end_idx])
    
    async def is_running(self) -> bool:
        """Check if Claude is still running"""
        if self.use_tmux:
            return await self._check_tmux_running()
        else:
            return self.process is not None and self.process.returncode is None
    
    async def _check_tmux_running(self) -> bool:
        """Check if tmux session exists"""
        cmd = ['tmux', 'has-session', '-t', self.tmux_session]
        try:
            await self._run_command(cmd)
            return True
        except subprocess.CalledProcessError:
            return False
    
    async def stop(self):
        """Stop Claude session"""
        if self.tmux_pane_mode:
            # In pane mode, just send exit command but don't kill the pane
            # The tmux session is managed by TmuxManager
            target = f"{self.tmux_session}:{self.tmux_window}"
            try:
                # Send Ctrl+C to stop current command
                cmd = ['tmux', 'send-keys', '-t', target, 'C-c']
                await self._run_command(cmd)
                await asyncio.sleep(0.5)
                # Send exit command
                cmd = ['tmux', 'send-keys', '-t', target, 'exit', 'Enter']
                await self._run_command(cmd)
            except subprocess.CalledProcessError:
                pass  # Pane might already be gone
        elif self.use_tmux and self.tmux_session:
            # Kill tmux session (single agent mode)
            cmd = ['tmux', 'kill-session', '-t', self.tmux_session]
            try:
                await self._run_command(cmd)
            except subprocess.CalledProcessError:
                pass  # Session might already be gone
        elif self.process:
            # Terminate process
            self.process.terminate()
            await self.process.wait()
        
        logger.info("Claude session stopped")
    
    async def _run_command(self, cmd: List[str], capture_output: bool = False):
        """Run a shell command"""
        if capture_output:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(
                    proc.returncode, cmd, output=stdout, stderr=stderr
                )
            
            return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
        else:
            proc = await asyncio.create_subprocess_exec(*cmd)
            await proc.wait()
            
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, cmd)