"""
OrchesIt Adaptive Recovery Module.
Error classification, exponential backoff, agent reassignment, and subtree replanning.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Callable, Dict, List, Optional
from orchesit.state import StateStore, TaskStatus


class ErrorCategory(str, Enum):
    TRANSIENT = "TRANSIENT"                      # Network glitch, lock contention, timeout
    IMPLEMENTATION_DEFECT = "IMPLEMENTATION_DEFECT"  # Unit test failure, bad syntax, missing export
    ARCHITECTURAL_FLAW = "ARCHITECTURAL_FLAW"        # Fundamental assumption invalid, incompatible contracts


class RecoveryManager:
    """Handles failure analysis and recovery strategies according to Rule 6."""

    def __init__(self, state_store: StateStore, max_retries: int = 3):
        self.store = state_store
        self.max_retries = max_retries

    def classify_error(self, error_message: str, exit_code: int) -> ErrorCategory:
        msg = error_message.lower()
        if any(w in msg for w in ["timeout", "connection reset", "eagain", "temporarily unavailable", "busy"]):
            return ErrorCategory.TRANSIENT
        if any(w in msg for w in ["syntaxerror", "assertionerror", "typeerror", "mismatched types", "undefined", "borrow"]):
            return ErrorCategory.IMPLEMENTATION_DEFECT
        if any(w in msg for w in ["unsupported architecture", "invalid schema", "incompatible kernel", "circular dependency"]):
            return ErrorCategory.ARCHITECTURAL_FLAW
        return ErrorCategory.IMPLEMENTATION_DEFECT

    def execute_recovery(
        self,
        task_id: str,
        category: ErrorCategory,
        error_context: str,
        retry_fn: Optional[Callable[[], bool]] = None,
    ) -> bool:
        retries = self.store.increment_task_retry(task_id)

        if retries > self.max_retries:
            self.store.update_task_status(task_id, TaskStatus.FAILED)
            return False

        if category == ErrorCategory.TRANSIENT:
            # Exponential backoff
            sleep_sec = 0.5 * (2 ** (retries - 1))
            time.sleep(sleep_sec)
            self.store.update_task_status(task_id, TaskStatus.READY)
            return retry_fn() if retry_fn else True

        elif category == ErrorCategory.IMPLEMENTATION_DEFECT:
            # Route back to executor with critique
            self.store.update_task_status(task_id, TaskStatus.READY)
            return retry_fn() if retry_fn else True

        elif category == ErrorCategory.ARCHITECTURAL_FLAW:
            # Requires subtree replanning
            self.store.update_task_status(task_id, TaskStatus.BLOCKED)
            return False

        return False
