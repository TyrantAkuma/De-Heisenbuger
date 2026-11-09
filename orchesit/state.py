"""
OrchesIt State Management Module.
Provides persistent ACID storage via SQLite for project states, task dependency graphs (DAG),
artifacts with SHA-256 hashing, execution records, verifications, and jury deliberations.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    EXECUTED = "EXECUTED"
    VERIFYING = "VERIFYING"
    DELIBERATING = "DELIBERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class Verdict(str, Enum):
    PASS = "PASS"
    PASS_WITH_CAVEATS = "PASS_WITH_CAVEATS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class DeliberationType(str, Enum):
    SINGLE_VERIFIER = "SINGLE_VERIFIER"
    ADVERSARIAL_JURY = "ADVERSARIAL_JURY"


def compute_sha256(file_path: str | Path) -> str:
    """Computes SHA-256 hash of a file on disk."""
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found for hashing: {file_path}")
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_string_sha256(content: str) -> str:
    """Computes SHA-256 hash of a text string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class StateStore:
    """Persistent ACID storage engine for OrchesIt using SQLite."""

    def __init__(self, db_path: str | Path = "orchesit_state.db"):
        self.db_path = str(db_path)
        self._init_db()

    @contextlib.contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'INITIALIZED',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    workstream TEXT NOT NULL,
                    executor_role TEXT NOT NULL,
                    verifier_role TEXT NOT NULL,
                    deliberation_type TEXT NOT NULL,
                    acceptance_criteria TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS task_dependencies (
                    task_id TEXT NOT NULL,
                    depends_on_task_id TEXT NOT NULL,
                    PRIMARY KEY (task_id, depends_on_task_id),
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    sha256_hash TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    summary TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    executor_role TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    exit_code INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS verifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    verifier_role TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    critique TEXT NOT NULL,
                    evidence_verified TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS jury_deliberations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    round_number INTEGER NOT NULL,
                    juror_role TEXT NOT NULL,
                    vote TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    reasoning TEXT NOT NULL,
                    rebuttal TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS orchestrator_resolutions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL UNIQUE,
                    final_verdict TEXT NOT NULL,
                    architectural_justification TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                """
            )

    def create_project(self, project_id: str, name: str, objective: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, objective, status, created_at, updated_at)
                VALUES (?, ?, ?, 'RUNNING', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    objective = excluded.objective,
                    updated_at = excluded.updated_at
                """,
                (project_id, name, objective, now, now),
            )

    def set_project_status(self, project_id: str, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, project_id),
            )

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def add_task(
        self,
        task_id: str,
        project_id: str,
        title: str,
        workstream: str,
        executor_role: str,
        verifier_role: str,
        deliberation_type: DeliberationType,
        acceptance_criteria: List[str],
        dependencies: Optional[List[str]] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO tasks (id, project_id, title, workstream, executor_role, verifier_role,
                                  deliberation_type, acceptance_criteria, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    workstream = excluded.workstream,
                    executor_role = excluded.executor_role,
                    verifier_role = excluded.verifier_role,
                    deliberation_type = excluded.deliberation_type,
                    acceptance_criteria = excluded.acceptance_criteria,
                    updated_at = excluded.updated_at
                """,
                (
                    task_id,
                    project_id,
                    title,
                    workstream,
                    executor_role,
                    verifier_role,
                    deliberation_type.value,
                    json.dumps(acceptance_criteria),
                    now,
                    now,
                ),
            )
            if dependencies:
                for dep in dependencies:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO task_dependencies (task_id, depends_on_task_id)
                        VALUES (?, ?)
                        """,
                        (task_id, dep),
                    )

    def update_task_status(self, task_id: str, status: TaskStatus) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, now, task_id),
            )

    def increment_task_retry(self, task_id: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                "UPDATE tasks SET retry_count = retry_count + 1, updated_at = ? WHERE id = ?",
                (now, task_id),
            )
            cur = conn.execute("SELECT retry_count FROM tasks WHERE id = ?", (task_id,))
            return cur.fetchone()[0]

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cur.fetchone()
            if not row:
                return None
            d = dict(row)
            d["acceptance_criteria"] = json.loads(d["acceptance_criteria"])
            return d

    def list_tasks(self, project_id: str) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.execute("SELECT * FROM tasks WHERE project_id = ? ORDER BY id", (project_id,))
            tasks = []
            for row in cur.fetchall():
                d = dict(row)
                d["acceptance_criteria"] = json.loads(d["acceptance_criteria"])
                tasks.append(d)
            return tasks

    def get_task_dependencies(self, task_id: str) -> List[str]:
        with self._connection() as conn:
            cur = conn.execute(
                "SELECT depends_on_task_id FROM task_dependencies WHERE task_id = ?",
                (task_id,),
            )
            return [row[0] for row in cur.fetchall()]

    def record_artifact(
        self,
        task_id: str,
        file_path: str,
        summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        p = Path(file_path)
        sha256 = compute_sha256(p)
        size = p.stat().st_size
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO artifacts (task_id, file_path, sha256_hash, file_size, summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, str(file_path), sha256, size, summary, now),
            )
            art_id = cur.lastrowid
        return {
            "id": art_id,
            "task_id": task_id,
            "file_path": str(file_path),
            "sha256_hash": sha256,
            "file_size": size,
            "summary": summary,
            "created_at": now,
        }

    def list_task_artifacts(self, task_id: str) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.execute(
                "SELECT * FROM artifacts WHERE task_id = ? ORDER BY id", (task_id,)
            )
            return [dict(r) for r in cur.fetchall()]

    def record_execution(
        self,
        task_id: str,
        executor_role: str,
        evidence: Dict[str, Any] | str,
        exit_code: int = 0,
        status: str = "SUCCESS",
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        evidence_str = json.dumps(evidence) if isinstance(evidence, (dict, list)) else str(evidence)
        with self._connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO executions (task_id, executor_role, evidence, exit_code, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, executor_role, evidence_str, exit_code, status, now),
            )
            return cur.lastrowid

    def record_verification(
        self,
        task_id: str,
        verifier_role: str,
        verdict: Verdict,
        critique: str,
        evidence_verified: Dict[str, Any] | List[str],
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        ev_str = json.dumps(evidence_verified)
        with self._connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO verifications (task_id, verifier_role, verdict, critique, evidence_verified, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, verifier_role, verdict.value, critique, ev_str, now),
            )
            return cur.lastrowid

    def record_jury_vote(
        self,
        task_id: str,
        round_number: int,
        juror_role: str,
        vote: str,
        confidence: float,
        reasoning: str,
        rebuttal: Optional[str] = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO jury_deliberations (task_id, round_number, juror_role, vote, confidence, reasoning, rebuttal, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, round_number, juror_role, vote, confidence, reasoning, rebuttal, now),
            )
            return cur.lastrowid

    def list_jury_deliberations(self, task_id: str) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.execute(
                "SELECT * FROM jury_deliberations WHERE task_id = ? ORDER BY round_number, id",
                (task_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def record_orchestrator_resolution(
        self,
        task_id: str,
        final_verdict: Verdict,
        architectural_justification: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO orchestrator_resolutions (task_id, final_verdict, architectural_justification, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    final_verdict = excluded.final_verdict,
                    architectural_justification = excluded.architectural_justification,
                    created_at = excluded.created_at
                """,
                (task_id, final_verdict.value, architectural_justification, now),
            )

    def get_orchestrator_resolution(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.execute(
                "SELECT * FROM orchestrator_resolutions WHERE task_id = ?",
                (task_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_full_task_summary(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self.get_task(task_id)
        if not task:
            return None
        with self._connection() as conn:
            cur = conn.execute("SELECT * FROM artifacts WHERE task_id = ?", (task_id,))
            artifacts = [dict(r) for r in cur.fetchall()]

            cur = conn.execute("SELECT * FROM executions WHERE task_id = ? ORDER BY id DESC LIMIT 1", (task_id,))
            latest_exec = cur.fetchone()

            cur = conn.execute("SELECT * FROM verifications WHERE task_id = ? ORDER BY id DESC LIMIT 1", (task_id,))
            latest_verif = cur.fetchone()

            cur = conn.execute("SELECT * FROM jury_deliberations WHERE task_id = ?", (task_id,))
            jury = [dict(r) for r in cur.fetchall()]

            cur = conn.execute("SELECT * FROM orchestrator_resolutions WHERE task_id = ?", (task_id,))
            resolution = cur.fetchone()

        task["artifacts"] = artifacts
        task["execution"] = dict(latest_exec) if latest_exec else None
        task["verification"] = dict(latest_verif) if latest_verif else None
        task["jury"] = jury
        task["resolution"] = dict(resolution) if resolution else None
        return task
