"""
Build Orchestrator - Core orchestration logic using asyncio
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path

from .config import Config
from .session_manager import SessionManager, Session, SessionStatus
from .prompt_manager import PromptManager, SyncPrompt
from .claude_interface import ClaudeInterface
from .exceptions import SyncError, SyncInterrupted
from .agent_manager import AgentManager
from .coordination import CoordinationManager
from .tmux_manager import TmuxManager
from .execution_strategies import (
    ExecutionMode, ExecutionStrategy, SequentialStrategy,
    ParallelStrategy, CollaborativeStrategy, DistributedStrategy, HybridStrategy
)


logger = logging.getLogger(__name__)


class XenosyncOrchestrator:
    """Main orchestration engine for sync sessions"""
    
    def __init__(self, config: Config, session_manager: SessionManager, 
                 prompt_manager: PromptManager):
        self.config = config
        self.session_manager = session_manager
        self.prompt_manager = prompt_manager
        self.claude = ClaudeInterface(config)
        
        # Multi-agent support
        self.multi_agent_enabled = config.get('multi_agent_enabled', False)
        self.num_agents = config.get('num_agents', 1)
        self.execution_mode = config.get('execution_mode', 'sequential')
        
        # Initialize multi-agent components if needed
        if self.multi_agent_enabled:
            self.agent_manager = AgentManager(config, num_agents=self.num_agents)
            self.coordination = CoordinationManager(config)
            self.strategy = self._get_execution_strategy()
            # Initialize TmuxManager for visual monitoring if enabled
            if config.get('use_tmux', True):
                self.tmux_manager = TmuxManager(f"xenosync-hive")
            else:
                self.tmux_manager = None
        else:
            self.agent_manager = None
            self.coordination = None
            self.strategy = None
            self.tmux_manager = None
        
        # State tracking
        self.current_session: Optional[Session] = None
        self.current_prompt: Optional[SyncPrompt] = None
        self.current_step = 0
        self.last_output_time = time.time()
        self.last_output_hash = ""
        self.idle_count = 0
        
        # Control flags
        self.running = False
        self.interrupted = False
    
    def _get_execution_strategy(self) -> ExecutionStrategy:
        """Get the appropriate execution strategy based on mode"""
        mode_map = {
            'sequential': SequentialStrategy,
            'parallel': ParallelStrategy,
            'collaborative': CollaborativeStrategy,
            'distributed': DistributedStrategy,
            'hybrid': HybridStrategy
        }
        
        strategy_class = mode_map.get(self.execution_mode, SequentialStrategy)
        return strategy_class(self.agent_manager, self.coordination)
    
    async def run(self, session: Session, prompt: SyncPrompt):
        """Run a sync session"""
        self.current_session = session
        self.current_prompt = prompt
        self.running = True
        
        try:
            logger.info(f"Starting sync session: {session.id}")
            
            # Check if multi-agent mode
            if self.multi_agent_enabled:
                logger.info(f"Starting multi-agent execution with {self.num_agents} agents in {self.execution_mode} mode")
                await self._run_multi_agent(session, prompt)
            else:
                # Single agent mode (traditional)
                await self._run_single_agent(session, prompt)
            
            # Mark session as completed
            self.session_manager.update_session_status(
                session.id, SessionStatus.COMPLETED
            )
            
        except SyncInterrupted:
            logger.info("Build interrupted by user")
            self.session_manager.update_session_status(
                session.id, SessionStatus.INTERRUPTED
            )
        except Exception as e:
            logger.error(f"Build failed: {e}")
            self.session_manager.update_session_status(
                session.id, SessionStatus.FAILED, error=str(e)
            )
            raise
        finally:
            self.running = False
            if self.multi_agent_enabled and self.agent_manager:
                # Only force exit if interrupted, otherwise keep agents running
                force_exit = self.interrupted
                await self.agent_manager.shutdown(force_exit=force_exit)
                
                # Clean up tmux session if forced
                if force_exit and self.tmux_manager:
                    self.tmux_manager.kill_session()
            else:
                await self.claude.stop()
    
    async def _run_single_agent(self, session: Session, prompt: SyncPrompt):
        """Run traditional single-agent execution"""
        # Initialize Claude
        await self.claude.start(session.id)
        
        # Send initial prompt
        await self._send_initial_prompt()
        
        # Wait for TODO list creation if configured
        if self.config.get('wait_for_todo', True):
            await self._wait_for_todo_list()
        
        # Main orchestration loop
        await self._orchestration_loop()
    
    async def _run_multi_agent(self, session: Session, prompt: SyncPrompt):
        """Run multi-agent execution using selected strategy"""
        # Create tmux session for visual monitoring if available
        if self.tmux_manager and self.tmux_manager.is_tmux_available():
            logger.info(f"Creating tmux session for {self.num_agents} agents")
            self.tmux_manager.create_session(self.num_agents)
            # Pass tmux manager to agent manager
            self.agent_manager.set_tmux_manager(self.tmux_manager)
        
        # Initialize agents
        await self.agent_manager.initialize_agents(session.id)
        
        # No need to initialize coordination - it uses session_id in each method call
        
        # Execute using the selected strategy
        success = await self.strategy.execute(prompt, session.id)
        
        if not success:
            raise SyncError("Multi-agent execution failed")
        
        # Enter monitoring mode - keep agents alive
        await self._monitor_agents(session)
    
    async def _send_initial_prompt(self):
        """Send the initial build prompt to Claude"""
        logger.info("Sending initial prompt")
        
        initial_content = self.current_prompt.initial_prompt
        if not initial_content:
            raise SyncError("No initial prompt content found")
        
        await self.claude.send_message(initial_content)
        
        # Log to session
        self.session_manager.log_event(
            self.current_session.id,
            'initial_prompt_sent',
            {'content_length': len(initial_content)}
        )
        
        # Reset idle tracking
        self.last_output_time = time.time()
    
    async def _wait_for_todo_list(self):
        """Wait for Claude to create initial TODO list"""
        logger.info("Waiting for TODO list creation")
        
        max_wait = self.config.get('todo_wait_timeout', 90)  # Default 90 seconds
        check_interval = 2
        elapsed = 0
        
        # Get TODO patterns from config or use defaults
        todo_patterns = self.config.get('todo_patterns', [
            'todos', 'todo', 'task', 'steps', 'plan', 'ready',
            'update todos', 'todo list', 'task list', 'action items',
            'next steps', 'implementation plan', 'sync steps'
        ])
        
        while elapsed < max_wait:
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            
            # Check Claude output - capture configured number of lines
            capture_lines = self.config.get('todo_capture_lines', 150)
            output = await self.claude.get_recent_output(lines=capture_lines)
            output_lower = output.lower()
            
            # Debug logging
            if elapsed % 10 == 0:  # Log every 10 seconds
                logger.debug(f"Checking for TODO list... (elapsed: {elapsed}s)")
                logger.debug(f"Output length: {len(output)} chars")
            
            # Look for TODO list indicators (case-insensitive)
            has_todo = any(pattern in output_lower for pattern in todo_patterns)
            
            # Better idle detection - check if last non-empty line is the prompt
            lines = output.strip().split('\n')
            last_line = ''
            for line in reversed(lines):
                if line.strip():
                    last_line = line.strip()
                    break
            
            # Check if we're at a Claude prompt
            is_at_prompt = (
                last_line == '>' or 
                last_line.endswith('>') or
                (len(lines) > 1 and lines[-1].strip() == '' and lines[-2].strip() == '>')
            )
            
            # Check if Claude is busy
            is_busy = any(
                indicator in output_lower 
                for indicator in ['thinking', 'typing', 'processing', '...']
            )
            
            logger.debug(f"TODO found: {has_todo}, At prompt: {is_at_prompt}, Busy: {is_busy}")
            
            if has_todo and is_at_prompt and not is_busy:
                # Wait a bit more to ensure Claude is done
                await asyncio.sleep(3)
                
                # Double-check idle state
                new_output = await self.claude.get_recent_output(lines=10)
                new_lines = new_output.strip().split('\n')
                still_at_prompt = any(line.strip() in ['>', '> '] for line in new_lines[-3:])
                
                if still_at_prompt:
                    logger.info("TODO list detected and Claude is ready, sending --continue")
                    await self.claude.send_message("--continue")
                    
                    self.session_manager.log_event(
                        self.current_session.id,
                        'initial_continue_sent',
                        {'wait_time': elapsed}
                    )
                    return
        
        # If we timeout, log what we found
        logger.warning(f"TODO list wait timeout after {elapsed}s")
        logger.debug(f"Final output sample: {output[-200:] if len(output) > 200 else output}")
        
        # Save debug output if configured
        if self.config.get('debug_output', False):
            debug_file = self.config.sessions_dir / 'debug' / f"{self.current_session.id}_todo_timeout.txt"
            debug_file.parent.mkdir(parents=True, exist_ok=True)
            with open(debug_file, 'w') as f:
                f.write(f"TODO detection timeout at {datetime.now()}\n")
                f.write(f"Elapsed: {elapsed}s\n")
                f.write(f"TODO patterns: {todo_patterns}\n")
                f.write(f"Output length: {len(output)} chars\n")
                f.write(f"\n--- Full Output ---\n{output}\n")
            logger.info(f"Debug output saved to {debug_file}")
    
    async def _orchestration_loop(self):
        """Main orchestration loop"""
        profile = self.config.profile
        step_check_interval = 60  # Check every minute
        last_step_time = time.time()
        
        while self.running and not self.interrupted:
            await asyncio.sleep(20)  # Check every 20 seconds
            
            current_time = time.time()
            time_since_last_step = current_time - last_step_time
            
            # Check for idle state
            if self.config.auto_continue:
                await self._check_and_handle_idle()
            
            # Check if it's time for next step
            if time_since_last_step > step_check_interval:
                should_send = await self._should_send_next_step(time_since_last_step)
                
                if should_send:
                    success = await self._send_next_step()
                    if success:
                        last_step_time = current_time
                    else:
                        # All steps completed
                        logger.info("All sync steps completed")
                        break
            
            # Check if Claude is still running
            if not await self.claude.is_running():
                logger.warning("Claude session ended unexpectedly")
                break
    
    async def _check_and_handle_idle(self):
        """Check if Claude is idle and send continue if needed"""
        profile = self.config.profile
        current_time = time.time()
        
        # Get recent output with more lines for better context
        output = await self.claude.get_recent_output(lines=20)
        output_hash = hash(output)
        
        # Check if output has changed
        if output_hash != self.last_output_hash:
            self.last_output_hash = output_hash
            self.last_output_time = current_time
            self.idle_count = 0
            return
        
        # Calculate idle time
        idle_time = current_time - self.last_output_time
        
        # Check if we should intervene
        if idle_time > profile.idle_threshold:
            # Better prompt detection
            lines = output.strip().split('\n')
            
            # Find last non-empty line
            last_line = ''
            for line in reversed(lines):
                if line.strip():
                    last_line = line.strip()
                    break
            
            # Check if we're at a Claude prompt
            is_at_prompt = (
                last_line == '>' or 
                last_line == '> ' or
                last_line.endswith('>') or
                # Check if prompt is on its own line
                (len(lines) > 1 and any(line.strip() in ['>', '> '] for line in lines[-3:]))
            )
            
            # Check if Claude is busy (expanded indicators)
            output_lower = output.lower()
            is_busy = any(
                indicator in output_lower 
                for indicator in ['thinking', 'typing', 'processing', 'writing', 
                                'creating', 'building', 'implementing', '...']
            )
            
            # Don't intervene if waiting for next step (expanded phrases)
            waiting_phrases = [
                'ready.', 'done.', 'finished.', 'complete.', 'completed step',
                'step complete', 'task complete', 'all set', 'waiting for',
                'please provide', 'next step'
            ]
            is_waiting_for_step = any(
                phrase in output_lower for phrase in waiting_phrases
            )
            
            # Debug logging
            if self.idle_count == 0:
                logger.debug(f"Idle check - At prompt: {is_at_prompt}, Busy: {is_busy}, Waiting: {is_waiting_for_step}")
            
            if is_at_prompt and not is_busy and not is_waiting_for_step:
                self.idle_count += 1
                
                # Only send continue after multiple idle detections
                if self.idle_count >= 2:
                    logger.info(f"Claude idle for {idle_time:.1f}s (count: {self.idle_count}), sending --continue")
                    await self.claude.send_message("--continue")
                    
                    self.session_manager.log_event(
                        self.current_session.id,
                        'idle_continue_sent',
                        {'idle_time': idle_time, 'idle_count': self.idle_count}
                    )
                    
                    # Reset tracking
                    self.last_output_time = current_time
                    self.idle_count = 0
                    
                    # Give Claude time to respond
                    await asyncio.sleep(2)
    
    async def _should_send_next_step(self, time_since_last_step: float) -> bool:
        """Determine if we should send the next step"""
        profile = self.config.profile
        
        # Check minimum time
        if time_since_last_step < profile.min_step_duration:
            return False
        
        # Force send if maximum time reached
        if time_since_last_step > profile.step_interval:
            logger.info("Maximum step interval reached")
            return True
        
        # Check if Claude is ready
        output = await self.claude.get_recent_output(lines=50)
        output_lower = output.lower()
        lines = output.strip().split('\n')
        
        # Check if at prompt (same logic as idle detection)
        last_line = ''
        for line in reversed(lines):
            if line.strip():
                last_line = line.strip()
                break
        
        is_at_prompt = (
            last_line == '>' or 
            last_line == '> ' or
            last_line.endswith('>') or
            (len(lines) > 1 and any(line.strip() in ['>', '> '] for line in lines[-3:]))
        )
        
        # Look for completion indicators (case-insensitive)
        completion_phrases = [
            'ready.', 'done.', 'finished.', 'complete.', 'completed',
            'step complete', "i've completed", 'i have completed',
            'successfully created', 'successfully implemented',
            'task complete', 'all set', 'ready for the next'
        ]
        
        has_completion = any(phrase in output_lower for phrase in completion_phrases)
        
        # Check if busy (expanded list)
        is_busy = any(
            word in output_lower for word in 
            ['thinking', 'typing', 'processing', 'working', 'building',
             'compiling', 'creating', 'implementing', 'writing', 'generating',
             'analyzing', 'designing', 'developing']
        )
        
        if is_at_prompt and has_completion and not is_busy:
            logger.info("Claude appears ready for next step")
            return True
        
        # Check for idle after minimum time + delay
        if time_since_last_step > (profile.min_step_duration + profile.idle_check_delay):
            # Check if output is stagnant
            old_output = await self.claude.get_recent_output(lines=10, offset=10)
            await asyncio.sleep(10)
            new_output = await self.claude.get_recent_output(lines=10)
            
            if old_output == new_output:
                logger.info("No new output detected, proceeding to next step")
                return True
        
        return False
    
    async def _send_next_step(self) -> bool:
        """Send the next build step"""
        self.current_step += 1
        
        if self.current_step > len(self.current_prompt.steps):
            return False  # All steps completed
        
        step = self.current_prompt.steps[self.current_step - 1]
        logger.info(f"Sending step {self.current_step}/{len(self.current_prompt.steps)}")
        
        # Optional delay before sending
        await asyncio.sleep(5)
        
        # Send step content
        await self.claude.send_message(step.content)
        
        # Update session
        self.session_manager.update_step_progress(
            self.current_session.id,
            self.current_step,
            'in_progress'
        )
        
        # Log event
        self.session_manager.log_event(
            self.current_session.id,
            'step_sent',
            {
                'step_number': self.current_step,
                'step_description': step.description[:100] if step.description else None
            }
        )
        
        # Log next step timing
        profile = self.config.profile
        next_step_time = datetime.now() + timedelta(seconds=profile.min_step_duration)
        logger.info(f"Next step no earlier than {next_step_time.strftime('%H:%M:%S')}")
        
        return True
    
    async def _monitor_agents(self, session: Session):
        """Monitor running agents without stopping them"""
        logger.info("=" * 60)
        logger.info("AGENTS COMPLETED INITIAL EXECUTION")
        logger.info("=" * 60)
        
        if self.tmux_manager:
            logger.info(f"✓ Agents are still running in tmux session: {self.tmux_manager.session}")
            logger.info(f"")
            logger.info(f"To view agents working:")
            logger.info(f"  tmux attach -t {self.tmux_manager.session}")
            logger.info(f"")
            logger.info(f"Navigation in tmux:")
            logger.info(f"  • Ctrl+B, 1  = Switch to agents window")
            logger.info(f"  • Ctrl+B, d  = Detach from tmux")
            logger.info(f"  • Ctrl+B, [  = Scroll mode (q to exit)")
            logger.info(f"")
        
        logger.info("Press Ctrl+C to shutdown agents and exit")
        logger.info("=" * 60)
        
        # Monitor loop - just keep alive
        try:
            while not self.interrupted:
                # Get agent metrics periodically
                if self.agent_manager:
                    metrics = self.agent_manager.get_agent_metrics()
                    active = sum(1 for a in metrics['agents'] if a['status'] != 'stopped')
                    if active > 0 and int(time.time()) % 60 == 0:  # Log every minute
                        logger.debug(f"Active agents: {active}, Summary: {metrics['summary']}")
                
                await asyncio.sleep(5)
                
        except KeyboardInterrupt:
            logger.info("\nReceived shutdown signal")
            self.interrupted = True
    
    def interrupt(self):
        """Interrupt the sync session"""
        logger.info("Interrupting sync session")
        self.interrupted = True
        self.running = False