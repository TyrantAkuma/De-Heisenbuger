# Market Requirements & Concurrency Analysis Document

**Project:** Heisenbug  
**Author:** `@RequirementsAnalyst`  
**Auditor:** `@AdversarialSystemsAuditor`  
**Date:** 2026-11-09  
**Status:** Verified by Adversarial Jury  

---

## 1. Executive Summary & Problem Space

Multithreaded software in production systems relies heavily on concurrent thread dispatch. In modern Linux systems, thread preemption and dispatching are governed by kernel CPU schedulers (historically CFS, now EEVDF).

Because CPU scheduling decisions are influenced by microsecond-level hardware interrupts, clock jitter, CPU thermal throttling, NUMA node balance, and unrelated background processes, the interleaving of concurrent instructions across threads is non-deterministic.

### The Heisenbug Phenomenon
A **Heisenbug** is a defect that alters its behavior or disappears entirely when an attempt is made to observe or debug it:
- A data race, lock order inversion, or memory visibility bug occurs in CI once every 200 runs.
- When run locally under a debugger (GDB, LLDB) or with logging (`println!`, `log::debug`), the added timing delays alter thread interleaving, masking the race condition.
- Engineering teams waste an estimated 15-25% of developer time (hundreds of hours per quarter) chasing intermittent CI failures.

---

## 2. Competitive Landscape & Technical Limitations of Alternatives

| Tool | Mechanism | Deterministic Replay? | Minimization? | Kernel Overhead | CI Friendly? |
|---|---|---|---|---|---|
| **ThreadSanitizer (TSan)** | Compile-time instrumentation | ❌ No (detects races, cannot force reproduction) | ❌ No | 2x-5x slowdown, 5x-10x memory | Heavy, high CI timeout rate |
| **rr (Record and Replay)** | Hardware performance counters (`perf_event`) | ✅ Yes | ❌ No (replays massive GB-sized traces) | Low overhead, but requires specific x86 Intel PMU | ❌ Broken on AMD, Cloud VMs, and ARM64 |
| **Tokio Loom** | Userspace mock runtime (Rust only) | ✅ Yes | ❌ Exhaustive state explosion | High (only unit tests, not real OS threads) | Restricted to Rust Loom tests |
| **Chaos Mode / stress-ng** | Artificial CPU thrashing | ❌ Non-deterministic | ❌ No | 100% CPU starvation | Unreliable flakiness amplifier |
| **Heisenbug (Ours)** | **Linux 6.12+ `sched_ext` (eBPF)** | **✅ 100% via 64-bit `--seed`** | **✅ DDmin: 100k events $\to$ 5 switches** | **< 3% overhead, native kernel hooks** | **✅ Works in VM/Bare-metal/Container** |

---

## 3. Core Architecture Requirements

### 3.1. Kernel-Level Thread Control via `sched_ext` (eBPF)
In Linux 6.12, the Extensible Scheduler Class (`sched_ext`, `SCX`) was merged into the upstream kernel. It exposes kernel scheduling hooks (`scx_bpf_dispatch`, `ops.enqueue`, `ops.select_cpu`) to verified eBPF bytecode.
- **Requirement 1.1:** Heisenbug attaches to `sched_ext` when loaded, registering custom dispatch logic for target process thread groups (`tgid`).
- **Requirement 1.2:** Unmonitored processes continue running on default kernel queues (`SCX_DSQ_GLOBAL` / local DSQs) with zero performance degradation.
- **Requirement 1.3:** For the target process, thread preemption points and CPU dispatch order are strictly governed by a deterministic pseudo-random sequence generated from a 64-bit seed.

### 3.2. 100% Reproducibility with `--seed <u64>`
- **Requirement 2.1:** Any run of `./heisenbug fuzz -- <command>` that crashes, deadlocks, or fails assertions must print the exact 64-bit seed used:
  ```
  [HEISENBUG] CRASH DETECTED (SIGSEGV / Assertion Failure)!
  [HEISENBUG] Reproduce with: heisenbug replay --seed 0x6a09e667f3bcc908 -- ./my_target
  ```
- **Requirement 2.2:** Running `heisenbug replay --seed <seed>` executes the identical thread dispatch sequence, reproducing the failure with 100% certainty.

### 3.3. Automatic Trace Minimization via DDmin
- **Requirement 3.1:** A typical run produces between 10,000 and 1,000,000 thread switch events before crashing.
- **Requirement 3.2:** Heisenbug incorporates Andreas Zeller's Delta Debugging (`DDmin`) algorithm.
- **Requirement 3.3:** DDmin systematically isolates the 1-minimal subset of thread switches required to reproduce the crash, minimizing a 100k-event execution down to fewer than 10 (target: ~5) critical switch interventions.
- **Requirement 3.4:** Outputs an exact timeline showing:
  - Thread ID and Name
  - Switch event sequence index
  - Code location or synchronization primitive that collided

### 3.4. Portability & Cross-Platform Userspace Simulation
- **Requirement 4.1:** When running on Linux 6.12+ with `CONFIG_SCHED_CLASS_EXT=y`, Heisenbug operates natively via kernel eBPF.
- **Requirement 4.2:** For development environments, CI containers without kernel privileges, and Windows/macOS developer machines, Heisenbug provides `heisenbug-sim`, a deterministic userspace scheduler and thread harness that implements the identical PRNG dispatch permutation and DDmin minimization algorithms.

---

## 4. User Personas & Core Journeys

1. **Rust / Go Systems Engineer:** Investigating an intermittent lock-free ringbuffer corruption occurring 1 in 100 CI builds. Runs `heisenbug fuzz`, gets crash seed in 12 seconds, runs `heisenbug minimize`, and receives a 5-step switch trace identifying the ABA race.
2. **Database Engine Architect:** Verifying ACID transaction write-ahead log (WAL) synchronization under high contention. Injects deterministic random thread interleavings to stress race windows.
3. **CI/CD Reliability Engineer:** Adds `heisenbug run --seed $BUILD_SEED` to test pipeline. Eliminates unreproducible flakes by archiving failure seeds as actionable bug tickets.
