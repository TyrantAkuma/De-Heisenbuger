"""
Unit test suite for OrchesIt Multi-Agent Control Plane.
"""

import os
import tempfile
import unittest
from pathlib import Path
from orchesit.jury import JurorVote
from orchesit.orchestrator import Orchestrator
from orchesit.recovery import ErrorCategory, RecoveryManager
from orchesit.scheduler import CyclicDependencyError, DAGScheduler, TokenBucketGovernor
from orchesit.state import DeliberationType, StateStore, TaskStatus, Verdict, compute_sha256, compute_string_sha256


class TestOrchesItCore(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_orchesit.db")
        self.orch = Orchestrator(db_path=self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_project_init_and_task_dag(self):
        self.orch.init_project("proj-1", "Test Project", "Objective A")
        self.orch.register_task(
            task_id="T1",
            project_id="proj-1",
            title="Task 1",
            workstream="Requirements",
            executor_role="@RequirementsAnalyst",
            verifier_role="@AdversarialSystemsAuditor",
            deliberation_type=DeliberationType.ADVERSARIAL_JURY,
            acceptance_criteria=["Criterion 1"],
            dependencies=[],
        )
        self.orch.register_task(
            task_id="T2",
            project_id="proj-1",
            title="Task 2",
            workstream="Architecture",
            executor_role="@PrincipalArchitect",
            verifier_role="@ReliabilityAuditor",
            deliberation_type=DeliberationType.ADVERSARIAL_JURY,
            acceptance_criteria=["Criterion 2"],
            dependencies=["T1"],
        )

        topo = self.orch.scheduler.validate_dag("proj-1")
        self.assertEqual(topo, ["T1", "T2"])

        ready = self.orch.scheduler.get_ready_tasks("proj-1")
        self.assertEqual([t["id"] for t in ready], ["T1"])

    def test_cycle_detection(self):
        self.orch.init_project("proj-cycle", "Cycle Proj", "Objective")
        self.orch.register_task(
            task_id="A", project_id="proj-cycle", title="A", workstream="W",
            executor_role="E", verifier_role="V", deliberation_type=DeliberationType.SINGLE_VERIFIER,
            acceptance_criteria=["A"], dependencies=["B"]
        )
        self.orch.register_task(
            task_id="B", project_id="proj-cycle", title="B", workstream="W",
            executor_role="E", verifier_role="V", deliberation_type=DeliberationType.SINGLE_VERIFIER,
            acceptance_criteria=["B"], dependencies=["A"]
        )
        with self.assertRaises(CyclicDependencyError):
            self.orch.scheduler.validate_dag("proj-cycle")

    def test_stage2_artifact_hashing_and_verification(self):
        self.orch.init_project("proj-verify", "Verify Proj", "Objective")
        self.orch.register_task(
            task_id="T1", project_id="proj-verify", title="Build Core", workstream="Core",
            executor_role="@SeniorBackendEngineer", verifier_role="@IndependentCodeReviewer",
            deliberation_type=DeliberationType.SINGLE_VERIFIER, acceptance_criteria=["Tests pass"]
        )

        # Create dummy artifact
        art_path = os.path.join(self.tmp_dir.name, "output.txt")
        Path(art_path).write_text("Deterministic output 12345", encoding="utf-8")
        expected_hash = compute_sha256(art_path)

        # Stage 2: Execution
        self.orch.record_stage2_execution(
            task_id="T1",
            executor_role="@SeniorBackendEngineer",
            artifacts=[{"path": art_path, "summary": "Core output"}],
            evidence={"exit_code": 0, "logs": "pass"},
        )

        # Stage 3: Verification
        self.orch.record_stage3_verification(
            task_id="T1",
            verifier_role="@IndependentCodeReviewer",
            verdict=Verdict.PASS,
            critique="Implementation meets all criteria without regressions.",
            evidence_verified={"hash_matched": True, "tests": "10/10 passed"},
        )

        summary = self.orch.store.get_full_task_summary("T1")
        self.assertEqual(summary["status"], TaskStatus.COMPLETED.value)
        self.assertEqual(summary["artifacts"][0]["sha256_hash"], expected_hash)
        self.assertEqual(summary["verification"]["verdict"], "PASS")

    def test_adversarial_jury_deliberation(self):
        self.orch.init_project("proj-jury", "Jury Proj", "Objective")
        self.orch.register_task(
            task_id="ARCH-1", project_id="proj-jury", title="Design Kernel Scheduler", workstream="Architecture",
            executor_role="@PrincipalArchitect", verifier_role="@ReliabilityAuditor",
            deliberation_type=DeliberationType.ADVERSARIAL_JURY, acceptance_criteria=["Scalable", "eBPF safety verified"]
        )

        round_1 = [
            JurorVote(juror_role="@TechnicalReviewer", vote="PASS", confidence=0.95, reasoning="Clean abstractions"),
            JurorVote(juror_role="@AdversarialCritic", vote="FAIL", confidence=0.85, reasoning="Race window in ring buffer reset"),
            JurorVote(juror_role="@DomainExpert", vote="PASS", confidence=0.90, reasoning="Conforms to Linux 6.12 sched_ext"),
            JurorVote(juror_role="@FactChecker", vote="PASS", confidence=1.0, reasoning="All function signatures verified"),
        ]

        round_2 = [
            JurorVote(juror_role="@TechnicalReviewer", vote="PASS", confidence=0.98, reasoning="Acknowledged atomic cursor mitigation"),
            JurorVote(juror_role="@AdversarialCritic", vote="PASS", confidence=0.88, reasoning="Mitigation confirmed valid", rebuttal="Satisfied with atomic read barrier"),
            JurorVote(juror_role="@DomainExpert", vote="PASS", confidence=0.95, reasoning="Sound design"),
            JurorVote(juror_role="@FactChecker", vote="PASS", confidence=1.0, reasoning="Deterministic"),
        ]

        verdict = self.orch.record_stage5_jury(
            task_id="ARCH-1",
            round_1_votes=round_1,
            round_2_cross_exam=round_2,
            orchestrator_justification="Adversarial race condition objection resolved via atomic barrier; unaniomus pass."
        )

        self.assertEqual(verdict, Verdict.PASS)
        task = self.orch.store.get_full_task_summary("ARCH-1")
        self.assertEqual(task["status"], TaskStatus.COMPLETED.value)
        self.assertEqual(len(task["jury"]), 8)

    def test_visualizer_html_export(self):
        self.orch.init_project("proj-ui", "UI Proj", "Objective")
        self.orch.register_task(
            task_id="T1", project_id="proj-ui", title="Task UI", workstream="UI",
            executor_role="@E", verifier_role="@V",
            deliberation_type=DeliberationType.SINGLE_VERIFIER, acceptance_criteria=["Render correctly"]
        )
        out_path = os.path.join(self.tmp_dir.name, "dash.html")
        self.orch.export_dashboard("proj-ui", out_path)
        content = Path(out_path).read_text(encoding="utf-8")
        self.assertIn("OrchesIt Autonomous Multi-Agent Control Plane", content)
        self.assertIn("#F8FAFC", content)  # Light theme canvas


if __name__ == "__main__":
    unittest.main()
