"""
Execution strategies for git worktree-based coordination
"""

import asyncio
import logging
import math
from typing import List, Dict, Optional, Any
from abc import ABC, abstractmethod

from .prompt_manager import SyncPrompt, SyncStep
from .agent_manager import AgentManager
from .git_coordination import GitWorktreeCoordinator
from .exceptions import StrategyError

logger = logging.getLogger(__name__)


class GitExecutionStrategy(ABC):
    """Base class for git worktree execution strategies"""
    
    def __init__(self, agent_manager: AgentManager, coordinator: GitWorktreeCoordinator):
        self.agent_manager = agent_manager
        self.coordinator = coordinator
    
    @abstractmethod
    async def execute(self, prompt: SyncPrompt, session_id: str) -> bool:
        """Execute the strategy"""
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """Get strategy description"""
        pass


class GitParallelStrategy(GitExecutionStrategy):
    """Parallel execution with git worktrees - complete isolation"""
    
    def get_description(self) -> str:
        return "Parallel execution with git worktrees - each agent works independently in isolated workspace"
    
    async def execute(self, prompt: SyncPrompt, session_id: str) -> bool:
        """Execute tasks in parallel using git worktrees"""
        try:
            logger.info("=" * 60)
            logger.info("GIT WORKTREE PARALLEL EXECUTION")
            logger.info("=" * 60)
            
            # Get agents
            agents = self.agent_manager.agents
            if not agents:
                raise StrategyError("No agents available")
            
            num_agents = len(agents)
            logger.info(f"Distributing {len(prompt.steps)} tasks among {num_agents} agents")
            
            # Pre-divide tasks among agents
            assignments = self._divide_tasks(prompt.steps, num_agents)
            
            # Assign tasks to agents via git branches
            for agent_id, agent_tasks in assignments.items():
                agent = self.agent_manager.get_agent_by_id(agent_id)
                if not agent:
                    continue
                
                logger.info(f"Agent {agent_id} assigned {len(agent_tasks)} tasks")
                
                # Create task branches for each assigned task
                for task in agent_tasks:
                    task_number = task.number
                    task_description = task.content
                    
                    # Create task branch in coordinator
                    branch_name = self.coordinator.assign_task(
                        agent_id, 
                        task_number,
                        task_description
                    )
                    
                    # Update agent's current task branch
                    agent.current_task_branch = branch_name
                    
                    logger.info(f"  - Task {task_number} on branch {branch_name}")
            
            # Send initial prompt to all agents with their assignments
            logger.info("Sending initial prompts to agents...")
            await self._send_initial_prompts(prompt, assignments)
            
            # Monitor execution
            logger.info("Monitoring parallel execution...")
            success = await self._monitor_execution(session_id, assignments)
            
            if success:
                logger.info("All agents completed their tasks successfully")
                
                # Merge completed work back to main
                logger.info("Merging completed work...")
                merge_results = self.coordinator.merge_completed_work(
                    strategy=self.coordinator.merge_strategy
                )
                
                logger.info(f"Merge results: {merge_results}")
                
                if merge_results['failed'] or merge_results['conflicts']:
                    logger.warning(f"Some merges failed or had conflicts: {merge_results}")
                    return False
            else:
                logger.warning("Some agents failed to complete their tasks")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Parallel execution failed: {e}")
            raise StrategyError(f"Parallel execution failed: {e}")
    
    def _divide_tasks(self, steps: List[SyncStep], num_agents: int) -> Dict[int, List[SyncStep]]:
        """Divide tasks among agents"""
        assignments = {i: [] for i in range(num_agents)}
        
        # Round-robin distribution for better balance
        for idx, step in enumerate(steps):
            agent_id = idx % num_agents
            assignments[agent_id].append(step)
        
        return assignments
    
    async def _send_initial_prompts(self, prompt: SyncPrompt, 
                                   assignments: Dict[int, List[SyncStep]]):
        """Send initial prompts to all agents with their task assignments"""
        
        for agent_id, tasks in assignments.items():
            if not tasks:
                continue
            
            # Build personalized prompt for this agent
            task_list = "\n".join([
                f"{task.number}. {task.content}"
                for idx, task in enumerate(tasks)
            ])
            
            message = f"""
{prompt.initial_prompt}

You are Agent {agent_id} working in your own git worktree.
Your workspace is completely isolated from other agents.

You have been assigned the following tasks:
{task_list}

IMPORTANT INSTRUCTIONS:
1. You are working in a git worktree - your own isolated workspace
2. Complete each task in sequence
3. Commit your changes frequently with descriptive messages
4. You can work at your own pace - no coordination needed
5. Your work will be automatically merged when complete

Your current git branch: {self.agent_manager.get_agent_by_id(agent_id).current_task_branch}

Begin with task {tasks[0].number}.
"""
            
            # Send message to agent
            await self.agent_manager.send_to_agent(agent_id, message)
            
            # Mark tasks as started
            for task in tasks:
                agent = self.agent_manager.get_agent_by_id(agent_id)
                if agent:
                    agent.start_task(task.number)
    
    async def _monitor_execution(self, session_id: str, 
                                assignments: Dict[int, List[SyncStep]]) -> bool:
        """Monitor execution progress"""
        
        check_interval = 30  # Check every 30 seconds
        max_duration = 3600  # Maximum 1 hour
        elapsed = 0
        
        while elapsed < max_duration:
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            
            # Check progress of each agent
            all_complete = True
            status_summary = []
            
            for agent_id, tasks in assignments.items():
                agent = self.agent_manager.get_agent_by_id(agent_id)
                if not agent:
                    continue
                
                # Get progress from git coordinator
                progress = self.coordinator.track_agent_progress(agent_id)
                
                if progress['status'] == 'no_task':
                    # Agent finished all tasks
                    status_summary.append(f"Agent {agent_id}: Completed")
                elif progress['status'] in ['assigned', 'in_progress']:
                    all_complete = False
                    task_num = progress.get('task_number', '?')
                    commit_count = progress.get('commits', 0)
                    
                    # Show actual agent commits (not inherited history)
                    if commit_count > 0:
                        status_summary.append(
                            f"Agent {agent_id}: Task {task_num} ({commit_count} commit{'s' if commit_count != 1 else ''})"
                        )
                    else:
                        status_summary.append(f"Agent {agent_id}: Task {task_num} (working)")
                else:
                    status_summary.append(f"Agent {agent_id}: {progress['status']}")
            
            # Log status
            if status_summary:
                logger.info("Status: " + " | ".join(status_summary))
            
            if all_complete:
                logger.info("All agents have completed their tasks")
                return True
        
        logger.warning(f"Execution timeout after {max_duration} seconds")
        return False


class GitCollaborativeStrategy(GitExecutionStrategy):
    """Collaborative execution with shared branches and coordination"""
    
    def get_description(self) -> str:
        return "Collaborative execution - agents coordinate on shared tasks via git branches"
    
    async def execute(self, prompt: SyncPrompt, session_id: str) -> bool:
        """Execute tasks collaboratively with branch-based coordination"""
        
        logger.info("=" * 60)
        logger.info("GIT COLLABORATIVE EXECUTION")
        logger.info("=" * 60)
        
        # This strategy would implement agents working on shared branches
        # with more sophisticated merge strategies
        
        # For now, fallback to parallel
        logger.info("Collaborative strategy not yet implemented, using parallel")
        parallel = GitParallelStrategy(self.agent_manager, self.coordinator)
        return await parallel.execute(prompt, session_id)


class GitAdaptiveStrategy(GitExecutionStrategy):
    """Adaptive strategy that adjusts based on task complexity"""
    
    def get_description(self) -> str:
        return "Adaptive execution - automatically chooses strategy based on task analysis"
    
    async def execute(self, prompt: SyncPrompt, session_id: str) -> bool:
        """Adaptively choose strategy based on task analysis"""
        
        logger.info("=" * 60)
        logger.info("GIT ADAPTIVE EXECUTION")
        logger.info("=" * 60)
        
        # Analyze tasks to determine best strategy
        num_tasks = len(prompt.steps)
        num_agents = len(self.agent_manager.agents)
        
        # Simple heuristic: use parallel for many independent tasks
        if num_tasks >= num_agents * 2:
            logger.info(f"Using parallel strategy for {num_tasks} tasks")
            strategy = GitParallelStrategy(self.agent_manager, self.coordinator)
        else:
            logger.info(f"Using collaborative strategy for {num_tasks} tasks")
            strategy = GitCollaborativeStrategy(self.agent_manager, self.coordinator)
        
        return await strategy.execute(prompt, session_id)