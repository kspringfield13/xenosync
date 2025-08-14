"""
Multi-Agent Orchestrator - Streamlined orchestration for parallel and collaborative execution
"""

import asyncio
import logging
import signal
import time
from typing import Optional, Dict, Any
from pathlib import Path

from .config import Config
from .file_session_manager import SessionManager, Session, SessionStatus
from .prompt_manager import PromptManager, SyncPrompt
from .exceptions import SyncError, SyncInterrupted
from .agent_manager import AgentManager
from .git_coordination import GitWorktreeCoordinator
from .tmux_manager import TmuxManager
from .git_strategies import GitParallelStrategy


logger = logging.getLogger(__name__)


class XenosyncOrchestrator:
    """Streamlined multi-agent orchestration engine"""
    
    def __init__(self, config: Config, session_manager: SessionManager, 
                 prompt_manager: PromptManager):
        self.config = config
        self.session_manager = session_manager
        self.prompt_manager = prompt_manager
        
        # Multi-agent configuration (always enabled)
        self.num_agents = max(2, config.get('num_agents', 2))  # Minimum 2 agents
        
        # Initialize multi-agent components
        self.agent_manager = AgentManager(config, num_agents=self.num_agents)
        self.coordination = GitWorktreeCoordinator(config)
        self.strategy = GitParallelStrategy(self.agent_manager, self.coordination)
        
        # Initialize TmuxManager for visual monitoring
        if config.get('use_tmux', True):
            self.tmux_manager = TmuxManager("xenosync-hive")
        else:
            self.tmux_manager = None
        
        # Session state
        self.current_session: Optional[Session] = None
        self.current_prompt: Optional[SyncPrompt] = None
        
        # Control flags
        self.running = False
        self.interrupted = False
        
        # Register signal handlers for graceful shutdown
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown"""
        try:
            def signal_handler(signum, frame):
                logger.info(f"Received signal {signum}, initiating graceful shutdown")
                self.interrupted = True
                self._cleanup_tmux_sessions()
            
            # Register handlers for common termination signals
            signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
            signal.signal(signal.SIGTERM, signal_handler)  # Termination request
            
            logger.debug("Signal handlers registered successfully")
        except Exception as e:
            logger.warning(f"Failed to register signal handlers: {e}")
    
    def _cleanup_tmux_sessions(self):
        """Clean up tmux sessions (can be called from signal handler)"""
        try:
            if self.tmux_manager:
                logger.info("Cleaning up tmux session from signal handler")
                self.tmux_manager.kill_session()
            
            # Safety net - kill any xenosync sessions
            from .tmux_manager import TmuxManager
            TmuxManager.kill_xenosync_sessions()
            
        except Exception as e:
            logger.error(f"Error during tmux cleanup: {e}")
    

    
    async def run(self, session: Session, prompt: SyncPrompt):
        """Run a multi-agent sync session"""
        self.current_session = session
        self.current_prompt = prompt
        self.running = True
        
        try:
            logger.info(f"Starting multi-agent session: {session.id}")
            logger.info(f"Agents: {self.num_agents}")
            
            # Create tmux session for visual monitoring
            if self.tmux_manager and self.tmux_manager.is_tmux_available():
                logger.info(f"Creating tmux session for {self.num_agents} agents")
                self.tmux_manager.create_session(self.num_agents)
                self.agent_manager.set_tmux_manager(self.tmux_manager)
                
                # Open monitoring terminal if enabled
                if self.config.get('auto_open_terminal', True):
                    logger.info("Opening monitoring terminal")
                    self.tmux_manager.open_monitoring_terminal(
                        preferred_terminal=self.config.get('preferred_terminal'),
                        auto_open=True
                    )
            
            # Initialize git worktree session
            logger.info("Initializing git worktree coordination")
            self.coordination.initialize_session(session.id, self.num_agents)
            
            # Set coordination manager in agent manager for work tracking
            self.agent_manager.set_coordination_manager(self.coordination)
            
            # Set strategy in agent manager for task callbacks
            self.agent_manager.set_strategy(self.strategy)
            
            # Initialize agents (will create worktrees)
            logger.info(f"Initializing {self.num_agents} agents with worktrees...")
            await self.agent_manager.initialize_agents(session.id)
            
            # Execute using the selected strategy
            logger.info(f"Executing tasks in parallel...")
            success = await self.strategy.execute(prompt, session.id)
            
            if not success:
                raise SyncError(f"Parallel execution failed")
            
            # Mark session as completed
            self.session_manager.update_session_status(
                session.id, SessionStatus.COMPLETED
            )
            
            # Enter monitoring mode - keep agents alive
            await self._monitor_agents(session)
            
        except SyncInterrupted:
            logger.info("Session interrupted by user")
            self.session_manager.update_session_status(
                session.id, SessionStatus.INTERRUPTED
            )
        except Exception as e:
            logger.error(f"Session failed: {e}")
            self.session_manager.update_session_status(
                session.id, SessionStatus.FAILED, error=str(e)
            )
            raise
        finally:
            self.running = False
            
            # Always attempt agent cleanup
            if self.agent_manager:
                force_exit = self.interrupted
                await self.agent_manager.shutdown(force_exit=force_exit)
            
            # Clean up git worktrees
            if self.coordination and session:
                try:
                    logger.info("Cleaning up git worktrees")
                    keep_branches = self.config.get('keep_branches_after_session', False)
                    cleanup_stats = self.coordination.cleanup_session(session.id, keep_branches=keep_branches)
                    logger.info(f"Cleanup stats: {cleanup_stats}")
                except Exception as e:
                    logger.error(f"Error cleaning up worktrees: {e}")
            
            # Always attempt tmux cleanup regardless of conditions
            self._cleanup_tmux_sessions()
    
    async def _monitor_agents(self, session: Session):
        """Monitor running agents with accurate status tracking"""
        logger.info("=" * 60)
        logger.info("AGENTS EXECUTING IN PARALLEL MODE")
        logger.info("=" * 60)
        
        logger.info("📊 Parallel Execution:")
        logger.info("  • Tasks have been distributed among agents")
        logger.info("  • Each agent works independently on assigned tasks")
        logger.info("  • No coordination required between agents")
        
        if self.tmux_manager:
            logger.info("")
            logger.info(f"✓ Agents running in tmux session: {self.tmux_manager.session}")
            logger.info("")
            logger.info("To view agents:")
            logger.info(f"  tmux attach -t {self.tmux_manager.session}")
            logger.info("")
            logger.info("Navigation:")
            logger.info("  • Ctrl+B, 1-N = Switch between agent panes")
            logger.info("  • Ctrl+B, d   = Detach from tmux")
            logger.info("  • Ctrl+B, [   = Scroll mode (q to exit)")
        
        logger.info("")
        logger.info("Press Ctrl+C to shutdown agents and exit")
        logger.info("=" * 60)
        
        # Initialize tracking variables
        last_status_check = time.time()
        status_interval = 30  # Show status every 30 seconds
        
        # Monitor loop
        try:
            while not self.interrupted:
                current_time = time.time()
                
                # Show detailed status update every interval
                if current_time - last_status_check >= status_interval:
                    await self._show_detailed_status(session)
                    last_status_check = current_time
                
                await asyncio.sleep(5)
                
        except KeyboardInterrupt:
            logger.info("\nReceived shutdown signal in monitor")
            self.interrupted = True
            
            # Ensure tmux cleanup happens
            self._cleanup_tmux_sessions()
            
            # Re-raise to propagate the interrupt
            raise
    
    async def _show_detailed_status(self, session: Session):
        """Display detailed status of all agents and tasks"""
        
        # Get agent statuses from agent_manager
        agent_metrics = self.agent_manager.get_agent_metrics()
        
        # Get coordination data from git
        coord_summary = self.coordination.get_session_status()
        
        # Get actual work progress
        work_progress = await self._calculate_work_progress(session)
        
        # Display formatted status
        logger.info("")
        logger.info("=" * 60)
        logger.info("📊 SYSTEM STATUS UPDATE")
        logger.info("-" * 60)
        
        # Agent Status
        logger.info("🤖 Agents:")
        for agent in agent_metrics['agents']:
            status_icon = self._get_status_icon(agent['status'])
            uptime = self._format_uptime(agent['uptime'])
            logger.info(f"  Agent {agent['id']}: {status_icon} {agent['status'].upper()} (uptime: {uptime})")
            
            # Show what the agent is working on if available
            if agent['status'] == 'working':
                # Get progress from git coordinator
                progress = self.coordination.track_agent_progress(agent['id'])
                if progress and progress.get('task_number'):
                    task_num = progress['task_number']
                    branch = progress.get('branch', 'unknown')
                    commits = progress.get('commits', 0)
                    logger.info(f"    └─ Task {task_num} on branch {branch} ({commits} commits)")
        
        # Work Progress
        logger.info("")
        logger.info("📝 Work Progress:")
        logger.info(f"  Total Tasks: {work_progress['total_tasks']}")
        logger.info(f"  Pending: {work_progress.get('pending_tasks', 0)}")
        logger.info(f"  Claimed: {work_progress['claimed_tasks']}")
        logger.info(f"  In Progress: {work_progress['in_progress_tasks']}")
        logger.info(f"  Completed: {work_progress['completed_tasks']} ✓")
        logger.info(f"  Failed: {work_progress['failed_tasks']} ✗")
        
        if work_progress['total_tasks'] > 0:
            completion_pct = (work_progress['completed_tasks'] / work_progress['total_tasks']) * 100
            logger.info(f"  Progress: {completion_pct:.1f}%")
        
        # File Activity
        if coord_summary.get('files_modified'):
            logger.info("")
            logger.info("📁 Recent File Activity:")
            for file in coord_summary['files_modified'][-5:]:  # Last 5 files
                logger.info(f"  • {file}")
        
        # Potential Issues
        if coord_summary.get('conflicts', 0) > 0:
            logger.info("")
            logger.info(f"⚠️  Warning: {coord_summary['conflicts']} file conflicts detected")
        
        stale_claims = coord_summary.get('stale_claims', 0)
        if stale_claims > 0:
            logger.info(f"⚠️  Warning: {stale_claims} stale work claims")
        
        logger.info("=" * 60)
    
    def _get_status_icon(self, status: str) -> str:
        """Get icon for agent status"""
        icons = {
            'working': '🔄',
            'idle': '✅',
            'error': '❌',
            'stopped': '⏹️',
            'starting': '🚀'
        }
        return icons.get(status.lower(), '❓')

    def _format_uptime(self, seconds: float) -> str:
        """Format uptime in human-readable format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    async def _calculate_work_progress(self, session: Session) -> Dict[str, int]:
        """Calculate actual work progress from git coordination data"""
        
        # Get session status from git coordinator
        git_status = self.coordination.get_session_status()
        
        if git_status.get('status') == 'no_session':
            return {
                'total_tasks': 0,
                'pending_tasks': 0,
                'claimed_tasks': 0,
                'in_progress_tasks': 0,
                'completed_tasks': 0,
                'failed_tasks': 0
            }
        
        # Extract task counts from git status
        total_tasks = git_status.get('total_tasks', 0)
        completed_tasks = git_status.get('completed_tasks', 0)
        in_progress_tasks = git_status.get('in_progress_tasks', 0)
        assigned_tasks = git_status.get('assigned_tasks', 0)
        
        # Calculate failed (if any tasks are marked failed in agent status)
        failed_tasks = 0
        for agent in git_status.get('agents', []):
            for task in agent.get('tasks', []):
                if task.get('status') == 'failed':
                    failed_tasks += 1
        
        # If no total from git status, get from prompt
        if total_tasks == 0 and self.current_prompt and hasattr(self.current_prompt, 'steps'):
            total_tasks = len(self.current_prompt.steps)
        
        return {
            'total_tasks': total_tasks,
            'pending_tasks': total_tasks - (assigned_tasks + in_progress_tasks + completed_tasks + failed_tasks),
            'claimed_tasks': assigned_tasks,
            'in_progress_tasks': in_progress_tasks,
            'completed_tasks': completed_tasks,
            'failed_tasks': failed_tasks
        }
    
    def interrupt(self):
        """Interrupt the sync session"""
        logger.info("Interrupting session")
        self.interrupted = True
        self.running = False