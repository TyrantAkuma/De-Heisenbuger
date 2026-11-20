//! Deterministic Pseudo-Random Number Generators (PRNG).
//!
//! Provides a bit-for-bit exact implementation of SplitMix64 matching
//! the eBPF kernel scheduler in `scx_heisenbug.bpf.c`.

/// Bit-for-bit SplitMix64 generator matching Linux eBPF kernel implementation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    /// Creates a new generator from a 64-bit seed.
    pub const fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    /// Advances state and produces the next pseudo-random 64-bit unsigned integer.
    #[inline]
    pub fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E3779B97F4A7C15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D049BB133111EB);
        z ^ (z >> 31)
    }

    /// Generates a bounded integer in range `[0, bound)`.
    #[inline]
    pub fn next_bounded(&mut self, bound: u64) -> u64 {
        if bound <= 1 {
            return 0;
        }
        self.next_u64() % bound
    }

    /// Returns current state for checkpointing.
    #[inline]
    pub fn state(&self) -> u64 {
        self.state
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_splitmix64_determinism() {
        let mut g1 = SplitMix64::new(0x123456789ABCDEF0);
        let mut g2 = SplitMix64::new(0x123456789ABCDEF0);

        for _ in 0..10_000 {
            assert_eq!(g1.next_u64(), g2.next_u64());
        }
    }

    #[test]
    fn test_splitmix64_different_seeds() {
        let mut g1 = SplitMix64::new(1);
        let mut g2 = SplitMix64::new(2);
        assert_ne!(g1.next_u64(), g2.next_u64());
    }

    #[test]
    fn test_bounded() {
        let mut g = SplitMix64::new(42);
        for _ in 0..1000 {
            let val = g.next_bounded(10);
            assert!(val < 10);
        }
    }
}
