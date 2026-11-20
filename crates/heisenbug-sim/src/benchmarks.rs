//! Concurrency benchmarks and reproducible Heisenbug examples.

use crate::scheduler::DeterministicScheduler;
use heisenbug_core::{ddmin, ExecutionTrace, MinimizationResult, SchedEvent};

/// Simulates a classic unsynchronized bank account transfer race condition.
///
/// Invariant: Account A balance + Account B balance MUST always equal $1,000.
/// In an unsynchronized read-modify-write interleaving, money is lost or created.
pub fn run_bank_transfer_race(seed: u64) -> Result<(), (ExecutionTrace, String)> {
    let mut sched = DeterministicScheduler::new_fuzz(seed, &[1, 2]);

    let mut account_a = 500i64;
    let mut account_b = 500i64;

    // Thread 1 registers
    let mut t1_read_a = 0;
    let mut t1_read_b = 0;
    let mut t1_stage = 0;

    // Thread 2 registers
    let mut t2_read_a = 0;
    let mut t2_read_b = 0;
    let mut t2_stage = 0;

    // Run until both threads finish their transfers
    for _ in 0..100 {
        let active = sched.schedule_point(Some("bank_transfer_step"));

        if active == 1 {
            match t1_stage {
                0 => {
                    // T1 reads Account A to transfer $100 from A to B
                    t1_read_a = account_a;
                    t1_stage = 1;
                }
                1 => {
                    // T1 reads Account B
                    t1_read_b = account_b;
                    t1_stage = 2;
                }
                2 => {
                    // T1 writes updated Account A
                    account_a = t1_read_a - 100;
                    t1_stage = 3;
                }
                3 => {
                    // T1 writes updated Account B
                    account_b = t1_read_b + 100;
                    t1_stage = 4;
                }
                _ => {}
            }
        } else if active == 2 {
            match t2_stage {
                0 => {
                    // T2 reads Account B to transfer $50 from B to A
                    t2_read_b = account_b;
                    t2_stage = 1;
                }
                1 => {
                    // T2 reads Account A
                    t2_read_a = account_a;
                    t2_stage = 2;
                }
                2 => {
                    // T2 writes updated Account B
                    account_b = t2_read_b - 50;
                    t2_stage = 3;
                }
                3 => {
                    // T2 writes updated Account A
                    account_a = t2_read_a + 50;
                    t2_stage = 4;
                }
                _ => {}
            }
        }

        if t1_stage == 4 && t2_stage == 4 {
            break;
        }
    }

    let total = account_a + account_b;
    if total != 1000 {
        let msg = format!(
            "HEISENBUG DETECTED: Bank invariant violated! Account A=${}, Account B=${}, Total=${} (expected $1000)",
            account_a, account_b, total
        );
        let trace = sched.finish(101);
        Err((trace, msg))
    } else {
        Ok(())
    }
}

/// Demonstrates DDmin trace minimization: takes 100,000 scheduling switch events
/// and minimizes them down to 5 critical switches required to reproduce the race.
pub fn run_100k_minimization_benchmark() -> MinimizationResult {
    let mut initial_events = Vec::with_capacity(100_000);

    for i in 0..100_000 {
        initial_events.push(SchedEvent {
            seq: i as u64,
            timestamp_ns: i as u64 * 50,
            tgid: 4242,
            prev_tid: (i % 8) as u32,
            next_tid: ((i + 1) % 8) as u32,
            cpu: (i % 4) as u32,
            flags: 0,
            annotation: None,
        });
    }

    // 5 critical switch points that define the race window
    let critical_switches = [1337, 7777, 25000, 68900, 99123];

    // Mark the annotations on the critical switches
    for &idx in &critical_switches {
        initial_events[idx].annotation = Some(format!("CRITICAL_RACE_INTERLEAVING_AT_{}", idx));
    }

    // Test oracle: crash occurs if and only if all 5 critical switches are present
    let oracle = |subset: &[SchedEvent]| -> bool {
        critical_switches
            .iter()
            .all(|&cid| subset.iter().any(|e| e.seq == cid as u64))
    };

    let mut result = ddmin(&initial_events, oracle);
    result.seed = 0x6a09e667f3bcc908;
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bank_transfer_race_reproducibility() {
        // Find a seed that causes the race condition
        let mut crash_seed = None;
        for s in 0..1000 {
            if let Err((trace, _msg)) = run_bank_transfer_race(s) {
                crash_seed = Some((s, trace.events.len()));
                break;
            }
        }

        assert!(crash_seed.is_some(), "At least one seed should trigger the race");
        let (seed, len) = crash_seed.unwrap();

        // 100% Deterministic Re-run verification: exact same seed must fail every time!
        for _ in 0..50 {
            let res = run_bank_transfer_race(seed);
            assert!(res.is_err(), "Must deterministically fail on seed 0x{:x}", seed);
            let (reproduced_trace, _) = res.unwrap_err();
            assert_eq!(reproduced_trace.events.len(), len);
        }
    }

    #[test]
    fn test_100k_minimization_to_5_switches() {
        let result = run_100k_minimization_benchmark();
        assert_eq!(result.original_events_count, 100_000);
        assert_eq!(result.minimized_events_count, 5);
        assert!(result.reduction_percentage > 99.99);

        let seqs: Vec<u64> = result.minimized_switches.iter().map(|e| e.seq).collect();
        assert_eq!(seqs, vec![1337, 7777, 25000, 68900, 99123]);
    }
}
