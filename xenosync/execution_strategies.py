"""
Execution Strategies - Streamlined parallel and collaborative execution modes
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum

from .agent_manager import AgentManager, Agent, AgentStatus
from .file_coordination import CoordinationManager, WorkStatus
from .prompt_manager import SyncStep, SyncPrompt
from .exceptions import StrategyError


logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    """Available execution modes"""
    PARALLEL = "parallel"  # Tasks divided among agents upfront
    COLLABORATIVE = "collaborative"  # Agents claim from shared task pool


@dataclass
class StepAssignment:
    """Assignment of a step to an agent"""
    step_number: int
    agent_id: int
    agent_uid: str
    status: str = "pending"
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
    
    def get_description(self) -> str:
        return "Parallel execution - tasks are divided among agents upfront"
    
    def get_mode_instructions(self, agent_id: int, total_agents: int) -> str:
        """Get parallel mode instructions for an agent"""
        return f"""=== PARALLEL EXECUTION MODE ===

You are Agent {agent_id + 1} of {total_agents} working in PARALLEL mode.

KEY INSTRUCTIONS:
• You will receive YOUR ASSIGNED TASKS shortly
• Work INDEPENDENTLY on your tasks - no coordination needed
• Other agents are working on different tasks in parallel
• Focus on completing your assignments efficiently
• You do NOT need to check what other agents are doing

Your goal: Complete all tasks assigned to you with high quality."""
    
    def distribute_tasks(self, steps: List[SyncStep], num_agents: int) -> Dict[int, List[SyncStep]]:
        """Distribute tasks among agents using round-robin"""
        assignments = {i: [] for i in range(num_agents)}
        
        for idx, step in enumerate(steps):
            agent_id = idx % num_agents
            assignments[agent_id].append(step)
        
        return assignments
    
    async def execute(self, prompt: SyncPrompt, session_id: str) -> bool:
        """Execute with pre-distributed task assignments"""
        logger.info(f"Starting PARALLEL execution with {self.agent_manager.num_agents} agents")
        
        # Send initial prompt with mode instructions
        await self.send_initial_prompt(prompt, session_id)
        await asyncio.sleep(10)  # Let agents process instructions
        
        # Distribute tasks among agents
        task_distribution = self.distribute_tasks(prompt.steps, self.agent_manager.num_agents)
        
        # Log distribution
        for agent_id, assigned_steps in task_distribution.items():
            task_numbers = [s.number for s in assigned_steps]
            logger.info(f"Agent {agent_id}: Assigned tasks {task_numbers}")
        
        # Send assigned tasks to each agent
        tasks = []
        for agent_id, assigned_steps in task_distribution.items():
            agent = self.agent_manager.pool.get_agent_by_id(agent_id)
            if not agent:
                continue
            
            # Create assignment records
            for step in assigned_steps:
                self.assignments[step.number] = StepAssignment(
                    step_number=step.number,
                    agent_id=agent_id,
                    agent_uid=agent.uid,
                    status="assigned"
                )
            
            # Format tasks for agent
            task_message = self._format_assigned_tasks(assigned_steps, agent_id)
            
            # Execute tasks for this agent
            task = self._execute_agent_tasks(agent, assigned_steps, task_message, session_id)
            tasks.append(task)
        
        # Wait for all agents to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check results
        success_count = sum(1 for r in results if r is True)
        logger.info(f"Parallel execution completed: {success_count}/{len(tasks)} agents succeeded")
        
        return success_count == len(tasks)
    
    def _format_assigned_tasks(self, steps: List[SyncStep], agent_id: int) -> str:
        """Format assigned tasks for an agent"""
        message = f"""=== YOUR ASSIGNED TASKS ===

You have been assigned {len(steps)} task(s) to complete:

"""
        for step in steps:
            message += f"TASK {step.number}:\n"
            message += f"{step.content}\n"
            if step.description:
                message += f"Description: {step.description}\n"
            message += "\n" + "-" * 40 + "\n\n"
        
        message += """IMPORTANT:
• Work through these tasks sequentially
• You do NOT need to coordinate with other agents
• Focus on quality and completeness
• Complete ALL assigned tasks before finishing

Begin working on your tasks now."""
        
        return message
    
    async def _execute_agent_tasks(self, agent: Agent, steps: List[SyncStep], 
                                  content: str, session_id: str) -> bool:
        """Execute tasks for a single agent"""
        try:
            # Send tasks to agent
            await self.agent_manager.send_to_agent(agent.id, content)
            
            # Update assignments to in-progress
            for step in steps:
                if step.number in self.assignments:
                    self.assignments[step.number].status = "in_progress"
                    self.assignments[step.number].started_at = asyncio.get_event_loop().time()
            
            # Log task start
            self.coordination.log_completed_work(
                agent.uid, session_id,
                f"Started working on tasks: {[s.number for s in steps]}",
                success=True
            )
            
            # Give agent time to work (parallel mode doesn't need active monitoring)
            await asyncio.sleep(60)  # Initial work time
            
            # Simple completion check - parallel mode assumes agents complete their work
            logger.info(f"Agent {agent.id} working on assigned tasks...")
            
            # Mark as completed (in real implementation, would check agent output)
            for step in steps:
                if step.number in self.assignments:
                    self.assignments[step.number].status = "completed"
                    self.assignments[step.number].completed_at = asyncio.get_event_loop().time()
            
            return True
            
        except Exception as e:
            logger.error(f"Error in agent {agent.id} execution: {e}")
            return False


class CollaborativeStrategy(ExecutionStrategy):
    """Collaborative execution with dynamic task claiming from shared pool"""
    
    def get_description(self) -> str:
        return "Collaborative execution - agents dynamically claim tasks from shared pool"
    
    def get_mode_instructions(self, agent_id: int, total_agents: int) -> str:
        """Get collaborative mode instructions for an agent"""
        return f"""=== COLLABORATIVE EXECUTION MODE ===

You are Agent {agent_id + 1} of {total_agents} working in COLLABORATIVE mode.

KEY INSTRUCTIONS:
• You will see ALL available tasks in a shared pool
• Before starting ANY task:
  1. Check /coordination/active_work_registry.json for claimed work
  2. Choose an unclaimed task
  3. Claim it by updating the coordination files
  4. Work on the task
  5. Mark it complete when done
• Other agents are working on different tasks from the same pool
• You CAN see and build upon work completed by others
• Coordinate through the file system to avoid conflicts

COORDINATION PROTOCOL:
1. ALWAYS check what's already claimed before starting
2. Update coordination files when claiming work
3. Check completed_work_log.json to see what's been done
4. Build on existing work when appropriate
5. Communicate progress through the coordination system

Your goal: Work efficiently with the team to complete all tasks."""
    
    async def execute(self, prompt: SyncPrompt, session_id: str) -> bool:
        """Execute with dynamic task claiming from shared pool"""
        logger.info(f"Starting COLLABORATIVE execution with {self.agent_manager.num_agents} agents")
        
        # Send initial prompt with mode instructions
        await self.send_initial_prompt(prompt, session_id)
        await asyncio.sleep(10)  # Let agents process instructions
        
        # Create shared task pool message
        task_pool_message = self._create_task_pool_message(prompt.steps)
        
        # Send task pool to all agents
        await self.agent_manager.broadcast_to_all(task_pool_message)
        
        # Initialize task tracking
        total_tasks = len(prompt.steps)
        logger.info(f"Created shared pool with {total_tasks} tasks")
        
        # Monitor collaborative execution
        success = await self._monitor_collaborative_execution(session_id, total_tasks)
        
        return success
    
    def _create_task_pool_message(self, steps: List[SyncStep]) -> str:
        """Create the shared task pool message"""
        message = """=== SHARED TASK POOL ===

All tasks are available for claiming. Choose tasks based on:
1. What hasn't been claimed yet
2. Your capabilities and expertise
3. Dependencies between tasks
4. Building on completed work

AVAILABLE TASKS:

"""
        for step in steps:
            message += f"TASK {step.number}:\n"
            message += f"{step.content}\n"
            if step.description:
                message += f"Description: {step.description}\n"
            message += "\n" + "-" * 40 + "\n\n"
        
        message += """COLLABORATION PROTOCOL:
1. Check /coordination/active_work_registry.json before claiming
2. Claim your chosen task in the coordination system
3. Update progress as you work
4. Mark complete when done
5. Check for new tasks after completing each one

Remember: You're part of a team. Coordinate effectively!

Begin by checking the coordination files and claiming your first task."""
        
        return message
    
    async def _monitor_collaborative_execution(self, session_id: str, total_tasks: int) -> bool:
        """Monitor collaborative execution progress"""
        max_time = 3600  # 1 hour maximum
        start_time = asyncio.get_event_loop().time()
        check_interval = 30  # Check every 30 seconds
        
        completed_tasks = set()
        last_progress = 0
        
        while len(completed_tasks) < total_tasks:
            # Check timeout
            if asyncio.get_event_loop().time() - start_time > max_time:
                logger.warning("Collaborative execution timed out")
                break
            
            # Check completed work
            try:
                completed_work = self.coordination.get_completed_work(session_id)
                if not isinstance(completed_work, list):
                    logger.warning(f"get_completed_work returned non-list: {type(completed_work)}")
                    completed_work = []
            except Exception as e:
                logger.error(f"Failed to get completed work: {e}")
                completed_work = []
            
            # Extract completed task numbers
            for work in completed_work:
                try:
                    # Validate work item structure
                    if not isinstance(work, dict):
                        logger.debug(f"Skipping non-dict work item: {type(work)}")
                        continue
                    
                    # Safely get description with fallback
                    description = work.get('description', '').lower()
                    if not description:
                        # Skip work items without description
                        logger.debug(f"Skipping work item without description: {work.get('agent_uid', 'unknown')}")
                        continue
                    
                    # Look for task number references
                    for i in range(1, total_tasks + 1):
                        if f"task {i}" in description or f"step {i}" in description:
                            completed_tasks.add(i)
                            break
                except Exception as e:
                    logger.warning(f"Error processing work item: {e} - Item: {work}")
                    continue
            
            # Check active claims
            active_claims = self.coordination.get_active_claims(session_id)
            active_count = len(active_claims)
            
            # Log progress
            current_progress = len(completed_tasks)
            if current_progress > last_progress:
                progress_pct = (current_progress / total_tasks) * 100
                logger.info(f"Progress: {current_progress}/{total_tasks} tasks ({progress_pct:.1f}%)")
                logger.info(f"Active claims: {active_count}")
                last_progress = current_progress
            
            # Check for conflicts and resolve
            conflicts = self.coordination.detect_conflicts(session_id)
            if conflicts:
                logger.warning(f"Detected {len(conflicts)} conflicts")
                # In collaborative mode, agents should resolve conflicts themselves
            
            # Clean up stale claims periodically
            if int(asyncio.get_event_loop().time()) % 300 == 0:  # Every 5 minutes
                cleaned = self.coordination.cleanup_stale_claims(session_id, hours=1)
                if cleaned > 0:
                    logger.info(f"Cleaned up {cleaned} stale claims")
            
            # Check agent health
            agent_metrics = self.agent_manager.get_agent_metrics()
            active_agents = sum(1 for a in agent_metrics['agents'] 
                              if a['status'] not in ['stopped', 'error'])
            
            if active_agents == 0:
                logger.error("No active agents remaining")
                break
            
            await asyncio.sleep(check_interval)
        
        # Final status
        success = len(completed_tasks) == total_tasks
        if success:
            logger.info(f"✅ Collaborative execution completed all {total_tasks} tasks!")
        else:
            logger.warning(f"⚠️ Collaborative execution incomplete: {len(completed_tasks)}/{total_tasks} tasks")
        
        return success