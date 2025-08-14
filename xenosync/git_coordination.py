"""
Git Worktree-based Coordination System
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

from .config import Config
from .exceptions import CoordinationError
from .git_utils import (
    WorktreeInfo, CommitInfo, ConflictInfo,
    create_worktree, remove_worktree, list_worktrees, prune_worktrees,
    get_current_branch, get_branch_commits, check_merge_conflicts,
    create_branch, delete_branch, merge_branch, commit_changes,
    get_status, enable_rerere, cleanup_worktree_branches,
    run_git_command, GitCommandError
)

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task status in git-based system"""
    ASSIGNED = "assigned"      # Branch created, task assigned
    IN_PROGRESS = "in_progress" # Commits detected on branch
    COMPLETED = "completed"     # Branch merged to main
    FAILED = "failed"          # Merge failed or agent error


@dataclass
class AgentTask:
    """Task assigned to an agent"""
    task_number: int
    agent_id: int
    agent_uid: str
    branch_name: str
    description: str
    status: TaskStatus
    assigned_at: datetime
    completed_at: Optional[datetime] = None
    commit_count: int = 0
    files_modified: List[str] = None
    merge_commit: Optional[str] = None
    baseline_commit: Optional[str] = None  # Track starting commit for accurate counting
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['status'] = self.status.value
        data['assigned_at'] = self.assigned_at.isoformat()
        if self.completed_at:
            data['completed_at'] = self.completed_at.isoformat()
        return data


@dataclass
class AgentWorktree:
    """Agent worktree information"""
    agent_id: int
    agent_uid: str
    session_id: str
    worktree_path: Path
    base_branch: str
    current_branch: Optional[str] = None
    created_at: datetime = None
    tasks: List[AgentTask] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.tasks is None:
            self.tasks = []


class GitWorktreeCoordinator:
    """Manages agent coordination using git worktrees"""
    
    def __init__(self, config: Config):
        self.config = config
        self.repo_root = Path.cwd()  # Assume we're in the repo root
        self.worktrees_dir = self.repo_root / '.worktrees'
        self.worktrees_dir.mkdir(exist_ok=True)
        
        # Track agent worktrees
        self.agent_worktrees: Dict[int, AgentWorktree] = {}
        
        # Session tracking
        self.current_session_id: Optional[str] = None
        self.session_base_branch: Optional[str] = None
        
        # Enable rerere for automatic conflict resolution
        enable_rerere(global_config=True)
        
        # Merge strategy configuration
        self.merge_strategy = config.get('merge_strategy', 'sequential')
        self.conflict_resolution = config.get('conflict_resolution', 'manual')
        
        logger.info(f"Initialized GitWorktreeCoordinator at {self.repo_root}")
    
    def initialize_session(self, session_id: str, num_agents: int) -> str:
        """
        Initialize a new session with base branch
        
        Args:
            session_id: Unique session identifier
            num_agents: Number of agents in the session
            
        Returns:
            Base branch name for the session
        """
        self.current_session_id = session_id
        self.session_base_branch = f"session/{session_id[:8]}/base"
        
        # Create session base branch from main
        try:
            create_branch(self.session_base_branch, base_branch='main')
            logger.info(f"Created session base branch: {self.session_base_branch}")
        except GitCommandError as e:
            if "already exists" in str(e):
                logger.warning(f"Session branch already exists: {self.session_base_branch}")
            else:
                raise
        
        # Prune any stale worktrees
        pruned = prune_worktrees()
        if pruned > 0:
            logger.info(f"Pruned {pruned} stale worktrees")
        
        return self.session_base_branch
    
    def create_agent_worktree(self, agent_id: int, agent_uid: str, 
                            session_id: str) -> Tuple[Path, str]:
        """
        Create a worktree for an agent
        
        Args:
            agent_id: Agent ID
            agent_uid: Unique agent identifier
            session_id: Session ID
            
        Returns:
            Tuple of (worktree_path, branch_name)
        """
        # Create worktree path
        worktree_path = self.worktrees_dir / f"agent-{agent_id}"
        
        # Create branch name
        branch_name = f"agent-{agent_id}/session-{session_id[:8]}"
        
        # Remove existing worktree if it exists
        if worktree_path.exists():
            logger.warning(f"Removing existing worktree at {worktree_path}")
            remove_worktree(worktree_path, force=True)
        
        # Create the worktree
        try:
            worktree_info = create_worktree(
                path=worktree_path,
                branch=branch_name,
                base_branch=self.session_base_branch or 'main',
                create_branch=True
            )
            
            logger.info(f"Created worktree for agent {agent_id} at {worktree_path}")
            
            # Track the worktree
            agent_wt = AgentWorktree(
                agent_id=agent_id,
                agent_uid=agent_uid,
                session_id=session_id,
                worktree_path=worktree_path,
                base_branch=branch_name,
                current_branch=branch_name
            )
            self.agent_worktrees[agent_id] = agent_wt
            
            # Initialize .gitignore in worktree if needed
            self._setup_worktree_gitignore(worktree_path)
            
            return worktree_path, branch_name
            
        except Exception as e:
            logger.error(f"Failed to create worktree for agent {agent_id}: {e}")
            raise CoordinationError(f"Failed to create worktree: {e}")
    
    def _setup_worktree_gitignore(self, worktree_path: Path):
        """Setup gitignore for agent worktree"""
        gitignore_path = worktree_path / '.gitignore'
        if not gitignore_path.exists():
            # Copy main .gitignore if it exists
            main_gitignore = self.repo_root / '.gitignore'
            if main_gitignore.exists():
                import shutil
                shutil.copy2(main_gitignore, gitignore_path)
    
    def assign_task(self, agent_id: int, task_number: int, 
                   task_description: str) -> str:
        """
        Assign a task to an agent by creating a task branch
        
        Args:
            agent_id: Agent ID
            task_number: Task number
            task_description: Description of the task
            
        Returns:
            Task branch name
        """
        if agent_id not in self.agent_worktrees:
            raise CoordinationError(f"Agent {agent_id} has no worktree")
        
        agent_wt = self.agent_worktrees[agent_id]
        
        # Create task branch name
        task_branch = f"agent-{agent_id}/task-{task_number}"
        
        # Create branch in agent's worktree
        try:
            # Switch to agent's worktree directory
            cwd = agent_wt.worktree_path
            
            # Create and checkout task branch
            create_branch(task_branch, base_branch=agent_wt.base_branch, cwd=cwd)
            
            # Get current commit as baseline
            baseline_commit = run_git_command(['rev-parse', 'HEAD'], cwd=cwd)[0].strip()
            
            # Create task object
            task = AgentTask(
                task_number=task_number,
                agent_id=agent_id,
                agent_uid=agent_wt.agent_uid,
                branch_name=task_branch,
                description=task_description,
                status=TaskStatus.ASSIGNED,
                assigned_at=datetime.now(),
                files_modified=[],
                baseline_commit=baseline_commit
            )
            
            agent_wt.tasks.append(task)
            agent_wt.current_branch = task_branch
            
            logger.info(f"Assigned task {task_number} to agent {agent_id} on branch {task_branch}")
            
            # Create initial commit to mark task start
            commit_message = f"Task {task_number}: Begin - {task_description[:50]}"
            commit_changes(commit_message, files=[], cwd=cwd)
            
            return task_branch
            
        except Exception as e:
            logger.error(f"Failed to assign task {task_number} to agent {agent_id}: {e}")
            raise CoordinationError(f"Failed to assign task: {e}")
    
    def track_agent_progress(self, agent_id: int) -> Dict[str, Any]:
        """
        Track progress of an agent's current task
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Progress information
        """
        if agent_id not in self.agent_worktrees:
            return {'status': 'no_worktree'}
        
        agent_wt = self.agent_worktrees[agent_id]
        
        if not agent_wt.current_branch:
            return {'status': 'no_task'}
        
        # Get current task
        current_task = None
        for task in agent_wt.tasks:
            if task.branch_name == agent_wt.current_branch:
                current_task = task
                break
        
        if not current_task:
            return {'status': 'task_not_found'}
        
        # Get git status in worktree
        status = get_status(cwd=agent_wt.worktree_path)
        
        # Get commits made since task was assigned (only agent's work)
        commits = get_branch_commits(
            current_task.branch_name,
            limit=100,  # Get all new commits
            since_commit=current_task.baseline_commit,
            cwd=agent_wt.worktree_path
        )
        
        # Update task status based on activity
        if commits:  # Any commits since baseline = agent is working
            current_task.status = TaskStatus.IN_PROGRESS
            current_task.commit_count = len(commits)
            
            # Collect all modified files
            files_modified = set()
            for commit in commits:
                files_modified.update(commit.files_changed)
            current_task.files_modified = list(files_modified)
        
        return {
            'status': current_task.status.value,
            'task_number': current_task.task_number,
            'branch': current_task.branch_name,
            'commits': len(commits),
            'staged_files': status['staged'],
            'modified_files': status['modified'],
            'untracked_files': status['untracked'],
            'files_touched': current_task.files_modified,
            'last_commit': commits[0].message if commits else None,
            'last_commit_time': commits[0].date.isoformat() if commits else None
        }
    
    def complete_task(self, agent_id: int, task_number: int, 
                     commit_message: Optional[str] = None) -> bool:
        """
        Mark a task as complete and prepare for merging
        
        Args:
            agent_id: Agent ID
            task_number: Task number
            commit_message: Optional final commit message
            
        Returns:
            True if successful
        """
        if agent_id not in self.agent_worktrees:
            raise CoordinationError(f"Agent {agent_id} has no worktree")
        
        agent_wt = self.agent_worktrees[agent_id]
        
        # Find the task
        task = None
        for t in agent_wt.tasks:
            if t.task_number == task_number:
                task = t
                break
        
        if not task:
            raise CoordinationError(f"Task {task_number} not found for agent {agent_id}")
        
        # Commit any pending changes
        if commit_message:
            try:
                status = get_status(cwd=agent_wt.worktree_path)
                if status['modified'] or status['staged']:
                    # Stage all changes
                    run_git_command(['add', '-A'], cwd=agent_wt.worktree_path)
                    # Commit
                    commit_hash = commit_changes(
                        commit_message,
                        cwd=agent_wt.worktree_path
                    )
                    logger.info(f"Created final commit for task {task_number}: {commit_hash[:8]}")
            except Exception as e:
                logger.warning(f"Failed to create final commit: {e}")
        
        # Mark task as completed
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now()
        
        logger.info(f"Task {task_number} marked as completed for agent {agent_id}")
        
        # Return to base branch
        run_git_command(
            ['checkout', agent_wt.base_branch],
            cwd=agent_wt.worktree_path
        )
        agent_wt.current_branch = agent_wt.base_branch
        
        return True
    
    def merge_completed_work(self, strategy: str = 'sequential') -> Dict[str, Any]:
        """
        Merge all completed work back to main branch
        
        Args:
            strategy: Merge strategy ('sequential' or 'parallel')
            
        Returns:
            Merge results
        """
        results = {
            'merged': [],
            'failed': [],
            'conflicts': []
        }
        
        # Collect all completed tasks
        completed_tasks = []
        for agent_wt in self.agent_worktrees.values():
            for task in agent_wt.tasks:
                if task.status == TaskStatus.COMPLETED:
                    completed_tasks.append(task)
        
        if not completed_tasks:
            logger.info("No completed tasks to merge")
            return results
        
        # Sort by task number for consistent ordering
        completed_tasks.sort(key=lambda t: t.task_number)
        
        logger.info(f"Merging {len(completed_tasks)} completed tasks using {strategy} strategy")
        
        # Switch to main branch
        run_git_command(['checkout', 'main'])
        
        if strategy == 'sequential':
            results = self._merge_sequential(completed_tasks)
        else:
            results = self._merge_parallel(completed_tasks)
        
        return results
    
    def _merge_sequential(self, tasks: List[AgentTask]) -> Dict[str, Any]:
        """Merge tasks one by one"""
        results = {
            'merged': [],
            'failed': [],
            'conflicts': []
        }
        
        for task in tasks:
            try:
                # Check for conflicts first
                conflicts = check_merge_conflicts(task.branch_name, 'main')
                
                if conflicts:
                    logger.warning(f"Task {task.task_number} has conflicts: {[c.file_path for c in conflicts]}")
                    results['conflicts'].append({
                        'task': task.task_number,
                        'branch': task.branch_name,
                        'conflicts': [c.file_path for c in conflicts]
                    })
                    
                    # Try automatic resolution if configured
                    if self.conflict_resolution == 'ours':
                        success, _ = merge_branch(
                            task.branch_name,
                            strategy='ours',
                            message=f"Merge task {task.task_number} (ours strategy)"
                        )
                    elif self.conflict_resolution == 'theirs':
                        success, _ = merge_branch(
                            task.branch_name,
                            strategy='recursive',
                            message=f"Merge task {task.task_number} (theirs strategy)"
                        )
                    else:
                        # Manual resolution required
                        results['failed'].append(task.task_number)
                        continue
                else:
                    # No conflicts, merge normally
                    success, conflicted = merge_branch(
                        task.branch_name,
                        message=f"Merge task {task.task_number}: {task.description[:50]}"
                    )
                
                if success:
                    results['merged'].append(task.task_number)
                    task.merge_commit = run_git_command(['rev-parse', 'HEAD'])[0].strip()
                    logger.info(f"Successfully merged task {task.task_number}")
                else:
                    results['failed'].append(task.task_number)
                    
            except Exception as e:
                logger.error(f"Failed to merge task {task.task_number}: {e}")
                results['failed'].append(task.task_number)
        
        return results
    
    def _merge_parallel(self, tasks: List[AgentTask]) -> Dict[str, Any]:
        """Attempt to merge all tasks at once"""
        results = {
            'merged': [],
            'failed': [],
            'conflicts': []
        }
        
        # Create a temporary integration branch
        integration_branch = f"integration/{self.current_session_id[:8]}"
        create_branch(integration_branch, base_branch='main')
        
        # Try to merge all branches into integration
        for task in tasks:
            try:
                success, conflicted = merge_branch(
                    task.branch_name,
                    message=f"Merge task {task.task_number}"
                )
                
                if success:
                    results['merged'].append(task.task_number)
                else:
                    results['conflicts'].append({
                        'task': task.task_number,
                        'branch': task.branch_name,
                        'conflicts': conflicted
                    })
            except Exception as e:
                logger.error(f"Failed to merge task {task.task_number}: {e}")
                results['failed'].append(task.task_number)
        
        # If all successful, merge integration to main
        if not results['failed'] and not results['conflicts']:
            run_git_command(['checkout', 'main'])
            success, _ = merge_branch(
                integration_branch,
                message=f"Merge session {self.current_session_id[:8]} work"
            )
            
            if success:
                logger.info(f"Successfully merged all {len(tasks)} tasks")
            else:
                logger.error("Failed to merge integration branch to main")
        
        return results
    
    def cleanup_session(self, session_id: str, keep_branches: bool = False) -> Dict[str, int]:
        """
        Clean up worktrees and branches for a session
        
        Args:
            session_id: Session ID to clean up
            keep_branches: Whether to keep branches after cleanup
            
        Returns:
            Cleanup statistics
        """
        stats = {
            'worktrees_removed': 0,
            'branches_deleted': 0
        }
        
        # Remove all agent worktrees
        for agent_id, agent_wt in list(self.agent_worktrees.items()):
            if agent_wt.session_id == session_id:
                try:
                    remove_worktree(agent_wt.worktree_path, force=True)
                    stats['worktrees_removed'] += 1
                    del self.agent_worktrees[agent_id]
                    logger.info(f"Removed worktree for agent {agent_id}")
                except Exception as e:
                    logger.error(f"Failed to remove worktree for agent {agent_id}: {e}")
        
        # Clean up branches if requested
        if not keep_branches:
            stats['branches_deleted'] = cleanup_worktree_branches(session_id)
        
        # Prune any stale worktrees
        prune_worktrees()
        
        logger.info(f"Cleanup complete: removed {stats['worktrees_removed']} worktrees, "
                   f"deleted {stats['branches_deleted']} branches")
        
        return stats
    
    def get_session_status(self) -> Dict[str, Any]:
        """Get comprehensive status of the current session"""
        if not self.current_session_id:
            return {'status': 'no_session'}
        
        # Get worktree information
        all_worktrees = list_worktrees()
        agent_worktree_paths = [str(wt.worktree_path) for wt in self.agent_worktrees.values()]
        
        # Collect task statistics
        total_tasks = 0
        completed_tasks = 0
        in_progress_tasks = 0
        assigned_tasks = 0
        
        agents_status = []
        
        for agent_id, agent_wt in self.agent_worktrees.items():
            agent_info = {
                'agent_id': agent_id,
                'agent_uid': agent_wt.agent_uid,
                'worktree_path': str(agent_wt.worktree_path),
                'current_branch': agent_wt.current_branch,
                'tasks': []
            }
            
            for task in agent_wt.tasks:
                total_tasks += 1
                if task.status == TaskStatus.COMPLETED:
                    completed_tasks += 1
                elif task.status == TaskStatus.IN_PROGRESS:
                    in_progress_tasks += 1
                elif task.status == TaskStatus.ASSIGNED:
                    assigned_tasks += 1
                
                agent_info['tasks'].append({
                    'number': task.task_number,
                    'status': task.status.value,
                    'branch': task.branch_name,
                    'commits': task.commit_count
                })
            
            agents_status.append(agent_info)
        
        return {
            'session_id': self.current_session_id,
            'base_branch': self.session_base_branch,
            'total_agents': len(self.agent_worktrees),
            'total_worktrees': len([wt for wt in all_worktrees if str(wt.path) in agent_worktree_paths]),
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'in_progress_tasks': in_progress_tasks,
            'assigned_tasks': assigned_tasks,
            'agents': agents_status
        }
    
    def recover_session(self, session_id: str) -> bool:
        """
        Attempt to recover a session from existing worktrees
        
        Args:
            session_id: Session ID to recover
            
        Returns:
            True if recovery successful
        """
        self.current_session_id = session_id
        self.session_base_branch = f"session/{session_id[:8]}/base"
        
        # List existing worktrees
        worktrees = list_worktrees()
        
        recovered = 0
        for wt in worktrees:
            # Check if this is an agent worktree for this session
            if 'agent-' in str(wt.path) and session_id[:8] in wt.branch:
                # Extract agent ID from path
                try:
                    agent_id = int(str(wt.path).split('agent-')[1].split('/')[0])
                    
                    # Create AgentWorktree object
                    agent_wt = AgentWorktree(
                        agent_id=agent_id,
                        agent_uid=f"recovered_{agent_id}",
                        session_id=session_id,
                        worktree_path=wt.path,
                        base_branch=wt.branch,
                        current_branch=wt.branch
                    )
                    
                    self.agent_worktrees[agent_id] = agent_wt
                    recovered += 1
                    
                    logger.info(f"Recovered worktree for agent {agent_id}")
                    
                except Exception as e:
                    logger.warning(f"Failed to recover worktree {wt.path}: {e}")
        
        if recovered > 0:
            logger.info(f"Recovered {recovered} agent worktrees for session {session_id}")
            return True
        
        return False