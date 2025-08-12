"""
File utilities for atomic operations and file-based coordination
"""

import json
import os
import fcntl
import tempfile
import shutil
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class FileLock:
    """Simple file-based lock using fcntl (Unix) or file existence (Windows)"""
    
    def __init__(self, path: Path, timeout: int = 30):
        self.path = path
        self.timeout = timeout
        self.lock_file = None
        self.locked = False
    
    def acquire(self) -> bool:
        """Acquire the lock"""
        start_time = time.time()
        lock_path = Path(str(self.path) + '.lock')
        
        while time.time() - start_time < self.timeout:
            try:
                # Try to create lock file exclusively
                self.lock_file = open(lock_path, 'x')
                
                # On Unix, also use fcntl for extra safety
                if hasattr(fcntl, 'flock'):
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                
                self.locked = True
                return True
                
            except (FileExistsError, IOError):
                # Lock is held by another process
                time.sleep(0.1)
                continue
        
        return False
    
    def release(self):
        """Release the lock"""
        if self.locked and self.lock_file:
            try:
                # Release fcntl lock if on Unix
                if hasattr(fcntl, 'flock'):
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                
                self.lock_file.close()
                
                # Remove lock file
                lock_path = Path(str(self.path) + '.lock')
                if lock_path.exists():
                    lock_path.unlink()
                    
            except Exception as e:
                logger.warning(f"Error releasing lock: {e}")
            finally:
                self.locked = False
                self.lock_file = None
    
    def __enter__(self):
        if not self.acquire():
            raise TimeoutError(f"Could not acquire lock for {self.path}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


@contextmanager
def atomic_write(path: Path, mode: str = 'w'):
    """Context manager for atomic file writes using temp file + rename"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create temp file in same directory for atomic rename
    fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix='.tmp_')
    
    try:
        with os.fdopen(fd, mode) as f:
            yield f
        
        # Atomic rename
        shutil.move(temp_path, path)
        
    except Exception:
        # Clean up temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def read_json_file(path: Path, default: Optional[Any] = None) -> Any:
    """Read JSON file with optional default value"""
    try:
        if not path.exists():
            return default if default is not None else {}
        
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Error reading JSON from {path}: {e}")
        return default if default is not None else {}


def write_json_file(path: Path, data: Any, indent: int = 2):
    """Write JSON file atomically"""
    path = Path(path)
    
    with atomic_write(path) as f:
        json.dump(data, f, indent=indent, default=str, ensure_ascii=False)


def append_to_json_array(path: Path, item: Any, max_items: Optional[int] = None) -> List:
    """Append item to JSON array file atomically"""
    with FileLock(path):
        data = read_json_file(path, default=[])
        
        if not isinstance(data, list):
            data = []
        
        data.append(item)
        
        # Trim if max_items specified
        if max_items and len(data) > max_items:
            data = data[-max_items:]
        
        write_json_file(path, data)
        return data


def update_json_file(path: Path, updater: Callable[[Any], Any]) -> Any:
    """Update JSON file atomically with a function"""
    with FileLock(path):
        data = read_json_file(path)
        updated_data = updater(data)
        write_json_file(path, updated_data)
        return updated_data


def ensure_directory(path: Path) -> Path:
    """Ensure directory exists"""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup_old_files(directory: Path, pattern: str, hours: int = 24):
    """Clean up files older than specified hours"""
    if not directory.exists():
        return 0
    
    cutoff_time = datetime.now() - timedelta(hours=hours)
    cleaned = 0
    
    for file_path in directory.glob(pattern):
        if file_path.is_file():
            # Check file modification time
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
            if mtime < cutoff_time:
                try:
                    file_path.unlink()
                    cleaned += 1
                except Exception as e:
                    logger.warning(f"Failed to clean up {file_path}: {e}")
    
    return cleaned


def is_file_stale(path: Path, hours: int = 2) -> bool:
    """Check if a file is older than specified hours"""
    if not path.exists():
        return False
    
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    age = datetime.now() - mtime
    return age.total_seconds() > (hours * 3600)


def safe_read_lines(path: Path, max_lines: Optional[int] = None) -> List[str]:
    """Safely read lines from a file"""
    try:
        if not path.exists():
            return []
        
        with open(path, 'r') as f:
            if max_lines:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        break
                    lines.append(line.rstrip('\n'))
                return lines
            else:
                return [line.rstrip('\n') for line in f]
                
    except Exception as e:
        logger.warning(f"Error reading lines from {path}: {e}")
        return []


def safe_append_line(path: Path, line: str):
    """Safely append a line to a file"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Ensure line ends with newline
    if not line.endswith('\n'):
        line += '\n'
    
    try:
        with open(path, 'a') as f:
            f.write(line)
    except Exception as e:
        logger.error(f"Error appending to {path}: {e}")
        raise


def get_file_age_hours(path: Path) -> float:
    """Get file age in hours"""
    if not path.exists():
        return 0
    
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    age = datetime.now() - mtime
    return age.total_seconds() / 3600


def find_latest_file(directory: Path, pattern: str) -> Optional[Path]:
    """Find the most recently modified file matching pattern"""
    if not directory.exists():
        return None
    
    files = list(directory.glob(pattern))
    if not files:
        return None
    
    return max(files, key=lambda p: p.stat().st_mtime)


def rotate_file(path: Path, max_backups: int = 5):
    """Rotate a file by creating numbered backups"""
    if not path.exists():
        return
    
    # Find next backup number
    for i in range(max_backups):
        backup_path = path.with_suffix(f'.{i}{path.suffix}')
        if not backup_path.exists():
            shutil.copy2(path, backup_path)
            break
    
    # Clean up old backups
    for i in range(max_backups, max_backups + 10):
        backup_path = path.with_suffix(f'.{i}{path.suffix}')
        if backup_path.exists():
            backup_path.unlink()


class JSONFileStore:
    """Simple JSON file-based key-value store with locking"""
    
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value by key"""
        data = read_json_file(self.path, {})
        return data.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set value for key"""
        def updater(data):
            if not isinstance(data, dict):
                data = {}
            data[key] = value
            return data
        
        update_json_file(self.path, updater)
    
    def delete(self, key: str) -> bool:
        """Delete key"""
        def updater(data):
            if isinstance(data, dict) and key in data:
                del data[key]
                return data
            return data
        
        data = update_json_file(self.path, updater)
        return key not in data
    
    def exists(self, key: str) -> bool:
        """Check if key exists"""
        data = read_json_file(self.path, {})
        return key in data
    
    def keys(self) -> List[str]:
        """Get all keys"""
        data = read_json_file(self.path, {})
        return list(data.keys()) if isinstance(data, dict) else []
    
    def clear(self):
        """Clear all data"""
        write_json_file(self.path, {})
    
    def get_all(self) -> Dict[str, Any]:
        """Get all key-value pairs"""
        return read_json_file(self.path, {})