//! Andreas Zeller's Delta Debugging (DDmin) algorithm for thread schedule minimization.
//!
//! Reduces huge execution traces (e.g. 100k switch events) down to the 1-minimal subset
//! of critical thread switches (e.g. ~5 switches) required to trigger the race condition.

use crate::trace::SchedEvent;
use serde::{Deserialize, Serialize};

/// Summary of a completed DDmin minimization run.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MinimizationResult {
    pub seed: u64,
    pub original_events_count: usize,
    pub minimized_events_count: usize,
    pub iterations: usize,
    pub reduction_percentage: f64,
    pub minimized_switches: Vec<SchedEvent>,
}

/// Executes Andreas Zeller's DDmin algorithm on a sequence of scheduling events.
///
/// # Arguments
/// * `initial_events` - The full trace of scheduling events leading to a crash.
/// * `test_oracle` - A closure that tests whether a proposed subset of events reproduces the crash.
///                   Returns `true` if crash occurs (FAIL outcome), `false` if test passes.
pub fn ddmin<F>(initial_events: &[SchedEvent], mut test_oracle: F) -> MinimizationResult
where
    F: FnMut(&[SchedEvent]) -> bool,
{
    let original_count = initial_events.len();
    if original_count == 0 {
        return MinimizationResult {
            seed: 0,
            original_events_count: 0,
            minimized_events_count: 0,
            iterations: 0,
            reduction_percentage: 0.0,
            minimized_switches: Vec::new(),
        };
    }

    let mut current_set = initial_events.to_vec();
    let mut n = 2; // Initial granularity: split into 2 chunks
    let mut iterations = 0;

    while current_set.len() >= 2 {
        iterations += 1;
        let len = current_set.len();
        let chunk_size = (len + n - 1) / n;
        let mut reduced = false;

        // 1. Test each individual subset
        for i in 0..n {
            let start = i * chunk_size;
            if start >= len {
                break;
            }
            let end = (start + chunk_size).min(len);
            let subset = &current_set[start..end];

            if !subset.is_empty() && test_oracle(subset) {
                current_set = subset.to_vec();
                n = 2.max(n - 1);
                reduced = true;
                break;
            }
        }

        if reduced {
            continue;
        }

        // 2. Test each complement (everything except chunk i)
        for i in 0..n {
            let start = i * chunk_size;
            if start >= len {
                break;
            }
            let end = (start + chunk_size).min(len);

            let mut complement = Vec::with_capacity(len - (end - start));
            complement.extend_from_slice(&current_set[..start]);
            complement.extend_from_slice(&current_set[end..]);

            if !complement.is_empty() && test_oracle(&complement) {
                current_set = complement;
                n = 2.max(n - 1);
                reduced = true;
                break;
            }
        }

        if reduced {
            continue;
        }

        // 3. Increase granularity if neither subsets nor complements failed
        if n < current_set.len() {
            n = (2 * n).min(current_set.len());
        } else {
            // Reached 1-minimality: cannot partition any further
            break;
        }
    }

    let minimized_count = current_set.len();
    let reduction_percentage = if original_count > 0 {
        ((original_count - minimized_count) as f64 / original_count as f64) * 100.0
    } else {
        0.0
    };

    MinimizationResult {
        seed: 0,
        original_events_count: original_count,
        minimized_events_count: minimized_count,
        iterations,
        reduction_percentage,
        minimized_switches: current_set,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ddmin_reduces_trace() {
        // Construct a trace of 10,000 events where only events at indices 42, 105, 512, 1024, 7890
        // constitute the race condition.
        let mut events = Vec::new();
        for i in 0..10_000 {
            events.push(SchedEvent {
                seq: i,
                timestamp_ns: i * 1000,
                tgid: 1000,
                prev_tid: (i % 4) as u32,
                next_tid: ((i + 1) % 4) as u32,
                cpu: 0,
                flags: 0,
                annotation: None,
            });
        }

        let critical_ids = [42, 105, 512, 1024, 7890];

        // Oracle returns true if all 5 critical events are present in the candidate subset
        let oracle = |subset: &[SchedEvent]| -> bool {
            critical_ids.iter().all(|&cid| subset.iter().any(|e| e.seq == cid))
        };

        let result = ddmin(&events, oracle);
        assert_eq!(result.minimized_events_count, 5);
        for &cid in &critical_ids {
            assert!(result.minimized_switches.iter().any(|e| e.seq == cid));
        }
        assert!(result.reduction_percentage > 99.9);
    }
}
