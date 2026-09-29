import os
import sys
import atexit
import signal
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_PID_FILE = BASE_DIR / "data" / "bot.pid"


class PIDLock:
    """
    Cross-platform singleton process PID lock implementation.
    Uses msvcrt on Windows and fcntl on Unix for exclusive OS-level locking.
    """

    def __init__(self, pid_file: Optional[Path] = None):
        self.pid_file = Path(pid_file) if pid_file else DEFAULT_PID_FILE
        self.file_handle = None
        self.is_locked = False

    def acquire(self) -> bool:
        """
        Attempt to acquire an exclusive lock on the PID file.
        Returns True if successful, False if locked by another process.
        """
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.file_handle = open(self.pid_file, "a+", encoding="utf-8")
            self.file_handle.seek(0)

            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self.file_handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            # Successfully acquired lock; record PID
            self.file_handle.seek(0)
            self.file_handle.truncate()
            self.file_handle.write(str(os.getpid()))
            self.file_handle.flush()
            self.is_locked = True

            # Register cleanup handlers
            atexit.register(self.release)
            self._setup_signal_handlers()
            return True

        except (OSError, IOError, PermissionError):
            if self.file_handle:
                try:
                    self.file_handle.close()
                except Exception:
                    pass
                self.file_handle = None
            return False

    def release(self):
        """Release the file lock and remove the PID file."""
        if not self.is_locked:
            return
        self.is_locked = False

        if self.file_handle:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    self.file_handle.seek(0)
                    msvcrt.locking(self.file_handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.file_handle.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                self.file_handle.close()
            except Exception:
                pass
            self.file_handle = None

        if self.pid_file.exists():
            try:
                self.pid_file.unlink()
            except Exception:
                pass

    def _setup_signal_handlers(self):
        def _handler(signum, frame):
            self.release()
            sys.exit(0)

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):
                # May fail if executed outside main thread (e.g. inside background thread)
                pass


_global_bot_lock: Optional[PIDLock] = None


def acquire_bot_pid_lock(pid_file: Optional[Path] = None) -> Optional[PIDLock]:
    """
    Singleton lock acquisition helper for Telegram Bot process.
    Returns PIDLock instance if acquired, or None if already running.
    """
    global _global_bot_lock
    lock = PIDLock(pid_file)
    if lock.acquire():
        _global_bot_lock = lock
        return lock
    return None
