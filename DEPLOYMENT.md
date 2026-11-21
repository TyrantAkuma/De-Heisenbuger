# Heisenbug Deployment & CI/CD Integration Guide

This guide details how to deploy Heisenbug on Linux 6.12+ hosts with `sched_ext` enabled, as well as integrating deterministic concurrency testing into modern CI/CD pipelines (GitHub Actions, GitLab CI).

---

## 1. Prerequisites for Linux 6.12+ `sched_ext`

To run native kernel eBPF scheduling:
1. **Linux Kernel:** 6.12 or newer.
2. **Kernel Config:** Must have `CONFIG_SCHED_CLASS_EXT=y` and `CONFIG_BPF_SYSCALL=y`.
3. **Capabilities:** `CAP_BPF` and `CAP_SYS_ADMIN` (or root).
4. **Tools:** `clang` (>= 16), `llvm`, `libbpf-dev`, `bpftool`.

Check kernel support:
```bash
# Check if sched_ext sysfs interface is present
ls -la /sys/kernel/sched_ext
```

### Compiling the BPF Program
```bash
clang -g -O2 -target bpf -D__TARGET_ARCH_x86 -I/usr/include/bpf -c bpf/scx_heisenbug.bpf.c -o bpf/scx_heisenbug.bpf.o
```

---

## 2. GitHub Actions CI Integration

Heisenbug can run in CI pipelines in both native kernel mode (on Linux 6.12+ runners) or in userspace simulation mode (cross-platform, zero privileges).

### Example Workflow (`.github/workflows/concurrency-test.yml`)

```yaml
name: Concurrency Race Condition Verification

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  heisenbug-fuzz:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Rust
        uses: dtolnay/rust-toolchain@stable

      - name: Run Heisenbug Fuzzing on Test Suite
        run: |
          cargo run -p heisenbug-cli -- fuzz --iters 500

      - name: Minimize Interleaving on Failure
        if: failure()
        run: |
          cargo run -p heisenbug-cli -- minimize
```

---

## 3. Running Replay in CI on Failure

When a test fails under a specific seed:
```bash
# Developer or CI can reproduce the crash deterministically
cargo run -p heisenbug-cli -- replay --seed 0x6a09e667f3bcc908
```
This guarantees 100% reproduction without flaky non-deterministic behavior.
