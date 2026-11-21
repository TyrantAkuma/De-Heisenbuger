# Security Audit & Kernel Hardening: Heisenbug

**Document ID:** `docs/03-security-audit.md`  
**Author:** `@RedTeamAttacker` & `@BlueTeamDefender`  
**Auditor:** Adversarial Security Jury  
**Status:** Verified & Hardened  

---

## 1. Threat Model & Security Boundaries

Heisenbug operates at the boundary between userspace testing frameworks and kernel space via Linux 6.12+ `sched_ext` (eBPF).

### Trust Boundaries
1. **Userspace $\to$ Kernel Boundary:** BPF maps (`target_pids`, `sched_config`, `replay_plan`). Malicious or corrupted userspace processes must not cause kernel crashes, kernel heap corruption, or denial-of-service (host CPU lockup).
2. **eBPF Program $\to$ Kernel Scheduler Core:** The custom dispatch routine (`scx_heisenbug_dispatch`) must never starve the CPU, create recursive locks, or violate kernel execution constraints.
3. **Monitored Process $\to$ Host System:** Non-target host processes (systemd, sshd, container daemons) must experience zero disruption or starvation when a target process is being fuzzed.

---

## 2. Red Team Attack Surface Analysis

| Vector ID | Threat Vector | Red Team Exploitation Scenario | Severity | Blue Team Mitigation |
|---|---|---|---|---|
| **V-01** | BPF Map Array Out-of-Bounds | Malicious replay plan index exceeding allocated array buffer causing kernel out-of-bounds read | **HIGH** | Strict bitwise masking and bound check (`step < SCX_HEISENBUG_MAX_REPLAY_EVENTS`) enforced prior to map lookup. |
| **V-02** | Scheduler Starvation / Hang | A fuzzed thread stalls or deadlocks in userspace, causing `sched_ext` to indefinitely stall CPU dispatching | **CRITICAL** | Integrated kernel watchdog (`scx_watchdog`). Slices default to `SCX_SLICE_DFL` (5ms). If target threads fail to make forward progress, kernel automatically unregisters scheduler. |
| **V-03** | Ringbuffer Memory Exhaustion | High-frequency thread switching produces millions of events per second, exhausting kernel BPF ringbuffer memory | **MEDIUM** | Ringbuffer allocated with bounded 16MB ring buffer (`BPF_MAP_TYPE_RINGBUF`). Drop policy drops non-critical events on backpressure instead of blocking kernel dispatch. |
| **V-04** | Privilege Escalation via BPF | Unauthorized user attempts to load arbitrary kernel scheduler bytecode | **HIGH** | `sched_ext` registration requires `CAP_BPF` + `CAP_SYS_ADMIN` in the initial user namespace. |
| **V-05** | Uncontrolled PRNG Cycle | PRNG enters short cycle or zero state causing repetitive thread starvation | **LOW** | SplitMix64 has provable period of $2^{64}$ and non-zero Weyl sequence adder (`0x9e3779b97f4a7c15`). Verified collision-free. |

---

## 3. Blue Team Verification & Defenses Implemented

1. **eBPF Verifier Compliance:**
   - All loops in `scx_heisenbug.bpf.c` are bounded with static maximum bounds.
   - Pointers returned by `bpf_map_lookup_elem` and `bpf_ringbuf_reserve` are null-checked before dereferencing.
   - No floating-point instructions or unsupported BPF helper calls.

2. **Host Isolation:**
   - Unmonitored TGIDs are dispatched unconditionally to `SCX_DSQ_GLOBAL` with `scx_bpf_dispatch(p, SCX_DSQ_GLOBAL, SCX_SLICE_DFL, enq_flags)`.
   - Host system background tasks operate unaffected.

3. **Userspace Sandboxing Fallback:**
   - On non-privileged or non-Linux systems, `heisenbug-sim` executes purely in userspace memory space, avoiding any raw kernel calls.
