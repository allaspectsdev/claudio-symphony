#!/usr/bin/env python3
"""Concurrency-safe JSON persistence for Claudio's multi-process runtime.

Claude Code can fire overlapping asynchronous hooks.  The runtime therefore
cannot use a fixed ``file.json.tmp`` or an unlocked read/modify/write cycle:
one hook can rename another hook's temporary file, or overwrite state that was
written after its read.  This module keeps the human-readable JSON files while
serializing transactions with portable lock files and committing through a
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


@contextmanager
def file_lock(path, timeout=5.0, stale_after=30.0):
    """Take an exclusive, cross-platform lock associated with ``path``.

    ``O_EXCL`` works on Windows and POSIX.  A timestamped lock is reclaimed if
    a process dies before cleanup; normal critical sections last milliseconds.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_path(path)
    deadline = time.monotonic() + max(0.0, float(timeout))
    fd = None
    while fd is None:
        try:
            candidate_fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                os.write(candidate_fd, f"{os.getpid()} {time.time():.6f}\n".encode())
            except Exception:
                os.close(candidate_fd)
                try: lock.unlink()
                except FileNotFoundError: pass
                raise
            fd = candidate_fd
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > stale_after:
                    lock.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise LockTimeout(f"timed out waiting for {lock}")
            time.sleep(random.uniform(0.005, 0.02))
    try:
        yield
    finally:
        try:
            os.close(fd)
        finally:
            try:
                lock.unlink()
            except FileNotFoundError:
                pass


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
        os.replace(str(tmp), str(path))
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def save_json(path, data, *, indent=2, newline=True, timeout=5.0):
    path = Path(path)
    with file_lock(path, timeout=timeout):
        _write_unlocked(path, data, indent=indent, newline=newline)


def update_json(path, default, mutator, *, indent=2, newline=True, timeout=5.0):
    """Atomically load, mutate, and replace a JSON document.

    ``mutator`` receives the current document.  It may mutate it in place and
    return ``None``, or return a replacement document.  The committed document
    is returned to the caller.
    """
    path = Path(path)
    with file_lock(path, timeout=timeout):
        current = load_json(path, default)
        replacement = mutator(current)
        if replacement is not None:
            current = replacement
        _write_unlocked(path, current, indent=indent, newline=newline)
        return current


@contextmanager
def edit_json(path, default, *, indent=2, newline=True, timeout=5.0):
    """Yield a document under lock and commit it when the context exits."""
    path = Path(path)
    with file_lock(path, timeout=timeout):
        current = load_json(path, default)
        yield current
        _write_unlocked(path, current, indent=indent, newline=newline)
