"""
Agent Manager - Manages multiple Claude instances for parallel execution
"""

import asyncio
import logging
import re
import time
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .config import Config
from .claude_interface import ClaudeInterface
from .exceptions import AgentError


logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Agent status states"""
    STARTING = "starting"
    READY = "ready"
    WORKING = "working"
    IDLE = "idle"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class Agent:
    """Individual agent instance"""
    id: int
    uid: str  # Unique identifier for coordination
    session_id: str
    status: AgentStatus = AgentStatus.STARTING
    current_step: Optional[int] = None
    claimed_work: List[str] = field(default_factory=list)
    completed_steps: List[int] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    last_message_sent: Optional[datetime] = None
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_available(self) -> bool:
        """Check if agent is available for work"""
        return self.status in [AgentStatus.READY, AgentStatus.IDLE]
    
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


class AgentPool:
    """Pool of agents for load distribution"""
    
    def __init__(self, size: int = 1):
        self.size = size
        self.agents: List[Agent] = []
        self._next_agent_idx = 0
    
    def add_agent(self, agent: Agent):
        """Add agent to pool"""
        self.agents.append(agent)
    
    def get_available_agent(self) -> Optional[Agent]:
        """Get next available agent using round-robin"""
        available = [a for a in self.agents if a.is_available]
        if not available:
            return None
        
        # Round-robin selection
        agent = available[self._next_agent_idx % len(available)]
        self._next_agent_idx += 1
        return agent
    
    def get_agent_by_id(self, agent_id: int) -> Optional[Agent]:
        """Get specific agent by ID"""
        for agent in self.agents:
            if agent.id == agent_id:
                return agent
        return None
    
    def get_idle_agents(self, threshold_seconds: int = 60) -> List[Agent]:
        """Get agents that have been idle for threshold seconds"""
        now = datetime.now()
        idle_agents = []
        
        for agent in self.agents:
            if agent.status == AgentStatus.IDLE:
                idle_time = (now - agent.last_activity).total_seconds()
                if idle_time > threshold_seconds:
                    idle_agents.append(agent)
        
        return idle_agents
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get pool statistics"""
        status_counts = {}
        for agent in self.agents:
            status = agent.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        total_steps = sum(len(a.completed_steps) for a in self.agents)
        avg_uptime = sum(a.uptime for a in self.agents) / len(self.agents) if self.agents else 0
        
        return {
            'total_agents': len(self.agents),
            'status_breakdown': status_counts,
            'total_completed_steps': total_steps,
            'average_uptime_seconds': avg_uptime,
            'available_agents': len([a for a in self.agents if a.is_available])
        }


class AgentManager:
    """Manages multiple Claude agent instances"""
    
    def __init__(self, config: Config, num_agents: int = 1):
        self.config = config
        self.num_agents = num_agents
        self.pool = AgentPool(num_agents)
        self.interfaces: Dict[int, ClaudeInterface] = {}
        self._agent_tasks: Dict[int, asyncio.Task] = {}
        self._monitoring_task: Optional[asyncio.Task] = None
        self._shutdown = False
        self.tmux_manager = None  # Will be set if tmux is available
    
    def set_tmux_manager(self, tmux_manager):
        """Set the tmux manager for visual monitoring"""
        self.tmux_manager = tmux_manager
    
    async def initialize_agents(self, session_id: str) -> List[Agent]:
        """Initialize all agent instances"""
        logger.info(f"Initializing {self.num_agents} agents for session {session_id}")
        
        agents = []
        for i in range(self.num_agents):
            agent = await self._create_agent(i, session_id)
            agents.append(agent)
            self.pool.add_agent(agent)
            
            # Stagger agent launches
            if i < self.num_agents - 1:
                await asyncio.sleep(self.config.get('agent_launch_delay', 5))
        
        # Start monitoring
        self._monitoring_task = asyncio.create_task(self._monitor_agents())
        
        logger.info(f"All {self.num_agents} agents initialized")
        return agents
    
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
        
        # Create Claude interface
        interface = ClaudeInterface(self.config)
        self.interfaces[agent_id] = interface
        
        # If tmux manager is available, tell the interface to use a specific pane
        if self.tmux_manager:
            # Set the interface to use tmux pane mode
            interface.set_tmux_pane_mode(self.tmux_manager.session, agent_id)
        
        # Set environment variables for coordination
        import os
        os.environ['XENOSYNC_SESSION_ID'] = session_id
        os.environ['XENOSYNC_AGENT_UID'] = uid
        
        # Start Claude session with coordination info
        try:
            await interface.start(f"{session_id}_agent_{agent_id}", agent_uid=uid)
            agent.status = AgentStatus.READY
            agent.update_activity()
            logger.info(f"Agent {agent_id} ({uid}) started successfully")
        except Exception as e:
            agent.status = AgentStatus.ERROR
            agent.error = str(e)
            logger.error(f"Failed to start agent {agent_id}: {e}")
            raise AgentError(f"Failed to start agent {agent_id}: {e}")
        
        return agent
    
    async def send_to_agent(self, agent_id: int, message: str) -> bool:
        """Send message to specific agent"""
        agent = self.pool.get_agent_by_id(agent_id)
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
        """Send message to all agents"""
        tasks = []
        for agent in self.pool.agents:
            if agent.status != AgentStatus.ERROR:
                tasks.append(self.send_to_agent(agent.id, message))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successful = sum(1 for r in results if r is True)
        logger.info(f"Broadcast sent to {successful}/{len(tasks)} agents")
    
    async def get_agent_output(self, agent_id: int, lines: int = 50) -> Optional[str]:
        """Get recent output from specific agent"""
        interface = self.interfaces.get(agent_id)
        if not interface:
            return None
        
        try:
            return await interface.get_recent_output(lines)
        except Exception as e:
            logger.error(f"Failed to get output from agent {agent_id}: {e}")
            return None
    
    async def check_agent_working(self, agent_id: int) -> bool:
        """Check if agent is actively working based on Claude Code status indicators"""
        agent = self.pool.get_agent_by_id(agent_id)
        
        # First check timing - if we recently sent a message, likely still working
        if agent and agent.time_since_message():
            time_since = agent.time_since_message()
            grace_period = self.config.message_grace_period
            if time_since < grace_period:  # Grace period - assume working during this time
                logger.debug(f"Agent {agent_id} in grace period ({time_since:.1f}s since message, grace={grace_period}s)")
                return True
        
        output = await self.get_agent_output(agent_id, lines=30)  # Increased from 10 to 30
        if not output:
            return False
        
        # Log output for debugging (first and last few lines)
        output_lines = output.strip().split('\n')
        if len(output_lines) > 5:
            sample_output = f"First: '{output_lines[0]}' ... Last: '{output_lines[-1]}'"
        else:
            sample_output = f"'{output.strip()[:100]}...'"
        logger.debug(f"Agent {agent_id} output sample: {sample_output}")
        
        # Claude Code displays working status as random verbs ending in "ing..."
        # Examples: "Cooking...", "Booping...", "Considering...", "Transmuting..."
        # Often followed by timing info: "Cooking... (121s • 4.4k tokens • esc to interrupt)"
        
        # Pattern to match working indicators - broader pattern for any word ending in ing...
        working_pattern = re.compile(
            r'\b\w+ing\.\.\..*?(?:\([^)]*\))?\s*(?:esc to interrupt)?\s*$', 
            re.MULTILINE | re.IGNORECASE
        )
        
        # Also match the simple pattern without extra info
        simple_working_pattern = re.compile(r'\b\w+ing\.\.\.\s*$', re.MULTILINE | re.IGNORECASE)
        
        # Additional pattern for processing-type statuses that Claude Code might use
        processing_pattern = re.compile(r'\b(?:processing|analyzing|generating|building)\b.*\.\.\.', re.IGNORECASE)
        
        # Check for working patterns
        is_working = bool(
            working_pattern.search(output) or 
            simple_working_pattern.search(output) or 
            processing_pattern.search(output)
        )
        
        if is_working:
            if agent:
                # Extract the actual working status for logging
                match = (working_pattern.search(output) or 
                        simple_working_pattern.search(output) or 
                        processing_pattern.search(output))
                if match:
                    status_text = match.group().strip()
                    logger.debug(f"Agent {agent_id} is working: '{status_text}'")
                
                # Update agent status if not already working
                if agent.status != AgentStatus.WORKING:
                    agent.status = AgentStatus.WORKING
                    agent.update_activity()
                    logger.info(f"Agent {agent_id} detected as working: {status_text}")
        else:
            # Log when no working pattern is found (for debugging)
            logger.debug(f"Agent {agent_id} no working pattern found in output")
        
        return is_working
    
    async def check_agent_ready(self, agent_id: int) -> bool:
        """Check if agent is ready for input (only if not actively working)"""
        # First check if agent is actively working
        if await self.check_agent_working(agent_id):
            return False  # Agent is working, not ready for new input
        
        output = await self.get_agent_output(agent_id, lines=20)
        if not output:
            return False
        
        # Check for Claude ready indicators only if not working
        ready_indicators = [
            "ready",
            "completed",
            "finished",
            "done",
            ">",  # Claude prompt
        ]
        
        output_lower = output.lower()
        is_ready = any(indicator in output_lower for indicator in ready_indicators)
        
        # Additional check: make sure there's no working indicator present
        if is_ready:
            # Double-check there's no working pattern
            working_pattern = re.compile(r'\b\w+ing\.\.\.', re.IGNORECASE)
            if working_pattern.search(output):
                logger.debug(f"Agent {agent_id} shows ready indicators but still has working pattern")
                return False
        
        if is_ready:
            agent = self.pool.get_agent_by_id(agent_id)
            if agent and agent.status == AgentStatus.WORKING:
                agent.status = AgentStatus.IDLE
                agent.update_activity()
                logger.info(f"Agent {agent_id} became idle")
        
        return is_ready
    
    async def detect_api_error(self, agent_id: int) -> bool:
        """Detect if an agent has encountered an API error"""
        # First check if agent is actively working - if so, probably not an error
        if await self.check_agent_working(agent_id):
            return False
        
        output = await self.get_agent_output(agent_id, lines=30)
        if not output:
            return False
        
        error_patterns = [
            "api error",
            "error: api",
            "rate limit",
            "too many requests", 
            "failed to respond",
            "request failed",
            "connection error",
            "network error",
            "503 service",
            "429 too many",
            "timeout",
            "authentication failed",
            "quota exceeded",
            "service unavailable"
        ]
        
        output_lower = output.lower()
        
        # Check for error patterns
        has_error = any(pattern in output_lower for pattern in error_patterns)
        
        # Also check if agent has been stuck on same output
        agent = self.pool.get_agent_by_id(agent_id)
        if agent:
            if not hasattr(agent, 'last_output_hash'):
                agent.last_output_hash = hash(output)
                agent.stuck_count = 0
            else:
                current_hash = hash(output)
                if current_hash == agent.last_output_hash:
                    agent.stuck_count += 1
                    # Consider stuck after 3 checks (30 seconds)
                    if agent.stuck_count >= 3 and has_error:
                        logger.warning(f"Agent {agent_id} appears stuck with error pattern")
                        return True
                else:
                    agent.last_output_hash = current_hash
                    agent.stuck_count = 0
        
        return has_error and getattr(agent, 'stuck_count', 0) >= 2
    
    async def recover_from_error(self, agent_id: int) -> bool:
        """Attempt to recover an agent from an API error"""
        agent = self.pool.get_agent_by_id(agent_id)
        if not agent:
            return False
        
        # Initialize recovery tracking
        if not hasattr(agent, 'recovery_attempts'):
            agent.recovery_attempts = 0
        
        agent.recovery_attempts += 1
        
        # Progressive recovery strategies
        recovery_commands = [
            "--continue",
            "Please retry the last operation and continue with your work",
            "If you encountered an error, please try again with a different approach",
            "Continue with your assigned tasks, skipping any problematic operations", 
            "What is your current status? Please proceed with the next available task"
        ]
        
        if agent.recovery_attempts <= len(recovery_commands):
            command = recovery_commands[agent.recovery_attempts - 1]
            logger.info(f"Recovery attempt {agent.recovery_attempts} for agent {agent_id}: {command}")
            
            # Send recovery command
            success = await self.send_to_agent(agent_id, command)
            if not success:
                return False
            
            # Wait and check if recovery worked
            await asyncio.sleep(15)
            
            # Check if agent has new output (recovery working)
            new_output = await self.get_agent_output(agent_id, lines=10)
            if new_output:
                output_lower = new_output.lower()
                
                # First check if agent is showing working status (best indicator)
                is_working = await self.check_agent_working(agent_id)
                if is_working:
                    logger.info(f"Agent {agent_id} recovery successful - agent is actively working!")
                    agent.recovery_attempts = 0
                    agent.stuck_count = 0
                    agent.status = AgentStatus.WORKING
                    agent.update_activity()
                    return True
                
                # Look for other signs of recovery
                recovery_indicators = [
                    "continuing",
                    "proceeding", 
                    "working on",
                    "starting",
                    "let me",
                    ">",  # New prompt
                    "i'll",
                    "sure"
                ]
                
                has_recovery = any(indicator in output_lower for indicator in recovery_indicators)
                no_new_errors = not any(pattern in output_lower for pattern in [
                    "api error", "error:", "failed", "timeout"
                ])
                
                if has_recovery and no_new_errors:
                    logger.info(f"Agent {agent_id} recovery successful - showing recovery indicators")
                    agent.recovery_attempts = 0
                    agent.stuck_count = 0
                    agent.status = AgentStatus.WORKING
                    agent.update_activity()
                    return True
        
        if agent.recovery_attempts >= len(recovery_commands):
            logger.warning(f"Agent {agent_id} failed all recovery attempts, marking as ERROR")
            agent.status = AgentStatus.ERROR
            agent.error = f"Failed to recover from API error after {agent.recovery_attempts} attempts"
        
        return False
    
    async def force_recovery(self, agent_id: int) -> bool:
        """Manually force recovery attempt for an agent"""
        agent = self.pool.get_agent_by_id(agent_id)
        if not agent:
            logger.error(f"Agent {agent_id} not found for forced recovery")
            return False
        
        logger.info(f"Forcing recovery for agent {agent_id}")
        
        # Reset recovery attempts for fresh start
        if hasattr(agent, 'recovery_attempts'):
            agent.recovery_attempts = 0
        
        # Try recovery
        return await self.recover_from_error(agent_id)
    
    async def get_agent_status_report(self) -> Dict[str, Any]:
        """Get detailed status report including error information"""
        report = {
            'total_agents': len(self.pool.agents),
            'agents': [],
            'error_summary': {
                'agents_with_errors': 0,
                'recovery_attempts': 0,
                'successful_recoveries': 0
            }
        }
        
        for agent in self.pool.agents:
            agent_info = {
                'id': agent.id,
                'status': agent.status.value,
                'error': getattr(agent, 'error', None),
                'recovery_attempts': getattr(agent, 'recovery_attempts', 0),
                'stuck_count': getattr(agent, 'stuck_count', 0),
                'uptime': agent.uptime
            }
            
            report['agents'].append(agent_info)
            
            # Update error summary
            if agent.status == AgentStatus.ERROR:
                report['error_summary']['agents_with_errors'] += 1
            
            if hasattr(agent, 'recovery_attempts'):
                report['error_summary']['recovery_attempts'] += agent.recovery_attempts
                if agent.recovery_attempts > 0 and agent.status != AgentStatus.ERROR:
                    report['error_summary']['successful_recoveries'] += 1
        
        return report
    
    async def _monitor_agents(self):
        """Monitor agent health and status"""
        while not self._shutdown:
            try:
                for agent in self.pool.agents:
                    # Skip agents that are already stopped or in error state
                    if agent.status in [AgentStatus.STOPPED, AgentStatus.ERROR]:
                        continue
                    
                    # Check if agent is still running
                    interface = self.interfaces.get(agent.id)
                    if interface and not await interface.is_running():
                        if agent.status != AgentStatus.STOPPED:
                            logger.warning(f"Agent {agent.id} stopped unexpectedly")
                            agent.status = AgentStatus.STOPPED
                            agent.error = "Process terminated"
                        continue
                    
                    # Check for API errors and attempt recovery
                    if agent.status in [AgentStatus.WORKING, AgentStatus.IDLE]:
                        error_detected = await self.detect_api_error(agent.id)
                        if error_detected:
                            logger.warning(f"API error detected for agent {agent.id}, attempting recovery")
                            recovery_success = await self.recover_from_error(agent.id)
                            if recovery_success:
                                logger.info(f"Successfully recovered agent {agent.id}")
                            continue  # Skip other checks while recovering
                    
                    # Check agent working/idle status (only if not recovering from error)
                    if agent.status == AgentStatus.WORKING:
                        # Check if still working first
                        if not await self.check_agent_working(agent.id):
                            # Not actively working, check if ready/idle
                            if await self.check_agent_ready(agent.id):
                                # Status update happens in check_agent_ready() - no duplicate logging
                                pass
                    elif agent.status == AgentStatus.IDLE:
                        # Check if idle agent has started working again
                        if await self.check_agent_working(agent.id):
                            agent.status = AgentStatus.WORKING
                            logger.info(f"Agent {agent.id} started working again")
                
                # Log statistics periodically
                if int(time.time()) % 60 == 0:  # Every minute
                    stats = self.pool.get_statistics()
                    logger.debug(f"Agent pool stats: {stats}")
                    
                    # Log recovery statistics
                    recovery_stats = {}
                    for agent in self.pool.agents:
                        if hasattr(agent, 'recovery_attempts') and agent.recovery_attempts > 0:
                            recovery_stats[agent.id] = agent.recovery_attempts
                    
                    if recovery_stats:
                        logger.info(f"Recovery stats: {recovery_stats}")
                
            except Exception as e:
                logger.error(f"Error in agent monitoring: {e}")
            
            await asyncio.sleep(self.config.agent_monitor_interval)  # Check at configured interval
    
    async def assign_step_to_agent(self, step_content: str, 
                                  agent_id: Optional[int] = None) -> Optional[int]:
        """Assign a step to an available agent"""
        if agent_id is not None:
            # Assign to specific agent
            agent = self.pool.get_agent_by_id(agent_id)
        else:
            # Get next available agent
            agent = self.pool.get_available_agent()
        
        if not agent:
            logger.warning("No available agents for step assignment")
            return None
        
        # Send step to agent
        success = await self.send_to_agent(agent.id, step_content)
        if success:
            return agent.id
        
        return None
    
    async def distribute_steps(self, steps: List[str], 
                             strategy: str = "round-robin") -> Dict[int, List[int]]:
        """Distribute steps across agents using specified strategy"""
        assignments = {}
        
        if strategy == "round-robin":
            # Distribute evenly across available agents
            available_agents = [a for a in self.pool.agents if a.is_available]
            if not available_agents:
                logger.error("No available agents for step distribution")
                return assignments
            
            for i, step in enumerate(steps):
                agent = available_agents[i % len(available_agents)]
                if agent.id not in assignments:
                    assignments[agent.id] = []
                assignments[agent.id].append(i)
                
        elif strategy == "load-balanced":
            # Assign to least loaded agents
            for i, step in enumerate(steps):
                # Find agent with fewest completed steps
                agent = min(self.pool.agents, 
                          key=lambda a: len(a.completed_steps) if a.is_available else float('inf'))
                
                if agent.is_available:
                    if agent.id not in assignments:
                        assignments[agent.id] = []
                    assignments[agent.id].append(i)
        
        elif strategy == "broadcast":
            # Send all steps to all agents (collaborative mode)
            for agent in self.pool.agents:
                if agent.is_available:
                    assignments[agent.id] = list(range(len(steps)))
        
        logger.info(f"Distributed {len(steps)} steps using {strategy} strategy")
        return assignments
    
    async def wait_for_agents(self, timeout: Optional[int] = None) -> bool:
        """Wait for all agents to become idle"""
        start_time = time.time()
        
        while True:
            # Check if all agents are idle or stopped
            working_agents = [a for a in self.pool.agents 
                            if a.status == AgentStatus.WORKING]
            
            if not working_agents:
                logger.info("All agents are idle")
                return True
            
            # Check timeout
            if timeout and (time.time() - start_time) > timeout:
                logger.warning(f"Timeout waiting for agents after {timeout}s")
                return False
            
            # Update agent states
            for agent in working_agents:
                await self.check_agent_ready(agent.id)
            
            await asyncio.sleep(self.config.wait_check_interval)
    
    async def shutdown(self, force_exit=False):
        """Shutdown all agents gracefully
        
        Args:
            force_exit: If True, send exit command to agents. If False, keep them running.
        """
        logger.info(f"Shutting down agent manager (force_exit={force_exit})")
        self._shutdown = True
        
        # Cancel monitoring
        if self._monitoring_task:
            self._monitoring_task.cancel()
        
        if force_exit:
            # Stop all agents
            for agent_id, interface in self.interfaces.items():
                try:
                    # Send exit command
                    await interface.send_message("/exit")
                    await asyncio.sleep(1)
                    
                    # Stop interface
                    await interface.stop()
                    
                    # Update agent status
                    agent = self.pool.get_agent_by_id(agent_id)
                    if agent:
                        agent.status = AgentStatus.STOPPED
                        
                except Exception as e:
                    logger.error(f"Error stopping agent {agent_id}: {e}")
            
            logger.info("All agents shut down")
        else:
            # Just update status without stopping
            for agent_id in self.interfaces:
                agent = self.pool.get_agent_by_id(agent_id)
                if agent:
                    agent.status = AgentStatus.IDLE
            
            logger.info("Agent manager shutdown (agents still running in tmux)")
    
    def get_agent_metrics(self) -> Dict[str, Any]:
        """Get detailed metrics for all agents"""
        metrics = {
            'agents': [],
            'summary': self.pool.get_statistics()
        }
        
        for agent in self.pool.agents:
            agent_metrics = {
                'id': agent.id,
                'uid': agent.uid,
                'status': agent.status.value,
                'uptime_seconds': agent.uptime,
                'completed_steps': len(agent.completed_steps),
                'current_step': agent.current_step,
                'last_activity': agent.last_activity.isoformat(),
                'error': agent.error
            }
            metrics['agents'].append(agent_metrics)
        
        return metrics