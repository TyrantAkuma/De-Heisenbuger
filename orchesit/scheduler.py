"""
OrchesIt Scheduler Module.
Dynamic DAG dependency resolution, Kahn's algorithm for topological sorting and cycle detection,
and token-bucket concurrency governor for managing agent execution load.
"""

from __future__ import annotations

import collections
import time
from typing import Dict, List, Optional, Set
from orchesit.state import StateStore, TaskStatus


class CyclicDependencyError(Exception):
    """Raised when a circular dependency is detected in the DAG."""
    pass


class TokenBucketGovernor:
    """Rate and concurrency governor using a token-bucket algorithm."""

    def __init__(self, capacity: int = 4, refill_rate_per_sec: float = 2.0):
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_rate = refill_rate_per_sec
        self.last_refill = time.monotonic()

    def acquire(self, tokens: int = 1, timeout: float = 5.0) -> bool:
        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            time.sleep(0.05)
        return False

    def release(self, tokens: int = 1) -> None:
        self.tokens = min(float(self.capacity), self.tokens + tokens)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(float(self.capacity), self.tokens + elapsed * self.refill_rate)
        self.last_refill = now


class DAGScheduler:
    """Manages DAG dependency resolution and ready-queue scheduling."""

    def __init__(self, state_store: StateStore, governor: Optional[TokenBucketGovernor] = None):
        self.store = state_store
        self.governor = governor or TokenBucketGovernor()

    def validate_dag(self, project_id: str) -> List[str]:
        """
        Uses Kahn's algorithm to ensure the DAG has no cycles
        and returns a valid topological order of task IDs.
        """
        tasks = self.store.list_tasks(project_id)
        task_ids = {t["id"] for t in tasks}

        in_degree: Dict[str, int] = {t_id: 0 for t_id in task_ids}
        adj_list: Dict[str, List[str]] = collections.defaultdict(list)

        for t_id in task_ids:
            deps = self.store.get_task_dependencies(t_id)
            for dep in deps:
                if dep in task_ids:
                    adj_list[dep].append(t_id)
                    in_degree[t_id] += 1

        queue = collections.deque([t_id for t_id, deg in in_degree.items() if deg == 0])
        topological_order: List[str] = []

        while queue:
            node = queue.popleft()
            topological_order.append(node)
            for neighbor in adj_list[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(topological_order) != len(task_ids):
            unresolved = [t_id for t_id, deg in in_degree.items() if deg > 0]
            raise CyclicDependencyError(
                f"Cyclic dependency detected involving tasks: {unresolved}"
            )

        return topological_order

    def get_ready_tasks(self, project_id: str) -> List[Dict[str, any]]:
        """
        Finds tasks that are currently PENDING and all of their dependencies
        have reached COMPLETED status.
        """
        tasks = self.store.list_tasks(project_id)
        task_map = {t["id"]: t for t in tasks}
        completed_ids = {t["id"] for t in tasks if t["status"] == TaskStatus.COMPLETED.value}

        ready = []
        for t in tasks:
            if t["status"] == TaskStatus.PENDING.value:
                deps = self.store.get_task_dependencies(t["id"])
                if all(dep in completed_ids for dep in deps):
                    ready.append(t)
        return ready

    def mark_ready(self, task_id: str) -> None:
        self.store.update_task_status(task_id, TaskStatus.READY)

    def is_project_complete(self, project_id: str) -> Tuple[bool, bool]:
        """
        Returns (is_done, has_failures).
        """
        tasks = self.store.list_tasks(project_id)
        if not tasks:
            return False, False
        all_terminal = all(
            t["status"] in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value)
            for t in tasks
        )
        has_failures = any(t["status"] == TaskStatus.FAILED.value for t in tasks)
        return all_terminal, has_failures
