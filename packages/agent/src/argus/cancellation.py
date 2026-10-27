"""Cooperative run cancellation.

Live runs execute in a worker thread, so cancelling their asyncio task cannot
stop them. Instead the API flags a run here and the pipeline checks the flag at
safe points: between phases, before each test case and before each step.
"""

from __future__ import annotations

import threading

_cancelled: set[str] = set()
_lock = threading.Lock()


class RunCancelled(RuntimeError):
    """Raised at a phase boundary after a user stopped the run."""


def cancel(run_id: str) -> None:
    with _lock:
        _cancelled.add(run_id)


def is_cancelled(run_id: str) -> bool:
    with _lock:
        return run_id in _cancelled


def clear(run_id: str) -> None:
    with _lock:
        _cancelled.discard(run_id)


def raise_if_cancelled(run_id: str) -> None:
    if is_cancelled(run_id):
        raise RunCancelled("Run stopped by user")
