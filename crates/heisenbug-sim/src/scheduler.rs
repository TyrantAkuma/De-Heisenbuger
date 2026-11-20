//! Deterministic userspace scheduler and interleaving engine.
//! Simulates kernel thread preemption hooks for testing race conditions.

use heisenbug_core::{ExecutionTrace, SchedEvent, SplitMix64};
use std::collections::VecDeque;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SchedulerMode {
    Fuzz,
    Replay,
}

pub struct DeterministicScheduler {
    pub seed: u64,
    prng: SplitMix64,
    mode: SchedulerMode,
    ready_queue: VecDeque<u32>,
    replay_plan: Vec<u32>,
    replay_cursor: usize,
    trace: ExecutionTrace,
    current_tid: u32,
}

impl DeterministicScheduler {
    pub fn new_fuzz(seed: u64, thread_ids: &[u32]) -> Self {
        let mut q = VecDeque::new();
        for &t in thread_ids {
            q.push_back(t);
        }
        let current = q.pop_front().unwrap_or(0);
        Self {
            seed,
            prng: SplitMix64::new(seed),
            mode: SchedulerMode::Fuzz,
            ready_queue: q,
            replay_plan: Vec::new(),
            replay_cursor: 0,
            trace: ExecutionTrace::new(seed, vec!["sim_runner".to_string()], 0),
            current_tid: current,
        }
    }

    pub fn new_replay(seed: u64, thread_ids: &[u32], plan: Vec<u32>) -> Self {
        let mut q = VecDeque::new();
        for &t in thread_ids {
            q.push_back(t);
        }
        let current = q.pop_front().unwrap_or(0);
        Self {
            seed,
            prng: SplitMix64::new(seed),
            mode: SchedulerMode::Replay,
            ready_queue: q,
            replay_plan: plan,
            replay_cursor: 0,
            trace: ExecutionTrace::new(seed, vec!["sim_runner".to_string()], 0),
            current_tid: current,
        }
    }

    /// Preemption or yield point. Chooses next thread to run according to mode.
    pub fn schedule_point(&mut self, annotation: Option<&str>) -> u32 {
        if self.ready_queue.is_empty() {
            return self.current_tid;
        }

        // Put currently running thread back onto queue
        self.ready_queue.push_back(self.current_tid);

        let next_tid = match self.mode {
            SchedulerMode::Fuzz => {
                let idx = self.prng.next_bounded(self.ready_queue.len() as u64) as usize;
                self.ready_queue.remove(idx).unwrap()
            }
            SchedulerMode::Replay => {
                if self.replay_cursor < self.replay_plan.len() {
                    let planned = self.replay_plan[self.replay_cursor];
                    self.replay_cursor += 1;
                    if let Some(pos) = self.ready_queue.iter().position(|&t| t == planned) {
                        self.ready_queue.remove(pos).unwrap()
                    } else {
                        self.ready_queue.pop_front().unwrap()
                    }
                } else {
                    self.ready_queue.pop_front().unwrap()
                }
            }
        };

        let prev = self.current_tid;
        self.current_tid = next_tid;

        self.trace.push_event(SchedEvent {
            seq: 0,
            timestamp_ns: self.trace.events.len() as u64 * 1000,
            tgid: 100,
            prev_tid: prev,
            next_tid,
            cpu: 0,
            flags: 0,
            annotation: annotation.map(|s| s.to_string()),
        });

        next_tid
    }

    pub fn current_tid(&self) -> u32 {
        self.current_tid
    }

    pub fn finish(mut self, exit_code: i32) -> ExecutionTrace {
        self.trace.crash_exit_code = exit_code;
        self.trace
    }
}
