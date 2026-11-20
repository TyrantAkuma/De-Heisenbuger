//! Heisenbug Core: PRNG, execution trace records, and DDmin trace minimization.

pub mod ddmin;
pub mod oracle;
pub mod prng;
pub mod trace;

pub use ddmin::{ddmin, MinimizationResult};
pub use oracle::{ProcessOracle, ProcessOutcome};
pub use prng::SplitMix64;
pub use trace::{ExecutionTrace, SchedEvent};
