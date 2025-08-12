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
from .file_coordination import CoordinationManager
from .tmux_manager import TmuxManager
from .execution_strategies import ExecutionStrategy, ParallelStrategy, CollaborativeStrategy


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
        self.execution_mode = config.get('execution_mode', 'parallel')  # Default to parallel
        
        # Validate execution mode
        if self.execution_mode not in ['parallel', 'collaborative']:
            logger.warning(f"Invalid execution mode '{self.execution_mode}', defaulting to 'parallel'")
            self.execution_mode = 'parallel'
        
        # Initialize multi-agent components
        self.agent_manager = AgentManager(config, num_agents=self.num_agents)
        self.coordination = CoordinationManager(config)
        self.strategy = self._get_execution_strategy()
        
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
    
    def _get_execution_strategy(self) -> ExecutionStrategy:
        """Get the appropriate execution strategy based on mode"""
        if self.execution_mode == 'collaborative':
            return CollaborativeStrategy(self.agent_manager, self.coordination)
        else:  # Default to parallel
            return ParallelStrategy(self.agent_manager, self.coordination)
    
    async def run(self, session: Session, prompt: SyncPrompt):
        """Run a multi-agent sync session"""
        self.current_session = session
        self.current_prompt = prompt
        self.running = True
        
        try:
            logger.info(f"Starting multi-agent session: {session.id}")
            logger.info(f"Mode: {self.execution_mode.upper()} | Agents: {self.num_agents}")
            
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
            
            # Initialize agents
            logger.info(f"Initializing {self.num_agents} agents...")
            await self.agent_manager.initialize_agents(session.id)
            
            # Execute using the selected strategy
            logger.info(f"Executing in {self.execution_mode} mode...")
            success = await self.strategy.execute(prompt, session.id)
            
            if not success:
                raise SyncError(f"{self.execution_mode.capitalize()} execution failed")
            
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
            
            # Always attempt tmux cleanup regardless of conditions
            self._cleanup_tmux_sessions()
    
    async def _monitor_agents(self, session: Session):
        """Monitor running agents without stopping them"""
        logger.info("=" * 60)
        logger.info(f"AGENTS EXECUTING IN {self.execution_mode.upper()} MODE")
        logger.info("=" * 60)
        
        if self.execution_mode == 'parallel':
            logger.info("📊 Parallel Execution:")
            logger.info("  • Tasks have been distributed among agents")
            logger.info("  • Each agent works independently on assigned tasks")
            logger.info("  • No coordination required between agents")
        else:  # collaborative
            logger.info("🤝 Collaborative Execution:")
            logger.info("  • All agents can see all tasks")
            logger.info("  • Agents claim work dynamically from the pool")
            logger.info("  • Coordination happens through file system")
        
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
        
        # Monitor loop
        try:
            monitor_interval = 0
            while not self.interrupted:
                # Get agent metrics periodically
                if self.agent_manager and monitor_interval % 12 == 0:  # Every minute
                    metrics = self.agent_manager.get_agent_metrics()
                    active = sum(1 for a in metrics['agents'] if a['status'] != 'stopped')
                    
                    if active > 0:
                        # Get coordination summary
                        coord_summary = self.coordination.get_coordination_summary(session.id)
                        
                        logger.info("")
                        logger.info(f"📊 Status Update:")
                        logger.info(f"  Active Agents: {active}/{self.num_agents}")
                        logger.info(f"  Tasks Completed: {coord_summary['completed_tasks']}")
                        logger.info(f"  Active Claims: {coord_summary['active_claims']}")
                        
                        if self.execution_mode == 'collaborative':
                            logger.info(f"  Messages Sent: {coord_summary['messages_sent']}")
                            if coord_summary['conflicts'] > 0:
                                logger.info(f"  ⚠️  Conflicts: {coord_summary['conflicts']}")
                
                await asyncio.sleep(5)
                monitor_interval += 1
                
        except KeyboardInterrupt:
            logger.info("\nReceived shutdown signal in monitor")
            self.interrupted = True
            
            # Ensure tmux cleanup happens
            self._cleanup_tmux_sessions()
            
            # Re-raise to propagate the interrupt
            raise
    
    def interrupt(self):
        """Interrupt the sync session"""
        logger.info("Interrupting session")
        self.interrupted = True
        self.running = False