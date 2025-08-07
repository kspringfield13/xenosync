"""
Coordination System - SQLite-backed agent coordination with work claims and conflict resolution
"""

import sqlite3
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
    id: int
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


@dataclass
class AgentMessage:
    """Inter-agent communication message"""
    id: int
    from_agent: str
    to_agent: Optional[str]  # None for broadcast
    message_type: str
    content: str
    timestamp: datetime
    read: bool = False


class CoordinationManager:
    """Manages agent coordination with SQLite backend"""
    
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.database_path
        self._init_database()
    
    def _init_database(self):
        """Initialize coordination tables in database"""
        with sqlite3.connect(self.db_path) as conn:
            # Work claims table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS work_claims (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_uid TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    files TEXT NOT NULL,  -- JSON array
                    description TEXT,
                    status TEXT NOT NULL,
                    claimed_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    released_at TIMESTAMP,
                    metadata TEXT,  -- JSON object
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            ''')
            
            # Agent registry table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS agent_registry (
                    agent_uid TEXT PRIMARY KEY,
                    agent_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    last_seen TIMESTAMP NOT NULL,
                    status TEXT NOT NULL,
                    capabilities TEXT,  -- JSON array of agent capabilities
                    metrics TEXT,  -- JSON object with performance metrics
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            ''')
            
            # Inter-agent messages table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS agent_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_agent TEXT NOT NULL,
                    to_agent TEXT,  -- NULL for broadcast
                    message_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    read BOOLEAN DEFAULT 0,
                    session_id TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            ''')
            
            # Completed work log
            conn.execute('''
                CREATE TABLE IF NOT EXISTS completed_work (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_uid TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    description TEXT NOT NULL,
                    files_modified TEXT,  -- JSON array
                    completed_at TIMESTAMP NOT NULL,
                    duration_seconds INTEGER,
                    success BOOLEAN DEFAULT 1,
                    error_message TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            ''')
            
            # Create indices for performance
            conn.execute('CREATE INDEX IF NOT EXISTS idx_claims_session ON work_claims(session_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_claims_status ON work_claims(status)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_claims_agent ON work_claims(agent_uid)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_messages_session ON agent_messages(session_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_messages_to ON agent_messages(to_agent)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_completed_session ON completed_work(session_id)')
            
            conn.commit()
    
    def register_agent(self, agent_uid: str, agent_id: int, session_id: str,
                      capabilities: Optional[List[str]] = None) -> bool:
        """Register an agent in the coordination system"""
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute('''
                    INSERT INTO agent_registry 
                    (agent_uid, agent_id, session_id, started_at, last_seen, status, capabilities)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    agent_uid, agent_id, session_id,
                    datetime.now(), datetime.now(), 'active',
                    json.dumps(capabilities or [])
                ))
                conn.commit()
                logger.info(f"Registered agent {agent_uid} for session {session_id}")
                return True
            except sqlite3.IntegrityError:
                logger.warning(f"Agent {agent_uid} already registered")
                return False
    
    def update_agent_status(self, agent_uid: str, status: str, metrics: Optional[Dict] = None):
        """Update agent status and metrics"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                UPDATE agent_registry 
                SET status = ?, last_seen = ?, metrics = ?
                WHERE agent_uid = ?
            ''', (status, datetime.now(), json.dumps(metrics) if metrics else None, agent_uid))
            conn.commit()
    
    def claim_work(self, agent_uid: str, session_id: str, files: List[str],
                  description: str, metadata: Optional[Dict] = None) -> Optional[int]:
        """Try to claim work on specific files"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Check for conflicts with active claims
            cursor = conn.execute('''
                SELECT id, agent_uid, files, description, updated_at
                FROM work_claims
                WHERE session_id = ? AND status IN (?, ?)
            ''', (session_id, WorkStatus.CLAIMED.value, WorkStatus.IN_PROGRESS.value))
            
            for row in cursor:
                claimed_files = json.loads(row['files'])
                # Check for file overlap
                if any(f in claimed_files for f in files):
                    # Check if claim is stale
                    updated_at = datetime.fromisoformat(row['updated_at'])
                    if (datetime.now() - updated_at).total_seconds() > 7200:  # 2 hours
                        # Release stale claim
                        logger.warning(f"Releasing stale claim {row['id']} from {row['agent_uid']}")
                        self.release_work(row['agent_uid'], row['id'])
                    else:
                        # Active conflict
                        logger.warning(f"Work conflict: {files} already claimed by {row['agent_uid']}")
                        return None
            
            # No conflicts, create claim
            cursor = conn.execute('''
                INSERT INTO work_claims
                (agent_uid, session_id, files, description, status, claimed_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                agent_uid, session_id, json.dumps(files), description,
                WorkStatus.CLAIMED.value, datetime.now(), datetime.now(),
                json.dumps(metadata) if metadata else None
            ))
            
            claim_id = cursor.lastrowid
            conn.commit()
            
            logger.info(f"Agent {agent_uid} claimed work on {len(files)} files (claim {claim_id})")
            return claim_id
    
    def update_work_status(self, claim_id: int, status: WorkStatus):
        """Update work claim status"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                UPDATE work_claims
                SET status = ?, updated_at = ?
                WHERE id = ?
            ''', (status.value, datetime.now(), claim_id))
            conn.commit()
    
    def release_work(self, agent_uid: str, claim_id: Optional[int] = None):
        """Release work claim(s)"""
        with sqlite3.connect(self.db_path) as conn:
            if claim_id:
                conn.execute('''
                    UPDATE work_claims
                    SET status = ?, released_at = ?, updated_at = ?
                    WHERE id = ? AND agent_uid = ?
                ''', (WorkStatus.RELEASED.value, datetime.now(), datetime.now(), claim_id, agent_uid))
            else:
                # Release all active claims for agent
                conn.execute('''
                    UPDATE work_claims
                    SET status = ?, released_at = ?, updated_at = ?
                    WHERE agent_uid = ? AND status IN (?, ?)
                ''', (
                    WorkStatus.RELEASED.value, datetime.now(), datetime.now(),
                    agent_uid, WorkStatus.CLAIMED.value, WorkStatus.IN_PROGRESS.value
                ))
            conn.commit()
    
    def get_active_claims(self, session_id: str) -> List[WorkClaim]:
        """Get all active work claims for a session"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM work_claims
                WHERE session_id = ? AND status IN (?, ?)
                ORDER BY claimed_at DESC
            ''', (session_id, WorkStatus.CLAIMED.value, WorkStatus.IN_PROGRESS.value))
            
            claims = []
            for row in cursor:
                claims.append(self._work_claim_from_row(row))
            
            return claims
    
    def _work_claim_from_row(self, row: sqlite3.Row) -> WorkClaim:
        """Convert database row to WorkClaim object"""
        return WorkClaim(
            id=row['id'],
            agent_uid=row['agent_uid'],
            session_id=row['session_id'],
            files=json.loads(row['files']),
            description=row['description'],
            status=WorkStatus(row['status']),
            claimed_at=datetime.fromisoformat(row['claimed_at']),
            updated_at=datetime.fromisoformat(row['updated_at']),
            released_at=datetime.fromisoformat(row['released_at']) if row['released_at'] else None,
            metadata=json.loads(row['metadata']) if row['metadata'] else None
        )
    
    def log_completed_work(self, agent_uid: str, session_id: str, description: str,
                          files_modified: Optional[List[str]] = None,
                          duration_seconds: Optional[int] = None,
                          success: bool = True, error_message: Optional[str] = None):
        """Log completed work"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO completed_work
                (agent_uid, session_id, description, files_modified, completed_at,
                 duration_seconds, success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                agent_uid, session_id, description,
                json.dumps(files_modified) if files_modified else None,
                datetime.now(), duration_seconds, success, error_message
            ))
            conn.commit()
            
            status = "completed" if success else "failed"
            logger.info(f"Agent {agent_uid} {status} work: {description}")
    
    def get_completed_work(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all completed work for a session"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM completed_work
                WHERE session_id = ?
                ORDER BY completed_at DESC
            ''', (session_id,))
            
            work_items = []
            for row in cursor:
                work_items.append({
                    'agent_uid': row['agent_uid'],
                    'description': row['description'],
                    'files_modified': json.loads(row['files_modified']) if row['files_modified'] else [],
                    'completed_at': row['completed_at'],
                    'duration_seconds': row['duration_seconds'],
                    'success': bool(row['success']),
                    'error_message': row['error_message']
                })
            
            return work_items
    
    def send_message(self, from_agent: str, to_agent: Optional[str], session_id: str,
                    message_type: str, content: str):
        """Send message between agents"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO agent_messages
                (from_agent, to_agent, message_type, content, timestamp, session_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (from_agent, to_agent, message_type, content, datetime.now(), session_id))
            conn.commit()
            
            target = to_agent or "all"
            logger.debug(f"Message from {from_agent} to {target}: {message_type}")
    
    def get_messages(self, agent_uid: str, session_id: str, 
                     unread_only: bool = True) -> List[AgentMessage]:
        """Get messages for an agent"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            if unread_only:
                cursor = conn.execute('''
                    SELECT * FROM agent_messages
                    WHERE session_id = ? AND (to_agent = ? OR to_agent IS NULL)
                    AND read = 0
                    ORDER BY timestamp
                ''', (session_id, agent_uid))
            else:
                cursor = conn.execute('''
                    SELECT * FROM agent_messages
                    WHERE session_id = ? AND (to_agent = ? OR to_agent IS NULL)
                    ORDER BY timestamp DESC
                    LIMIT 100
                ''', (session_id, agent_uid))
            
            messages = []
            for row in cursor:
                messages.append(AgentMessage(
                    id=row['id'],
                    from_agent=row['from_agent'],
                    to_agent=row['to_agent'],
                    message_type=row['message_type'],
                    content=row['content'],
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    read=bool(row['read'])
                ))
            
            # Mark messages as read
            if unread_only and messages:
                message_ids = [m.id for m in messages]
                placeholders = ','.join(['?' for _ in message_ids])
                conn.execute(
                    f"UPDATE agent_messages SET read = 1 WHERE id IN ({placeholders})",
                    message_ids
                )
                conn.commit()
            
            return messages
    
    def get_agent_workload(self, session_id: str) -> Dict[str, int]:
        """Get workload distribution across agents"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT agent_uid, COUNT(*) as claim_count
                FROM work_claims
                WHERE session_id = ? AND status IN (?, ?)
                GROUP BY agent_uid
            ''', (session_id, WorkStatus.CLAIMED.value, WorkStatus.IN_PROGRESS.value))
            
            workload = {}
            for row in cursor:
                workload[row['agent_uid']] = row['claim_count']
            
            return workload
    
    def detect_conflicts(self, session_id: str) -> List[Tuple[str, str, List[str]]]:
        """Detect file conflicts between agents"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT agent_uid, files FROM work_claims
                WHERE session_id = ? AND status IN (?, ?)
            ''', (session_id, WorkStatus.CLAIMED.value, WorkStatus.IN_PROGRESS.value))
            
            claims = []
            for row in cursor:
                claims.append((row['agent_uid'], json.loads(row['files'])))
            
            conflicts = []
            for i, (agent1, files1) in enumerate(claims):
                for agent2, files2 in claims[i+1:]:
                    shared_files = list(set(files1) & set(files2))
                    if shared_files:
                        conflicts.append((agent1, agent2, shared_files))
            
            return conflicts
    
    def cleanup_stale_claims(self, session_id: str, hours: int = 2) -> int:
        """Clean up stale work claims"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                UPDATE work_claims
                SET status = ?, released_at = ?, updated_at = ?
                WHERE session_id = ? AND status IN (?, ?)
                AND updated_at < ?
            ''', (
                WorkStatus.RELEASED.value, datetime.now(), datetime.now(),
                session_id, WorkStatus.CLAIMED.value, WorkStatus.IN_PROGRESS.value,
                cutoff_time
            ))
            
            cleaned = cursor.rowcount
            conn.commit()
            
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} stale claims for session {session_id}")
            
            return cleaned
    
    def get_coordination_summary(self, session_id: str) -> Dict[str, Any]:
        """Get coordination summary for a session"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Active agents
            cursor = conn.execute('''
                SELECT COUNT(*) as count FROM agent_registry
                WHERE session_id = ? AND status = 'active'
            ''', (session_id,))
            active_agents = cursor.fetchone()['count']
            
            # Active claims
            cursor = conn.execute('''
                SELECT COUNT(*) as count FROM work_claims
                WHERE session_id = ? AND status IN (?, ?)
            ''', (session_id, WorkStatus.CLAIMED.value, WorkStatus.IN_PROGRESS.value))
            active_claims = cursor.fetchone()['count']
            
            # Completed work
            cursor = conn.execute('''
                SELECT COUNT(*) as count, SUM(success) as successful
                FROM completed_work WHERE session_id = ?
            ''', (session_id,))
            row = cursor.fetchone()
            completed_count = row['count'] or 0
            successful_count = row['successful'] or 0
            
            # Messages
            cursor = conn.execute('''
                SELECT COUNT(*) as count FROM agent_messages
                WHERE session_id = ?
            ''', (session_id,))
            message_count = cursor.fetchone()['count']
            
            return {
                'active_agents': active_agents,
                'active_claims': active_claims,
                'completed_tasks': completed_count,
                'successful_tasks': successful_count,
                'messages_sent': message_count,
                'workload': self.get_agent_workload(session_id),
                'conflicts': len(self.detect_conflicts(session_id))
            }