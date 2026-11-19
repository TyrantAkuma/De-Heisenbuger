# System Architecture & Technical Specification: Heisenbug

**Document ID:** `docs/02-architecture.md`  
**Author:** `@PrincipalArchitect`  
**Auditor:** `@ReliabilityAuditor`  
**Status:** Verified by Adversarial Jury  

---

## 1. System Overview & Component Diagram

Heisenbug operates across two primary execution tiers:
1. **Kernel eBPF Sched_Ext Engine (`scx_heisenbug`):** A custom Linux 6.12+ extensible scheduler written in BPF C. Attaches to `struct sched_ext_ops`, intercepts task enqueue and dispatch points, and decides thread execution order according to seed-driven pseudo-random dispatch or replay plans.
2. **Userspace Rust Control Plane (`heisenbug-cli`, `heisenbug-core`, `heisenbug-sim`):** Orchestrates test execution, sets up eBPF maps, consumes thread switch event telemetry via ring buffer, drives the DDmin minimization engine, and coordinates replay.

```
+-------------------------------------------------------------------------+
|                           DEVELOPER / CI RUNNER                         |
|                                                                         |
|  $ heisenbug fuzz --iters 50 -- ./my_target_binary                      |
|  $ heisenbug minimize --seed 0x6a09e667f3bcc908 -- ./my_target_binary   |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                  USERSPACE CONTROL PLANE (Rust)                         |
|                                                                         |
|  +--------------------+   +---------------------+   +----------------+  |
|  |   heisenbug-cli    |-->|   heisenbug-core    |<--| heisenbug-sim  |  |
|  |  (CLI / UX / TUI)  |   | (PRNG, DDmin, Trace)|   | (Cross-plat SIM|  |
|  +--------------------+   +----------+----------+   +----------------+  |
|                                      |                                  |
|                           +----------v----------+                       |
|                           |   heisenbug-ebpf    |                       |
|                           | (BPF Loader & Maps) |                       |
|                           +----------+----------+                       |
+--------------------------------------|----------------------------------+
                                       | ioctl / sys_bpf / RingBuf
=======================================|===================================
                       LINUX 6.12+ KERNEL SPACE
+--------------------------------------v----------------------------------+
|                   sched_ext Extensible Scheduler Class                  |
|                                                                         |
|   +------------------------------------------------------------------+  |
|   | struct sched_ext_ops scx_heisenbug_ops                           |  |
|   |   .select_cpu = scx_heisenbug_select_cpu                         |  |
|   |   .enqueue    = scx_heisenbug_enqueue                            |  |
|   |   .dispatch   = scx_heisenbug_dispatch                           |  |
|   |   .running    = scx_heisenbug_running                            |  |
|   |   .stopping   = scx_heisenbug_stopping                           |  |
|   +------------------------------------------------------------------+  |
|                                                                         |
|   BPF Maps:                                                             |
|   - target_pids     : BPF_MAP_TYPE_HASH (tgid -> filter flag)           |
|   - sched_config    : BPF_MAP_TYPE_ARRAY (seed, mode, switch_counter)   |
|   - replay_plan     : BPF_MAP_TYPE_ARRAY (pre-computed switch order)    |
|   - events_ringbuf  : BPF_MAP_TYPE_RINGBUF (switch events to userspace) |
|                                                                         |
|   DSQs:                                                                 |
|   - SCX_DSQ_LOCAL   : CPU-local runqueue for non-target processes       |
|   - SCX_DSQ_GLOBAL  : Default system-wide fallback queue                |
|   - HEISEN_DSQ_BASE : Custom DSQ per monitored thread group             |
+-------------------------------------------------------------------------+
```

---

## 2. Kernel `sched_ext` Dispatch Protocol

### 2.1. Task Identification & Interception
1. When target binary is launched, its `pid`/`tgid` is inserted into `target_pids`.
2. In `scx_heisenbug_enqueue(struct task_struct *p, u64 enq_flags)`:
   - If `p->tgid` is NOT in `target_pids`, dispatch immediately to `SCX_DSQ_GLOBAL` with `scx_bpf_dispatch(p, SCX_DSQ_GLOBAL, SCX_SLICE_DFL, enq_flags)`. Kernel overhead on unmonitored workloads is $< 0.1\%$.
   - If `p->tgid` is tracked, the thread is enqueued into the custom DSQ `HEISEN_DSQ_BASE`.

### 2.2. Seed-Driven Dispatching (`scx_heisenbug_dispatch`)
In `scx_heisenbug_dispatch(s32 cpu, struct task_struct *prev)`:
- In `MODE_FUZZ`: The next task to run from `HEISEN_DSQ_BASE` is selected using SplitMix64 seeded with the 64-bit seed.
- In `MODE_REPLAY`: The next task to run is retrieved directly from `replay_plan` index `step_idx`.
- A thread switch event record is submitted to `events_ringbuf`:
  ```c
  struct sched_event {
      u64 timestamp_ns;
      u64 event_id;
      u32 tgid;
      u32 prev_tid;
      u32 next_tid;
      u32 cpu;
      u8  flags;
  };
  ```

---

## 3. Mathematical Specification: SplitMix64 PRNG

SplitMix64 is chosen for its simplicity, speed, zero allocation, and 64-bit period with excellent avalanche properties. It fits easily within eBPF verifier instruction limits (< 20 BPF insns).

$$\text{State Update: } s \leftarrow (s + \text{0x9E3779B97F4A7C15}) \pmod{2^{64}}$$
$$\text{Calculation: } z \leftarrow (s \oplus (s \gg 30)) \times \text{0xBF58476D1CE4E5B9}$$
$$z \leftarrow (z \oplus (z \gg 27)) \times \text{0x94D049BB133111EB}$$
$$\text{Output: } \text{SplitMix64}(s) = z \oplus (z \gg 31)$$

Both the eBPF C program and the Rust `heisenbug-core::prng` module execute this exact transformation bit-for-bit.

---

## 4. Algorithmic Specification: DDmin Trace Minimization

Let $T = [e_1, e_2, \dots, e_n]$ be the sequence of thread scheduling interventions (switches) that reproduce the bug (e.g. $n = 100,000$).
Let $\text{Test}(C) \in \{\text{PASS}, \text{FAIL}\}$ test whether executing subset of interventions $C \subseteq T$ reproduces the crash.

Andreas Zeller's DDmin algorithm partitions $T$ into $k$ subsets ($k=2$ initially):
1. Subsets: $c_1, c_2, \dots, c_k$ of size $\approx \frac{n}{k}$.
2. Test each subset $c_i$:
   - If $\text{Test}(c_i) == \text{FAIL}$, recurse on $c_i$ with $k=2$.
3. Test each complement $\bar{c_i} = T \setminus c_i$:
   - If $\text{Test}(\bar{c_i}) == \text{FAIL}$, recurse on $\bar{c_i}$ with $k = \max(k-1, 2)$.
4. If neither subsets nor complements fail:
   - If $k < n$, increase granularity $k \leftarrow \min(2k, n)$ and repeat.
   - If $k == n$, terminate: $T$ is 1-minimal.

Using this protocol, Heisenbug shrinks 100,000 switch traces to ~5 essential switch points.

---

## 5. Security and Kernel Safety Boundaries

1. **CAP_SYS_ADMIN / CAP_BPF Requirement:** Loading `sched_ext` programs requires root or `CAP_BPF` + `CAP_SYS_ADMIN`.
2. **Crash Resilience:** If `scx_heisenbug` fails or panics, the kernel's built-in `sched_ext` watchdog detects starvation or timeout and automatically unregisters the scheduler, returning safely to EEVDF without locking the host.
3. **Cross-Platform User Space Fallback:** On machines without Linux 6.12 kernel privileges, `heisenbug-sim` provides pure userspace deterministic scheduling for validation and CI workflows.
