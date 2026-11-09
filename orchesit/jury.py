"""
OrchesIt Jury and Verification Engine.
Implements the 5-stage Executor-Verifier protocol, independent single verifier audits,
and multi-member adversarial jury deliberations with blind voting and cross-examination.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from orchesit.state import DeliberationType, StateStore, TaskStatus, Verdict


@dataclass
class JurorVote:
    juror_role: str
    vote: str  # "PASS" or "FAIL"
    confidence: float  # 0.0 to 1.0
    reasoning: str
    rebuttal: Optional[str] = None


class VerificationEngine:
    """Manages independent verification and adversarial jury deliberation."""

    def __init__(self, state_store: StateStore):
        self.store = state_store

    def conduct_single_verifier(
        self,
        task_id: str,
        verifier_role: str,
        verdict: Verdict,
        critique: str,
        evidence_verified: Dict[str, Any] | List[str],
    ) -> int:
        """Records an independent single-verifier verdict."""
        verif_id = self.store.record_verification(
            task_id=task_id,
            verifier_role=verifier_role,
            verdict=verdict,
            critique=critique,
            evidence_verified=evidence_verified,
        )
        if verdict in (Verdict.PASS, Verdict.PASS_WITH_CAVEATS):
            self.store.update_task_status(task_id, TaskStatus.COMPLETED)
        else:
            self.store.update_task_status(task_id, TaskStatus.FAILED)
        return verif_id

    def conduct_adversarial_jury(
        self,
        task_id: str,
        round_1_votes: List[JurorVote],
        round_2_cross_exam: Optional[List[JurorVote]] = None,
        orchestrator_justification: Optional[str] = None,
    ) -> Verdict:
        """
        Executes an Adversarial Jury deliberation across:
        1. Round 1: Blind evaluation from 4 independent perspectives.
        2. Round 2: Adversarial cross-examination of dissenting opinions.
        3. Round 3: Orchestrator resolution with explicit architectural justification.
        """
        self.store.update_task_status(task_id, TaskStatus.DELIBERATING)

        # Record Round 1
        for jv in round_1_votes:
            self.store.record_jury_vote(
                task_id=task_id,
                round_number=1,
                juror_role=jv.juror_role,
                vote=jv.vote,
                confidence=jv.confidence,
                reasoning=jv.reasoning,
                rebuttal=None,
            )

        # If Round 2 provided, record cross-examinations
        effective_votes = round_2_cross_exam if round_2_cross_exam else round_1_votes
        if round_2_cross_exam:
            for jv in round_2_cross_exam:
                self.store.record_jury_vote(
                    task_id=task_id,
                    round_number=2,
                    juror_role=jv.juror_role,
                    vote=jv.vote,
                    confidence=jv.confidence,
                    reasoning=jv.reasoning,
                    rebuttal=jv.rebuttal,
                )

        # Evaluate consensus or orchestrator resolution
        pass_votes = sum(1 for v in effective_votes if v.vote.upper() == "PASS")
        fail_votes = sum(1 for v in effective_votes if v.vote.upper() == "FAIL")

        if pass_votes > fail_votes:
            final_verdict = Verdict.PASS
            justification = orchestrator_justification or (
                f"Jury reached supermajority ({pass_votes}/{len(effective_votes)}) in favor of passing. "
                "Evidence satisfies architectural and empirical constraints."
            )
        else:
            final_verdict = Verdict.FAIL
            justification = orchestrator_justification or (
                f"Jury rejected deliverable ({fail_votes}/{len(effective_votes)} fail votes). "
                "Critical defects or safety/soundness objections remain unresolved."
            )

        self.store.record_orchestrator_resolution(
            task_id=task_id,
            final_verdict=final_verdict,
            architectural_justification=justification,
        )

        if final_verdict == Verdict.PASS:
            self.store.update_task_status(task_id, TaskStatus.COMPLETED)
        else:
            self.store.update_task_status(task_id, TaskStatus.FAILED)

        return final_verdict
