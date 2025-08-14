"""
Execution Strategy - Unified parallel execution mode
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from .agent_manager import AgentManager, Agent, AgentStatus
from .file_coordination import CoordinationManager, WorkStatus
from .prompt_manager import SyncStep, SyncPrompt
from .exceptions import StrategyError


logger = logging.getLogger(__name__)


@dataclass
class StepAssignment:
    """Assignment of a step to an agent"""
    step_number: int
    agent_id: int
    agent_uid: str
    status: str = "pending"
    claim_id: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


class ExecutionStrategy(ABC):
    """Abstract base class for execution strategies"""
    
    def __init__(self, agent_manager: AgentManager, coordination: CoordinationManager):
        self.agent_manager = agent_manager
        self.coordination = coordination
        self.assignments: Dict[int, StepAssignment] = {}
    
    @abstractmethod
    async def execute(self, prompt: SyncPrompt, session_id: str) -> bool:
        """Execute the prompt using this strategy"""
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """Get human-readable description of this strategy"""
        pass
    
    @abstractmethod
    def get_mode_instructions(self, agent_id: int, total_agents: int) -> str:
        """Get mode-specific instructions for an agent"""
        pass
    
    async def send_initial_prompt(self, prompt: SyncPrompt, session_id: str):
        """Send initial prompt to all agents with strategy-specific instructions"""
        base_prompt = prompt.initial_prompt
        num_agents = self.agent_manager.num_agents
        
        # Send customized prompt to each agent
        for agent in self.agent_manager.pool.agents:
            # Get mode-specific instructions for this agent
            instructions = self.get_mode_instructions(agent.id, num_agents)
            
            # Combine base prompt with instructions
            full_prompt = f"{base_prompt}\n\n{instructions}"
            
            # Send to agent
            await self.agent_manager.send_to_agent(agent.id, full_prompt)
        
        logger.info(f"Sent initial prompts to {num_agents} agents")


class ParallelStrategy(ExecutionStrategy):
    """Parallel execution with pre-distributed task assignments"""
    
    def __init__(self, agent_manager: AgentManager, coordination: CoordinationManager):
        super().__init__(agent_manager, coordination)
        # Task queue management for sequential delivery
        self.agent_task_queues: Dict[int, List[SyncStep]] = {}  # Remaining tasks per agent
        self.current_agent_task: Dict[int, Optional[SyncStep]] = {}  # Current task per agent
        self.completed_agent_tasks: Dict[int, List[int]] = {}  # Completed task numbers per agent
        self.session_id: Optional[str] = None  # Store session ID for callbacks
    
    def get_description(self) -> str:
        return "Parallel execution - tasks are divided among agents upfront"
    
    def get_mode_instructions(self, agent_id: int, total_agents: int) -> str:
        """Get parallel mode instructions for an agent"""
        return f"""=== PARALLEL EXECUTION MODE ===

You are Agent {agent_id + 1} of {total_agents} working in PARALLEL mode.

KEY INSTRUCTIONS:
• You will receive tasks ONE AT A TIME
• Complete each task thoroughly before moving to the next
• Work INDEPENDENTLY - no coordination needed with other agents
• Focus on completing your current task with high quality
• You will automatically receive the next task when ready

Your goal: Complete each task assigned to you with high quality."""
    
    def distribute_tasks(self, steps: List[SyncStep], num_agents: int) -> Dict[int, List[SyncStep]]:
        """Distribute tasks among agents using round-robin"""
        assignments = {i: [] for i in range(num_agents)}
        
        for idx, step in enumerate(steps):
            agent_id = idx % num_agents
            assignments[agent_id].append(step)
        
        return assignments
    
    async def send_next_task_to_agent(self, agent_id: int, session_id: str) -> bool:
        """Send the next task from agent's queue"""
        # Check if agent has a queue
        if agent_id not in self.agent_task_queues:
            logger.debug(f"Agent {agent_id} has no task queue")
            return False
        
        # Check if there are remaining tasks
        queue = self.agent_task_queues[agent_id]
        if not queue:
            logger.info(f"Agent {agent_id} has completed all assigned tasks")
            self.current_agent_task[agent_id] = None
            return False
        
        # Get next task
        next_task = queue.pop(0)
        self.current_agent_task[agent_id] = next_task
        
        # Get agent
        agent = self.agent_manager.pool.get_agent_by_id(agent_id)
        if not agent:
            logger.error(f"Agent {agent_id} not found")
            return False
        
        # Format and send task
        total_tasks = len(self.completed_agent_tasks.get(agent_id, [])) + len(queue) + 1
        completed_count = len(self.completed_agent_tasks.get(agent_id, []))
        task_message = self._format_single_task(next_task, agent_id, completed_count + 1, total_tasks)
        
        # Create work claim for this task
        claim_id = self.coordination.claim_work(
            agent_uid=agent.uid,
            session_id=session_id,
            files=[],
            description=f"Task {next_task.number}: {next_task.content[:100]}",
            metadata={
                'task_number': next_task.number,
                'agent_id': agent_id,
                'strategy': 'parallel'
            }
        )
        
        if claim_id:
            # Update assignment
            if next_task.number in self.assignments:
                self.assignments[next_task.number].status = "claimed"
                self.assignments[next_task.number].claim_id = claim_id
            
            # Update task registry
            self.coordination.update_task_status(
                session_id=session_id,
                task_number=next_task.number,
                status='claimed',
                agent_uid=agent.uid,
                claim_id=claim_id
            )
            
            # Send task to agent
            await self.agent_manager.send_to_agent(agent_id, task_message)
            
            # Track task start time in agent
            agent = self.agent_manager.get_agent_by_id(agent_id)
            if agent:
                agent.start_task(next_task.number)
            
            # Update to in-progress
            self.coordination.update_work_status(
                claim_id=claim_id,
                session_id=session_id,
                status=WorkStatus.IN_PROGRESS
            )
            
            self.coordination.update_task_status(
                session_id=session_id,
                task_number=next_task.number,
                status='in_progress'
            )
            
            if next_task.number in self.assignments:
                self.assignments[next_task.number].status = "in_progress"
            
            logger.info(f"Sent task {next_task.number} to agent {agent_id} (task {completed_count + 1}/{total_tasks})")
            return True
        else:
            logger.warning(f"Failed to claim work for task {next_task.number}")
            # Put task back in queue
            queue.insert(0, next_task)
            return False
    
    def _format_single_task(self, step: SyncStep, agent_id: int, task_position: int, total_tasks: int) -> str:
        """Format a single task for an agent"""
        message = f"""=== TASK {task_position} of {total_tasks} ===

TASK {step.number}: {step.content}
"""
        if step.description:
            message += f"Description: {step.description}\n"
        
        message += """
----------------------------------------

IMPORTANT:
• Focus on completing THIS task thoroughly
• You will receive the next task automatically when done
• Take your time to ensure quality

Begin working on this task now."""
        
        return message
    
    async def execute(self, prompt: SyncPrompt, session_id: str) -> bool:
        """Execute with pre-distributed task assignments"""
        logger.info(f"Starting PARALLEL execution with {self.agent_manager.num_agents} agents")
        
        # Store session ID for callbacks
        self.session_id = session_id
        
        # Register all tasks in the coordination system
        tasks_data = [
            {
                'number': step.number,
                'content': step.content,
                'description': getattr(step, 'description', '')
            }
            for step in prompt.steps
        ]
        self.coordination.register_tasks(session_id, tasks_data)
        logger.info(f"Registered {len(prompt.steps)} tasks in coordination system")
        
        # Send initial prompt with mode instructions
        await self.send_initial_prompt(prompt, session_id)
        await asyncio.sleep(10)  # Let agents process instructions
        
        # Distribute tasks among agents
        task_distribution = self.distribute_tasks(prompt.steps, self.agent_manager.num_agents)
        
        # Log distribution
        for agent_id, assigned_steps in task_distribution.items():
            task_numbers = [s.number for s in assigned_steps]
            logger.info(f"Agent {agent_id}: Assigned tasks {task_numbers}")
        
        # Initialize task queues and send first task to each agent
        tasks = []
        for agent_id, assigned_steps in task_distribution.items():
            agent = self.agent_manager.pool.get_agent_by_id(agent_id)
            if not agent:
                continue
            
            # Initialize agent's task queue and tracking
            self.agent_task_queues[agent_id] = assigned_steps.copy()
            self.current_agent_task[agent_id] = None
            self.completed_agent_tasks[agent_id] = []
            
            # Create assignment records
            for step in assigned_steps:
                self.assignments[step.number] = StepAssignment(
                    step_number=step.number,
                    agent_id=agent_id,
                    agent_uid=agent.uid,
                    status="pending"
                )
            
            # Start agent with first task
            task = self._start_agent_with_first_task(agent, session_id)
            tasks.append(task)
        
        # Wait for all agents to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check results
        success_count = sum(1 for r in results if r is True)
        logger.info(f"Parallel execution completed: {success_count}/{len(tasks)} agents succeeded")
        
        return success_count == len(tasks)
    
    async def _start_agent_with_first_task(self, agent: Agent, session_id: str) -> bool:
        """Start an agent with their first task"""
        try:
            # Send the first task to the agent
            success = await self.send_next_task_to_agent(agent.id, session_id)
            
            if not success:
                logger.error(f"Failed to send first task to agent {agent.id}")
                return False
            
            logger.info(f"Agent {agent.id} started with first task")
            return True
            
        except Exception as e:
            logger.error(f"Error starting agent {agent.id}: {e}")
            return False


