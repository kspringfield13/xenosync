"""
Tmux Manager - Visual management of multiple agent sessions
Ported and enhanced from Multi-Claude
"""

import subprocess
import time
import logging
import tempfile
import uuid
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from .exceptions import TmuxError


logger = logging.getLogger(__name__)


class TmuxManager:
    """Manage tmux sessions for visual agent monitoring"""
    
    def __init__(self, session_name: str = "xenosync_collective"):
        self.session = session_name
        self.pane_mapping: Dict[int, str] = {}
        self.window_mapping: Dict[str, int] = {
            'orchestrator': 0,
            'agents': 1,
            'monitor': 2
        }
        self._initialized = False
    
    def is_tmux_available(self) -> bool:
        """Check if tmux is installed and available"""
        try:
            result = subprocess.run(['tmux', '-V'], capture_output=True, text=True)
            return result.returncode == 0
        except FileNotFoundError:
            return False
    
    def session_exists(self) -> bool:
        """Check if tmux session already exists"""
        result = subprocess.run(
            f"tmux has-session -t {self.session}",
            shell=True, capture_output=True
        )
        return result.returncode == 0
    
    def create_session(self, num_agents: int, layout: str = "tiled") -> bool:
        """Create tmux session with specified number of agent panes"""
        if not self.is_tmux_available():
            logger.warning("tmux is not available, visual mode disabled")
            return False
        
        # Kill existing session if it exists
        if self.session_exists():
            logger.info(f"Killing existing tmux session: {self.session}")
            self.kill_session()
            time.sleep(0.5)
        
        try:
            # Create new session with orchestrator window
            result = subprocess.run(
                f"tmux new-session -d -s {self.session} -n orchestrator",
                shell=True, capture_output=True
            )
            if result.returncode != 0:
                raise TmuxError(f"Failed to create tmux session: {result.stderr.decode()}")
            
            # Create agents window
            subprocess.run(
                f"tmux new-window -t {self.session}:1 -n agents",
                shell=True, capture_output=True
            )
            
            # Create monitor window
            subprocess.run(
                f"tmux new-window -t {self.session}:2 -n monitor",
                shell=True, capture_output=True
            )
            
            # Create agent panes in the agents window
            for i in range(1, num_agents):
                subprocess.run(
                    f"tmux split-window -t {self.session}:agents",
                    shell=True, capture_output=True
                )
                # Apply layout after each split for better distribution
                subprocess.run(
                    f"tmux select-layout -t {self.session}:agents {layout}",
                    shell=True, capture_output=True
                )
            
            # Configure tmux display
            self._configure_display(num_agents)
            
            # Get pane IDs for agent window
            result = subprocess.run(
                f"tmux list-panes -t {self.session}:agents -F '#{{pane_index}}'",
                shell=True, capture_output=True, text=True
            )
            
            pane_ids = sorted([pid.strip() for pid in result.stdout.strip().split('\n')])
            
            # Create pane mapping
            for i, pane_id in enumerate(pane_ids[:num_agents]):
                self.pane_mapping[i] = f"{self.session}:agents.{pane_id}"
            
            self._initialized = True
            logger.info(f"Created tmux session '{self.session}' with {num_agents} agent panes")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create tmux session: {e}")
            return False
    
    def _configure_display(self, num_agents: int):
        """Configure tmux for optimal display"""
        commands = [
            # Enable aggressive resize for better space usage
            f"tmux set-option -t {self.session} -g aggressive-resize on",
            
            # Enable mouse support
            f"tmux set-option -t {self.session} -g mouse on",
            
            # Configure pane borders
            f"tmux set-option -t {self.session} -g pane-border-style 'fg=colour240'",
            f"tmux set-option -t {self.session} -g pane-active-border-style 'fg=colour250'",
            
            # Enable pane titles
            f"tmux set-option -t {self.session} -g pane-border-status top",
            
            # Status bar configuration
            f"tmux set-option -t {self.session} -g status-style 'bg=colour235,fg=colour250'",
            f"tmux set-option -t {self.session} -g status-left '[Builder] '",
            f"tmux set-option -t {self.session} -g status-right 'Agents: {num_agents} | %H:%M'",
            
            # Window title format
            f"tmux set-option -t {self.session} -g window-status-format ' #I:#W '",
            f"tmux set-option -t {self.session} -g window-status-current-format ' #I:#W* '",
        ]
        
        for cmd in commands:
            subprocess.run(cmd, shell=True, capture_output=True)
    
    def send_to_pane(self, agent_id: int, command: str, enter: bool = True):
        """Send command to specific agent pane"""
        pane = self.pane_mapping.get(agent_id)
        if not pane:
            logger.warning(f"No pane mapping for agent {agent_id}")
            return
        
        try:
            # Handle multi-line commands
            if '\n' in command and enter:
                self._send_multiline(pane, command)
            else:
                self._send_simple(pane, command, enter)
                
        except Exception as e:
            logger.error(f"Failed to send to pane {agent_id}: {e}")
    
    def _send_simple(self, pane: str, command: str, enter: bool):
        """Send simple single-line command"""
        # Escape single quotes
        escaped_cmd = command.replace("'", "'\"'\"'")
        
        subprocess.run(
            f"tmux send-keys -t {pane} '{escaped_cmd}'",
            shell=True, capture_output=True
        )
        
        if enter:
            subprocess.run(
                f"tmux send-keys -t {pane} C-m",
                shell=True, capture_output=True
            )
    
    def _send_multiline(self, pane: str, command: str):
        """Send multi-line command using buffer method"""
        # Create temporary file for complex input
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            f.write(command)
            temp_path = f.name
        
        # Use unique buffer name
        buf_name = f"xenosync_{uuid.uuid4().hex[:8]}"
        
        try:
            # Load into tmux buffer
            result = subprocess.run(
                f"tmux load-buffer -b {buf_name} {temp_path}",
                shell=True, capture_output=True
            )
            
            if result.returncode == 0:
                # Paste buffer
                subprocess.run(
                    f"tmux paste-buffer -d -b {buf_name} -t {pane}",
                    shell=True, capture_output=True
                )
                time.sleep(0.2)  # Small delay for Claude Code
            else:
                # Fallback to line-by-line
                for line in command.split('\n'):
                    if line:
                        self._send_simple(pane, line, True)
            
            # Send final Enter
            subprocess.run(
                f"tmux send-keys -t {pane} C-m",
                shell=True, capture_output=True
            )
            
        finally:
            # Clean up temp file
            try:
                Path(temp_path).unlink()
            except:
                pass
    
    def send_to_orchestrator(self, message: str):
        """Send message to orchestrator window"""
        target = f"{self.session}:orchestrator"
        
        # Clear and send message
        subprocess.run(
            f"tmux send-keys -t {target} C-c",  # Clear any existing input
            shell=True, capture_output=True
        )
        time.sleep(0.1)
        
        subprocess.run(
            f"tmux send-keys -t {target} 'clear' C-m",
            shell=True, capture_output=True
        )
        
        # Send the message
        escaped_msg = message.replace("'", "'\"'\"'")
        subprocess.run(
            f"tmux send-keys -t {target} 'echo \"{escaped_msg}\"' C-m",
            shell=True, capture_output=True
        )
    
    def capture_pane(self, agent_id: int, lines: int = 50) -> str:
        """Capture recent output from agent pane"""
        pane = self.pane_mapping.get(agent_id)
        if not pane:
            return ""
        
        result = subprocess.run(
            f"tmux capture-pane -t {pane} -p -S -{lines}",
            shell=True, capture_output=True, text=True
        )
        return result.stdout
    
    def capture_all_panes(self, lines: int = 20) -> Dict[int, str]:
        """Capture output from all agent panes"""
        outputs = {}
        for agent_id in self.pane_mapping:
            outputs[agent_id] = self.capture_pane(agent_id, lines)
        return outputs
    
    def set_pane_title(self, agent_id: int, title: str):
        """Set title for specific agent pane"""
        pane = self.pane_mapping.get(agent_id)
        if not pane:
            return
        
        # Escape special characters in title
        safe_title = title.replace("'", "").replace('"', '')[:30]  # Limit length
        
        subprocess.run(
            f"tmux select-pane -t {pane} -T '{safe_title}'",
            shell=True, capture_output=True
        )
    
    def set_window_title(self, window: str, title: str):
        """Set title for a window"""
        window_id = self.window_mapping.get(window)
        if window_id is None:
            return
        
        subprocess.run(
            f"tmux rename-window -t {self.session}:{window_id} '{title}'",
            shell=True, capture_output=True
        )
    
    def highlight_pane(self, agent_id: int, color: str = "red"):
        """Highlight a specific pane border"""
        pane = self.pane_mapping.get(agent_id)
        if not pane:
            return
        
        color_map = {
            'red': 'colour196',
            'green': 'colour46',
            'yellow': 'colour226',
            'blue': 'colour33'
        }
        
        tmux_color = color_map.get(color, 'colour250')
        
        subprocess.run(
            f"tmux select-pane -t {pane} -P 'fg={tmux_color}'",
            shell=True, capture_output=True
        )
    
    def reset_pane_highlight(self, agent_id: int):
        """Reset pane border to default"""
        pane = self.pane_mapping.get(agent_id)
        if not pane:
            return
        
        subprocess.run(
            f"tmux select-pane -t {pane} -P 'fg=default'",
            shell=True, capture_output=True
        )
    
    def attach_session(self):
        """Attach to the tmux session"""
        if not self.session_exists():
            logger.error(f"Session {self.session} does not exist")
            return
        
        subprocess.run(f"tmux attach-session -t {self.session}", shell=True)
    
    def switch_to_window(self, window: str):
        """Switch to specific window in tmux session"""
        window_id = self.window_mapping.get(window)
        if window_id is None:
            return
        
        subprocess.run(
            f"tmux select-window -t {self.session}:{window_id}",
            shell=True, capture_output=True
        )
    
    def kill_session(self):
        """Kill the tmux session"""
        if self.session_exists():
            subprocess.run(
                f"tmux kill-session -t {self.session}",
                shell=True, capture_output=True
            )
            logger.info(f"Killed tmux session '{self.session}'")
    
    def get_session_info(self) -> Dict[str, Any]:
        """Get information about the tmux session"""
        if not self.session_exists():
            return {'exists': False}
        
        # Get session details
        result = subprocess.run(
            f"tmux list-sessions -F '#{{session_name}}:#{{session_windows}}:#{{session_attached}}' | grep '^{self.session}:'",
            shell=True, capture_output=True, text=True
        )
        
        if result.returncode != 0:
            return {'exists': False}
        
        parts = result.stdout.strip().split(':')
        
        return {
            'exists': True,
            'name': parts[0] if len(parts) > 0 else self.session,
            'windows': int(parts[1]) if len(parts) > 1 else 0,
            'attached': parts[2] == '1' if len(parts) > 2 else False,
            'num_agents': len(self.pane_mapping)
        }
    
    def create_dashboard_layout(self, num_agents: int):
        """Create an optimized dashboard layout for monitoring"""
        if num_agents <= 2:
            layout = "even-horizontal"
        elif num_agents <= 4:
            layout = "tiled"
        elif num_agents <= 6:
            layout = "main-horizontal"
        else:
            layout = "tiled"
        
        subprocess.run(
            f"tmux select-layout -t {self.session}:agents {layout}",
            shell=True, capture_output=True
        )
        
        # Adjust pane sizes for better visibility
        if num_agents > 4:
            # Make panes more uniform
            subprocess.run(
                f"tmux select-layout -t {self.session}:agents -E",
                shell=True, capture_output=True
            )