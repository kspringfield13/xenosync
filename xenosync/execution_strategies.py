"""
Execution Strategies - Different modes for orchestrating multi-agent workflows
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from .agent_manager import AgentManager, Agent, AgentStatus
from .coordination import CoordinationManager, WorkStatus
from .prompt_manager import SyncStep, SyncPrompt
from .exceptions import StrategyError


logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    """Available execution modes"""
    SEQUENTIAL = "sequential"  # Single agent, step by step (default)
    PARALLEL = "parallel"  # Multiple agents, independent tasks
    COLLABORATIVE = "collaborative"  # All agents see all steps, self-organize
    DISTRIBUTED = "distributed"  # Smart distribution based on dependencies
    HYBRID = "hybrid"  # Mix of parallel and sequential phases
    COMPETITIVE = "competitive"  # Agents race to complete tasks


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
        """Execute the build prompt using this strategy"""
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """Get human-readable description of this strategy"""
        pass
    
    async def send_initial_prompt(self, prompt: SyncPrompt, session_id: str):
        """Send initial prompt to all agents with strategy-specific instructions"""
        base_prompt = prompt.initial_prompt
        num_agents = self.agent_manager.num_agents
        
        # Add coordination instructions
        instructions = self.get_coordination_instructions(num_agents)
        full_prompt = f"{base_prompt}\n\n{instructions}"
        
        # Send to all agents
        await self.agent_manager.broadcast_to_all(full_prompt)
        logger.info(f"Sent initial prompt to {num_agents} agents")
    
    @abstractmethod
    def get_coordination_instructions(self, num_agents: int) -> str:
        """Get strategy-specific coordination instructions"""
        pass
    
    def analyze_step_dependencies(self, steps: List[SyncStep]) -> Dict[int, List[int]]:
        """Analyze dependencies between steps"""
        dependencies = {}
        
        for step in steps:
            if step.dependencies:
                dependencies[step.number] = step.dependencies
            else:
                # Try to infer dependencies from content
                deps = []
                for other_step in steps:
                    if other_step.number < step.number:
                        # Check if current step references previous step
                        if f"step {other_step.number}" in step.content.lower():
                            deps.append(other_step.number)
                dependencies[step.number] = deps
        
        return dependencies


class SequentialStrategy(ExecutionStrategy):
    """Traditional single-agent sequential execution"""
    
    def get_description(self) -> str:
        return "Sequential execution with a single agent"
    
    def get_coordination_instructions(self, num_agents: int) -> str:
        return "You will work through the sync steps sequentially."
    
    async def execute(self, prompt: SyncPrompt, session_id: str) -> bool:
        """Execute steps sequentially with single agent"""
        # Use only first agent for sequential mode
        agent = self.agent_manager.pool.agents[0] if self.agent_manager.pool.agents else None
        if not agent:
            logger.error("No agents available for sequential execution")
            return False
        
        logger.info(f"Starting sequential execution with agent {agent.id}")
        
        # Send initial prompt
        await self.agent_manager.send_to_agent(agent.id, prompt.initial_prompt)
        
        # Wait for agent to be ready
        await asyncio.sleep(10)
        
        # Execute steps one by one
        for step in prompt.steps:
            logger.info(f"Executing step {step.number}: {step.description[:50]}...")
            
            # Create assignment
            assignment = StepAssignment(
                step_number=step.number,
                agent_id=agent.id,
                agent_uid=agent.uid,
                status="in_progress",
                started_at=asyncio.get_event_loop().time()
            )
            self.assignments[step.number] = assignment
            
            # Send step to agent
            step_content = f"Step {step.number}: {step.content}"
            if step.description:
                step_content = f"{step_content}\n\nDescription: {step.description}"
            
            await self.agent_manager.send_to_agent(agent.id, step_content)
            
            # Wait for completion
            max_wait = 600  # 10 minutes max per step
            elapsed = 0
            check_interval = 10
            
            while elapsed < max_wait:
                await asyncio.sleep(check_interval)
                elapsed += check_interval
                
                if await self.agent_manager.check_agent_ready(agent.id):
                    assignment.status = "completed"
                    assignment.completed_at = asyncio.get_event_loop().time()
                    logger.info(f"Step {step.number} completed")
                    break
            
            if assignment.status != "completed":
                logger.warning(f"Step {step.number} timed out")
                assignment.status = "timeout"
                return False
        
        logger.info("Sequential execution completed successfully")
        return True


class ParallelStrategy(ExecutionStrategy):
    """Parallel execution with independent task assignment"""
    
    def get_description(self) -> str:
        return "Parallel execution with agents working independently"
    
    def get_coordination_instructions(self, num_agents: int) -> str:
        return f"""IMPORTANT: You are part of a team of {num_agents} agents working in parallel.
Before making changes:
1. Check for existing work claims to avoid conflicts
2. Claim your work area before starting
3. Focus on your assigned tasks
4. Log completed work when done"""
    
    async def execute(self, prompt: SyncPrompt, session_id: str) -> bool:
        """Execute steps in parallel across multiple agents"""
        logger.info(f"Starting parallel execution with {self.agent_manager.num_agents} agents")
        
        # Send initial prompt to all agents
        await self.send_initial_prompt(prompt, session_id)
        await asyncio.sleep(10)
        
        # Distribute steps across agents
        assignments = await self.agent_manager.distribute_steps(
            [step.content for step in prompt.steps],
            strategy="round-robin"
        )
        
        # Send assigned steps to each agent
        tasks = []
        for agent_id, step_indices in assignments.items():
            agent = self.agent_manager.pool.get_agent_by_id(agent_id)
            if not agent:
                continue
            
            # Build step bundle for this agent
            assigned_steps = [prompt.steps[i] for i in step_indices]
            step_content = f"You have been assigned {len(assigned_steps)} steps:\n\n"
            
            for step in assigned_steps:
                step_content += f"Step {step.number}: {step.content}\n"
                if step.description:
                    step_content += f"   Description: {step.description}\n"
                step_content += "\n"
                
                # Create assignment record
                self.assignments[step.number] = StepAssignment(
                    step_number=step.number,
                    agent_id=agent_id,
                    agent_uid=agent.uid,
                    status="assigned"
                )
            
            logger.info(f"Assigning {len(assigned_steps)} steps to agent {agent_id}: {[s.number for s in assigned_steps]}")
            
            # Send steps to agent
            tasks.append(self._execute_agent_steps(agent, assigned_steps, step_content, session_id))
        
        # Wait for all agents to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check results
        success_count = sum(1 for r in results if r is True)
        logger.info(f"Parallel execution completed: {success_count}/{len(tasks)} agents succeeded")
        
        return success_count == len(tasks)
    
    async def _execute_agent_steps(self, agent: Agent, steps: List[SyncStep], 
                                  content: str, session_id: str) -> bool:
        """Execute steps for a single agent"""
        try:
            # Claim work for these steps
            files_to_claim = []  # Extract from steps if needed
            claim_id = self.coordination.claim_work(
                agent.uid, session_id, files_to_claim,
                f"Working on steps {[s.number for s in steps]}"
            )
            
            if not claim_id:
                logger.warning(f"Agent {agent.id} could not claim work")
                return False
            
            # Send steps to agent
            await self.agent_manager.send_to_agent(agent.id, content)
            
            # Update assignments
            for step in steps:
                if step.number in self.assignments:
                    self.assignments[step.number].status = "in_progress"
                    self.assignments[step.number].started_at = asyncio.get_event_loop().time()
            
            # Give agent time to start processing
            await asyncio.sleep(30)  # Initial wait before checking
            
            # Wait for this specific agent to complete
            max_wait = 1200  # 20 minutes for all steps
            elapsed = 0
            check_interval = 10
            
            while elapsed < max_wait:
                await asyncio.sleep(check_interval)
                elapsed += check_interval
                
                # Check if this specific agent is ready (idle)
                if await self.agent_manager.check_agent_ready(agent.id):
                    # Mark steps as completed
                    for step in steps:
                        if step.number in self.assignments:
                            self.assignments[step.number].status = "completed"
                            self.assignments[step.number].completed_at = asyncio.get_event_loop().time()
                    
                    # Log completed work
                    self.coordination.log_completed_work(
                        agent.uid, session_id,
                        f"Completed steps {[s.number for s in steps]}",
                        success=True
                    )
                    
                    # Release claim
                    self.coordination.release_work(agent.uid, claim_id)
                    logger.info(f"Agent {agent.id} completed its assigned steps")
                    return True
            
            # Timeout reached
            logger.warning(f"Agent {agent.id} timed out after {elapsed}s")
            self.coordination.release_work(agent.uid, claim_id)
            return False
                
        except Exception as e:
            logger.error(f"Error in agent {agent.id} execution: {e}")
            return False


class CollaborativeStrategy(ExecutionStrategy):
    """Collaborative execution where agents self-organize"""
    
    def get_description(self) -> str:
        return "Collaborative mode where agents coordinate and self-organize"
    
    def get_coordination_instructions(self, num_agents: int) -> str:
        return f"""IMPORTANT: You are part of a collaborative team of {num_agents} agents.

Collaboration Protocol:
1. You will receive ALL project steps
2. Review the complete task list before choosing what to work on
3. Check what others have claimed in the coordination system
4. Choose work that complements what others are doing
5. Create detailed work claims including:
   - Which steps you're working on
   - Which files you'll modify
   - Expected interfaces/APIs you'll create
6. Regularly check completed work and adjust your approach
7. Focus on integration points between components
8. Communicate through clear commits and interfaces

Your goal is to work as a cohesive team to complete the entire project efficiently."""
    
    async def execute(self, prompt: SyncPrompt, session_id: str) -> bool:
        """Execute with agents self-organizing around all steps"""
        logger.info(f"Starting collaborative execution with {self.agent_manager.num_agents} agents")
        
        # Send initial prompt to all agents
        await self.send_initial_prompt(prompt, session_id)
        await asyncio.sleep(10)
        
        # Send all steps to all agents
        all_steps_content = "\n\nCOMPLETE PROJECT STEPS:\n"
        for step in prompt.steps:
            all_steps_content += f"\nStep {step.number}: {step.content}"
            if step.description:
                all_steps_content += f"\n   Description: {step.description}"
        
        all_steps_content += """

Review all steps and choose which ones to work on based on:
- What others have already claimed
- Your analysis of the codebase
- Dependencies between steps
- Your strengths and the step requirements

Remember to claim your work before starting and update the completed work log when done."""
        
        # Broadcast steps to all agents
        await self.agent_manager.broadcast_to_all(all_steps_content)
        
        # Monitor progress
        total_steps = len(prompt.steps)
        completed_steps = set()
        max_time = 3600  # 1 hour max
        start_time = asyncio.get_event_loop().time()
        
        while len(completed_steps) < total_steps:
            # Check timeout
            if asyncio.get_event_loop().time() - start_time > max_time:
                logger.warning("Collaborative execution timed out")
                break
            
            # Check completed work
            completed_work = self.coordination.get_completed_work(session_id)
            for work in completed_work:
                # Extract completed step numbers from descriptions
                for step in prompt.steps:
                    if f"step {step.number}" in work['description'].lower():
                        completed_steps.add(step.number)
            
            # Log progress
            progress = len(completed_steps) / total_steps * 100
            logger.info(f"Collaborative progress: {len(completed_steps)}/{total_steps} steps ({progress:.1f}%)")
            
            # Check for conflicts and resolve
            conflicts = self.coordination.detect_conflicts(session_id)
            if conflicts:
                logger.warning(f"Detected {len(conflicts)} conflicts, agents should coordinate")
                # Could send messages to agents about conflicts
            
            # Clean up stale claims
            self.coordination.cleanup_stale_claims(session_id)
            
            await asyncio.sleep(30)  # Check every 30 seconds
        
        success = len(completed_steps) == total_steps
        logger.info(f"Collaborative execution {'completed' if success else 'incomplete'}: "
                   f"{len(completed_steps)}/{total_steps} steps done")
        
        return success


class DistributedStrategy(ExecutionStrategy):
    """Smart distributed execution based on dependencies"""
    
    def get_description(self) -> str:
        return "Distributed execution with dependency-aware task assignment"
    
    def get_coordination_instructions(self, num_agents: int) -> str:
        return f"""IMPORTANT: You are part of a distributed team of {num_agents} agents.

Tasks will be assigned based on dependencies and your capabilities.
- Wait for your assigned tasks
- Complete them efficiently
- Signal completion clearly
- Be ready for follow-up tasks"""
    
    async def execute(self, prompt: SyncPrompt, session_id: str) -> bool:
        """Execute with smart distribution based on dependencies"""
        logger.info(f"Starting distributed execution with {self.agent_manager.num_agents} agents")
        
        # Analyze dependencies
        dependencies = self.analyze_step_dependencies(prompt.steps)
        logger.info(f"Analyzed dependencies: {dependencies}")
        
        # Send initial prompt
        await self.send_initial_prompt(prompt, session_id)
        await asyncio.sleep(10)
        
        # Create execution waves based on dependencies
        waves = self._create_execution_waves(prompt.steps, dependencies)
        logger.info(f"Created {len(waves)} execution waves")
        
        # Execute waves
        for wave_num, wave_steps in enumerate(waves, 1):
            logger.info(f"Executing wave {wave_num} with {len(wave_steps)} steps")
            
            # Distribute wave steps to available agents
            assignments = {}
            available_agents = [a for a in self.agent_manager.pool.agents if a.is_available]
            
            for i, step in enumerate(wave_steps):
                agent = available_agents[i % len(available_agents)]
                if agent.id not in assignments:
                    assignments[agent.id] = []
                assignments[agent.id].append(step)
            
            # Execute wave in parallel
            tasks = []
            for agent_id, agent_steps in assignments.items():
                agent = self.agent_manager.pool.get_agent_by_id(agent_id)
                if agent:
                    content = self._format_wave_steps(agent_steps, wave_num)
                    tasks.append(self._execute_agent_steps(agent, agent_steps, content, session_id))
            
            # Wait for wave completion
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            if not all(r is True for r in results if not isinstance(r, Exception)):
                logger.error(f"Wave {wave_num} failed")
                return False
            
            logger.info(f"Wave {wave_num} completed successfully")
        
        logger.info("Distributed execution completed successfully")
        return True
    
    def _create_execution_waves(self, steps: List[SyncStep], 
                               dependencies: Dict[int, List[int]]) -> List[List[SyncStep]]:
        """Create waves of steps that can be executed in parallel"""
        waves = []
        completed_steps = set()
        remaining_steps = list(steps)
        
        while remaining_steps:
            # Find steps that can be executed (all dependencies met)
            wave = []
            for step in remaining_steps[:]:
                step_deps = dependencies.get(step.number, [])
                if all(dep in completed_steps for dep in step_deps):
                    wave.append(step)
                    remaining_steps.remove(step)
            
            if not wave:
                # No progress possible, add remaining as final wave
                logger.warning("Dependency deadlock, adding remaining steps as final wave")
                waves.append(remaining_steps)
                break
            
            waves.append(wave)
            completed_steps.update(s.number for s in wave)
        
        return waves
    
    def _format_wave_steps(self, steps: List[SyncStep], wave_num: int) -> str:
        """Format steps for a wave"""
        content = f"=== Execution Wave {wave_num} ===\n\n"
        content += f"You have been assigned {len(steps)} step(s) to execute:\n\n"
        
        for step in steps:
            content += f"Step {step.number}: {step.content}\n"
            if step.description:
                content += f"   Description: {step.description}\n"
            if step.dependencies:
                content += f"   Dependencies: Steps {step.dependencies} (already completed)\n"
            content += "\n"
        
        content += "Complete these steps and signal when done."
        return content


class HybridStrategy(ExecutionStrategy):
    """Hybrid execution mixing parallel and sequential phases"""
    
    def get_description(self) -> str:
        return "Hybrid execution with mixed parallel and sequential phases"
    
    def get_coordination_instructions(self, num_agents: int) -> str:
        return f"""IMPORTANT: You are part of a hybrid team of {num_agents} agents.

The project will be executed in phases:
- Some phases will be collaborative (work together)
- Some phases will be sequential (one agent at a time)
- Follow the phase instructions carefully"""
    
    async def execute(self, prompt: SyncPrompt, session_id: str) -> bool:
        """Execute with hybrid approach based on step characteristics"""
        logger.info(f"Starting hybrid execution with {self.agent_manager.num_agents} agents")
        
        # Categorize steps into phases
        phases = self._categorize_steps(prompt.steps)
        logger.info(f"Created {len(phases)} execution phases")
        
        # Send initial prompt
        await self.send_initial_prompt(prompt, session_id)
        await asyncio.sleep(10)
        
        # Execute phases
        for phase_num, (phase_type, phase_steps) in enumerate(phases, 1):
            logger.info(f"Executing phase {phase_num} ({phase_type}) with {len(phase_steps)} steps")
            
            if phase_type == "parallel":
                # Use parallel strategy for this phase
                strategy = ParallelStrategy(self.agent_manager, self.coordination)
                mini_prompt = SyncPrompt(
                    name=f"Phase {phase_num}",
                    filename="",
                    format="hybrid",
                    initial_prompt="",
                    steps=phase_steps
                )
                success = await strategy.execute(mini_prompt, session_id)
                
            elif phase_type == "sequential":
                # Use sequential strategy for critical steps
                strategy = SequentialStrategy(self.agent_manager, self.coordination)
                mini_prompt = SyncPrompt(
                    name=f"Phase {phase_num}",
                    filename="",
                    format="hybrid",
                    initial_prompt="",
                    steps=phase_steps
                )
                success = await strategy.execute(mini_prompt, session_id)
                
            else:  # collaborative
                # Use collaborative strategy
                strategy = CollaborativeStrategy(self.agent_manager, self.coordination)
                mini_prompt = SyncPrompt(
                    name=f"Phase {phase_num}",
                    filename="",
                    format="hybrid",
                    initial_prompt="",
                    steps=phase_steps
                )
                success = await strategy.execute(mini_prompt, session_id)
            
            if not success:
                logger.error(f"Phase {phase_num} failed")
                return False
        
        logger.info("Hybrid execution completed successfully")
        return True
    
    def _categorize_steps(self, steps: List[SyncStep]) -> List[Tuple[str, List[SyncStep]]]:
        """Categorize steps into execution phases"""
        phases = []
        
        # Simple heuristic: 
        # - Initial setup steps: sequential
        # - Independent feature steps: parallel
        # - Integration steps: collaborative
        # - Final steps: sequential
        
        if len(steps) <= 3:
            # Small project, just go sequential
            phases.append(("sequential", steps))
        else:
            # Setup phase (first 20% of steps)
            setup_count = max(1, len(steps) // 5)
            phases.append(("sequential", steps[:setup_count]))
            
            # Development phase (middle 60%)
            dev_start = setup_count
            dev_end = setup_count + (len(steps) * 3 // 5)
            if dev_end > dev_start:
                phases.append(("parallel", steps[dev_start:dev_end]))
            
            # Integration phase (next 10%)
            int_end = dev_end + (len(steps) // 10)
            if int_end > dev_end and int_end <= len(steps):
                phases.append(("collaborative", steps[dev_end:int_end]))
            
            # Finalization phase (last 10%)
            if int_end < len(steps):
                phases.append(("sequential", steps[int_end:]))
        
        return phases


def get_strategy(mode: ExecutionMode, agent_manager: AgentManager, 
                 coordination: CoordinationManager) -> ExecutionStrategy:
    """Factory function to get the appropriate execution strategy"""
    strategies = {
        ExecutionMode.SEQUENTIAL: SequentialStrategy,
        ExecutionMode.PARALLEL: ParallelStrategy,
        ExecutionMode.COLLABORATIVE: CollaborativeStrategy,
        ExecutionMode.DISTRIBUTED: DistributedStrategy,
        ExecutionMode.HYBRID: HybridStrategy,
    }
    
    strategy_class = strategies.get(mode)
    if not strategy_class:
        raise StrategyError(f"Unknown execution mode: {mode}")
    
    return strategy_class(agent_manager, coordination)