"""
Module: agent_manager
Purpose: Manages multiple Claude agent instances for parallel task execution

This module handles the lifecycle of multiple Claude agents, including initialization,
task assignment, status monitoring, error recovery, and shutdown. It provides the
core agent pool management functionality for multi-agent coordination.

Key Classes:
    - AgentManager: Main manager for agent pool
    - Agent: Individual agent instance tracking
    - AgentStatus: Agent state enumeration

Key Functions:
    - initialize_agents(): Create and start agent instances
    - send_to_agent(): Send messages to specific agents
    - check_agent_working(): Detect if agent is actively working
    - handle_error_recovery(): Recover from agent failures
    - _monitor_agents(): Continuous agent monitoring loop

Dependencies:
    - claude_interface: Claude CLI wrapper
    - config: Configuration management
    - asyncio: Asynchronous operations
    - datetime: Timestamp tracking

Usage:
    manager = AgentManager(config, num_agents=4)
    await manager.initialize_agents(session_id)
    await manager.send_to_agent(agent_id, message)
    
Author: Xenosync Team
Created: 2024-08-14
Modified: 2024-08-14
"""

import asyncio
import logging
import re
import os
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .config import Config
from .claude_interface import ClaudeInterface
from .exceptions import AgentError


logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Simplified agent status states"""
    STARTING = "starting"  # Agent is being initialized
    WORKING = "working"    # Agent is actively processing (detected by "...ing..." pattern)
    COMPLETED = "completed" # Agent has completed all assigned tasks
    ERROR = "error"        # Agent has encountered an error that needs recovery
    STOPPED = "stopped"    # Agent has been shut down


@dataclass
class Agent:
    """Simplified agent instance"""
    id: int
    uid: str
    session_id: str
    status: AgentStatus = AgentStatus.STARTING
    start_time: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    last_message_sent: Optional[datetime] = None
    error: Optional[str] = None
    recovery_attempts: int = 0
    # Task timing fields
    current_task_start_time: Optional[datetime] = None
    current_task_number: Optional[int] = None
    last_completion_check: Optional[datetime] = None
    # Git worktree fields
    worktree_path: Optional[str] = None
    worktree_branch: Optional[str] = None
    current_task_branch: Optional[str] = None
    
    # Enhanced completion detection fields
    last_verification_time: Optional[datetime] = None
    last_verification_score: float = 0.5
    completion_confidence_history: list = field(default_factory=list)
    last_file_activity_check: Optional[datetime] = None
    completion_signals_log: list = field(default_factory=list)
    
    @property
    def is_available(self) -> bool:
        """Check if agent is available for work (not in error, stopped, or completed state)"""
        return self.status not in [AgentStatus.ERROR, AgentStatus.STOPPED, AgentStatus.COMPLETED]
    
    @property
    def uptime(self) -> float:
        """Get agent uptime in seconds"""
        return (datetime.now() - self.start_time).total_seconds()
    
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.now()
    
    def time_since_message(self) -> Optional[float]:
        """Get seconds since last message was sent to this agent"""
        if not self.last_message_sent:
            return None
        return (datetime.now() - self.last_message_sent).total_seconds()
    
    def start_task(self, task_number: int):
        """Mark the start of a new task"""
        self.current_task_number = task_number
        self.current_task_start_time = datetime.now()
        self.last_completion_check = None
        logger.debug(f"Agent {self.id} started task {task_number} at {self.current_task_start_time}")
    
    def can_check_for_completion(self, min_duration_seconds: int = 180) -> bool:
        """Check if enough time has passed to check for task completion"""
        if not self.current_task_start_time:
            return False
        
        elapsed = (datetime.now() - self.current_task_start_time).total_seconds()
        return elapsed >= min_duration_seconds
    
    def time_since_last_check(self) -> float:
        """Get seconds since last completion check"""
        if not self.last_completion_check:
            return float('inf')
        return (datetime.now() - self.last_completion_check).total_seconds()
    
    def get_task_elapsed_time(self) -> float:
        """Get seconds since current task started"""
        if not self.current_task_start_time:
            return 0.0
        return (datetime.now() - self.current_task_start_time).total_seconds()


class AgentManager:
    """Simplified manager for multiple Claude agent instances"""
    
    def __init__(self, config: Config, num_agents: int = 2):
        self.config = config
        self.num_agents = max(2, num_agents)  # Minimum 2 agents
        self.agents: List[Agent] = []
        self.interfaces: Dict[int, ClaudeInterface] = {}
        self._monitoring_task: Optional[asyncio.Task] = None
        self._shutdown = False
        self._next_agent_idx = 0  # For round-robin distribution
        self.tmux_manager = None  # Will be set if tmux is available
        self.coordination = None  # Will be set by orchestrator
        self.strategy = None  # Will be set by orchestrator for task callbacks
        self._agent_work_tracking = {}  # Track previous status for work completion
        
        # Task timing configuration
        self.task_minimum_duration = config.get('task_minimum_duration', 300)  # 5 minutes default
        self.task_completion_check_interval = config.get('task_completion_check_interval', 180)  # 3 minutes default
        logger.info(f"Task timing: min {self.task_minimum_duration}s, check interval {self.task_completion_check_interval}s")
        
        # Flag to stop monitoring regular agents when finalization starts
        self.stop_regular_monitoring = False
    
    def set_tmux_manager(self, tmux_manager):
        """Set the tmux manager for visual monitoring"""
        self.tmux_manager = tmux_manager
    
    def set_coordination_manager(self, coordination):
        """Set the coordination manager for work tracking"""
        self.coordination = coordination
    
    def set_strategy(self, strategy):
        """Set the execution strategy for task callbacks"""
        self.strategy = strategy
    
    async def initialize_agents(self, session_id: str) -> List[Agent]:
        """Initialize all agent instances"""
        logger.info(f"Initializing {self.num_agents} agents for session {session_id}")
        
        for i in range(self.num_agents):
            agent = await self._create_agent(i, session_id)
            self.agents.append(agent)
            
            # Stagger agent launches
            if i < self.num_agents - 1:
                launch_delay = self.config.get('agent_launch_delay', 3)
                await asyncio.sleep(launch_delay)
        
        # Start monitoring
        self._monitoring_task = asyncio.create_task(self._monitor_agents())
        
        logger.info(f"All {self.num_agents} agents initialized")
        return self.agents
    
    async def _create_agent(self, agent_id: int, session_id: str) -> Agent:
        """Create and start a single agent"""
        # Generate unique ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        uid = f"agent_{agent_id}_{timestamp}_{session_id[:8]}"
        
        agent = Agent(
            id=agent_id,
            uid=uid,
            session_id=session_id
        )
        
        # Create project workspace for this agent
        if self.coordination and hasattr(self.coordination, 'create_agent_workspace'):
            try:
                from pathlib import Path
                workspace_path, project_path = self.coordination.create_agent_workspace(
                    agent_id, uid, session_id
                )
                agent.worktree_path = str(project_path)  # For compatibility
                agent.worktree_branch = None  # No branch in project mode
                logger.info(f"Created project workspace for agent {agent_id} at {project_path}")
            except Exception as e:
                logger.error(f"Failed to create project workspace for agent {agent_id}: {e}")
                # Continue without workspace for backward compatibility
        
        # Create Claude interface
        interface = ClaudeInterface(self.config)
        self.interfaces[agent_id] = interface
        
        # Set working directory to project folder
        if agent.worktree_path:  # Using worktree_path for compatibility
            interface.working_directory = agent.worktree_path
            logger.info(f"Agent {agent_id} will work in project directory: {agent.worktree_path}")
        
        # If tmux manager is available, tell the interface to use a specific pane
        if self.tmux_manager:
            interface.set_tmux_pane_mode(self.tmux_manager.session, agent_id)
        
        # Set environment variables for coordination
        os.environ['XENOSYNC_SESSION_ID'] = session_id
        os.environ['XENOSYNC_AGENT_UID'] = uid
        if agent.worktree_path:
            os.environ['XENOSYNC_PROJECT_PATH'] = agent.worktree_path
            # No branch in project mode
        
        # Start Claude session
        try:
            await interface.start(f"{session_id}_agent_{agent_id}", agent_uid=uid)
            agent.status = AgentStatus.WORKING  # Assume working initially
            agent.update_activity()
            logger.info(f"Agent {agent_id} ({uid}) started successfully")
        except Exception as e:
            agent.status = AgentStatus.ERROR
            agent.error = str(e)
            logger.error(f"Failed to start agent {agent_id}: {e}")
            raise AgentError(f"Failed to start agent {agent_id}: {e}")
        
        return agent
    
    def get_agent_by_id(self, agent_id: int) -> Optional[Agent]:
        """Get specific agent by ID"""
        for agent in self.agents:
            if agent.id == agent_id:
                return agent
        return None
    
    def get_available_agent(self) -> Optional[Agent]:
        """Get next available agent using round-robin"""
        available = [a for a in self.agents if a.is_available]
        if not available:
            return None
        
        # Round-robin selection
        agent = available[self._next_agent_idx % len(available)]
        self._next_agent_idx += 1
        return agent
    
    async def send_to_agent(self, agent_id: int, message: str) -> bool:
        """Send message to specific agent"""
        agent = self.get_agent_by_id(agent_id)
        if not agent:
            logger.error(f"Agent {agent_id} not found")
            return False
        
        interface = self.interfaces.get(agent_id)
        if not interface:
            logger.error(f"No interface for agent {agent_id}")
            return False
        
        try:
            # Add agent identifier to message for tracking
            tagged_message = f"{message}\n\n[Agent ID: {agent.uid}]"
            await interface.send_message(tagged_message)
            
            agent.status = AgentStatus.WORKING
            agent.last_message_sent = datetime.now()
            agent.update_activity()
            
            logger.info(f"Sent message to agent {agent_id} ({len(message)} chars)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send message to agent {agent_id}: {e}")
            agent.status = AgentStatus.ERROR
            agent.error = str(e)
            return False
    
    async def broadcast_to_all(self, message: str):
        """Send message to all available agents"""
        tasks = []
        for agent in self.agents:
            if agent.is_available:
                tasks.append(self.send_to_agent(agent.id, message))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successful = sum(1 for r in results if r is True)
        logger.info(f"Broadcast sent to {successful}/{len(tasks)} agents")
    
    async def get_agent_output(self, agent_id: int, lines: int = 10) -> Optional[str]:
        """Get recent output from specific agent"""
        interface = self.interfaces.get(agent_id)
        if not interface:
            return None
        
        try:
            return await interface.get_recent_output(lines)
        except Exception as e:
            logger.error(f"Failed to get output from agent {agent_id}: {e}")
            return None
    
    async def is_agent_running(self, agent_id: int) -> bool:
        """Check if agent process is still running"""
        interface = self.interfaces.get(agent_id)
        if not interface:
            return False
        
        try:
            return await interface.is_running()
        except Exception as e:
            logger.error(f"Failed to check if agent {agent_id} is running: {e}")
            return False
    
    async def check_agent_working(self, agent_id: int) -> bool:
        """Check if agent is actively working using enhanced pattern detection"""
        agent = self.get_agent_by_id(agent_id)
        if not agent:
            return False
        
        # Get more lines of output for better pattern detection
        output = await self.get_agent_output(agent_id, lines=20)
        if not output:
            # If no output available, use grace period as fallback
            if agent.time_since_message():
                time_since = agent.time_since_message()
                grace_period = self.config.get('message_grace_period', 30)
                if time_since < grace_period:
                    logger.debug(f"Agent {agent_id} in grace period ({time_since:.1f}s < {grace_period}s)")
                    return True
            return False
        
        lines = output.strip().split('\n')
        # Check last 10 non-empty lines for patterns
        recent_lines = [line.strip() for line in lines if line.strip()][-10:]
        
        # First check for completion patterns (takes precedence)
        completion_result = self._check_completion_patterns(recent_lines)
        if completion_result['has_completion_patterns']:
            logger.debug(f"Agent {agent_id} completion patterns found, marking as not working")
            return False
        
        # Then check for working patterns
        working_result = self._check_working_patterns(recent_lines)
        if working_result['has_working_patterns']:
            logger.debug(f"Agent {agent_id} working pattern found: '{working_result['matched_line']}'")
            return True
        
        # Grace period as final fallback only if no patterns found
        if agent.time_since_message():
            time_since = agent.time_since_message()
            grace_period = self.config.get('message_grace_period', 30)
            if time_since < grace_period:
                logger.debug(f"Agent {agent_id} in grace period ({time_since:.1f}s < {grace_period}s), no patterns found")
                return True
        
        logger.debug(f"Agent {agent_id} shows no working patterns in recent output")
        return False
    
    def _check_working_patterns(self, lines: list) -> Dict[str, Any]:
        """Check for working patterns in output lines"""
        working_patterns = [
            r'\w+ing\.\.\.+',  # Standard *ing... patterns (Thinking..., Processing...)
            r'(thinking|processing|analyzing|creating|writing|building|implementing|working|compiling|testing|debugging|planning|designing|coding|executing)[^\w]*\.\.\.+',
            r'(in progress|working on|currently|please wait)',
            r'(step \d+|task \d+|phase \d+)',  # Step/task indicators
            r'\.\.\.+$',  # Lines ending with ...
        ]
        
        for line in lines:
            for pattern in working_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    return {
                        'has_working_patterns': True,
                        'matched_line': line,
                        'matched_pattern': pattern
                    }
        
        return {'has_working_patterns': False, 'matched_line': '', 'matched_pattern': ''}
    
    def _check_completion_patterns(self, lines: list) -> Dict[str, Any]:
        """Check for completion patterns in output lines"""
        # Get completion patterns from config
        completion_patterns = self.config.get('semantic_completion_patterns', [
            r'(task|work|implementation|project)\s+(completed|finished|done)',
            r'(i have|i\'ve)\s+(completed|finished|done)',
            r'(ready for|completed|finished).*review',
            r'\bCOMPLETED\b',  # Direct response to verification
            r'(all|everything)\s+(is\s+)?(done|finished|completed)',
            r'(finished|completed|done)\s+(working|implementing|building)',
        ])
        
        for line in lines:
            for pattern in completion_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    return {
                        'has_completion_patterns': True,
                        'matched_line': line,
                        'matched_pattern': pattern
                    }
        
        return {'has_completion_patterns': False, 'matched_line': '', 'matched_pattern': ''}
    
    async def calculate_completion_confidence(self, agent_id: int) -> Dict[str, Any]:
        """
        Calculate weighted confidence score for agent completion using multiple signals
        
        Returns:
            Dict with:
            - overall_confidence: float (0-1)
            - completion_likely: bool
            - signal_scores: Dict with individual signal scores
            - signal_details: Dict with detailed information from each signal
        """
        agent = self.get_agent_by_id(agent_id)
        if not agent:
            return {
                'overall_confidence': 0.0,
                'completion_likely': False,
                'signal_scores': {},
                'signal_details': {}
            }
        
        try:
            # Get configuration weights
            weights = {
                'pattern_detection': self.config.get('completion_weight_patterns', 0.25),
                'file_activity': self.config.get('completion_weight_file_activity', 0.25),
                'semantic_verification': self.config.get('completion_weight_verification', 0.35),
                'time_factors': self.config.get('completion_weight_time', 0.15)
            }
            
            signal_scores = {}
            signal_details = {}
            
            # Signal 1: Pattern Detection (enhanced check_agent_working)
            is_working = await self.check_agent_working(agent_id)
            pattern_score = 0.0 if is_working else 1.0  # If not working, likely completed
            
            signal_scores['pattern_detection'] = pattern_score
            signal_details['pattern_detection'] = {
                'is_working': is_working,
                'description': 'Based on working/completion patterns in agent output'
            }
            
            # Signal 2: File Activity
            file_activity = await self.check_file_activity(agent_id)
            file_score = 0.0 if file_activity['has_recent_activity'] else 1.0
            
            # Adjust file score based on how long since last activity
            minutes_since = file_activity['minutes_since_activity']
            timeout_minutes = self.config.get('file_activity_timeout', 10)
            
            if minutes_since != float('inf'):
                # Gradual increase in confidence as time passes without activity
                time_factor = min(1.0, minutes_since / timeout_minutes)
                file_score = time_factor
            
            signal_scores['file_activity'] = file_score
            signal_details['file_activity'] = {
                'has_recent_activity': file_activity['has_recent_activity'],
                'minutes_since_activity': minutes_since,
                'active_files': file_activity['active_files'],
                'description': f'No file changes for {minutes_since:.1f} minutes'
            }
            
            # Signal 3: Semantic Verification (if enabled and not recently done)
            verification_enabled = self.config.get('completion_verification_enabled', True)
            verification_interval = self.config.get('completion_verification_interval', 300)  # 5 minutes
            
            verification_score = 0.5  # Default neutral score
            verification_details = {'enabled': verification_enabled}
            
            if verification_enabled:
                # Check if verification was done recently
                last_verification = getattr(agent, 'last_verification_time', None)
                current_time = datetime.now()
                
                should_verify = (
                    last_verification is None or 
                    (current_time - last_verification).total_seconds() > verification_interval
                )
                
                if should_verify:
                    logger.debug(f"Running completion verification for agent {agent_id}")
                    verification_result = await self.verify_agent_completion(agent_id)
                    
                    if verification_result['verification_sent']:
                        verification_score = verification_result['confidence_score']
                        agent.last_verification_time = current_time  # Track when we last verified
                        
                        verification_details.update({
                            'verification_sent': True,
                            'completion_confirmed': verification_result['completion_confirmed'],
                            'confidence_score': verification_score,
                            'response_summary': verification_result['response_text'][:100] + '...' if len(verification_result['response_text']) > 100 else verification_result['response_text']
                        })
                    else:
                        verification_details.update({
                            'verification_sent': False,
                            'error': verification_result['response_text']
                        })
                else:
                    # Use previous verification result if recent
                    verification_score = getattr(agent, 'last_verification_score', 0.5)
                    time_since_verification = (current_time - last_verification).total_seconds() / 60
                    verification_details.update({
                        'verification_sent': False,
                        'reason': f'Recent verification {time_since_verification:.1f}m ago',
                        'last_score': verification_score
                    })
            
            signal_scores['semantic_verification'] = verification_score
            signal_details['semantic_verification'] = verification_details
            
            # Signal 4: Time Factors
            time_score = 0.5  # Default neutral
            
            # Consider how long agent has been working on current task
            if agent.current_task_start_time:
                task_duration_minutes = agent.get_task_elapsed_time() / 60
                minimum_duration = self.config.get('task_minimum_duration', 300) / 60  # Convert to minutes
                
                if task_duration_minutes > minimum_duration:
                    # Increase confidence over time (but cap at reasonable limit)
                    time_factor = min(1.0, (task_duration_minutes - minimum_duration) / minimum_duration)
                    time_score = 0.5 + (time_factor * 0.5)  # Range: 0.5 to 1.0
            
            signal_scores['time_factors'] = time_score
            signal_details['time_factors'] = {
                'task_duration_minutes': task_duration_minutes if agent.current_task_start_time else 0,
                'description': f'Task running for {task_duration_minutes:.1f} minutes' if agent.current_task_start_time else 'No active task timing'
            }
            
            # Calculate weighted overall confidence
            overall_confidence = (
                signal_scores['pattern_detection'] * weights['pattern_detection'] +
                signal_scores['file_activity'] * weights['file_activity'] +
                signal_scores['semantic_verification'] * weights['semantic_verification'] +
                signal_scores['time_factors'] * weights['time_factors']
            )
            
            # Determine if completion is likely
            confidence_threshold = self.config.get('completion_confidence_threshold', 0.7)
            completion_likely = overall_confidence >= confidence_threshold
            
            logger.debug(f"Agent {agent_id} completion confidence: {overall_confidence:.3f} "
                        f"(pattern: {signal_scores['pattern_detection']:.2f}, "
                        f"file: {signal_scores['file_activity']:.2f}, "
                        f"verification: {signal_scores['semantic_verification']:.2f}, "
                        f"time: {signal_scores['time_factors']:.2f}) -> "
                        f"{'COMPLETED' if completion_likely else 'WORKING'}")
            
            return {
                'overall_confidence': overall_confidence,
                'completion_likely': completion_likely,
                'signal_scores': signal_scores,
                'signal_details': signal_details,
                'weights_used': weights,
                'threshold': confidence_threshold
            }
            
        except Exception as e:
            logger.error(f"Error calculating completion confidence for agent {agent_id}: {e}")
            return {
                'overall_confidence': 0.0,
                'completion_likely': False,
                'signal_scores': {},
                'signal_details': {'error': str(e)}
            }
    
    async def has_error_pattern(self, agent_id: int) -> bool:
        """Check if agent output contains error patterns"""
        output = await self.get_agent_output(agent_id, lines=20)
        if not output:
            return False
        
        error_patterns = [
            "api error",
            "rate limit",
            "too many requests",
            "failed to respond",
            "connection error",
            "timeout",
            "service unavailable"
        ]
        
        output_lower = output.lower()
        return any(pattern in output_lower for pattern in error_patterns)
    
    async def check_file_activity(self, agent_id: int) -> Dict[str, Any]:
        """
        Check file activity in agent's project directory
        
        Returns:
            Dict with activity information:
            - has_recent_activity: bool
            - last_activity_time: datetime or None
            - minutes_since_activity: float
            - active_files: int (files modified in last period)
        """
        agent = self.get_agent_by_id(agent_id)
        if not agent or not agent.worktree_path:
            return {
                'has_recent_activity': False,
                'last_activity_time': None,
                'minutes_since_activity': float('inf'),
                'active_files': 0
            }
        
        try:
            from pathlib import Path
            import time
            
            project_path = Path(agent.worktree_path)
            if not project_path.exists():
                return {
                    'has_recent_activity': False,
                    'last_activity_time': None,
                    'minutes_since_activity': float('inf'),
                    'active_files': 0
                }
            
            # Configuration
            activity_window_minutes = self.config.get('file_activity_window', 15)  # 15 minutes default
            activity_timeout_minutes = self.config.get('file_activity_timeout', 10)  # 10 minutes default
            
            current_time = time.time()
            activity_window_seconds = activity_window_minutes * 60
            activity_timeout_seconds = activity_timeout_minutes * 60
            
            last_activity_time = None
            active_files_count = 0
            
            # Check all files in project directory (excluding .git)
            for file_path in project_path.rglob('*'):
                if file_path.is_file() and '.git' not in str(file_path):
                    try:
                        mtime = file_path.stat().st_mtime
                        
                        # Count files modified in activity window
                        if current_time - mtime <= activity_window_seconds:
                            active_files_count += 1
                        
                        # Track most recent modification
                        if last_activity_time is None or mtime > last_activity_time:
                            last_activity_time = mtime
                            
                    except (OSError, IOError):
                        continue  # Skip files we can't access
            
            # Calculate time since last activity
            if last_activity_time:
                minutes_since_activity = (current_time - last_activity_time) / 60
                has_recent_activity = minutes_since_activity <= activity_timeout_minutes
                activity_datetime = datetime.fromtimestamp(last_activity_time)
            else:
                minutes_since_activity = float('inf')
                has_recent_activity = False
                activity_datetime = None
            
            logger.debug(f"Agent {agent_id} file activity: {active_files_count} active files, "
                        f"{minutes_since_activity:.1f}m since last change")
            
            return {
                'has_recent_activity': has_recent_activity,
                'last_activity_time': activity_datetime,
                'minutes_since_activity': minutes_since_activity,
                'active_files': active_files_count
            }
            
        except Exception as e:
            logger.error(f"Error checking file activity for agent {agent_id}: {e}")
            return {
                'has_recent_activity': False,
                'last_activity_time': None,
                'minutes_since_activity': float('inf'),
                'active_files': 0
            }
    
    async def verify_agent_completion(self, agent_id: int) -> Dict[str, Any]:
        """
        Send verification message to agent and parse response for completion confirmation
        
        Returns:
            Dict with verification results:
            - verification_sent: bool
            - completion_confirmed: bool  
            - confidence_score: float (0-1)
            - response_text: str
        """
        agent = self.get_agent_by_id(agent_id)
        if not agent:
            return {
                'verification_sent': False,
                'completion_confirmed': False,
                'confidence_score': 0.0,
                'response_text': ''
            }
        
        try:
            # Get verification message from config
            verification_message = self.config.get(
                'completion_verification_message',
                "Please confirm if you have completed your assigned tasks. "
                "Respond with 'COMPLETED' if finished, or describe what you're still working on."
            )
            
            # Send verification message
            success = await self.send_to_agent(agent_id, verification_message)
            if not success:
                return {
                    'verification_sent': False,
                    'completion_confirmed': False,
                    'confidence_score': 0.0,
                    'response_text': 'Failed to send verification message'
                }
            
            # Wait for response
            response_wait_time = self.config.get('verification_response_wait', 30)  # 30 seconds
            await asyncio.sleep(response_wait_time)
            
            # Get recent output to parse response
            response_lines = self.config.get('verification_response_lines', 15)
            output = await self.get_agent_output(agent_id, lines=response_lines)
            
            if not output:
                return {
                    'verification_sent': True,
                    'completion_confirmed': False,
                    'confidence_score': 0.0,
                    'response_text': 'No response received'
                }
            
            # Parse response for completion indicators
            completion_result = self._parse_completion_response(output)
            
            logger.debug(f"Agent {agent_id} verification result: "
                        f"confirmed={completion_result['completion_confirmed']}, "
                        f"confidence={completion_result['confidence_score']:.2f}")
            
            return {
                'verification_sent': True,
                'completion_confirmed': completion_result['completion_confirmed'],
                'confidence_score': completion_result['confidence_score'],
                'response_text': output[-500:] if len(output) > 500 else output  # Last 500 chars
            }
            
        except Exception as e:
            logger.error(f"Error during agent {agent_id} completion verification: {e}")
            return {
                'verification_sent': False,
                'completion_confirmed': False,
                'confidence_score': 0.0,
                'response_text': f'Verification error: {str(e)}'
            }
    
    def _parse_completion_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse agent response for completion indicators
        
        Returns:
            Dict with:
            - completion_confirmed: bool
            - confidence_score: float (0-1)
        """
        if not response_text:
            return {'completion_confirmed': False, 'confidence_score': 0.0}
        
        response_lower = response_text.lower()
        confidence_score = 0.0
        completion_confirmed = False
        
        # Get completion patterns from config
        completion_patterns = self.config.get('semantic_completion_patterns', [
            r'(task|work|implementation|project)\s+(completed|finished|done)',
            r'(i have|i\'ve)\s+(completed|finished|done)',
            r'(ready for|completed|finished).*review',
            r'\bCOMPLETED\b',  # Direct response to verification
            r'(all|everything)\s+(is\s+)?(done|finished|completed)',
            r'(finished|completed|done)\s+(working|implementing|building)',
        ])
        
        # Check for explicit completion patterns
        for pattern in completion_patterns:
            matches = re.findall(pattern, response_lower, re.IGNORECASE)
            if matches:
                confidence_score += 0.3  # Each pattern adds confidence
                completion_confirmed = True
                logger.debug(f"Completion pattern matched: {pattern} -> {matches}")
        
        # Check for negative indicators (still working)
        working_indicators = [
            r'(still|currently|now)\s+(working|implementing|building)',
            r'(in progress|working on|not.*done|not.*finished)',
            r'(need to|have to|going to)\s+(finish|complete|implement)',
            r'(almost|nearly|close to)\s+(done|finished|completed)',
        ]
        
        for pattern in working_indicators:
            if re.search(pattern, response_lower, re.IGNORECASE):
                confidence_score -= 0.4  # Negative indicators reduce confidence
                completion_confirmed = False
                logger.debug(f"Working indicator found: {pattern}")
        
        # Direct completion confirmations get highest confidence
        direct_confirmations = ['completed', 'finished', 'done', 'ready']
        for confirmation in direct_confirmations:
            if f" {confirmation}" in response_lower or response_lower.startswith(confirmation):
                confidence_score += 0.4
                completion_confirmed = True
        
        # Normalize confidence score
        confidence_score = max(0.0, min(1.0, confidence_score))
        
        return {
            'completion_confirmed': completion_confirmed,
            'confidence_score': confidence_score
        }
    
    async def handle_error_recovery(self, agent_id: int) -> bool:
        """Handle error detection and recovery with exponential backoff"""
        agent = self.get_agent_by_id(agent_id)
        if not agent:
            return False
        
        agent.recovery_attempts += 1
        
        # Exponential backoff: 5s, 10s, 20s, 40s
        wait_times = [5, 10, 20, 40]
        
        if agent.recovery_attempts > 3:
            # After 3 attempts, mark as ERROR
            logger.error(f"Agent {agent_id} failed all recovery attempts")
            agent.status = AgentStatus.ERROR
            agent.error = f"Failed to recover after {agent.recovery_attempts} attempts"
            return False
        
        # Wait with exponential backoff
        wait_time = wait_times[min(agent.recovery_attempts - 1, len(wait_times) - 1)]
        logger.info(f"Recovery attempt {agent.recovery_attempts} for agent {agent_id}, waiting {wait_time}s")
        await asyncio.sleep(wait_time)
        
        # Send recovery message
        recovery_message = "Please continue with your assigned tasks. If you encountered an error, try again."
        success = await self.send_to_agent(agent_id, recovery_message)
        
        if success:
            # Wait a bit and check if agent recovered
            await asyncio.sleep(5)
            if await self.check_agent_working(agent_id):
                logger.info(f"Agent {agent_id} recovered successfully")
                agent.recovery_attempts = 0
                agent.status = AgentStatus.WORKING
                return True
        
        return False
    
    async def _monitor_agents(self):
        """Simplified monitoring loop with task completion tracking"""
        while not self._shutdown:
            try:
                for agent in self.agents:
                    if agent.status == AgentStatus.STOPPED:
                        continue
                    
                    # Skip monitoring regular agents if finalization has started
                    # Only monitor the finalization agent (highest ID)
                    if self.stop_regular_monitoring:
                        # Get the highest agent ID (finalization agent)
                        max_agent_id = max(a.id for a in self.agents) if self.agents else -1
                        # Skip all agents except the finalization agent
                        if agent.id < max_agent_id:
                            continue
                    
                    # Track previous status for transition detection
                    previous_status = self._agent_work_tracking.get(agent.id)
                    
                    # Check if process is still running
                    if not await self.is_agent_running(agent.id):
                        agent.status = AgentStatus.STOPPED
                        logger.warning(f"Agent {agent.id} process stopped")
                        continue
                    
                    # Handle agents that are currently working
                    if agent.status == AgentStatus.WORKING:
                        # Check if minimum task duration has passed
                        if agent.can_check_for_completion(self.task_minimum_duration):
                            # Check if enough time has passed since last check
                            if agent.time_since_last_check() >= self.task_completion_check_interval:
                                agent.last_completion_check = datetime.now()
                                
                                # Log timing info
                                elapsed = agent.get_task_elapsed_time()
                                logger.debug(f"Checking agent {agent.id} completion after {elapsed:.1f}s (task {agent.current_task_number})")
                                
                                # Use enhanced completion detection with multiple signals
                                logger.debug(f"Running enhanced completion detection for agent {agent.id}")
                                completion_analysis = await self.calculate_completion_confidence(agent.id)
                                
                                # Log confidence details
                                confidence = completion_analysis['overall_confidence']
                                completion_likely = completion_analysis['completion_likely']
                                
                                logger.info(f"Agent {agent.id} completion analysis: "
                                          f"confidence={confidence:.3f}, "
                                          f"likely_complete={completion_likely}")
                                
                                # Store confidence history
                                agent.completion_confidence_history.append({
                                    'timestamp': datetime.now(),
                                    'confidence': confidence,
                                    'completion_likely': completion_likely,
                                    'signal_scores': completion_analysis['signal_scores']
                                })
                                
                                # Keep only last 10 entries
                                if len(agent.completion_confidence_history) > 10:
                                    agent.completion_confidence_history = agent.completion_confidence_history[-10:]
                                
                                if not completion_likely:
                                    # Agent is still working
                                    logger.info(f"Agent {agent.id} still working on task {agent.current_task_number} "
                                              f"after {elapsed:.1f}s (confidence: {confidence:.3f})")
                                    continue
                                
                                # Check for errors before marking complete
                                if await self.has_error_pattern(agent.id):
                                    logger.warning(f"Agent {agent.id} has error pattern, attempting recovery")
                                    await self.handle_error_recovery(agent.id)
                                else:
                                    # Task completed with high confidence
                                    logger.info(f"Agent {agent.id} completed task {agent.current_task_number} "
                                              f"after {elapsed:.1f}s (confidence: {confidence:.3f})")
                                    
                                    # Process task completion
                                    if self.coordination:
                                        session_id = agent.session_id
                                        
                                        # Mark agent project as complete if using project coordination
                                        if hasattr(self.coordination, 'complete_agent_project'):
                                            try:
                                                self.coordination.complete_agent_project(agent.id)
                                                agent.status = AgentStatus.COMPLETED  # Mark agent as completed
                                                logger.info(f"Agent {agent.id} project marked as complete and agent status set to COMPLETED")
                                            except Exception as e:
                                                logger.error(f"Failed to mark agent {agent.id} project complete: {e}")
                                        
                                        logger.info(f"Agent {agent.id} completed task {agent.current_task_number}")
                                        
                                        # Clear current task info
                                        agent.current_task_number = None
                                        agent.current_task_start_time = None
                                        
                                        # Trigger next task delivery if strategy is available
                                        if self.strategy and hasattr(self.strategy, 'send_next_task_to_agent'):
                                            logger.info(f"Requesting next task for agent {agent.id}")
                                            try:
                                                # Send next task from the agent's queue
                                                next_task_sent = await self.strategy.send_next_task_to_agent(
                                                    agent.id, session_id
                                                )
                                                if next_task_sent:
                                                    logger.info(f"Next task sent to agent {agent.id}")
                                                    # Agent is now working on the next task
                                                    agent.status = AgentStatus.WORKING
                                                else:
                                                    logger.info(f"No more tasks for agent {agent.id}")
                                            except Exception as e:
                                                logger.error(f"Error sending next task to agent {agent.id}: {e}")
                        else:
                            # Task still in minimum duration period
                            if agent.current_task_start_time:
                                elapsed = agent.get_task_elapsed_time()
                                if elapsed > 0 and int(elapsed) % 60 == 0:  # Log every minute during minimum period
                                    remaining = self.task_minimum_duration - elapsed
                                    logger.info(f"Agent {agent.id} working on task {agent.current_task_number} for {elapsed:.0f}s (minimum period: {remaining:.0f}s remaining)")
                    
                    # Handle agents that are not working (initial status check)
                    else:
                        # Check if agent has started working
                        is_working = await self.check_agent_working(agent.id)
                        
                        if is_working:
                            if agent.status != AgentStatus.WORKING:
                                logger.info(f"Agent {agent.id} started working")
                                agent.status = AgentStatus.WORKING
                                agent.last_activity = datetime.now()
                                agent.recovery_attempts = 0
                    
                    # Update tracking
                    self._agent_work_tracking[agent.id] = agent.status
                
            except Exception as e:
                logger.error(f"Error in agent monitoring: {e}")
            
            await asyncio.sleep(10)  # Check every 10 seconds
    
    async def _detect_modified_files(self, agent_id: int) -> List[str]:
        """Try to detect modified files from agent output"""
        files = []
        try:
            output = await self.get_agent_output(agent_id, lines=50)
            if output:
                # Look for common file modification patterns
                import re
                # Match patterns like "Modified: filename.py" or "Writing to filename.py"
                patterns = [
                    r'(?:Modified|Writing to|Created|Updated|Saved)[:.]?\s+([^\s]+\.[a-zA-Z]+)',
                    r'File\s+([^\s]+\.[a-zA-Z]+)\s+(?:modified|created|updated)',
                ]
                for pattern in patterns:
                    matches = re.findall(pattern, output, re.IGNORECASE)
                    files.extend(matches)
        except Exception as e:
            logger.debug(f"Could not detect modified files for agent {agent_id}: {e}")
        
        return list(set(files))  # Return unique files
    
    async def distribute_steps(self, steps: List[str]) -> Dict[int, List[int]]:
        """Distribute steps across agents using round-robin"""
        assignments = {}
        available_agents = [a for a in self.agents if a.is_available]
        
        if not available_agents:
            logger.error("No available agents for step distribution")
            return assignments
        
        # Round-robin distribution
        for i, step in enumerate(steps):
            agent = available_agents[i % len(available_agents)]
            if agent.id not in assignments:
                assignments[agent.id] = []
            assignments[agent.id].append(i)
        
        logger.info(f"Distributed {len(steps)} steps across {len(available_agents)} agents")
        return assignments
    
    async def wait_for_agents(self, timeout: Optional[int] = None) -> bool:
        """Wait for all agents to finish working"""
        import time
        start_time = time.time()
        
        while True:
            # Check if any agents are still working
            working_agents = [a for a in self.agents if a.status == AgentStatus.WORKING]
            
            if not working_agents:
                logger.info("All agents finished working")
                return True
            
            # Check timeout
            if timeout and (time.time() - start_time) > timeout:
                logger.warning(f"Timeout waiting for agents after {timeout}s")
                return False
            
            await asyncio.sleep(5)
    
    async def shutdown(self, force_exit=False):
        """Shutdown all agents"""
        logger.info(f"Shutting down agent manager (force_exit={force_exit})")
        self._shutdown = True
        
        # Cancel monitoring
        if self._monitoring_task:
            self._monitoring_task.cancel()
        
        if force_exit:
            # Stop all agents
            for agent_id, interface in self.interfaces.items():
                try:
                    await interface.send_message("/exit")
                    await asyncio.sleep(1)
                    await interface.stop()
                    
                    agent = self.get_agent_by_id(agent_id)
                    if agent:
                        agent.status = AgentStatus.STOPPED
                        
                except Exception as e:
                    logger.error(f"Error stopping agent {agent_id}: {e}")
            
            logger.info("All agents shut down")
        else:
            # Just update status without stopping
            for agent in self.agents:
                if agent.status != AgentStatus.ERROR:
                    agent.status = AgentStatus.STOPPED
            
            logger.info("Agent manager shutdown (agents still running in tmux)")
    
    def get_agent_metrics(self) -> Dict[str, Any]:
        """Get simplified metrics for all agents"""
        status_counts = {}
        for agent in self.agents:
            status = agent.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            'agents': [
                {
                    'id': agent.id,
                    'uid': agent.uid,
                    'status': agent.status.value,
                    'uptime': agent.uptime,
                    'error': agent.error
                }
                for agent in self.agents
            ],
            'summary': {
                'total_agents': len(self.agents),
                'status_breakdown': status_counts,
                'available_agents': len([a for a in self.agents if a.is_available])
            }
        }

    async def spawn_finalization_agent(self, session_id: str, work_dir: str, prompt: str) -> Optional[int]:
        """Spawn a special finalization agent for post-merge optimization"""
        try:
            # Create finalization agent with special ID (using next available ID)
            agent_id = len(self.agents)  # Use next ID after regular agents
            
            # Generate unique ID for finalization agent
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            uid = f"finalizer_{timestamp}_{session_id[:8]}"
            
            agent = Agent(
                id=agent_id,
                uid=uid,
                session_id=session_id,
                status=AgentStatus.STARTING
            )
            
            # Set the working directory to the final-project folder
            agent.worktree_path = str(work_dir)
            
            # Add to agents list
            self.agents.append(agent)
            
            # Stop monitoring regular agents now that finalization is starting
            self.stop_regular_monitoring = True
            logger.info("Stopping regular agent monitoring - finalization phase started")
            
            # Create Claude interface for finalization agent
            interface = ClaudeInterface(self.config)
            self.interfaces[agent_id] = interface
            
            # Set the working directory for the interface
            interface.working_directory = work_dir
            
            # Set up tmux pane for finalization agent
            if self.tmux_manager:
                # Create new pane for finalization agent first
                pane_created = self.tmux_manager.add_new_pane(agent_id)
                if not pane_created:
                    logger.warning(f"Failed to create tmux pane for finalization agent {agent_id}, falling back to direct mode")
                    # Fallback to direct mode if tmux pane creation fails
                    interface.use_tmux = False
                else:
                    # Successfully created pane, set tmux pane mode
                    interface.set_tmux_pane_mode(self.tmux_manager.session, agent_id)
                    logger.info(f"Finalization agent will use newly created tmux pane {agent_id}")
            else:
                # No tmux manager available, use direct mode
                logger.info("No tmux manager available, finalization agent will run in direct mode")
                interface.use_tmux = False
            
            # If using direct mode, ensure claude command can be found
            if not interface.use_tmux:
                import shutil
                claude_cmd = self.config.get('claude_command', 'claude')
                if isinstance(claude_cmd, list):
                    claude_cmd = claude_cmd[0]
                
                claude_path = shutil.which(claude_cmd)
                if not claude_path:
                    logger.error(f"Claude command '{claude_cmd}' not found in PATH for finalization agent")
                    return None
                else:
                    logger.info(f"Using claude command at: {claude_path}")
            
            # Start Claude in the final-project directory
            await interface.start(session_id, uid)
            
            # Send the finalization prompt
            await interface.send_message(prompt)
            agent.last_message_sent = datetime.now()
            agent.status = AgentStatus.WORKING
            
            logger.info(f"Spawned finalization agent {uid} (ID: {agent_id}) in {work_dir}")
            
            return agent_id
            
        except Exception as e:
            logger.error(f"Failed to spawn finalization agent: {e}")
            return None
    
    async def stop_finalization_agent(self, agent_id: int):
        """Stop the finalization agent"""
        try:
            agent = self.get_agent_by_id(agent_id)
            if not agent:
                logger.warning(f"Finalization agent {agent_id} not found")
                return
            
            # Stop the Claude interface
            if agent_id in self.interfaces:
                interface = self.interfaces[agent_id]
                await interface.stop()
                del self.interfaces[agent_id]
            
            # Update agent status
            agent.status = AgentStatus.STOPPED
            logger.info(f"Stopped finalization agent {agent.uid}")
            
        except Exception as e:
            logger.error(f"Error stopping finalization agent: {e}")
    
    # Compatibility methods for existing code
    @property
    def pool(self):
        """Compatibility property for existing code that references self.pool"""
        class PoolCompat:
            def __init__(self, manager):
                self.manager = manager
            
            @property
            def agents(self):
                return self.manager.agents
            
            def get_agent_by_id(self, agent_id: int):
                return self.manager.get_agent_by_id(agent_id)
            
            def get_available_agent(self):
                return self.manager.get_available_agent()
        
        return PoolCompat(self)