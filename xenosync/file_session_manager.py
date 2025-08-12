"""
File-based session management using JSON files
"""

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
from .file_utils import (
    read_json_file, write_json_file, safe_append_line,
    update_json_file, ensure_directory, JSONFileStore,
    rotate_file, FileLock
)


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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['status'] = self.status.value
        data['started_at'] = self.started_at.isoformat()
        if self.ended_at:
            data['ended_at'] = self.ended_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Session':
        """Create from dictionary"""
        data['status'] = SessionStatus(data['status'])
        data['started_at'] = datetime.fromisoformat(data['started_at'])
        if data.get('ended_at'):
            data['ended_at'] = datetime.fromisoformat(data['ended_at'])
        return cls(**data)


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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['status'] = self.status.value
        if self.started_at:
            data['started_at'] = self.started_at.isoformat()
        if self.completed_at:
            data['completed_at'] = self.completed_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SyncStep':
        """Create from dictionary"""
        data['status'] = StepStatus(data['status'])
        if data.get('started_at'):
            data['started_at'] = datetime.fromisoformat(data['started_at'])
        if data.get('completed_at'):
            data['completed_at'] = datetime.fromisoformat(data['completed_at'])
        return cls(**data)


@dataclass
class SessionEvent:
    """Session event for audit trail"""
    session_id: str
    timestamp: datetime
    event_type: str
    data: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'session_id': self.session_id,
            'timestamp': self.timestamp.isoformat(),
            'event_type': self.event_type,
            'data': self.data
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionEvent':
        """Create from dictionary"""
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class FileSessionManager:
    """Manages sync sessions with file-based backend"""
    
    def __init__(self, config: Config):
        self.config = config
        self.sessions_dir = config.sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        
        # Create sessions index file
        self.index_path = self.sessions_dir / 'sessions_index.json'
        if not self.index_path.exists():
            write_json_file(self.index_path, {})
    
    def get_session_path(self, session_id: str) -> Path:
        """Get path for session directory"""
        return self.sessions_dir / session_id
    
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
                'prompt_format': prompt.format
            }
        )
        
        # Create session directory
        session_path = self.get_session_path(session_id)
        ensure_directory(session_path)
        
        # Save session data
        session_file = session_path / 'session.json'
        write_json_file(session_file, session.to_dict())
        
        # Save steps
        steps = []
        for i, step in enumerate(prompt.steps, 1):
            sync_step = SyncStep(
                session_id=session_id,
                step_number=i,
                description=step.description or '',
                content=step.content,
                status=StepStatus.PENDING,
                started_at=None,
                completed_at=None,
                error=None
            )
            steps.append(sync_step.to_dict())
        
        steps_file = session_path / 'steps.json'
        write_json_file(steps_file, steps)
        
        # Create events log
        events_file = session_path / 'events.log'
        events_file.touch()
        
        # Log session creation
        self.log_event(session_id, 'session_created', {
            'project': prompt.name,
            'total_steps': len(prompt.steps)
        })
        
        # Update sessions index
        self._update_index(session_id, 'add', {
            'project_name': prompt.name,
            'status': SessionStatus.ACTIVE.value,
            'started_at': datetime.now().isoformat()
        })
        
        logger.info(f"Created session {session_id} for {prompt.name}")
        return session
    
    def _update_index(self, session_id: str, action: str, data: Optional[Dict] = None):
        """Update sessions index"""
        def updater(index):
            if action == 'add':
                index[session_id] = data or {}
            elif action == 'update' and session_id in index:
                index[session_id].update(data or {})
            elif action == 'remove' and session_id in index:
                del index[session_id]
            return index
        
        update_json_file(self.index_path, updater)
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID"""
        session_path = self.get_session_path(session_id)
        session_file = session_path / 'session.json'
        
        if not session_file.exists():
            return None
        
        try:
            data = read_json_file(session_file)
            return Session.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None
    
    def get_active_sessions(self) -> List[Session]:
        """Get all active sessions"""
        return self._get_sessions_by_status(SessionStatus.ACTIVE)
    
    def get_all_sessions(self, limit: int = 100) -> List[Session]:
        """Get all sessions with limit"""
        index = read_json_file(self.index_path, {})
        
        # Sort by started_at descending
        sorted_sessions = sorted(
            index.items(),
            key=lambda x: x[1].get('started_at', ''),
            reverse=True
        )[:limit]
        
        sessions = []
        for session_id, _ in sorted_sessions:
            session = self.get_session(session_id)
            if session:
                sessions.append(session)
        
        return sessions
    
    def _get_sessions_by_status(self, status: SessionStatus) -> List[Session]:
        """Get sessions by status"""
        index = read_json_file(self.index_path, {})
        sessions = []
        
        for session_id, info in index.items():
            if info.get('status') == status.value:
                session = self.get_session(session_id)
                if session:
                    sessions.append(session)
        
        return sorted(sessions, key=lambda s: s.started_at, reverse=True)
    
    def update_session_status(self, session_id: str, status: SessionStatus, 
                            error: Optional[str] = None):
        """Update session status"""
        session_path = self.get_session_path(session_id)
        session_file = session_path / 'session.json'
        
        if not session_file.exists():
            logger.error(f"Session {session_id} not found")
            return
        
        ended_at = datetime.now() if status != SessionStatus.ACTIVE else None
        
        def updater(data):
            data['status'] = status.value
            if ended_at:
                data['ended_at'] = ended_at.isoformat()
            if error:
                data['error'] = error
            return data
        
        update_json_file(session_file, updater)
        
        # Update index
        self._update_index(session_id, 'update', {
            'status': status.value,
            'ended_at': ended_at.isoformat() if ended_at else None
        })
        
        self.log_event(session_id, 'status_changed', {
            'new_status': status.value,
            'error': error
        })
    
    def update_step_progress(self, session_id: str, step_number: int, status: str):
        """Update build step progress"""
        session_path = self.get_session_path(session_id)
        steps_file = session_path / 'steps.json'
        
        if not steps_file.exists():
            logger.error(f"Steps file not found for session {session_id}")
            return
        
        step_status = StepStatus(status)
        now = datetime.now()
        
        def updater(steps):
            for step in steps:
                if step['step_number'] == step_number:
                    step['status'] = step_status.value
                    
                    if step_status == StepStatus.IN_PROGRESS:
                        step['started_at'] = now.isoformat()
                    elif step_status in [StepStatus.COMPLETED, StepStatus.FAILED]:
                        step['completed_at'] = now.isoformat()
                    
                    break
            return steps
        
        update_json_file(steps_file, updater)
        
        # Update session current step if in progress
        if step_status == StepStatus.IN_PROGRESS:
            session_file = session_path / 'session.json'
            
            def session_updater(data):
                data['current_step'] = step_number
                return data
            
            update_json_file(session_file, session_updater)
        
        self.log_event(session_id, 'step_progress', {
            'step_number': step_number,
            'status': status
        })
    
    def log_event(self, session_id: str, event_type: str, data: Dict[str, Any]):
        """Log a session event"""
        session_path = self.get_session_path(session_id)
        events_file = session_path / 'events.log'
        
        event = SessionEvent(
            session_id=session_id,
            timestamp=datetime.now(),
            event_type=event_type,
            data=data
        )
        
        # Append to log file
        log_line = json.dumps(event.to_dict(), default=str)
        safe_append_line(events_file, log_line)
    
    def get_session_events(self, session_id: str) -> List[SessionEvent]:
        """Get all events for a session"""
        session_path = self.get_session_path(session_id)
        events_file = session_path / 'events.log'
        
        if not events_file.exists():
            return []
        
        events = []
        try:
            with open(events_file, 'r') as f:
                for line in f:
                    if line.strip():
                        try:
                            data = json.loads(line)
                            events.append(SessionEvent.from_dict(data))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"Failed to read events for session {session_id}: {e}")
        
        return events
    
    def get_session_steps(self, session_id: str) -> List[SyncStep]:
        """Get all steps for a session"""
        session_path = self.get_session_path(session_id)
        steps_file = session_path / 'steps.json'
        
        if not steps_file.exists():
            return []
        
        try:
            steps_data = read_json_file(steps_file, [])
            return [SyncStep.from_dict(step) for step in steps_data]
        except Exception as e:
            logger.error(f"Failed to load steps for session {session_id}: {e}")
            return []
    
    def archive_session(self, session_id: str, status: str = 'completed'):
        """Archive a session"""
        session_status = SessionStatus(status.upper())
        self.update_session_status(session_id, session_status)
        
        # Create archive directory if needed
        if self.config.get('archive_completed', True):
            archive_dir = self.sessions_dir / 'archive' / session_id
            archive_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy session files to archive
            session_path = self.get_session_path(session_id)
            if session_path.exists():
                import shutil
                for file in session_path.iterdir():
                    if file.is_file():
                        shutil.copy2(file, archive_dir / file.name)
        
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
        index = read_json_file(self.index_path, {})
        return len(index)
    
    def get_statistics(self, days: int = 30) -> Dict[str, Any]:
        """Get session statistics"""
        cutoff_date = datetime.now() - timedelta(days=days)
        index = read_json_file(self.index_path, {})
        
        # Filter sessions by date
        recent_sessions = {}
        for session_id, info in index.items():
            if 'started_at' in info:
                started_at = datetime.fromisoformat(info['started_at'])
                if started_at > cutoff_date:
                    recent_sessions[session_id] = info
        
        # Count by status
        status_counts = {}
        for info in recent_sessions.values():
            status = info.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Calculate average duration for completed sessions
        durations = []
        for session_id in recent_sessions:
            session = self.get_session(session_id)
            if session and session.status == SessionStatus.COMPLETED and session.duration:
                durations.append(session.duration.total_seconds() / 60)  # minutes
        
        avg_duration_minutes = sum(durations) / len(durations) if durations else 0
        
        # Success rate
        completed = status_counts.get(SessionStatus.COMPLETED.value, 0)
        failed = status_counts.get(SessionStatus.FAILED.value, 0)
        success_rate = (completed / (completed + failed) * 100) if (completed + failed) > 0 else 0
        
        return {
            'total_sessions': len(recent_sessions),
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
                'session': session.to_dict(),
                'steps': [step.to_dict() for step in steps],
                'events': [event.to_dict() for event in events]
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


# Create alias for compatibility
SessionManager = FileSessionManager