"""
Module: project_strategies
Purpose: Execution strategies for distributing tasks across agent project workspaces

This module implements various strategies for coordinating multi-agent execution
in isolated project workspaces. It handles task distribution, agent prompting,
progress monitoring, and final project merging.

Key Classes:
    - ProjectExecutionStrategy: Abstract base for execution strategies
    - ProjectParallelStrategy: Parallel execution with task distribution
    - ProjectCollaborativeStrategy: Collaborative execution (future)
    - ProjectAdaptiveStrategy: Adaptive strategy selection

Key Functions:
    - execute(): Main execution entry point for strategies
    - _divide_tasks(): Distributes tasks among agents
    - _send_initial_prompts(): Sends customized prompts to agents
    - _monitor_execution(): Tracks agent progress

Dependencies:
    - asyncio: Asynchronous execution
    - agent_manager: Agent lifecycle management
    - project_coordination: Workspace management
    - prompt_manager: Task and prompt handling

Usage:
    strategy = ProjectParallelStrategy(agent_manager, coordinator)
    success = await strategy.execute(prompt, session_id)
    
Author: Xenosync Team
Created: 2024-08-14
Modified: 2024-08-14
"""

import asyncio
import logging
from typing import List, Dict, Optional, Any
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from .prompt_manager import SyncPrompt, SyncStep
from .agent_manager import AgentManager
from .project_coordination import ProjectWorkspaceCoordinator
from .exceptions import StrategyError

logger = logging.getLogger(__name__)


class ProjectExecutionStrategy(ABC):
    """Base class for project workspace execution strategies"""
    
    def __init__(self, agent_manager: AgentManager, coordinator: ProjectWorkspaceCoordinator):
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


class ProjectParallelStrategy(ProjectExecutionStrategy):
    """Parallel execution with isolated project workspaces"""
    
    def __init__(self, agent_manager: AgentManager, coordinator: ProjectWorkspaceCoordinator):
        super().__init__(agent_manager, coordinator)
        # Track when each agent started working for minimum duration enforcement
        self.agent_start_times: Dict[int, datetime] = {}
    
    def get_description(self) -> str:
        return "Parallel execution with isolated project workspaces - each agent builds in their own project folder"
    
    async def execute(self, prompt: SyncPrompt, session_id: str) -> bool:
        """Execute tasks in parallel using project workspaces"""
        try:
            logger.info("=" * 60)
            logger.info("PROJECT-BASED PARALLEL EXECUTION")
            logger.info("=" * 60)
            
            # Get agents
            agents = self.agent_manager.agents
            if not agents:
                raise StrategyError("No agents available")
            
            num_agents = len(agents)
            logger.info(f"Distributing {len(prompt.steps)} tasks among {num_agents} agents")
            
            # Pre-divide tasks among agents
            assignments = self._divide_tasks(prompt.steps, num_agents)
            
            # Log task distribution
            for agent_id, agent_tasks in assignments.items():
                agent = self.agent_manager.get_agent_by_id(agent_id)
                if agent:
                    logger.info(f"Agent {agent_id} assigned {len(agent_tasks)} tasks in project: {agent.worktree_path}")
            
            # Record agent start times for minimum duration tracking
            current_time = datetime.now()
            for agent_id in assignments.keys():
                self.agent_start_times[agent_id] = current_time
            
            # Send initial prompt to all agents with their assignments
            logger.info("Sending initial prompts to agents...")
            await self._send_initial_prompts(prompt, assignments)
            
            # Monitor execution
            logger.info("Monitoring parallel execution...")
            success = await self._monitor_execution(session_id, assignments)
            
            if success:
                logger.info("All agents completed their tasks successfully")
                
                # Merge completed projects
                logger.info("Merging agent projects into final project...")
                merge_results = self.coordinator.merge_agent_projects()
                
                logger.info(f"Merge results: {merge_results}")
                
                if merge_results['failed_projects']:
                    logger.warning(f"Some projects failed to merge: {merge_results['failed_projects']}")
                    return False
                
                # Log final project location
                final_project_path = self.coordinator.workspace_dir / 'final-project'
                logger.info(f"✅ Final merged project available at: {final_project_path}")
                
                # Run finalization phase if enabled
                if self.agent_manager.config.get('enable_finalization', True):
                    logger.info("")
                    logger.info("Starting post-merge finalization phase...")
                    finalization_success = await self._run_finalization_phase(session_id, prompt)
                    
                    if finalization_success:
                        logger.info("🎉 PROJECT FINALIZED AND READY FOR PRODUCTION!")
                        logger.info(f"📁 Optimized project location: {final_project_path}")
                    else:
                        logger.warning("Finalization phase failed, but merged project is still available")
                        # Don't fail the entire execution if finalization fails
                        # The merged project is still usable
                else:
                    logger.info("Finalization phase disabled in configuration")
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
            
            agent = self.agent_manager.get_agent_by_id(agent_id)
            if not agent:
                continue
            
            # Build personalized prompt for this agent
            task_list = "\n".join([
                f"{idx + 1}. {task.content}"
                for idx, task in enumerate(tasks)
            ])
            
            message = f"""
{prompt.initial_prompt}

**IMPORTANT: You are working in an isolated project directory.**

You are Agent {agent_id} working in your own project folder.
Your current directory is: {agent.worktree_path or 'project/'}

ALL files you create should be in this directory or subdirectories you create.
DO NOT navigate outside this directory.
DO NOT try to access or modify xenosync code.

Your project workspace is completely isolated from other agents.

You have been assigned the following tasks:
{task_list}

INSTRUCTIONS:
1. You are in a fresh project directory - create all files here
2. Organize your code as you see fit (create src/, tests/, docs/, etc.)
3. Complete each task in sequence
4. Your work will be automatically merged with other agents' work
5. Focus on your assigned tasks only

Begin with task 1: {tasks[0].content}
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
        """Monitor execution progress with enhanced completion detection and minimum duration"""
        
        check_interval = 30  # Check every 30 seconds
        max_duration = 3600  # Maximum 1 hour
        elapsed = 0
        
        # Get configuration settings
        minimum_duration_minutes = self.agent_manager.config.get('minimum_work_duration_minutes', 10)
        require_confidence = self.agent_manager.config.get('require_completion_confidence', True)
        
        logger.info(f"Monitoring with minimum work duration: {minimum_duration_minutes} minutes")
        logger.info(f"Enhanced completion detection: {'enabled' if require_confidence else 'disabled'}")
        
        while elapsed < max_duration:
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            
            # Check progress of each agent
            all_complete = True
            status_summary = []
            agents_ready_for_completion = {}  # Track which agents meet completion criteria
            
            for agent_id, tasks in assignments.items():
                agent = self.agent_manager.get_agent_by_id(agent_id)
                if not agent:
                    continue
                
                # Get progress from project coordinator
                progress = self.coordinator.track_agent_progress(agent_id)
                
                # Calculate work duration for this agent
                start_time = self.agent_start_times.get(agent_id)
                work_duration_minutes = 0
                if start_time:
                    work_duration_minutes = (datetime.now() - start_time).total_seconds() / 60
                
                # Check minimum duration requirement
                meets_minimum_duration = work_duration_minutes >= minimum_duration_minutes
                
                if progress['status'] == 'no_project':
                    # No project yet
                    status_summary.append(f"Agent {agent_id}: No project ({work_duration_minutes:.1f}m)")
                    all_complete = False
                elif progress['status'] in ['initialized', 'in_progress']:
                    files = progress.get('files_created', 0)
                    commits = progress.get('commits', 0)
                    
                    status_parts = [f"Agent {agent_id}: Working"]
                    if files > 0:
                        status_parts.append(f"{files} files")
                    if commits > 1:  # More than initial commit
                        status_parts.append(f"{commits} commits")
                    status_parts.append(f"{work_duration_minutes:.1f}m")
                    
                    status_summary.append(" - ".join(status_parts))
                    
                    # Check if this agent is ready for completion consideration
                    if meets_minimum_duration:
                        if require_confidence:
                            # Use enhanced completion detection
                            try:
                                completion_analysis = await self.agent_manager.calculate_completion_confidence(agent_id)
                                completion_likely = completion_analysis['completion_likely']
                                confidence = completion_analysis['overall_confidence']
                                
                                if completion_likely:
                                    # Also check project quality before allowing completion
                                    if await self._validate_project_quality(agent_id, progress):
                                        agents_ready_for_completion[agent_id] = {
                                            'confidence': confidence,
                                            'duration_minutes': work_duration_minutes,
                                            'reason': 'enhanced_detection'
                                        }
                                        logger.info(f"Agent {agent_id} ready for completion: confidence={confidence:.3f}, duration={work_duration_minutes:.1f}m")
                                    else:
                                        logger.info(f"Agent {agent_id} high confidence but insufficient project quality")
                                else:
                                    all_complete = False
                            except Exception as e:
                                logger.error(f"Error in enhanced completion detection for agent {agent_id}: {e}")
                                # Fallback to basic pattern check
                                if not await self.agent_manager.check_agent_working(agent_id):
                                    if await self._validate_project_quality(agent_id, progress):
                                        agents_ready_for_completion[agent_id] = {
                                            'confidence': 0.5,
                                            'duration_minutes': work_duration_minutes,
                                            'reason': 'fallback_pattern_check'
                                        }
                                else:
                                    all_complete = False
                        else:
                            # Use basic pattern detection (legacy mode)
                            if not await self.agent_manager.check_agent_working(agent_id):
                                if await self._validate_project_quality(agent_id, progress):
                                    agents_ready_for_completion[agent_id] = {
                                        'confidence': 0.5,
                                        'duration_minutes': work_duration_minutes,
                                        'reason': 'basic_pattern_check'
                                    }
                            else:
                                all_complete = False
                    else:
                        # Agent hasn't worked long enough yet
                        remaining_minutes = minimum_duration_minutes - work_duration_minutes
                        logger.debug(f"Agent {agent_id} needs {remaining_minutes:.1f} more minutes before completion consideration")
                        all_complete = False
                        
                elif progress['status'] == 'completed':
                    files = progress.get('files_created', 0)
                    status_summary.append(f"Agent {agent_id}: Completed ({files} files, {work_duration_minutes:.1f}m)")
                    # Already marked as completed
                else:
                    status_summary.append(f"Agent {agent_id}: {progress['status']} ({work_duration_minutes:.1f}m)")
                    all_complete = False
            
            # Log status with each agent on its own line
            if status_summary:
                logger.info("Status Update:")
                for status in status_summary:
                    logger.info(f"  {status}")
            
            # Check if we should mark agents as complete
            if agents_ready_for_completion:
                logger.info(f"Agents ready for completion: {list(agents_ready_for_completion.keys())}")
                
                # Mark ready agents as complete
                for agent_id, completion_info in agents_ready_for_completion.items():
                    try:
                        self.coordinator.complete_agent_project(agent_id)
                        logger.info(f"Marked agent {agent_id} project as complete "
                                  f"(reason: {completion_info['reason']}, "
                                  f"confidence: {completion_info['confidence']:.3f}, "
                                  f"duration: {completion_info['duration_minutes']:.1f}m)")
                    except Exception as e:
                        logger.error(f"Failed to complete agent {agent_id} project: {e}")
            
            # Check if all agents are now complete
            all_actually_complete = True
            for agent_id in assignments.keys():
                progress = self.coordinator.track_agent_progress(agent_id)
                if progress['status'] != 'completed':
                    all_actually_complete = False
                    break
            
            if all_actually_complete:
                logger.info("All agents have completed their projects")
                return True
        
        logger.warning(f"Execution timeout after {max_duration} seconds")
        return False
    
    async def _validate_project_quality(self, agent_id: int, progress: Dict[str, Any]) -> bool:
        """Validate that the agent's project has substantial work before allowing completion"""
        try:
            quality_threshold = self.agent_manager.config.get('project_quality_threshold', 3)
            work_threshold = self.agent_manager.config.get('project_substantial_work_threshold', 500)
            
            files_created = progress.get('files_created', 0)
            
            # Check minimum file count (excluding README.md from initial setup)
            if files_created < quality_threshold:
                logger.debug(f"Agent {agent_id} project quality check failed: only {files_created} files (need {quality_threshold})")
                return False
            
            # Check for substantial content in files
            agent = self.agent_manager.get_agent_by_id(agent_id)
            if not agent or not agent.worktree_path:
                return False
            
            from pathlib import Path
            project_path = Path(agent.worktree_path)
            
            total_content_size = 0
            meaningful_files = 0
            
            for file_path in project_path.rglob('*'):
                if file_path.is_file() and '.git' not in str(file_path):
                    try:
                        content = file_path.read_text(encoding='utf-8', errors='ignore')
                        # Skip very small files (likely just placeholders)
                        if len(content.strip()) > 50:  # More than just a basic comment or title
                            total_content_size += len(content)
                            meaningful_files += 1
                    except Exception:
                        continue  # Skip files we can't read
            
            # Check total content threshold
            if total_content_size < work_threshold:
                logger.debug(f"Agent {agent_id} project quality check failed: only {total_content_size} chars of content (need {work_threshold})")
                return False
            
            # Check meaningful file count
            if meaningful_files < 2:  # At least 2 files with real content
                logger.debug(f"Agent {agent_id} project quality check failed: only {meaningful_files} meaningful files")
                return False
            
            logger.debug(f"Agent {agent_id} project quality check passed: {meaningful_files} files, {total_content_size} chars")
            return True
            
        except Exception as e:
            logger.error(f"Error validating project quality for agent {agent_id}: {e}")
            return False
    
    async def _run_finalization_phase(self, session_id: str, prompt: SyncPrompt) -> bool:
        """Run post-merge optimization and documentation with dedicated finalization agent"""
        try:
            logger.info("=" * 60)
            logger.info("🔧 POST-MERGE FINALIZATION PHASE")
            logger.info("=" * 60)
            
            # Get finalization settings from config
            finalization_timeout = self.agent_manager.config.get('finalization_timeout', 600)
            finalization_tasks = self.agent_manager.config.get('finalization_tasks', [
                'immediate_testing',
                'debug_and_fix',
                'core_mechanics_validation',
                'integration_testing', 
                'playability_validation',
                'production_readiness'
            ])
            
            # Get the final project path
            final_project_path = self.coordinator.workspace_dir / 'final-project'
            
            if not final_project_path.exists():
                logger.error("Final project directory does not exist, cannot run finalization")
                return False
            
            logger.info(f"Starting finalization agent for: {final_project_path}")
            
            # Build the finalization prompt
            task_descriptions = {
                'immediate_testing': "Test the application immediately to verify it works",
                'debug_and_fix': "Identify and fix any bugs, errors, or broken functionality",
                'core_mechanics_validation': "Ensure all core features and mechanics work properly",
                'integration_testing': "Test all components work together seamlessly",
                'playability_validation': "For games: ensure the game is actually playable and fun",
                'production_readiness': "Final optimization and polish for production use"
            }
            
            tasks_text = "\n".join([
                f"   {i+1}. {task_descriptions.get(task, task)}"
                for i, task in enumerate(finalization_tasks)
            ])
            
            finalization_prompt = f"""
You are an Integration Engineer & QA Specialist responsible for making this merged project ACTUALLY WORK.

**Project Location:** {final_project_path}
**Original Task:** {prompt.name}
{prompt.description}

🚨 **CRITICAL MISSION: MAKE IT WORK FIRST, OPTIMIZE LATER** 🚨

You are working in the final merged project directory that contains contributions from multiple agents.
Your PRIMARY job is to ensure the project actually functions correctly, not to optimize code.

**INTEGRATION & QA TASKS:**
{tasks_text}

**STEP-BY-STEP INSTRUCTIONS:**

1. **IMMEDIATE TESTING (HIGHEST PRIORITY)**
   - Open index.html in a browser and see if it works
   - Try to interact with the application/game immediately
   - Check browser console for any JavaScript errors
   - Test basic functionality (can you play the game? do buttons work?)
   - Document what works and what doesn't work

2. **DEBUG AND FIX CRITICAL ISSUES**
   - Fix any JavaScript errors preventing the app from running
   - Resolve missing file references (404 errors for CSS, images, sounds)
   - Fix broken HTML structure or missing elements
   - Correct any syntax errors in CSS or JavaScript
   - Ensure all required assets are present and properly linked

3. **CORE MECHANICS VALIDATION**
   - For games: Can the player move? Do controls respond? Does gameplay work?
   - For apps: Do main features function? Can users complete intended actions?
   - Test each major feature individually
   - Fix broken game mechanics, movement, collision detection
   - Ensure core functionality works before worrying about polish

4. **INTEGRATION TESTING**
   - Test how different components work together
   - Verify data flows between different parts of the application
   - Check if multiple agents' contributions integrate properly
   - Resolve conflicts between different implementations
   - Merge duplicate code ONLY if it doesn't break functionality

5. **PLAYABILITY VALIDATION (FOR GAMES)**
   - Actually play the game for several minutes
   - Check if it's fun and engaging, not just technically functional
   - Verify game rules work correctly (scoring, win/lose conditions)
   - Test edge cases (what happens when player reaches boundaries?)
   - Ensure game progression works (levels, difficulty scaling)

6. **PRODUCTION READINESS (LOWEST PRIORITY)**
   - ONLY after everything works: clean up code organization
   - Create README.md with setup instructions and how to play/use
   - Remove debug console.log statements
   - Add basic comments for complex logic
   - Minor performance optimizations if needed

**🎯 SUCCESS CRITERIA:**
- The application/game WORKS when you open it
- All major features are functional
- No critical bugs or errors
- Users can actually use/play the project successfully
- Browser console shows no errors during normal use

**⚠️ CRITICAL GUIDELINES:**
- NEVER optimize code that isn't working yet
- NEVER remove code unless you're certain it's unused
- If you find duplicate implementations, TEST both before choosing one
- Focus on making it work, not making it pretty
- When in doubt, prioritize functionality over optimization
- Test frequently as you make changes

**🔧 DEBUGGING METHODOLOGY:**
1. Test first, understand what's broken
2. Fix the most critical issues first (app won't start)
3. Move to medium issues (features don't work)
4. Finally address minor issues (polish)
5. Test again after each fix

Your success is measured by whether someone can open this project and actually use it without encountering errors.
MAKE IT WORK FIRST. Everything else is secondary.

Start by opening the project and testing it immediately to see what's broken.
"""
            
            # Spawn the finalization agent
            logger.info("Spawning finalization agent...")
            
            # Use agent manager to spawn a special finalization agent
            finalization_agent_id = await self.agent_manager.spawn_finalization_agent(
                session_id,
                final_project_path,
                finalization_prompt
            )
            
            if finalization_agent_id is None:
                logger.error("Failed to spawn finalization agent")
                return False
            
            logger.info(f"Finalization agent spawned with ID: {finalization_agent_id}")
            
            # Monitor finalization progress with timeout
            start_time = asyncio.get_event_loop().time()
            check_interval = 15  # Check every 15 seconds
            
            while (asyncio.get_event_loop().time() - start_time) < finalization_timeout:
                await asyncio.sleep(check_interval)
                
                # Check if finalization agent is still working
                agent = self.agent_manager.get_agent_by_id(finalization_agent_id)
                if not agent:
                    logger.error("Finalization agent disappeared")
                    return False
                
                # Check agent status
                if agent.status == 'completed':
                    logger.info("✅ Finalization phase completed successfully")
                    return True
                elif agent.status == 'error':
                    logger.error("Finalization agent encountered an error")
                    return False
                
                # Log progress
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                remaining = finalization_timeout - elapsed
                logger.info(f"Finalization in progress... ({elapsed}s elapsed, {remaining}s remaining)")
            
            logger.warning(f"Finalization phase timed out after {finalization_timeout} seconds")
            
            # Stop the finalization agent
            await self.agent_manager.stop_finalization_agent(finalization_agent_id)
            
            return False
            
        except Exception as e:
            logger.error(f"Finalization phase failed: {e}")
            return False


class ProjectCollaborativeStrategy(ProjectExecutionStrategy):
    """Collaborative execution with shared project components"""
    
    def get_description(self) -> str:
        return "Collaborative execution - agents coordinate on shared project components"
    
    async def execute(self, prompt: SyncPrompt, session_id: str) -> bool:
        """Execute tasks collaboratively in project workspaces"""
        
        logger.info("=" * 60)
        logger.info("PROJECT COLLABORATIVE EXECUTION")
        logger.info("=" * 60)
        
        # This strategy would implement agents working on different parts
        # of the same project with more coordination
        
        # For now, fallback to parallel
        logger.info("Collaborative strategy not yet implemented, using parallel")
        parallel = ProjectParallelStrategy(self.agent_manager, self.coordinator)
        return await parallel.execute(prompt, session_id)


class ProjectAdaptiveStrategy(ProjectExecutionStrategy):
    """Adaptive strategy that adjusts based on project requirements"""
    
    def get_description(self) -> str:
        return "Adaptive execution - automatically chooses strategy based on project analysis"
    
    async def execute(self, prompt: SyncPrompt, session_id: str) -> bool:
        """Adaptively choose strategy based on project requirements"""
        
        logger.info("=" * 60)
        logger.info("PROJECT ADAPTIVE EXECUTION")
        logger.info("=" * 60)
        
        # Analyze tasks to determine best strategy
        num_tasks = len(prompt.steps)
        num_agents = len(self.agent_manager.agents)
        
        # Simple heuristic: use parallel for many independent tasks
        if num_tasks >= num_agents * 2:
            logger.info(f"Using parallel strategy for {num_tasks} tasks")
            strategy = ProjectParallelStrategy(self.agent_manager, self.coordinator)
        else:
            logger.info(f"Using collaborative strategy for {num_tasks} tasks")
            strategy = ProjectCollaborativeStrategy(self.agent_manager, self.coordinator)
        
        return await strategy.execute(prompt, session_id)