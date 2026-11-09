# CompanyOS & OrchesIt Battle Plan: Heisenbug

**Project Name:** Heisenbug (Deterministic Concurrency Race Condition Reproducer & Minimizer)  
**Target:** Linux 6.12+ `sched_ext` (eBPF) + Rust Userspace Control Plane  
**Orchestration Mode:** OrchesIt Autonomous Jury Multi-Agent SDLC  
**Date:** 2026-11-09  

---

## 1. Domain Detection & Classification
- **Domain:** Systems Engineering / Operating Systems Kernel / Developer Infrastructure & Reliability Tools.
- **Subdomain:** Concurrency testing, eBPF extensible schedulers (`sched_ext`), deterministic replay, algorithmic delta debugging (`DDmin`).
- **Domain Constraints:**
  - Kernel safety: eBPF verifier compliance, no unbounded loops, zero kernel panics or deadlock in `sched_ext_ops`.
  - Determinism: 100% bit-exact parity between kernel BPF PRNG and userspace PRNG.
  - Minimization scalability: DDmin algorithmic complexity $O(n^2)$ reduced to $O(n \log n)$ via adaptive chunking for 100k events.
  - Portability: Dual-mode architecture—native Linux 6.12+ `sched_ext` kernel driver + deterministic userspace simulation engine (`heisenbug-sim`) for cross-platform validation (Windows/macOS/Linux CI).

---

## 2. Workforce Sizing & Roles

Every task in the DAG is staffed with an Executor and an Independent Verifier. Critical milestone tasks convene a 4-member Adversarial Jury.

| Task ID | Task Title | Executor Role | Verifier Role | Deliberation Type | Dependencies |
|---------|------------|---------------|---------------|-------------------|--------------|
| `TASK-01` | Premise & Market Requirements | `@RequirementsAnalyst` | `@AdversarialSystemsAuditor` | Adversarial Jury | None |
| `TASK-02` | System Architecture & Contracts | `@PrincipalArchitect` | `@ReliabilityAuditor` | Adversarial Jury | `TASK-01` |
| `TASK-03` | Core PRNG & DDmin Minimization Engine | `@SeniorBackendEngineer` | `@IndependentCodeReviewer` | Single Verifier | `TASK-02` |
| `TASK-04` | Linux 6.12+ sched_ext eBPF Kernel Scheduler | `@KernelBPFEngineer` | `@SystemsVerifier` | Single Verifier | `TASK-02` |
| `TASK-05` | Deterministic Concurrency Sim & Testbed | `@RuntimeSystemsEngineer` | `@IndependentCodeReviewer` | Single Verifier | `TASK-03` |
| `TASK-06` | Developer CLI & Diagnostic Suite | `@CLIEngineer` | `@UXAuditor` | Single Verifier | `TASK-03`, `TASK-05` |
| `TASK-07` | Security Hardening (eBPF & Kernel Boundaries) | `@RedTeamAttacker` | `@BlueTeamDefender` | Adversarial Jury | `TASK-04`, `TASK-06` |
| `TASK-08` | QA Validation Loop & DDmin Benchmark | `@QAAutomationEngineer` | `@VerificationLead` | Adversarial Jury | `TASK-05`, `TASK-06` |
| `TASK-09` | Technical Documentation & Delivery | `@TechnicalWriter` | `@DocumentationAuditor` | Single Verifier | `TASK-07`, `TASK-08` |

---

## 3. Directory Sandboxing & Layout Plan

```
c:\antigravity\Heisenbug/
├── docs/
│   ├── 00-battle-plan.md
│   ├── 01-market-requirements.md
│   ├── 02-architecture.md
│   ├── 02-api-contracts.json
│   ├── 02-bpf-schema.json
│   ├── 03-security-audit.md
│   └── 04-test-results.md
├── orchesit/                     # OrchesIt Multi-Agent Control Plane
│   ├── __init__.py
│   ├── state.py
│   ├── scheduler.py
│   ├── jury.py
│   ├── recovery.py
│   ├── model_router.py
│   ├── visualizer.py
│   └── cli.py
├── bpf/                          # eBPF C kernel code
│   ├── scx_heisenbug.bpf.c       # sched_ext eBPF ops
│   ├── scx_common.h              # Shared structs between BPF and userspace
│   └── vmlinux.h                 # Kernel BPF type definitions (subset)
├── crates/
│   ├── heisenbug-core/           # PRNG, DDmin algorithm, trace representation
│   ├── heisenbug-ebpf/           # Sched_ext loader and controller
│   ├── heisenbug-sim/            # Deterministic multithreaded testbed & runner
│   └── heisenbug-cli/            # Production CLI binary (heisenbug)
├── Cargo.toml                    # Root workspace manifest
├── dashboard.html                # High-contrast light-theme UI dashboard
├── orchesit_state.db             # Persistent ACID SQLite database
└── README.md                     # Production release documentation
```

---

## 4. Acceptance Gates
- Phase 1 Gate: `docs/01-market-requirements.md` verified by Adversarial Jury.
- Phase 2 Gate: `docs/02-architecture.md`, API contracts, and BPF schema verified.
- Phase 3 Gate: Full Rust workspace compiles cleanly with zero warnings (`cargo test` passes).
- Phase 4 Gate: eBPF verifier safety, memory safety, bounded loops, and capability constraints audited (`docs/03-security-audit.md`).
- Phase 5 Gate: DDmin minimization algorithm demonstrated on live trace: 100k events minimized to 5 critical switches with reproducible crash.
- Phase 6 Gate: Production documentation, interactive light-theme visual dashboard generated.
