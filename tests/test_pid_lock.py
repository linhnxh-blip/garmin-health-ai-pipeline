import os
import sys
import subprocess
import pytest
from pathlib import Path
from click.testing import CliRunner

from src.utils.pid_lock import PIDLock, acquire_bot_pid_lock
from main import cli


def test_acquire_and_release_pid_lock(tmp_path):
    pid_file = tmp_path / "bot.pid"
    lock = PIDLock(pid_file)

    assert lock.acquire() is True
    assert lock.is_locked is True
    assert pid_file.exists()
    lock.file_handle.seek(0)
    assert lock.file_handle.read().strip() == str(os.getpid())

    lock.release()
    assert lock.is_locked is False
    assert not pid_file.exists()


def test_second_instance_same_process_fails(tmp_path):
    pid_file = tmp_path / "bot.pid"
    lock1 = PIDLock(pid_file)
    assert lock1.acquire() is True

    # Note: On Windows/msvcrt, locking within the same process file handle or secondary open:
    lock2 = PIDLock(pid_file)
    assert lock2.acquire() is False

    lock1.release()
    assert lock2.acquire() is True
    lock2.release()


def test_cross_process_pid_lock_conflict(tmp_path):
    pid_file = tmp_path / "bot.pid"
    lock1 = PIDLock(pid_file)
    assert lock1.acquire() is True

    # Run child process trying to acquire lock on same pid_file
    code = f"""
import sys
from pathlib import Path
from src.utils.pid_lock import PIDLock

pid_file = Path(r'{pid_file}')
lock = PIDLock(pid_file)
if lock.acquire():
    print("ACQUIRED")
else:
    print("LOCKED")
"""
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert "LOCKED" in res.stdout

    lock1.release()

    res2 = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert "ACQUIRED" in res2.stdout


def test_cli_bot_conflict(tmp_path, monkeypatch):
    pid_file = tmp_path / "bot.pid"
    
    # Hold lock with instance 1
    lock1 = PIDLock(pid_file)
    assert lock1.acquire() is True

    # Patch DEFAULT_PID_FILE in src.utils.pid_lock
    import src.utils.pid_lock as pid_module
    monkeypatch.setattr(pid_module, "DEFAULT_PID_FILE", pid_file)

    runner = CliRunner()
    result = runner.invoke(cli, ["bot", "--once"])
    assert result.exit_code == 0
    assert "Đã có một tiến trình Bot đang chạy nền trên máy. Hủy lệnh để tránh lỗi 409 Conflict." in result.output

    lock1.release()
