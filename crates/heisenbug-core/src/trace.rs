//! Execution trace representation and serialization.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

/// An individual thread switch or scheduling intervention event.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SchedEvent {
    /// Global sequential index of this event in the execution trace
    pub seq: u64,
    /// Monotonic timestamp in nanoseconds
    pub timestamp_ns: u64,
    /// Thread group ID (Process ID)
    pub tgid: u32,
    /// Previous thread ID on CPU
    pub prev_tid: u32,
    /// Next thread ID dispatched to CPU
    pub next_tid: u32,
    /// CPU core index
    pub cpu: u32,
    /// Flags or context indicators (e.g. voluntary yield vs preemption)
    pub flags: u32,
    /// Optional symbol / location annotation for minimized diagnostics
    pub annotation: Option<String>,
}

/// A complete recording of a test run's scheduling decisions.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionTrace {
    /// 64-bit seed used to drive thread dispatch
    pub seed: u64,
    /// Total number of scheduling events observed
    pub total_events: usize,
    /// Target command line executed
    pub target_command: Vec<String>,
    /// Exit status code (e.g. non-zero for crash/assertion failure)
    pub crash_exit_code: i32,
    /// Sequence of scheduling events
    pub events: Vec<SchedEvent>,
}

impl ExecutionTrace {
    pub fn new(seed: u64, target_command: Vec<String>, crash_exit_code: i32) -> Self {
        Self {
            seed,
            total_events: 0,
            target_command,
            crash_exit_code,
            events: Vec::new(),
        }
    }

    pub fn push_event(&mut self, mut event: SchedEvent) {
        event.seq = self.events.len() as u64;
        self.events.push(event);
        self.total_events = self.events.len();
    }

    /// Computes cryptographic SHA-256 hash of this execution trace.
    pub fn compute_sha256(&self) -> String {
        let json = serde_json::to_string(self).unwrap_or_default();
        let mut hasher = Sha256::new();
        hasher.update(json.as_bytes());
        format!("{:x}", hasher.finalize())
    }

    /// Serializes trace to formatted JSON string.
    pub fn to_json_pretty(&self) -> Result<String, serde_json::Error> {
        serde_json::to_string_pretty(self)
    }

    /// Deserializes trace from JSON string.
    pub fn from_json(json: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(json)
    }
}
