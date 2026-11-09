"""
OrchesIt Orchestrator Engine.
Master coordinator managing the lifecycle: premise challenge, workforce sizing,
five-stage executor-verifier protocol, and delivery reporting.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from orchesit.jury import JurorVote, VerificationEngine
from orchesit.recovery import ErrorCategory, RecoveryManager
from orchesit.scheduler import DAGScheduler, TokenBucketGovernor
from orchesit.state import DeliberationType, StateStore, TaskStatus, Verdict
from orchesit.visualizer import DashboardVisualizer


class Orchestrator:
    """Master orchestrator implementing the 10 OrchesIt Invariant Ground Rules."""

    def __init__(self, db_path: str = "orchesit_state.db", max_concurrency: int = 4):
        self.db_path = db_path
        self.store = StateStore(db_path)
        self.governor = TokenBucketGovernor(capacity=max_concurrency)
        self.scheduler = DAGScheduler(self.store, self.governor)
        self.jury = VerificationEngine(self.store)
        self.recovery = RecoveryManager(self.store)
        self.visualizer = DashboardVisualizer(self.store)

    def init_project(self, project_id: str, name: str, objective: str) -> None:
        self.store.create_project(project_id, name, objective)

    def register_task(
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
        self.store.add_task(
            task_id=task_id,
            project_id=project_id,
            title=title,
            workstream=workstream,
            executor_role=executor_role,
            verifier_role=verifier_role,
            deliberation_type=deliberation_type,
            acceptance_criteria=acceptance_criteria,
            dependencies=dependencies,
        )

    def record_stage2_execution(
        self,
        task_id: str,
        executor_role: str,
        artifacts: List[Dict[str, str]],  # List of {"path": ..., "summary": ...}
        evidence: Dict[str, Any] | str,
        exit_code: int = 0,
    ) -> None:
        """Stage 2: Executor submits deliverables and computed SHA-256 hashes."""
        self.store.update_task_status(task_id, TaskStatus.EXECUTED)
        self.store.record_execution(
            task_id=task_id,
            executor_role=executor_role,
            evidence=evidence,
            exit_code=exit_code,
            status="SUCCESS" if exit_code == 0 else "ERROR",
        )
        for art in artifacts:
            if os.path.exists(art["path"]):
                self.store.record_artifact(
                    task_id=task_id,
                    file_path=art["path"],
                    summary=art.get("summary"),
                )

    def record_stage3_verification(
        self,
        task_id: str,
        verifier_role: str,
        verdict: Verdict,
        critique: str,
        evidence_verified: Dict[str, Any] | List[str],
    ) -> None:
        """Stage 3 & 4: Independent single-verifier conducts audit and issues verdict."""
        self.store.update_task_status(task_id, TaskStatus.VERIFYING)
        self.jury.conduct_single_verifier(
            task_id=task_id,
            verifier_role=verifier_role,
            verdict=verdict,
            critique=critique,
            evidence_verified=evidence_verified,
        )

    def record_stage5_jury(
        self,
        task_id: str,
        round_1_votes: List[JurorVote],
        round_2_cross_exam: Optional[List[JurorVote]] = None,
        orchestrator_justification: Optional[str] = None,
    ) -> Verdict:
        """Stage 5: Convene multi-member adversarial jury for critical milestone tasks."""
        return self.jury.conduct_adversarial_jury(
            task_id=task_id,
            round_1_votes=round_1_votes,
            round_2_cross_exam=round_2_cross_exam,
            orchestrator_justification=orchestrator_justification,
        )

    def export_dashboard(self, project_id: str, output_path: str = "dashboard.html") -> str:
        out = self.visualizer.export_dashboard(project_id, output_path)
        return str(out)

    def get_project_summary(self, project_id: str) -> Dict[str, Any]:
        proj = self.store.get_project(project_id)
        tasks = self.store.list_tasks(project_id)
        completed = sum(1 for t in tasks if t["status"] == TaskStatus.COMPLETED.value)
        failed = sum(1 for t in tasks if t["status"] == TaskStatus.FAILED.value)
        is_done, has_failures = self.scheduler.is_project_complete(project_id)
        return {
            "project": proj,
            "tasks_total": len(tasks),
            "tasks_completed": completed,
            "tasks_failed": failed,
            "is_complete": is_done,
            "has_failures": has_failures,
        }
