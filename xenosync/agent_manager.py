"""
Agent Manager - Simplified management of multiple Claude instances for parallel execution
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
    
    @property
    def is_available(self) -> bool:
        """Check if agent is available for work (not in error or stopped state)"""
        return self.status not in [AgentStatus.ERROR, AgentStatus.STOPPED]
    
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
        
        # Create worktree for this agent if using git coordination
        if self.coordination and hasattr(self.coordination, 'create_agent_worktree'):
            try:
                from pathlib import Path
                worktree_path, branch_name = self.coordination.create_agent_worktree(
                    agent_id, uid, session_id
                )
                agent.worktree_path = str(worktree_path)
                agent.worktree_branch = branch_name
                logger.info(f"Created worktree for agent {agent_id} at {worktree_path}")
            except Exception as e:
                logger.error(f"Failed to create worktree for agent {agent_id}: {e}")
                # Continue without worktree for backward compatibility
        
        # Create Claude interface
        interface = ClaudeInterface(self.config)
        self.interfaces[agent_id] = interface
        
        # Set working directory if worktree exists
        if agent.worktree_path:
            interface.working_directory = agent.worktree_path
            logger.info(f"Agent {agent_id} will work in {agent.worktree_path}")
        
        # If tmux manager is available, tell the interface to use a specific pane
        if self.tmux_manager:
            interface.set_tmux_pane_mode(self.tmux_manager.session, agent_id)
        
        # Set environment variables for coordination
        os.environ['XENOSYNC_SESSION_ID'] = session_id
        os.environ['XENOSYNC_AGENT_UID'] = uid
        if agent.worktree_path:
            os.environ['XENOSYNC_WORKTREE_PATH'] = agent.worktree_path
            os.environ['XENOSYNC_WORKTREE_BRANCH'] = agent.worktree_branch
        
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
        
        # Enhanced working patterns
        working_patterns = [
            r'\w+ing\.\.\.+',  # Standard *ing... patterns (Thinking..., Processing...)
            r'(thinking|processing|analyzing|creating|writing|building|implementing|working|compiling|testing|debugging|planning|designing|coding|executing)[^\w]*\.\.\.+',
            r'(in progress|working on|currently|please wait)',
            r'(step \d+|task \d+|phase \d+)',  # Step/task indicators
            r'\.\.\.+$',  # Lines ending with ...
        ]
        
        lines = output.strip().split('\n')
        # Check last 10 non-empty lines for working patterns
        recent_lines = [line.strip() for line in lines if line.strip()][-10:]
        
        for line in recent_lines:
            for pattern in working_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    logger.debug(f"Agent {agent_id} working pattern found: '{line}' (matched: {pattern})")
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
                                
                                # Check if agent is actually done using enhanced pattern detection
                                is_working = await self.check_agent_working(agent.id)
                                
                                if is_working:
                                    logger.info(f"Agent {agent.id} still working on task {agent.current_task_number} after {elapsed:.1f}s (patterns detected)")
                                elif not is_working:
                                    # Double-check with additional pattern verification
                                    logger.info(f"Agent {agent.id} appears idle, performing double-check for working patterns")
                                    
                                    # Get more recent output for thorough check
                                    output = await self.get_agent_output(agent.id, lines=30)
                                    still_working = False
                                    
                                    if output:
                                        # Look for any "*ing..." patterns in recent output
                                        recent_lines = output.split('\n')[-15:]  # Last 15 lines
                                        for line in recent_lines:
                                            if re.search(r'\w+ing\.\.\.+', line.strip(), re.IGNORECASE):
                                                logger.info(f"Agent {agent.id} still shows working patterns: '{line.strip()}'")
                                                still_working = True
                                                break
                                    
                                    if still_working:
                                        logger.info(f"Agent {agent.id} kept working due to detected patterns after {elapsed:.1f}s")
                                        continue  # Don't mark as complete, continue monitoring
                                    
                                    # Check for errors
                                    if await self.has_error_pattern(agent.id):
                                        logger.warning(f"Agent {agent.id} has error pattern, attempting recovery")
                                        await self.handle_error_recovery(agent.id)
                                    else:
                                        # Task actually completed
                                        logger.info(f"Agent {agent.id} confirmed completed task {agent.current_task_number} after {elapsed:.1f}s (no working patterns found)")
                                        
                                        # Process task completion
                                        if self.coordination:
                                            session_id = agent.session_id
                                            
                                            # Get all current work for this agent
                                            all_claims = self.coordination.get_all_claims(session_id)
                                            agent_claims = [c for c in all_claims 
                                                          if c.get('agent_uid') == agent.uid 
                                                          and c.get('status') == 'in_progress']
                                            
                                            if agent_claims:
                                                # Try to detect files modified from recent output
                                                files_modified = await self._detect_modified_files(agent.id)
                                                
                                                # Mark all agent's work as completed
                                                for claim in agent_claims:
                                                    # Complete the work claim
                                                    self.coordination.complete_work(
                                                        claim_id=claim['id'],
                                                        agent_uid=agent.uid,
                                                        session_id=session_id,
                                                        files_modified=files_modified,
                                                        success=True  # Assume success if no error pattern
                                                    )
                                                    
                                                    # Update task registry if task_number is in metadata
                                                    metadata = claim.get('metadata', {})
                                                    task_number = metadata.get('task_number')
                                                    if task_number:
                                                        self.coordination.update_task_status(
                                                            session_id=session_id,
                                                            task_number=task_number,
                                                            status='completed'
                                                        )
                                                    
                                                    logger.info(f"Agent {agent.id} completed: {claim.get('description', 'Unknown')[:50]}")
                                                
                                                logger.info(f"Agent {agent.id} completed {len(agent_claims)} task(s)")
                                                
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