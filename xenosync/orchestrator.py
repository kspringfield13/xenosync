"""
Module: orchestrator
Purpose: Main orchestration engine for multi-agent AI coordination

This module serves as the central control system for Xenosync, managing the entire
lifecycle of multi-agent sessions. It coordinates agent initialization, task
distribution, execution monitoring, and cleanup. The orchestrator integrates all
major subsystems including agent management, project coordination, and tmux visualization.

Key Classes:
    - XenosyncOrchestrator: Main orchestration engine

Key Functions:
    - run(): Execute a multi-agent session
    - _monitor_agents(): Monitor agent execution progress
    - _show_detailed_status(): Display system status
    - _cleanup_tmux_sessions(): Clean up terminal sessions
    - _setup_signal_handlers(): Handle graceful shutdown

Dependencies:
    - agent_manager: Agent lifecycle management
    - project_coordination: Workspace management
    - project_strategies: Execution strategies
    - tmux_manager: Terminal multiplexer integration
    - file_session_manager: Session persistence
    - prompt_manager: Task management

Usage:
    orchestrator = XenosyncOrchestrator(config, session_manager, prompt_manager)
    await orchestrator.run(session, prompt)
    
Author: Xenosync Team
Created: 2024-08-14
Modified: 2024-08-14
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
from .project_coordination import ProjectWorkspaceCoordinator
from .tmux_manager import TmuxManager
from .project_strategies import ProjectParallelStrategy


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
        self.coordination = ProjectWorkspaceCoordinator(config)
        self.strategy = ProjectParallelStrategy(self.agent_manager, self.coordination)
        
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
        self.force_merge = False  # Flag for manual merge trigger
        
        # Register signal handlers for graceful shutdown
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown and manual merge trigger"""
        try:
            def shutdown_handler(signum, frame):
                logger.info(f"Received signal {signum}, initiating graceful shutdown")
                self.interrupted = True
                self._cleanup_tmux_sessions()
            
            def merge_handler(signum, frame):
                logger.info(f"Received signal {signum} (SIGUSR1), triggering manual merge")
                self.force_merge = True
            
            # Register handlers for common termination signals
            signal.signal(signal.SIGINT, shutdown_handler)   # Ctrl+C
            signal.signal(signal.SIGTERM, shutdown_handler)  # Termination request
            signal.signal(signal.SIGUSR1, merge_handler)     # Manual merge trigger
            
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
            
            # Create session workspace directory
            workspace_dir = Path('xsync-sessions') / session.id / 'workspace'
            workspace_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created session workspace at: {workspace_dir}")
            
            # Initialize project workspace coordination
            logger.info("Initializing project workspace coordination")
            self.coordination.initialize_session(session.id, self.num_agents, workspace_dir=workspace_dir)
            
            # Set coordination manager in agent manager for work tracking
            self.agent_manager.set_coordination_manager(self.coordination)
            
            # Set strategy in agent manager for task callbacks
            self.agent_manager.set_strategy(self.strategy)
            
            # Initialize agents (will create project workspaces)
            logger.info(f"Initializing {self.num_agents} agents with project workspaces...")
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
            
            # Clean up project workspaces
            if self.coordination and session:
                try:
                    logger.info("Cleaning up project workspaces")
                    keep_projects = self.config.get('keep_projects_after_session', True)
                    cleanup_stats = self.coordination.cleanup_session(session.id, keep_projects=keep_projects)
                    logger.info(f"Cleanup stats: {cleanup_stats}")
                except Exception as e:
                    logger.error(f"Error cleaning up workspaces: {e}")
            
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
        logger.info("")
        import os
        logger.info("Manual merge triggers:")
        logger.info(f"  • Signal trigger: kill -USR1 {os.getpid()}")
        logger.info("  • File trigger: touch .xenosync_merge_now")
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
                
                # Check for manual merge triggers
                manual_merge_requested = False
                
                # Check file-based trigger
                merge_trigger_file = Path('.xenosync_merge_now')
                if merge_trigger_file.exists():
                    logger.info("")
                    logger.info("🔧 Manual merge triggered via file (.xenosync_merge_now)")
                    logger.info("")
                    manual_merge_requested = True
                    # Remove trigger file
                    try:
                        merge_trigger_file.unlink()
                    except Exception as e:
                        logger.warning(f"Failed to remove trigger file: {e}")
                
                # Check signal-based trigger
                if self.force_merge:
                    logger.info("")
                    logger.info("🔧 Manual merge triggered via signal (SIGUSR1)")
                    logger.info("")
                    manual_merge_requested = True
                    self.force_merge = False  # Reset flag
                
                # Check if all projects are completed and ready to merge
                coord_status = self.coordination.get_session_status()
                completed = coord_status.get('completed_projects', 0)
                total = coord_status.get('total_projects', 0)
                merged = coord_status.get('merged_projects', 0)
                
                # Improved merge trigger logic with dual conditions and safety checks
                should_merge = False
                merge_reason = ""
                
                # Safety check: Don't merge if already merged
                if merged > 0:
                    if manual_merge_requested:
                        logger.info("🔧 Manual merge requested, but projects already merged. Skipping.")
                elif completed == 0:
                    if manual_merge_requested:
                        logger.info("🔧 Manual merge requested, but no projects completed yet. Waiting for at least one completion.")
                else:
                    # Condition 1: Automatic merge when all projects completed
                    if completed > 0 and completed == total:
                        should_merge = True
                        merge_reason = "automatic"
                    
                    # Condition 2: Manual merge when requested with at least 1 completed
                    elif manual_merge_requested and completed > 0:
                        should_merge = True
                        merge_reason = "manual"
                
                if should_merge:
                    logger.info("")
                    if merge_reason == "manual":
                        logger.info(f"🔧 Manual merge initiated! Merging {completed}/{total} completed projects...")
                    elif merge_reason == "automatic":
                        logger.info("🎯 All agent projects completed! Starting automatic merge...")
                    logger.info("")
                    
                    try:
                        merge_results = self.coordination.merge_agent_projects()
                        
                        if merge_results['merged_projects']:
                            final_project = self.coordination.workspace_dir / 'final-project'
                            logger.info("✅ MERGE COMPLETED SUCCESSFULLY!")
                            logger.info(f"📁 Final project location: {final_project}")
                            logger.info(f"📊 Merged {len(merge_results['merged_projects'])} agent projects")
                            logger.info(f"📄 Total files in final project: {merge_results['total_files']}")
                            
                            if merge_results['conflicts']:
                                logger.warning(f"⚠️  {len(merge_results['conflicts'])} file conflicts detected:")
                                for conflict in merge_results['conflicts'][:5]:  # Show first 5
                                    agents = conflict.get('agents', [])
                                    file = conflict.get('file', 'unknown')
                                    logger.warning(f"   • {file}: agents {agents}")
                            
                            logger.info("")
                            logger.info("🎉 PROJECT READY! Check the final-project directory.")
                            logger.info("   You can now copy/move the final-project folder anywhere.")
                            logger.info("")
                            
                        else:
                            logger.error("❌ Merge failed - no projects were merged")
                            
                    except Exception as e:
                        logger.error(f"❌ Merge failed with error: {e}")
                
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
            if agent['status'] in ['working', 'completed']:
                # Get progress from project coordinator
                progress = self.coordination.track_agent_progress(agent['id'])
                if progress:
                    files_created = progress.get('files_created', 0)
                    commits = progress.get('commits', 0)
                    project_path = progress.get('project_path', 'unknown')
                    short_path = self._shorten_agent_path(project_path)
                    
                    if agent['status'] == 'working':
                        logger.info(f"    └─ Working in {short_path} ({files_created} files, {commits} commits)")
                    elif agent['status'] == 'completed':
                        logger.info(f"    └─ Completed work in {short_path} ({files_created} files, {commits} commits)")
        
        
        # Show individual agent project details
        logger.info("")
        logger.info("🔍 Agent Projects:")
        for agent_info in coord_summary.get('agents', []):
            agent_id = agent_info.get('agent_id')
            status = agent_info.get('status', 'unknown')
            files = agent_info.get('files_created', 0)
            commits = agent_info.get('commits', 0)
            
            status_icon = '🔄' if status == 'in_progress' else ('✅' if status == 'completed' else '📝')
            logger.info(f"  Agent {agent_id}: {status_icon} {status} - {files} files, {commits} commits")
        
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
            'completed': '✅',
            'idle': '💤',
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
    
    def _shorten_agent_path(self, full_path: str) -> str:
        """Shorten agent project path to ~/agent-N/project format"""
        try:
            path = Path(full_path)
            # Look for agent-N/project pattern in the path
            parts = path.parts
            for i, part in enumerate(parts):
                if part.startswith('agent-') and i + 1 < len(parts) and parts[i + 1] == 'project':
                    return f"~/{part}/project"
            # Fallback: show last 2 parts if pattern not found
            if len(parts) >= 2:
                return f"~/{'/'.join(parts[-2:])}"
            return f"~/{path.name}"
        except Exception:
            # Fallback for any path parsing errors
            return str(full_path).split('/')[-2:] if '/' in str(full_path) else str(full_path)

    async def _calculate_work_progress(self, session: Session) -> Dict[str, int]:
        """Calculate work progress from project coordination data"""
        
        # Get session status from project coordinator
        coord_status = self.coordination.get_session_status()
        
        if coord_status.get('session_id') != session.id:
            return {
                'total_tasks': 0,
                'pending_tasks': 0,
                'claimed_tasks': 0,
                'in_progress_tasks': 0,
                'completed_tasks': 0,
                'failed_tasks': 0,
                'merged_tasks': 0
            }
        
        # Get actual project statuses from coordination
        total_projects = coord_status.get('total_projects', 0)
        completed_projects = coord_status.get('completed_projects', 0)
        merged_projects = coord_status.get('merged_projects', 0)
        
        # Calculate in-progress (agents working but not complete)
        in_progress_projects = 0
        initialized_projects = 0
        
        for agent_info in coord_status.get('agents', []):
            agent_status = agent_info.get('status', 'unknown')
            if agent_status == 'in_progress':
                in_progress_projects += 1
            elif agent_status == 'initialized':
                initialized_projects += 1
        
        # If no total from coordination, get from prompt
        if total_projects == 0 and self.current_prompt and hasattr(self.current_prompt, 'steps'):
            # In project mode, each agent gets tasks, so total "projects" is num_agents
            total_projects = self.num_agents
        
        return {
            'total_tasks': total_projects,
            'pending_tasks': initialized_projects,
            'claimed_tasks': 0,  # Not used in project mode
            'in_progress_tasks': in_progress_projects,
            'completed_tasks': completed_projects,
            'failed_tasks': 0,  # Not implemented yet
            'merged_tasks': merged_projects,
            'total_files': coord_status.get('total_files', 0)
        }
    
    def interrupt(self):
        """Interrupt the sync session"""
        logger.info("Interrupting session")
        self.interrupted = True
        self.running = False