"""
Module: git_utils
Purpose: Git command wrappers and utilities for version control operations

This module provides a comprehensive set of git operations used throughout Xenosync.
It wraps git commands in Python functions with proper error handling and return
type consistency. Used primarily for managing project repositories.

Key Classes:
    - WorktreeInfo: Git worktree information
    - CommitInfo: Git commit details
    - ConflictInfo: Merge conflict information
    - GitCommandError: Git operation exceptions

Key Functions:
    - run_git_command(): Execute git commands safely
    - create_worktree(): Create new worktree
    - create_branch(): Create git branch
    - commit_changes(): Commit with message
    - merge_branch(): Merge branches
    - get_status(): Get repository status

Dependencies:
    - subprocess: Command execution
    - pathlib: Path operations
    - datetime: Timestamp parsing

Usage:
    result = run_git_command(['status', '--porcelain'], cwd=project_path)
    commit_hash = commit_changes("Initial commit", cwd=project_path)
    
Author: Xenosync Team
Created: 2024-08-14
Modified: 2024-08-14
"""

import subprocess
import json
import logging
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class WorktreeInfo:
    """Information about a git worktree"""
    path: Path
    branch: str
    commit: str
    is_bare: bool = False
    is_detached: bool = False
    is_locked: bool = False
    lock_reason: Optional[str] = None


@dataclass
class CommitInfo:
    """Information about a git commit"""
    hash: str
    author: str
    date: datetime
    message: str
    files_changed: List[str]


@dataclass
class ConflictInfo:
    """Information about a merge conflict"""
    file_path: str
    conflict_type: str  # 'content', 'delete', 'rename'
    our_changes: Optional[str] = None
    their_changes: Optional[str] = None


class GitCommandError(Exception):
    """Exception raised when a git command fails"""
    pass


def run_git_command(args: List[str], cwd: Optional[Path] = None, 
                   check: bool = True) -> Tuple[str, str, int]:
    """
    Run a git command safely with error handling
    
    Args:
        args: Git command arguments (e.g., ['status', '--porcelain'])
        cwd: Working directory for the command
        check: Whether to raise exception on non-zero exit
        
    Returns:
        Tuple of (stdout, stderr, returncode)
    """
    cmd = ['git'] + args
    
    logger.debug(f"Running git command: {' '.join(cmd)} in {cwd or 'current dir'}")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check
        )
        return result.stdout, result.stderr, result.returncode
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Git command failed: {e.cmd}")
        logger.error(f"Exit code: {e.returncode}")
        logger.error(f"Stdout: {e.stdout}")
        logger.error(f"Stderr: {e.stderr}")
        
        if check:
            raise GitCommandError(f"Git command failed: {' '.join(cmd)}\n{e.stderr}")
        return e.stdout, e.stderr, e.returncode


def create_worktree(path: Path, branch: str, base_branch: str = 'main',
                   create_branch: bool = True) -> WorktreeInfo:
    """
    Create a new git worktree
    
    Args:
        path: Path where worktree should be created
        branch: Branch name for the worktree
        base_branch: Base branch to create from
        create_branch: Whether to create a new branch
        
    Returns:
        WorktreeInfo object
    """
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Build command
    args = ['worktree', 'add', str(path)]
    
    if create_branch:
        args.extend(['-b', branch, base_branch])
    else:
        args.append(branch)
    
    stdout, stderr, returncode = run_git_command(args)
    
    if returncode != 0:
        raise GitCommandError(f"Failed to create worktree at {path}: {stderr}")
    
    logger.info(f"Created worktree at {path} on branch {branch}")
    
    # Get worktree info
    worktrees = list_worktrees()
    for wt in worktrees:
        if wt.path == path:
            return wt
    
    # Fallback if not found in list
    return WorktreeInfo(path=path, branch=branch, commit='HEAD')


def remove_worktree(path: Path, force: bool = False) -> bool:
    """
    Remove a git worktree
    
    Args:
        path: Path of worktree to remove
        force: Force removal even if worktree has changes
        
    Returns:
        True if successful
    """
    args = ['worktree', 'remove', str(path)]
    if force:
        args.append('--force')
    
    stdout, stderr, returncode = run_git_command(args, check=False)
    
    if returncode != 0:
        if 'is not a working tree' in stderr:
            logger.warning(f"Worktree {path} does not exist")
            return False
        elif not force:
            logger.error(f"Failed to remove worktree {path}: {stderr}")
            logger.info("Try with force=True to remove unclean worktree")
            return False
        else:
            raise GitCommandError(f"Failed to force remove worktree {path}: {stderr}")
    
    logger.info(f"Removed worktree at {path}")
    return True


def list_worktrees() -> List[WorktreeInfo]:
    """
    List all git worktrees in the repository
    
    Returns:
        List of WorktreeInfo objects
    """
    stdout, stderr, returncode = run_git_command(['worktree', 'list', '--porcelain'])
    
    if returncode != 0:
        raise GitCommandError(f"Failed to list worktrees: {stderr}")
    
    worktrees = []
    current_wt = {}
    
    for line in stdout.strip().split('\n'):
        if not line:
            if current_wt:
                worktrees.append(WorktreeInfo(
                    path=Path(current_wt.get('worktree', '')),
                    branch=current_wt.get('branch', '').replace('refs/heads/', ''),
                    commit=current_wt.get('HEAD', ''),
                    is_bare=current_wt.get('bare') == 'true',
                    is_detached=current_wt.get('detached') == 'true',
                    is_locked=bool(current_wt.get('locked')),
                    lock_reason=current_wt.get('locked')
                ))
                current_wt = {}
        else:
            key, _, value = line.partition(' ')
            current_wt[key] = value
    
    # Add last worktree if exists
    if current_wt:
        worktrees.append(WorktreeInfo(
            path=Path(current_wt.get('worktree', '')),
            branch=current_wt.get('branch', '').replace('refs/heads/', ''),
            commit=current_wt.get('HEAD', ''),
            is_bare=current_wt.get('bare') == 'true',
            is_detached=current_wt.get('detached') == 'true',
            is_locked=bool(current_wt.get('locked')),
            lock_reason=current_wt.get('locked')
        ))
    
    return worktrees


def prune_worktrees() -> int:
    """
    Prune stale worktree administrative files
    
    Returns:
        Number of pruned worktrees
    """
    # First get count of current worktrees
    before = len(list_worktrees())
    
    stdout, stderr, returncode = run_git_command(['worktree', 'prune', '-v'])
    
    if returncode != 0:
        logger.warning(f"Failed to prune worktrees: {stderr}")
        return 0
    
    # Count how many were pruned
    after = len(list_worktrees())
    pruned = before - after
    
    if pruned > 0:
        logger.info(f"Pruned {pruned} stale worktrees")
    
    return pruned


def get_current_branch(cwd: Optional[Path] = None) -> str:
    """
    Get the current branch name
    
    Args:
        cwd: Working directory
        
    Returns:
        Branch name
    """
    stdout, stderr, returncode = run_git_command(
        ['rev-parse', '--abbrev-ref', 'HEAD'],
        cwd=cwd
    )
    
    if returncode != 0:
        raise GitCommandError(f"Failed to get current branch: {stderr}")
    
    return stdout.strip()


def get_branch_commits(branch: str, limit: int = 10, 
                      since_commit: Optional[str] = None,
                      cwd: Optional[Path] = None) -> List[CommitInfo]:
    """
    Get recent commits from a branch
    
    Args:
        branch: Branch name
        limit: Maximum number of commits to return
        since_commit: Only get commits after this commit hash
        cwd: Working directory
        
    Returns:
        List of CommitInfo objects
    """
    # Get commit logs with file changes
    if since_commit:
        # Get commits since baseline: since_commit..branch
        commit_range = f'{since_commit}..{branch}'
    else:
        commit_range = branch
    
    args = [
        'log', commit_range,
        f'--max-count={limit}',
        '--pretty=format:%H|%an|%ai|%s',
        '--name-only'
    ]
    
    stdout, stderr, returncode = run_git_command(args, cwd=cwd, check=False)
    
    if returncode != 0:
        if 'unknown revision' in stderr:
            logger.warning(f"Branch {branch} does not exist")
            return []
        raise GitCommandError(f"Failed to get branch commits: {stderr}")
    
    commits = []
    current_commit = None
    files = []
    
    for line in stdout.strip().split('\n'):
        if '|' in line:
            # Save previous commit if exists
            if current_commit:
                current_commit.files_changed = files
                commits.append(current_commit)
                files = []
            
            # Parse new commit
            parts = line.split('|')
            if len(parts) >= 4:
                # Parse git date format: "2025-08-14 10:13:16 -0400"
                # Convert to ISO format: "2025-08-14T10:13:16-04:00"
                date_str = parts[2]
                # Replace first space with T and fix timezone format
                if ' ' in date_str:
                    date_part, tz_part = date_str.rsplit(' ', 1)
                    if len(tz_part) == 5 and (tz_part[0] == '+' or tz_part[0] == '-'):
                        # Add colon to timezone: -0400 -> -04:00
                        tz_part = tz_part[:3] + ':' + tz_part[3:]
                    date_str = date_part + tz_part
                
                current_commit = CommitInfo(
                    hash=parts[0],
                    author=parts[1],
                    date=datetime.fromisoformat(date_str.replace(' ', 'T')),
                    message=parts[3],
                    files_changed=[]
                )
        elif line and current_commit:
            # This is a file change
            files.append(line)
    
    # Add last commit
    if current_commit:
        current_commit.files_changed = files
        commits.append(current_commit)
    
    return commits


def check_merge_conflicts(source_branch: str, target_branch: str,
                         cwd: Optional[Path] = None) -> List[ConflictInfo]:
    """
    Check if merging source into target would cause conflicts
    
    Args:
        source_branch: Branch to merge from
        target_branch: Branch to merge into
        cwd: Working directory
        
    Returns:
        List of ConflictInfo objects (empty if no conflicts)
    """
    # Save current branch
    original_branch = get_current_branch(cwd)
    
    try:
        # Checkout target branch
        run_git_command(['checkout', target_branch], cwd=cwd)
        
        # Try merge with --no-commit --no-ff
        stdout, stderr, returncode = run_git_command(
            ['merge', '--no-commit', '--no-ff', source_branch],
            cwd=cwd,
            check=False
        )
        
        conflicts = []
        
        if returncode != 0:
            # Get conflicted files
            stdout, stderr, returncode = run_git_command(
                ['diff', '--name-only', '--diff-filter=U'],
                cwd=cwd
            )
            
            for file_path in stdout.strip().split('\n'):
                if file_path:
                    conflicts.append(ConflictInfo(
                        file_path=file_path,
                        conflict_type='content'
                    ))
        
        # Abort the merge
        run_git_command(['merge', '--abort'], cwd=cwd, check=False)
        
        return conflicts
        
    finally:
        # Return to original branch
        run_git_command(['checkout', original_branch], cwd=cwd, check=False)


def create_branch(branch_name: str, base_branch: str = 'main',
                 cwd: Optional[Path] = None) -> bool:
    """
    Create a new branch
    
    Args:
        branch_name: Name of the new branch
        base_branch: Branch to create from
        cwd: Working directory
        
    Returns:
        True if successful
    """
    stdout, stderr, returncode = run_git_command(
        ['checkout', '-b', branch_name, base_branch],
        cwd=cwd,
        check=False
    )
    
    if returncode != 0:
        if 'already exists' in stderr:
            logger.warning(f"Branch {branch_name} already exists")
            return False
        raise GitCommandError(f"Failed to create branch {branch_name}: {stderr}")
    
    logger.info(f"Created branch {branch_name} from {base_branch}")
    return True


def delete_branch(branch_name: str, force: bool = False,
                 cwd: Optional[Path] = None) -> bool:
    """
    Delete a branch
    
    Args:
        branch_name: Name of the branch to delete
        force: Force deletion even if not merged
        cwd: Working directory
        
    Returns:
        True if successful
    """
    args = ['branch', '-d' if not force else '-D', branch_name]
    
    stdout, stderr, returncode = run_git_command(args, cwd=cwd, check=False)
    
    if returncode != 0:
        if 'not found' in stderr:
            logger.warning(f"Branch {branch_name} does not exist")
            return False
        elif not force and 'not fully merged' in stderr:
            logger.warning(f"Branch {branch_name} is not fully merged. Use force=True")
            return False
        raise GitCommandError(f"Failed to delete branch {branch_name}: {stderr}")
    
    logger.info(f"Deleted branch {branch_name}")
    return True


def merge_branch(source_branch: str, target_branch: Optional[str] = None,
                message: Optional[str] = None, strategy: str = 'recursive',
                cwd: Optional[Path] = None) -> Tuple[bool, List[str]]:
    """
    Merge a branch
    
    Args:
        source_branch: Branch to merge from
        target_branch: Branch to merge into (current branch if None)
        message: Commit message for merge
        strategy: Merge strategy ('recursive', 'ours', 'theirs')
        cwd: Working directory
        
    Returns:
        Tuple of (success, list of conflicted files)
    """
    # Checkout target branch if specified
    if target_branch:
        run_git_command(['checkout', target_branch], cwd=cwd)
    
    # Build merge command
    args = ['merge', source_branch, f'--strategy={strategy}']
    if message:
        args.extend(['-m', message])
    
    stdout, stderr, returncode = run_git_command(args, cwd=cwd, check=False)
    
    if returncode != 0:
        # Check for conflicts
        stdout, stderr, returncode = run_git_command(
            ['diff', '--name-only', '--diff-filter=U'],
            cwd=cwd
        )
        
        conflicted_files = [f for f in stdout.strip().split('\n') if f]
        
        if conflicted_files:
            logger.warning(f"Merge resulted in conflicts: {conflicted_files}")
            return False, conflicted_files
        else:
            raise GitCommandError(f"Merge failed: {stderr}")
    
    logger.info(f"Successfully merged {source_branch} into {target_branch or 'current branch'}")
    return True, []


def commit_changes(message: str, files: Optional[List[str]] = None,
                  cwd: Optional[Path] = None) -> str:
    """
    Commit changes
    
    Args:
        message: Commit message
        files: Specific files to commit (all staged if None)
        cwd: Working directory
        
    Returns:
        Commit hash
    """
    # Stage files if specified
    if files:
        run_git_command(['add'] + files, cwd=cwd)
    
    # Commit
    stdout, stderr, returncode = run_git_command(
        ['commit', '-m', message],
        cwd=cwd,
        check=False
    )
    
    if returncode != 0:
        if 'nothing to commit' in stdout or 'nothing to commit' in stderr:
            logger.warning("Nothing to commit")
            return ""
        raise GitCommandError(f"Failed to commit: {stderr}")
    
    # Get commit hash
    stdout, stderr, returncode = run_git_command(['rev-parse', 'HEAD'], cwd=cwd)
    commit_hash = stdout.strip()
    
    logger.info(f"Created commit {commit_hash[:8]}: {message}")
    return commit_hash


def get_status(cwd: Optional[Path] = None) -> Dict[str, List[str]]:
    """
    Get git status
    
    Args:
        cwd: Working directory
        
    Returns:
        Dictionary with keys: 'staged', 'modified', 'untracked'
    """
    stdout, stderr, returncode = run_git_command(
        ['status', '--porcelain'],
        cwd=cwd
    )
    
    status = {
        'staged': [],
        'modified': [],
        'untracked': []
    }
    
    for line in stdout.strip().split('\n'):
        if not line:
            continue
        
        status_code = line[:2]
        file_path = line[3:]
        
        if status_code[0] in 'ADMR':
            status['staged'].append(file_path)
        if status_code[1] == 'M':
            status['modified'].append(file_path)
        elif status_code == '??':
            status['untracked'].append(file_path)
    
    return status


def enable_rerere(global_config: bool = True) -> bool:
    """
    Enable git rerere (Reuse Recorded Resolution) for automatic conflict resolution
    
    Args:
        global_config: Whether to enable globally or just for current repo
        
    Returns:
        True if successful
    """
    args = ['config']
    if global_config:
        args.append('--global')
    args.extend(['rerere.enabled', 'true'])
    
    stdout, stderr, returncode = run_git_command(args)
    
    if returncode != 0:
        logger.error(f"Failed to enable rerere: {stderr}")
        return False
    
    logger.info(f"Enabled git rerere {'globally' if global_config else 'for current repo'}")
    return True


def cleanup_worktree_branches(session_id: str, keep_merged: bool = False) -> int:
    """
    Clean up branches created for a session
    
    Args:
        session_id: Session ID to clean up
        keep_merged: Whether to keep merged branches
        
    Returns:
        Number of branches deleted
    """
    # List all branches
    stdout, stderr, returncode = run_git_command(['branch', '-a'])
    
    if returncode != 0:
        logger.error(f"Failed to list branches: {stderr}")
        return 0
    
    deleted = 0
    session_prefix = f"agent-"
    
    for line in stdout.strip().split('\n'):
        branch = line.strip().replace('* ', '')
        
        # Skip if not a session branch
        if not branch.startswith(session_prefix) or session_id[:8] not in branch:
            continue
        
        # Check if merged
        if not keep_merged:
            stdout, stderr, returncode = run_git_command(
                ['branch', '--merged', 'main'],
                check=False
            )
            is_merged = branch in stdout
        else:
            is_merged = False
        
        # Delete branch
        if delete_branch(branch, force=not is_merged):
            deleted += 1
    
    if deleted > 0:
        logger.info(f"Deleted {deleted} branches for session {session_id}")
    
    return deleted