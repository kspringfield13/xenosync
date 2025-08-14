"""
Module: project_coordination
Purpose: Manages isolated project workspaces for multi-agent parallel development

This module provides the core coordination system for Xenosync's project-based
architecture. Each agent receives an isolated project directory where they can
create files, commit changes, and work independently. Projects are then merged
into a final unified project directory.

Key Classes:
    - ProjectWorkspaceCoordinator: Main coordinator for project workspaces
    - AgentProject: Tracks individual agent project state
    - ProjectStatus: Enum for project lifecycle states

Key Functions:
    - initialize_session(): Sets up workspace for a session
    - create_agent_workspace(): Creates isolated project for an agent
    - merge_agent_projects(): Combines all agent work into final project
    - track_agent_progress(): Monitors agent project activity

Dependencies:
    - pathlib: Path manipulation
    - git (via git_utils): Version control in projects
    - shutil: File operations for merging

Usage:
    coordinator = ProjectWorkspaceCoordinator(config)
    coordinator.initialize_session(session_id, num_agents)
    workspace_path, project_path = coordinator.create_agent_workspace(agent_id, uid, session_id)
    
Author: Xenosync Team
Created: 2024-08-14
Modified: 2024-08-14
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

from .config import Config
from .exceptions import CoordinationError
from .git_utils import run_git_command, GitCommandError

logger = logging.getLogger(__name__)


class ProjectStatus(Enum):
    """Status of agent project"""
    INITIALIZED = "initialized"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    MERGED = "merged"
    FAILED = "failed"


@dataclass
class AgentProject:
    """Agent project information"""
    agent_id: int
    agent_uid: str
    session_id: str
    workspace_path: Path
    project_path: Path
    status: ProjectStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    files_created: List[str] = None
    commits: int = 0
    
    def __post_init__(self):
        if self.files_created is None:
            self.files_created = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['status'] = self.status.value
        data['workspace_path'] = str(self.workspace_path)
        data['project_path'] = str(self.project_path)
        data['created_at'] = self.created_at.isoformat()
        if self.completed_at:
            data['completed_at'] = self.completed_at.isoformat()
        return data


class ProjectWorkspaceCoordinator:
    """Manages agent project workspaces - each agent gets an isolated project folder"""
    
    def __init__(self, config: Config):
        self.config = config
        self.workspace_dir: Optional[Path] = None
        self.current_session_id: Optional[str] = None
        self.agent_projects: Dict[int, AgentProject] = {}
        
        # Project configuration
        self.project_name = config.get('project_name', 'project')
        self.use_git = config.get('use_git_in_projects', True)
        self.merge_strategy = config.get('project_merge_strategy', 'combine')
        
        logger.info("Initialized ProjectWorkspaceCoordinator")
    
    def initialize_session(self, session_id: str, num_agents: int, 
                          workspace_dir: Optional[Path] = None) -> Path:
        """
        Initialize a new session with workspace
        
        Args:
            session_id: Unique session identifier
            num_agents: Number of agents in the session
            workspace_dir: Optional workspace directory
            
        Returns:
            Workspace directory path
        """
        self.current_session_id = session_id
        
        # Set up workspace directory
        if workspace_dir:
            self.workspace_dir = workspace_dir
        else:
            # Default to xsync-sessions/{session_id}/workspace
            self.workspace_dir = Path('xsync-sessions') / session_id / 'workspace'
        
        # Create workspace directory
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Session workspace created at: {self.workspace_dir}")
        
        # Create final-project directory structure
        final_project_dir = self.workspace_dir / 'final-project'
        final_project_dir.mkdir(exist_ok=True)
        
        # Initialize git in final project if using git
        if self.use_git:
            try:
                run_git_command(['init'], cwd=final_project_dir)
                run_git_command(['config', 'user.name', 'Xenosync'], cwd=final_project_dir)
                run_git_command(['config', 'user.email', 'xenosync@local'], cwd=final_project_dir)
                
                # Create initial commit
                readme_path = final_project_dir / 'README.md'
                readme_path.write_text(f"# {self.project_name}\n\nMerged project from session {session_id}\n")
                run_git_command(['add', 'README.md'], cwd=final_project_dir)
                run_git_command(['commit', '-m', 'Initial commit'], cwd=final_project_dir)
                
                logger.info("Initialized git in final-project directory")
            except GitCommandError as e:
                logger.warning(f"Failed to initialize git in final-project: {e}")
        
        return self.workspace_dir
    
    def create_agent_workspace(self, agent_id: int, agent_uid: str, 
                              session_id: str) -> Tuple[Path, Path]:
        """
        Create a workspace with project folder for an agent
        
        Args:
            agent_id: Agent ID
            agent_uid: Unique agent identifier
            session_id: Session ID
            
        Returns:
            Tuple of (workspace_path, project_path)
        """
        if not self.workspace_dir:
            raise CoordinationError("Workspace not initialized")
        
        # Create agent workspace
        agent_workspace = self.workspace_dir / f"agent-{agent_id}"
        agent_workspace.mkdir(parents=True, exist_ok=True)
        
        # Create project folder inside workspace
        project_path = agent_workspace / self.project_name
        project_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize git in project if configured
        if self.use_git:
            try:
                # Initialize git repo
                run_git_command(['init'], cwd=project_path)
                run_git_command(['config', 'user.name', f'Agent-{agent_id}'], cwd=project_path)
                run_git_command(['config', 'user.email', f'agent-{agent_id}@xenosync.local'], 
                              cwd=project_path)
                
                # Create initial commit
                readme_path = project_path / 'README.md'
                readme_path.write_text(f"# Agent {agent_id} Project\n\nWorkspace for Agent {agent_id}\n")
                run_git_command(['add', 'README.md'], cwd=project_path)
                run_git_command(['commit', '-m', 'Initial project setup'], cwd=project_path)
                
                logger.info(f"Initialized git repo in {project_path}")
            except GitCommandError as e:
                logger.warning(f"Failed to initialize git for agent {agent_id}: {e}")
        
        # Track the agent project
        agent_project = AgentProject(
            agent_id=agent_id,
            agent_uid=agent_uid,
            session_id=session_id,
            workspace_path=agent_workspace,
            project_path=project_path,
            status=ProjectStatus.INITIALIZED,
            created_at=datetime.now()
        )
        self.agent_projects[agent_id] = agent_project
        
        logger.info(f"Created project workspace for agent {agent_id} at {project_path}")
        
        return agent_workspace, project_path
    
    def track_agent_progress(self, agent_id: int) -> Dict[str, Any]:
        """
        Track progress of an agent's project
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Progress information
        """
        if agent_id not in self.agent_projects:
            return {'status': 'no_project'}
        
        project = self.agent_projects[agent_id]
        
        # Count files in project
        files_created = []
        if project.project_path.exists():
            for file_path in project.project_path.rglob('*'):
                if file_path.is_file() and '.git' not in str(file_path):
                    relative_path = file_path.relative_to(project.project_path)
                    files_created.append(str(relative_path))
        
        project.files_created = files_created
        
        # Get git commit count if using git
        commit_count = 0
        if self.use_git and (project.project_path / '.git').exists():
            try:
                result = run_git_command(['rev-list', '--count', 'HEAD'], 
                                       cwd=project.project_path)
                commit_count = int(result[0].strip()) if result else 0
            except:
                pass
        
        project.commits = commit_count
        
        # Update status based on activity - but preserve completion status
        if project.status != ProjectStatus.COMPLETED:  # Don't override completed status
            if files_created or commit_count > 1:  # More than initial commit
                project.status = ProjectStatus.IN_PROGRESS
        
        return {
            'status': project.status.value,
            'files_created': len(files_created),
            'file_list': files_created[:10],  # First 10 files
            'commits': commit_count,
            'workspace_path': str(project.workspace_path),
            'project_path': str(project.project_path)
        }
    
    def complete_agent_project(self, agent_id: int) -> bool:
        """
        Mark an agent's project as complete
        
        Args:
            agent_id: Agent ID
            
        Returns:
            True if successful
        """
        if agent_id not in self.agent_projects:
            raise CoordinationError(f"Agent {agent_id} has no project")
        
        project = self.agent_projects[agent_id]
        
        # Create final commit if using git
        if self.use_git and (project.project_path / '.git').exists():
            try:
                # Check for uncommitted changes
                status_result = run_git_command(['status', '--porcelain'], 
                                              cwd=project.project_path)
                if status_result and status_result[0].strip():
                    # Stage all changes
                    run_git_command(['add', '-A'], cwd=project.project_path)
                    # Commit
                    run_git_command(['commit', '-m', f'Final commit for agent {agent_id}'], 
                                  cwd=project.project_path)
                    logger.info(f"Created final commit for agent {agent_id}")
            except Exception as e:
                logger.warning(f"Failed to create final commit: {e}")
        
        # Mark as completed
        project.status = ProjectStatus.COMPLETED
        project.completed_at = datetime.now()
        
        logger.info(f"Agent {agent_id} project marked as completed")
        return True
    
    def merge_agent_projects(self) -> Dict[str, Any]:
        """
        Merge all completed agent projects into final-project
        
        Returns:
            Merge results
        """
        results = {
            'merged_projects': [],
            'failed_projects': [],
            'total_files': 0,
            'conflicts': []
        }
        
        final_project_dir = self.workspace_dir / 'final-project'
        
        # Collect completed projects
        completed_projects = [p for p in self.agent_projects.values() 
                            if p.status == ProjectStatus.COMPLETED]
        
        if not completed_projects:
            logger.info("No completed projects to merge")
            return results
        
        logger.info(f"Merging {len(completed_projects)} agent projects")
        
        if self.merge_strategy == 'git' and self.use_git:
            results = self._merge_with_git(completed_projects, final_project_dir)
        else:
            results = self._merge_with_files(completed_projects, final_project_dir)
        
        # Mark merged projects
        for project in completed_projects:
            if project.agent_id in results['merged_projects']:
                project.status = ProjectStatus.MERGED
        
        return results
    
    def _merge_with_files(self, projects: List[AgentProject], 
                         final_dir: Path) -> Dict[str, Any]:
        """Merge projects by copying files"""
        results = {
            'merged_projects': [],
            'failed_projects': [],
            'total_files': 0,
            'conflicts': []
        }
        
        # Track which files came from which agent
        file_sources = {}
        
        for project in projects:
            try:
                files_copied = 0
                
                for file_path in project.project_path.rglob('*'):
                    if file_path.is_file() and '.git' not in str(file_path):
                        relative_path = file_path.relative_to(project.project_path)
                        dest_path = final_dir / relative_path
                        
                        # Check for conflicts
                        if dest_path.exists():
                            if str(relative_path) not in file_sources:
                                file_sources[str(relative_path)] = []
                            file_sources[str(relative_path)].append(project.agent_id)
                            
                            # Handle conflict based on strategy
                            if self.config.get('conflict_resolution', 'skip') == 'overwrite':
                                dest_path.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(file_path, dest_path)
                                files_copied += 1
                            else:
                                results['conflicts'].append({
                                    'file': str(relative_path),
                                    'agents': file_sources[str(relative_path)]
                                })
                        else:
                            # No conflict, copy file
                            dest_path.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(file_path, dest_path)
                            files_copied += 1
                            file_sources[str(relative_path)] = [project.agent_id]
                
                results['merged_projects'].append(project.agent_id)
                results['total_files'] += files_copied
                logger.info(f"Merged {files_copied} files from agent {project.agent_id}")
                
            except Exception as e:
                logger.error(f"Failed to merge project from agent {project.agent_id}: {e}")
                results['failed_projects'].append(project.agent_id)
        
        # Create merge summary
        summary_path = final_dir / 'MERGE_SUMMARY.md'
        summary_content = f"# Merge Summary\n\n"
        summary_content += f"Session: {self.current_session_id}\n"
        summary_content += f"Merged Projects: {len(results['merged_projects'])}\n"
        summary_content += f"Total Files: {results['total_files']}\n"
        summary_content += f"Conflicts: {len(results['conflicts'])}\n\n"
        
        if results['conflicts']:
            summary_content += "## Conflicts\n\n"
            for conflict in results['conflicts']:
                summary_content += f"- {conflict['file']}: agents {conflict['agents']}\n"
        
        summary_path.write_text(summary_content)
        
        # Commit if using git
        if self.use_git and (final_dir / '.git').exists():
            try:
                run_git_command(['add', '-A'], cwd=final_dir)
                run_git_command(['commit', '-m', 
                               f"Merged {len(results['merged_projects'])} agent projects"], 
                               cwd=final_dir)
            except:
                pass
        
        return results
    
    def _merge_with_git(self, projects: List[AgentProject], 
                       final_dir: Path) -> Dict[str, Any]:
        """Merge projects using git"""
        results = {
            'merged_projects': [],
            'failed_projects': [],
            'total_files': 0,
            'conflicts': []
        }
        
        # Add each project as a remote and merge
        for i, project in enumerate(projects):
            try:
                remote_name = f"agent-{project.agent_id}"
                
                # Add project as remote
                run_git_command(['remote', 'add', remote_name, 
                               str(project.project_path)], cwd=final_dir)
                
                # Fetch from remote
                run_git_command(['fetch', remote_name], cwd=final_dir)
                
                # Merge
                try:
                    run_git_command(['merge', f'{remote_name}/main', '--no-ff',
                                   '-m', f'Merge agent {project.agent_id} project'],
                                   cwd=final_dir)
                    results['merged_projects'].append(project.agent_id)
                    logger.info(f"Successfully merged agent {project.agent_id} via git")
                except GitCommandError as e:
                    if 'conflict' in str(e).lower():
                        results['conflicts'].append({
                            'agent': project.agent_id,
                            'error': 'merge conflict'
                        })
                        # Abort merge
                        run_git_command(['merge', '--abort'], cwd=final_dir)
                    results['failed_projects'].append(project.agent_id)
                
                # Remove remote
                run_git_command(['remote', 'remove', remote_name], cwd=final_dir)
                
            except Exception as e:
                logger.error(f"Failed to merge agent {project.agent_id}: {e}")
                results['failed_projects'].append(project.agent_id)
        
        # Count files in final project
        file_count = len(list(final_dir.rglob('*'))) - 1  # Exclude .git
        results['total_files'] = file_count
        
        return results
    
    def get_session_status(self) -> Dict[str, Any]:
        """Get comprehensive status of the current session"""
        if not self.current_session_id:
            return {'status': 'no_session'}
        
        # Collect project statistics
        total_projects = len(self.agent_projects)
        completed_projects = sum(1 for p in self.agent_projects.values() 
                               if p.status == ProjectStatus.COMPLETED)
        merged_projects = sum(1 for p in self.agent_projects.values() 
                            if p.status == ProjectStatus.MERGED)
        total_files = sum(len(p.files_created) for p in self.agent_projects.values())
        
        agents_status = []
        for agent_id, project in self.agent_projects.items():
            agents_status.append({
                'agent_id': agent_id,
                'status': project.status.value,
                'files_created': len(project.files_created),
                'commits': project.commits,
                'project_path': str(project.project_path)
            })
        
        return {
            'session_id': self.current_session_id,
            'workspace_dir': str(self.workspace_dir),
            'total_projects': total_projects,
            'completed_projects': completed_projects,
            'merged_projects': merged_projects,
            'total_files': total_files,
            'agents': agents_status,
            'final_project_path': str(self.workspace_dir / 'final-project')
        }
    
    def cleanup_session(self, session_id: str, keep_projects: bool = True) -> Dict[str, int]:
        """
        Clean up session workspace
        
        Args:
            session_id: Session ID to clean up
            keep_projects: Whether to keep project folders
            
        Returns:
            Cleanup statistics
        """
        stats = {
            'projects_removed': 0,
            'files_removed': 0
        }
        
        if not keep_projects and self.workspace_dir and self.workspace_dir.exists():
            # Count files before deletion
            stats['files_removed'] = len(list(self.workspace_dir.rglob('*')))
            stats['projects_removed'] = len(self.agent_projects)
            
            # Remove entire workspace
            shutil.rmtree(self.workspace_dir)
            logger.info(f"Removed workspace directory: {self.workspace_dir}")
        else:
            logger.info(f"Keeping project files at: {self.workspace_dir}")
        
        # Clear tracking
        self.agent_projects.clear()
        
        return stats