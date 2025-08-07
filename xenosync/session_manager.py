"""
Session management with SQLite backend
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum
import uuid

from .config import Config
from .exceptions import SessionError


logger = logging.getLogger(__name__)


class SessionStatus(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    PAUSED = "paused"


class StepStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Session:
    """Build session data model"""
    id: str
    prompt_file: str
    project_name: str
    status: SessionStatus
    started_at: datetime
    ended_at: Optional[datetime]
    current_step: int
    total_steps: int
    error: Optional[str]
    metadata: Dict[str, Any]
    
    @property
    def duration(self) -> Optional[timedelta]:
        if self.ended_at:
            return self.ended_at - self.started_at
        elif self.status == SessionStatus.ACTIVE:
            return datetime.now() - self.started_at
        return None
    
    @property
    def progress_percentage(self) -> int:
        if self.total_steps == 0:
            return 0
        return int((self.current_step / self.total_steps) * 100)


@dataclass
class SyncStep:
    """Build step data model"""
    session_id: str
    step_number: int
    description: str
    content: str
    status: StepStatus
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error: Optional[str]
    
    @property
    def duration(self) -> Optional[timedelta]:
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None


@dataclass
class SessionEvent:
    """Session event for audit trail"""
    session_id: str
    timestamp: datetime
    event_type: str
    data: Dict[str, Any]


class SessionManager:
    """Manages sync sessions with SQLite backend"""
    
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.database_path
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    prompt_file TEXT NOT NULL,
                    project_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    ended_at TIMESTAMP,
                    current_step INTEGER DEFAULT 0,
                    total_steps INTEGER NOT NULL,
                    error TEXT,
                    metadata TEXT
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS build_steps (
                    session_id TEXT NOT NULL,
                    step_number INTEGER NOT NULL,
                    description TEXT,
                    content TEXT,
                    status TEXT NOT NULL,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    error TEXT,
                    PRIMARY KEY (session_id, step_number),
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS session_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    event_type TEXT NOT NULL,
                    data TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            ''')
            
            # Create indices
            conn.execute('CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_events_session ON session_events(session_id)')
            
            conn.commit()
    
    def create_session(self, prompt) -> Session:
        """Create a new sync session"""
        session_id = str(uuid.uuid4())
        session = Session(
            id=session_id,
            prompt_file=prompt.filename,
            project_name=prompt.name,
            status=SessionStatus.ACTIVE,
            started_at=datetime.now(),
            ended_at=None,
            current_step=0,
            total_steps=len(prompt.steps),
            error=None,
            metadata={
                'prompt_format': prompt.format,
                'profile': self.config.profile.name
            }
        )
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO sessions 
                (id, prompt_file, project_name, status, started_at, ended_at, 
                 current_step, total_steps, error, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session.id, session.prompt_file, session.project_name,
                session.status.value, session.started_at, session.ended_at,
                session.current_step, session.total_steps, session.error,
                json.dumps(session.metadata)
            ))
            
            # Insert sync steps
            for i, step in enumerate(prompt.steps, 1):
                conn.execute('''
                    INSERT INTO build_steps
                    (session_id, step_number, description, content, status)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    session_id, i, step.description, step.content,
                    StepStatus.PENDING.value
                ))
            
            conn.commit()
        
        # Log session creation
        self.log_event(session_id, 'session_created', {
            'project': prompt.name,
            'total_steps': len(prompt.steps)
        })
        
        logger.info(f"Created session {session_id} for {prompt.name}")
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                'SELECT * FROM sessions WHERE id = ?', (session_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return self._session_from_row(row)
    
    def _session_from_row(self, row: sqlite3.Row) -> Session:
        """Convert database row to Session object"""
        return Session(
            id=row['id'],
            prompt_file=row['prompt_file'],
            project_name=row['project_name'],
            status=SessionStatus(row['status']),
            started_at=datetime.fromisoformat(row['started_at']),
            ended_at=datetime.fromisoformat(row['ended_at']) if row['ended_at'] else None,
            current_step=row['current_step'],
            total_steps=row['total_steps'],
            error=row['error'],
            metadata=json.loads(row['metadata']) if row['metadata'] else {}
        )
    
    def get_active_sessions(self) -> List[Session]:
        """Get all active sessions"""
        return self._get_sessions_by_status(SessionStatus.ACTIVE)
    
    def get_all_sessions(self, limit: int = 100) -> List[Session]:
        """Get all sessions with limit"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                'SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?',
                (limit,)
            )
            return [self._session_from_row(row) for row in cursor]
    
    def _get_sessions_by_status(self, status: SessionStatus) -> List[Session]:
        """Get sessions by status"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                'SELECT * FROM sessions WHERE status = ? ORDER BY started_at DESC',
                (status.value,)
            )
            return [self._session_from_row(row) for row in cursor]
    
    def update_session_status(self, session_id: str, status: SessionStatus, 
                            error: Optional[str] = None):
        """Update session status"""
        ended_at = datetime.now() if status != SessionStatus.ACTIVE else None
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                UPDATE sessions 
                SET status = ?, ended_at = ?, error = ?
                WHERE id = ?
            ''', (status.value, ended_at, error, session_id))
            conn.commit()
        
        self.log_event(session_id, 'status_changed', {
            'new_status': status.value,
            'error': error
        })
    
    def update_step_progress(self, session_id: str, step_number: int, status: str):
        """Update build step progress"""
        step_status = StepStatus(status)
        now = datetime.now()
        
        with sqlite3.connect(self.db_path) as conn:
            if step_status == StepStatus.IN_PROGRESS:
                conn.execute('''
                    UPDATE build_steps 
                    SET status = ?, started_at = ?
                    WHERE session_id = ? AND step_number = ?
                ''', (step_status.value, now, session_id, step_number))
            elif step_status in [StepStatus.COMPLETED, StepStatus.FAILED]:
                conn.execute('''
                    UPDATE build_steps 
                    SET status = ?, completed_at = ?
                    WHERE session_id = ? AND step_number = ?
                ''', (step_status.value, now, session_id, step_number))
            
            # Update session current step
            if step_status == StepStatus.IN_PROGRESS:
                conn.execute('''
                    UPDATE sessions 
                    SET current_step = ?
                    WHERE id = ?
                ''', (step_number, session_id))
            
            conn.commit()
        
        self.log_event(session_id, 'step_progress', {
            'step_number': step_number,
            'status': status
        })
    
    def log_event(self, session_id: str, event_type: str, data: Dict[str, Any]):
        """Log a session event"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO session_events (session_id, timestamp, event_type, data)
                VALUES (?, ?, ?, ?)
            ''', (session_id, datetime.now(), event_type, json.dumps(data)))
            conn.commit()
    
    def get_session_events(self, session_id: str) -> List[SessionEvent]:
        """Get all events for a session"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM session_events 
                WHERE session_id = ? 
                ORDER BY timestamp
            ''', (session_id,))
            
            events = []
            for row in cursor:
                events.append(SessionEvent(
                    session_id=row['session_id'],
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    event_type=row['event_type'],
                    data=json.loads(row['data']) if row['data'] else {}
                ))
            
            return events
    
    def get_session_steps(self, session_id: str) -> List[SyncStep]:
        """Get all steps for a session"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM build_steps 
                WHERE session_id = ? 
                ORDER BY step_number
            ''', (session_id,))
            
            steps = []
            for row in cursor:
                steps.append(SyncStep(
                    session_id=row['session_id'],
                    step_number=row['step_number'],
                    description=row['description'],
                    content=row['content'],
                    status=StepStatus(row['status']),
                    started_at=datetime.fromisoformat(row['started_at']) if row['started_at'] else None,
                    completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
                    error=row['error']
                ))
            
            return steps
    
    def archive_session(self, session_id: str, status: str = 'completed'):
        """Archive a session"""
        session_status = SessionStatus(status.upper())
        self.update_session_status(session_id, session_status)
        
        # Create archive directory if needed
        if self.config.get('archive_completed', True):
            archive_dir = self.config.sessions_dir / 'archive' / session_id
            archive_dir.mkdir(parents=True, exist_ok=True)
            
            # Export session data
            session = self.get_session(session_id)
            if session:
                export_data = {
                    'session': asdict(session),
                    'steps': [asdict(step) for step in self.get_session_steps(session_id)],
                    'events': [asdict(event) for event in self.get_session_events(session_id)]
                }
                
                export_file = archive_dir / 'session_data.json'
                with open(export_file, 'w') as f:
                    json.dump(export_data, f, indent=2, default=str)
        
        logger.info(f"Archived session {session_id} with status {status}")
    
    def kill_session(self, session_id: str) -> bool:
        """Kill an active session"""
        session = self.get_session(session_id)
        if not session or session.status != SessionStatus.ACTIVE:
            return False
        
        # Update status
        self.update_session_status(session_id, SessionStatus.INTERRUPTED)
        
        # Kill tmux session if using tmux
        if self.config.use_tmux:
            import subprocess
            short_id = session_id[:8]
            tmux_session = f"xsync-{short_id}"
            try:
                subprocess.run(['tmux', 'kill-session', '-t', tmux_session], check=True)
            except subprocess.CalledProcessError:
                pass  # Session might not exist
        
        return True
    
    def resume_session(self, session_id: str) -> Optional[Session]:
        """Resume a paused or interrupted session"""
        session = self.get_session(session_id)
        if not session:
            return None
        
        if session.status not in [SessionStatus.PAUSED, SessionStatus.INTERRUPTED]:
            logger.warning(f"Cannot resume session in status {session.status}")
            return None
        
        # Update status to active
        self.update_session_status(session_id, SessionStatus.ACTIVE)
        
        self.log_event(session_id, 'session_resumed', {
            'previous_status': session.status.value
        })
        
        return self.get_session(session_id)
    
    def count_sessions(self) -> int:
        """Get total number of sessions"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT COUNT(*) FROM sessions')
            return cursor.fetchone()[0]
    
    def get_statistics(self, days: int = 30) -> Dict[str, Any]:
        """Get session statistics"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with sqlite3.connect(self.db_path) as conn:
            # Total sessions
            cursor = conn.execute(
                'SELECT COUNT(*) FROM sessions WHERE started_at > ?',
                (cutoff_date,)
            )
            total_sessions = cursor.fetchone()[0]
            
            # Status breakdown
            cursor = conn.execute('''
                SELECT status, COUNT(*) 
                FROM sessions 
                WHERE started_at > ?
                GROUP BY status
            ''', (cutoff_date,))
            status_counts = dict(cursor.fetchall())
            
            # Average duration
            cursor = conn.execute('''
                SELECT AVG(julianday(ended_at) - julianday(started_at)) * 24 * 60
                FROM sessions 
                WHERE status = ? AND started_at > ? AND ended_at IS NOT NULL
            ''', (SessionStatus.COMPLETED.value, cutoff_date))
            avg_duration_minutes = cursor.fetchone()[0] or 0
            
            # Success rate
            completed = status_counts.get(SessionStatus.COMPLETED.value, 0)
            failed = status_counts.get(SessionStatus.FAILED.value, 0)
            success_rate = (completed / (completed + failed) * 100) if (completed + failed) > 0 else 0
            
            return {
                'total_sessions': total_sessions,
                'status_breakdown': status_counts,
                'average_duration_minutes': round(avg_duration_minutes, 1),
                'success_rate': round(success_rate, 1),
                'period_days': days
            }
    
    def generate_summary(self, session_id: str, format: str = 'markdown') -> Optional[str]:
        """Generate session summary in specified format"""
        session = self.get_session(session_id)
        if not session:
            return None
        
        steps = self.get_session_steps(session_id)
        events = self.get_session_events(session_id)
        
        if format == 'markdown':
            return self._generate_markdown_summary(session, steps, events)
        elif format == 'json':
            data = {
                'session': asdict(session),
                'steps': [asdict(step) for step in steps],
                'events': [asdict(event) for event in events]
            }
            return json.dumps(data, indent=2, default=str)
        elif format == 'html':
            return self._generate_html_summary(session, steps, events)
        else:
            raise ValueError(f"Unknown format: {format}")
    
    def _generate_markdown_summary(self, session: Session, steps: List[SyncStep], 
                                 events: List[SessionEvent]) -> str:
        """Generate markdown summary"""
        summary = f"""# Sync Session Summary

## Session: {session.id}

### Overview
- **Project**: {session.project_name}
- **Status**: {session.status.value}
- **Started**: {session.started_at.strftime('%Y-%m-%d %H:%M:%S')}
- **Ended**: {session.ended_at.strftime('%Y-%m-%d %H:%M:%S') if session.ended_at else 'N/A'}
- **Duration**: {session.duration or 'N/A'}
- **Progress**: {session.current_step}/{session.total_steps} steps ({session.progress_percentage}%)

### Sync Steps
"""
        
        for step in steps:
            icon = {
                StepStatus.COMPLETED: "✅",
                StepStatus.IN_PROGRESS: "🔄",
                StepStatus.FAILED: "❌",
                StepStatus.PENDING: "⏳",
                StepStatus.SKIPPED: "⏭️"
            }.get(step.status, "❓")
            
            summary += f"\n{icon} **Step {step.step_number}**: {step.description or 'N/A'}\n"
            if step.duration:
                summary += f"   - Duration: {step.duration}\n"
            if step.error:
                summary += f"   - Error: {step.error}\n"
        
        if session.error:
            summary += f"\n### Error\n{session.error}\n"
        
        summary += f"\n---\n*Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
        
        return summary
    
    def _generate_html_summary(self, session: Session, steps: List[SyncStep], 
                             events: List[SessionEvent]) -> str:
        """Generate HTML summary"""
        # Simple HTML template
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Session {session.id}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .status-{SessionStatus.COMPLETED.value} {{ color: green; }}
        .status-{SessionStatus.FAILED.value} {{ color: red; }}
        .status-{SessionStatus.ACTIVE.value} {{ color: blue; }}
        .step {{ margin: 10px 0; padding: 10px; border-left: 3px solid #ccc; }}
        .step-completed {{ border-color: green; }}
        .step-failed {{ border-color: red; }}
        .step-in_progress {{ border-color: orange; }}
    </style>
</head>
<body>
    <h1>Sync Session Summary</h1>
    <h2>Session: {session.id}</h2>
    
    <h3>Overview</h3>
    <ul>
        <li><strong>Project</strong>: {session.project_name}</li>
        <li><strong>Status</strong>: <span class="status-{session.status.value}">{session.status.value}</span></li>
        <li><strong>Progress</strong>: {session.current_step}/{session.total_steps} ({session.progress_percentage}%)</li>
        <li><strong>Duration</strong>: {session.duration or 'N/A'}</li>
    </ul>
    
    <h3>Sync Steps</h3>
"""
        
        for step in steps:
            html += f"""
    <div class="step step-{step.status.value}">
        <strong>Step {step.step_number}</strong>: {step.description or 'N/A'}
        <br>Status: {step.status.value}
        {f'<br>Duration: {step.duration}' if step.duration else ''}
    </div>
"""
        
        html += """
</body>
</html>"""
        
        return html
    
    def display_session_summary(self, session: Session):
        """Display session summary to console"""
        status_colors = {
            SessionStatus.ACTIVE: "\033[34m",  # Blue
            SessionStatus.COMPLETED: "\033[32m",  # Green
            SessionStatus.FAILED: "\033[31m",  # Red
            SessionStatus.INTERRUPTED: "\033[33m",  # Yellow
            SessionStatus.PAUSED: "\033[35m"  # Magenta
        }
        
        color = status_colors.get(session.status, "")
        reset = "\033[0m"
        
        print(f"{color}● {session.id[:8]}{reset} - {session.project_name}")
        print(f"  Status: {session.status.value} | Progress: {session.current_step}/{session.total_steps}")
        if session.duration:
            print(f"  Duration: {session.duration}")
    
    def display_session_status(self, session: Session, detailed: bool = False):
        """Display detailed session status"""
        self.display_session_summary(session)
        
        if detailed:
            print("\nSteps:")
            steps = self.get_session_steps(session.id)
            for step in steps:
                icon = {
                    StepStatus.COMPLETED: "✅",
                    StepStatus.IN_PROGRESS: "🔄",
                    StepStatus.FAILED: "❌",
                    StepStatus.PENDING: "⏳",
                    StepStatus.SKIPPED: "⏭️"
                }.get(step.status, "❓")
                
                print(f"  {icon} Step {step.step_number}: {step.description or 'N/A'}")
                if step.duration:
                    print(f"     Duration: {step.duration}")
    
    def display_statistics(self, stats: Dict[str, Any]):
        """Display statistics to console"""
        print(f"\n📊 Build Statistics (last {stats['period_days']} days)")
        print("=" * 50)
        print(f"Total Sessions: {stats['total_sessions']}")
        print(f"Success Rate: {stats['success_rate']}%")
        print(f"Average Duration: {stats['average_duration_minutes']} minutes")
        print("\nStatus Breakdown:")
        for status, count in stats['status_breakdown'].items():
            print(f"  {status}: {count}")
    
    def stream_logs(self, session_id: str):
        """Stream session logs (placeholder for log streaming)"""
        # This would be implemented to stream actual log files
        print(f"Streaming logs for session {session_id}...")
        print("(Log streaming not yet implemented)")