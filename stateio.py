#!/usr/bin/env python3
"""Concurrency-safe JSON persistence for Claudio's multi-process runtime.

Claude Code can fire overlapping asynchronous hooks.  The runtime therefore
cannot use a fixed ``file.json.tmp`` or an unlocked read/modify/write cycle:
one hook can rename another hook's temporary file, or overwrite state that was
written after its read.  This module keeps the human-readable JSON files while
serializing transactions with kernel advisory locks and committing through a
unique same-directory temporary file.
"""
from __future__ import annotations

import copy
import json
import os
import random
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


class LockTimeout(TimeoutError):
    """Raised when a state file remains locked beyond the caller's deadline."""


def load_json(path, default):
    path = Path(path)
    try:
        return json.loads(path.read_text()) if path.exists() else copy.deepcopy(default)
    except (OSError, ValueError, TypeError):
        return copy.deepcopy(default)


def _lock_path(path: Path) -> Path:
    return path.with_name(path.name + ".lock")


# Hook processes have a hard ~1s budget (Claude kills them), so hot-path
# callers wait only briefly.  ``stale_after`` is accepted for API
# compatibility but no longer needed: locks are kernel advisory locks, which
# the OS releases the instant the holder exits — even when a hook is killed
# mid-transaction — so an orphaned lock cannot silence other sessions.
HOT_TIMEOUT = 0.25
HOT_STALE_AFTER = 3.0

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt


def _try_lock(fd) -> bool:
    if fcntl is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        return False


def _unlock(fd) -> None:
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
    else:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


@contextmanager
def file_lock(path, timeout=5.0, stale_after=None):
    """Take an exclusive, cross-platform lock associated with ``path``.

    Uses ``flock`` (POSIX) or ``msvcrt.locking`` (Windows) on a persistent
    ``<name>.lock`` file.  Each call opens its own descriptor, so the lock
    excludes other threads as well as other processes.  The lock file itself
    is left in place: deleting it would let two holders lock different inodes.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_path(path)
    deadline = time.monotonic() + max(0.0, float(timeout))
    fd = os.open(str(lock), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        while not _try_lock(fd):
            if time.monotonic() >= deadline:
                raise LockTimeout(f"timed out waiting for {lock}")
            time.sleep(random.uniform(0.005, 0.02))
    except BaseException:
        os.close(fd)
        raise
    try:
        yield
    finally:
        try:
            _unlock(fd)
        except OSError:
            pass
        finally:
            os.close(fd)


def _replace(src, dst, attempts=5):
    """``os.replace`` that tolerates Windows' transient sharing violations
    (another process briefly has ``dst`` open for reading)."""
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.01)


def _write_unlocked(path: Path, data, *, indent=2, newline=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=indent)
    if newline:
        text += "\n"
    fd, tmpname = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmpname)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        _replace(str(tmp), str(path))
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def save_json(path, data, *, indent=2, newline=True, timeout=5.0, stale_after=30.0):
    path = Path(path)
    with file_lock(path, timeout=timeout, stale_after=stale_after):
        _write_unlocked(path, data, indent=indent, newline=newline)


def update_json(path, default, mutator, *, indent=2, newline=True, timeout=5.0,
                stale_after=30.0):
    """Atomically load, mutate, and replace a JSON document.

    ``mutator`` receives the current document.  It may mutate it in place and
    return ``None``, or return a replacement document.  The committed document
    is returned to the caller.
    """
    path = Path(path)
    with file_lock(path, timeout=timeout, stale_after=stale_after):
        current = load_json(path, default)
        replacement = mutator(current)
        if replacement is not None:
            current = replacement
        _write_unlocked(path, current, indent=indent, newline=newline)
        return current


@contextmanager
def edit_json(path, default, *, indent=2, newline=True, timeout=5.0, stale_after=30.0):
    """Yield a document under lock and commit it when the context exits."""
    path = Path(path)
    with file_lock(path, timeout=timeout, stale_after=stale_after):
        current = load_json(path, default)
        yield current
        _write_unlocked(path, current, indent=indent, newline=newline)
