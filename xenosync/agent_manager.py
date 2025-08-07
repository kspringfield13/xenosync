"""
Agent Manager - Manages multiple Claude instances for parallel execution
"""

import asyncio
import logging
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
        
        # Start Claude session
        try:
            await interface.start(f"{session_id}_agent_{agent_id}")
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
    
    async def check_agent_ready(self, agent_id: int) -> bool:
        """Check if agent is ready for input"""
        output = await self.get_agent_output(agent_id, lines=20)
        if not output:
            return False
        
        # Check for Claude ready indicators
        ready_indicators = [
            "ready",
            "completed",
            "finished",
            "done",
            ">",  # Claude prompt
        ]
        
        output_lower = output.lower()
        is_ready = any(indicator in output_lower for indicator in ready_indicators)
        
        if is_ready:
            agent = self.pool.get_agent_by_id(agent_id)
            if agent and agent.status == AgentStatus.WORKING:
                agent.status = AgentStatus.IDLE
                agent.update_activity()
        
        return is_ready
    
    async def _monitor_agents(self):
        """Monitor agent health and status"""
        while not self._shutdown:
            try:
                for agent in self.pool.agents:
                    # Check if agent is still running
                    interface = self.interfaces.get(agent.id)
                    if interface and not await interface.is_running():
                        if agent.status != AgentStatus.STOPPED:
                            logger.warning(f"Agent {agent.id} stopped unexpectedly")
                            agent.status = AgentStatus.STOPPED
                            agent.error = "Process terminated"
                    
                    # Check for idle agents
                    if agent.status == AgentStatus.WORKING:
                        if await self.check_agent_ready(agent.id):
                            agent.status = AgentStatus.IDLE
                            logger.info(f"Agent {agent.id} became idle")
                
                # Log statistics periodically
                if int(time.time()) % 60 == 0:  # Every minute
                    stats = self.pool.get_statistics()
                    logger.debug(f"Agent pool stats: {stats}")
                
            except Exception as e:
                logger.error(f"Error in agent monitoring: {e}")
            
            await asyncio.sleep(10)  # Check every 10 seconds
    
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
            
            await asyncio.sleep(5)
    
    async def shutdown(self):
        """Shutdown all agents gracefully"""
        logger.info("Shutting down agent manager")
        self._shutdown = True
        
        # Cancel monitoring
        if self._monitoring_task:
            self._monitoring_task.cancel()
        
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