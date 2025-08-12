"""
File-based Coordination System - Agent coordination using files instead of database
"""

import json
import logging
import hashlib
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

from .config import Config
from .exceptions import CoordinationError
from .file_utils import (
    read_json_file, write_json_file, append_to_json_array,
    update_json_file, ensure_directory, cleanup_old_files,
    is_file_stale, safe_append_line, JSONFileStore, FileLock
)


logger = logging.getLogger(__name__)


class WorkStatus(Enum):
    """Work claim status"""
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RELEASED = "released"


@dataclass
class WorkClaim:
    """Work claim data model"""
    id: str  # Changed from int to str for file-based system
    agent_uid: str
    session_id: str
    files: List[str]
    description: str
    status: WorkStatus
    claimed_at: datetime
    updated_at: datetime
    released_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def is_active(self) -> bool:
        """Check if claim is still active"""
        return self.status in [WorkStatus.CLAIMED, WorkStatus.IN_PROGRESS]
    
    def is_stale(self, hours: int = 2) -> bool:
        """Check if claim is stale"""
        if not self.is_active():
            return False
        age = datetime.now() - self.updated_at
        return age.total_seconds() > (hours * 3600)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['status'] = self.status.value
        data['claimed_at'] = self.claimed_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        if self.released_at:
            data['released_at'] = self.released_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkClaim':
        """Create from dictionary"""
        data['status'] = WorkStatus(data['status'])
        data['claimed_at'] = datetime.fromisoformat(data['claimed_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        if data.get('released_at'):
            data['released_at'] = datetime.fromisoformat(data['released_at'])
        return cls(**data)


@dataclass
class AgentMessage:
    """Inter-agent communication message"""
    id: str  # Changed from int to str
    from_agent: str
    to_agent: Optional[str]  # None for broadcast
    message_type: str
    content: str
    timestamp: datetime
    read: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'from_agent': self.from_agent,
            'to_agent': self.to_agent,
            'message_type': self.message_type,
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'read': self.read
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentMessage':
        """Create from dictionary"""
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class FileCoordinationManager:
    """Manages agent coordination with file-based backend"""
    
    def __init__(self, config: Config):
        self.config = config
        # Use sessions directory for coordination data
        self.base_path = config.sessions_dir / 'coordination'
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize coordination structure
        self._init_coordination_structure()
    
    def _init_coordination_structure(self):
        """Initialize the coordination directory structure"""
        # Create standard directories
        ensure_directory(self.base_path / 'agent_locks')
        ensure_directory(self.base_path / 'agent_messages')
        ensure_directory(self.base_path / 'sessions')
        
        # Initialize JSON files if they don't exist
        if not (self.base_path / 'active_work_registry.json').exists():
            write_json_file(self.base_path / 'active_work_registry.json', {})
        
        if not (self.base_path / 'completed_work_log.json').exists():
            write_json_file(self.base_path / 'completed_work_log.json', [])
        
        if not (self.base_path / 'planned_work_queue.json').exists():
            write_json_file(self.base_path / 'planned_work_queue.json', [])
        
        if not (self.base_path / 'agent_registry.json').exists():
            write_json_file(self.base_path / 'agent_registry.json', {})
    
    def get_session_coordination_path(self, session_id: str) -> Path:
        """Get session-specific coordination directory"""
        path = self.base_path / 'sessions' / session_id
        ensure_directory(path)
        ensure_directory(path / 'agent_locks')
        ensure_directory(path / 'agent_messages')
        
        # Initialize session-specific files
        if not (path / 'active_work_registry.json').exists():
            write_json_file(path / 'active_work_registry.json', {})
        
        if not (path / 'completed_work_log.json').exists():
            write_json_file(path / 'completed_work_log.json', [])
        
        if not (path / 'planned_work_queue.json').exists():
            write_json_file(path / 'planned_work_queue.json', [])
        
        return path
    
    def register_agent(self, agent_uid: str, agent_id: int, session_id: str,
                      capabilities: Optional[List[str]] = None) -> bool:
        """Register an agent in the coordination system"""
        try:
            session_path = self.get_session_coordination_path(session_id)
            registry_path = session_path / 'agent_registry.json'
            
            def updater(data):
                if not isinstance(data, dict):
                    data = {}
                
                data[agent_uid] = {
                    'agent_id': agent_id,
                    'session_id': session_id,
                    'started_at': datetime.now().isoformat(),
                    'last_seen': datetime.now().isoformat(),
                    'status': 'active',
                    'capabilities': capabilities or []
                }
                return data
            
            update_json_file(registry_path, updater)
            logger.info(f"Registered agent {agent_uid} for session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register agent {agent_uid}: {e}")
            return False
    
    def update_agent_status(self, agent_uid: str, session_id: str, status: str, 
                          metrics: Optional[Dict] = None):
        """Update agent status and metrics"""
        session_path = self.get_session_coordination_path(session_id)
        registry_path = session_path / 'agent_registry.json'
        
        def updater(data):
            if agent_uid in data:
                data[agent_uid]['status'] = status
                data[agent_uid]['last_seen'] = datetime.now().isoformat()
                if metrics:
                    data[agent_uid]['metrics'] = metrics
            return data
        
        update_json_file(registry_path, updater)
    
    def claim_work(self, agent_uid: str, session_id: str, files: List[str],
                  description: str, metadata: Optional[Dict] = None) -> Optional[str]:
        """Try to claim work on specific files"""
        session_path = self.get_session_coordination_path(session_id)
        registry_path = session_path / 'active_work_registry.json'
        locks_dir = session_path / 'agent_locks'
        
        # Generate claim ID
        claim_id = f"{agent_uid}_{int(time.time() * 1000)}"
        
        with FileLock(registry_path):
            # Read current registry
            registry = read_json_file(registry_path, {})
            
            # Check for conflicts
            for existing_claim_id, claim_data in registry.items():
                if claim_data.get('status') in ['claimed', 'in_progress']:
                    claimed_files = claim_data.get('files', [])
                    
                    # Check for file overlap
                    if any(f in claimed_files for f in files):
                        # Check if claim is stale
                        updated_at = datetime.fromisoformat(claim_data['updated_at'])
                        if (datetime.now() - updated_at).total_seconds() > 7200:  # 2 hours
                            # Release stale claim
                            logger.warning(f"Releasing stale claim {existing_claim_id}")
                            claim_data['status'] = 'released'
                            claim_data['released_at'] = datetime.now().isoformat()
                        else:
                            # Active conflict
                            logger.warning(f"Work conflict: {files} already claimed by {claim_data['agent_uid']}")
                            return None
            
            # No conflicts, create claim
            claim = WorkClaim(
                id=claim_id,
                agent_uid=agent_uid,
                session_id=session_id,
                files=files,
                description=description,
                status=WorkStatus.CLAIMED,
                claimed_at=datetime.now(),
                updated_at=datetime.now(),
                metadata=metadata
            )
            
            # Add to registry
            registry[claim_id] = claim.to_dict()
            write_json_file(registry_path, registry)
            
            # Create lock file
            lock_file = locks_dir / f"{claim_id}.lock"
            lock_data = {
                'agent_uid': agent_uid,
                'timestamp': datetime.now().isoformat(),
                'planned_scope': {
                    'files': files,
                    'features': metadata.get('features', []) if metadata else [],
                    'estimated_duration': metadata.get('estimated_duration', 'unknown') if metadata else 'unknown'
                },
                'status': 'planning'
            }
            write_json_file(lock_file, lock_data)
            
            logger.info(f"Agent {agent_uid} claimed work on {len(files)} files (claim {claim_id})")
            return claim_id
    
    def update_work_status(self, claim_id: str, session_id: str, status: WorkStatus):
        """Update work claim status"""
        session_path = self.get_session_coordination_path(session_id)
        registry_path = session_path / 'active_work_registry.json'
        
        def updater(data):
            if claim_id in data:
                data[claim_id]['status'] = status.value
                data[claim_id]['updated_at'] = datetime.now().isoformat()
            return data
        
        update_json_file(registry_path, updater)
        
        # Update lock file if it exists
        locks_dir = session_path / 'agent_locks'
        lock_file = locks_dir / f"{claim_id}.lock"
        if lock_file.exists():
            lock_data = read_json_file(lock_file)
            lock_data['status'] = status.value
            write_json_file(lock_file, lock_data)
    
    def release_work(self, agent_uid: str, session_id: str, claim_id: Optional[str] = None):
        """Release work claim(s)"""
        session_path = self.get_session_coordination_path(session_id)
        registry_path = session_path / 'active_work_registry.json'
        locks_dir = session_path / 'agent_locks'
        
        def updater(data):
            if claim_id:
                # Release specific claim
                if claim_id in data and data[claim_id]['agent_uid'] == agent_uid:
                    data[claim_id]['status'] = WorkStatus.RELEASED.value
                    data[claim_id]['released_at'] = datetime.now().isoformat()
                    data[claim_id]['updated_at'] = datetime.now().isoformat()
            else:
                # Release all claims for agent
                for cid, claim in data.items():
                    if claim['agent_uid'] == agent_uid and claim['status'] in ['claimed', 'in_progress']:
                        claim['status'] = WorkStatus.RELEASED.value
                        claim['released_at'] = datetime.now().isoformat()
                        claim['updated_at'] = datetime.now().isoformat()
            return data
        
        update_json_file(registry_path, updater)
        
        # Remove lock files
        if claim_id:
            lock_file = locks_dir / f"{claim_id}.lock"
            if lock_file.exists():
                lock_file.unlink()
        else:
            # Remove all locks for agent
            for lock_file in locks_dir.glob(f"{agent_uid}_*.lock"):
                lock_file.unlink()
    
    def get_active_claims(self, session_id: str) -> List[WorkClaim]:
        """Get all active work claims for a session"""
        session_path = self.get_session_coordination_path(session_id)
        registry_path = session_path / 'active_work_registry.json'
        
        registry = read_json_file(registry_path, {})
        claims = []
        
        for claim_id, claim_data in registry.items():
            if claim_data.get('status') in ['claimed', 'in_progress']:
                try:
                    claim = WorkClaim.from_dict(claim_data)
                    claims.append(claim)
                except Exception as e:
                    logger.warning(f"Failed to parse claim {claim_id}: {e}")
        
        return claims
    
    def log_completed_work(self, agent_uid: str, session_id: str, description: str,
                          files_modified: Optional[List[str]] = None,
                          duration_seconds: Optional[int] = None,
                          success: bool = True, error_message: Optional[str] = None):
        """Log completed work"""
        session_path = self.get_session_coordination_path(session_id)
        log_path = session_path / 'completed_work_log.json'
        
        work_entry = {
            'agent_uid': agent_uid,
            'session_id': session_id,
            'description': description,
            'files_modified': files_modified or [],
            'completed_at': datetime.now().isoformat(),
            'duration_seconds': duration_seconds,
            'success': success,
            'error_message': error_message
        }
        
        append_to_json_array(log_path, work_entry, max_items=1000)
        
        status = "completed" if success else "failed"
        logger.info(f"Agent {agent_uid} {status} work: {description}")
    
    def get_completed_work(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all completed work for a session"""
        session_path = self.get_session_coordination_path(session_id)
        log_path = session_path / 'completed_work_log.json'
        
        return read_json_file(log_path, [])
    
    def send_message(self, from_agent: str, to_agent: Optional[str], session_id: str,
                    message_type: str, content: str):
        """Send message between agents"""
        session_path = self.get_session_coordination_path(session_id)
        messages_dir = session_path / 'agent_messages'
        
        # Generate message ID
        message_id = f"{int(time.time() * 1000)}_{from_agent[:8]}"
        
        message = AgentMessage(
            id=message_id,
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            content=content,
            timestamp=datetime.now(),
            read=False
        )
        
        # Save message to file
        filename = f"{message_id}_{to_agent or 'broadcast'}.json"
        message_file = messages_dir / filename
        write_json_file(message_file, message.to_dict())
        
        target = to_agent or "all"
        logger.debug(f"Message from {from_agent} to {target}: {message_type}")
    
    def get_messages(self, agent_uid: str, session_id: str, 
                     unread_only: bool = True) -> List[AgentMessage]:
        """Get messages for an agent"""
        session_path = self.get_session_coordination_path(session_id)
        messages_dir = session_path / 'agent_messages'
        
        messages = []
        
        if not messages_dir.exists():
            return messages
        
        for message_file in messages_dir.glob('*.json'):
            try:
                message_data = read_json_file(message_file)
                
                # Check if message is for this agent
                if message_data['to_agent'] == agent_uid or message_data['to_agent'] is None:
                    if not unread_only or not message_data.get('read', False):
                        message = AgentMessage.from_dict(message_data)
                        messages.append(message)
                        
                        # Mark as read
                        if not message_data.get('read', False):
                            message_data['read'] = True
                            write_json_file(message_file, message_data)
                            
            except Exception as e:
                logger.warning(f"Failed to read message {message_file}: {e}")
        
        # Sort by timestamp
        messages.sort(key=lambda m: m.timestamp)
        return messages
    
    def get_agent_workload(self, session_id: str) -> Dict[str, int]:
        """Get workload distribution across agents"""
        session_path = self.get_session_coordination_path(session_id)
        registry_path = session_path / 'active_work_registry.json'
        
        registry = read_json_file(registry_path, {})
        workload = {}
        
        for claim_data in registry.values():
            if claim_data.get('status') in ['claimed', 'in_progress']:
                agent_uid = claim_data['agent_uid']
                workload[agent_uid] = workload.get(agent_uid, 0) + 1
        
        return workload
    
    def detect_conflicts(self, session_id: str) -> List[Tuple[str, str, List[str]]]:
        """Detect file conflicts between agents"""
        session_path = self.get_session_coordination_path(session_id)
        registry_path = session_path / 'active_work_registry.json'
        
        registry = read_json_file(registry_path, {})
        active_claims = []
        
        for claim_data in registry.values():
            if claim_data.get('status') in ['claimed', 'in_progress']:
                active_claims.append((claim_data['agent_uid'], claim_data.get('files', [])))
        
        conflicts = []
        for i, (agent1, files1) in enumerate(active_claims):
            for agent2, files2 in active_claims[i+1:]:
                shared_files = list(set(files1) & set(files2))
                if shared_files:
                    conflicts.append((agent1, agent2, shared_files))
        
        return conflicts
    
    def cleanup_stale_claims(self, session_id: str, hours: int = 2) -> int:
        """Clean up stale work claims"""
        session_path = self.get_session_coordination_path(session_id)
        registry_path = session_path / 'active_work_registry.json'
        locks_dir = session_path / 'agent_locks'
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        cleaned = 0
        
        def updater(data):
            nonlocal cleaned
            for claim_id, claim in data.items():
                if claim['status'] in ['claimed', 'in_progress']:
                    updated_at = datetime.fromisoformat(claim['updated_at'])
                    if updated_at < cutoff_time:
                        claim['status'] = WorkStatus.RELEASED.value
                        claim['released_at'] = datetime.now().isoformat()
                        claim['updated_at'] = datetime.now().isoformat()
                        cleaned += 1
                        
                        # Remove lock file
                        lock_file = locks_dir / f"{claim_id}.lock"
                        if lock_file.exists():
                            lock_file.unlink()
            return data
        
        update_json_file(registry_path, updater)
        
        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} stale claims for session {session_id}")
        
        # Also clean up old message files
        cleanup_old_files(session_path / 'agent_messages', '*.json', hours=24)
        
        return cleaned
    
    def get_coordination_summary(self, session_id: str) -> Dict[str, Any]:
        """Get coordination summary for a session"""
        session_path = self.get_session_coordination_path(session_id)
        
        # Read registry files
        registry = read_json_file(session_path / 'active_work_registry.json', {})
        completed_work = read_json_file(session_path / 'completed_work_log.json', [])
        agent_registry = read_json_file(session_path / 'agent_registry.json', {})
        
        # Count active agents
        active_agents = sum(1 for agent in agent_registry.values() 
                          if agent.get('status') == 'active')
        
        # Count active claims
        active_claims = sum(1 for claim in registry.values() 
                          if claim.get('status') in ['claimed', 'in_progress'])
        
        # Count completed work
        completed_count = len(completed_work)
        successful_count = sum(1 for work in completed_work if work.get('success'))
        
        # Count messages
        messages_dir = session_path / 'agent_messages'
        message_count = len(list(messages_dir.glob('*.json'))) if messages_dir.exists() else 0
        
        return {
            'active_agents': active_agents,
            'active_claims': active_claims,
            'completed_tasks': completed_count,
            'successful_tasks': successful_count,
            'messages_sent': message_count,
            'workload': self.get_agent_workload(session_id),
            'conflicts': len(self.detect_conflicts(session_id))
        }


# Create alias for compatibility
CoordinationManager = FileCoordinationManager