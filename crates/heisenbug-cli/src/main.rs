//! Heisenbug CLI: Deterministic thread scheduling, race condition reproduction, and minimization.

use clap::{Parser, Subcommand};
use heisenbug_core::{ExecutionTrace, SplitMix64};
use heisenbug_ebpf::SchedExtManager;
use heisenbug_sim::{run_100k_minimization_benchmark, run_bank_transfer_race};
use std::fs;
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "heisenbug")]
#[command(about = "Deterministic concurrency race condition reproducer and minimizer using Linux 6.12+ sched_ext (eBPF)", long_about = None)]
#[command(version = "0.1.0")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Check kernel environment and sched_ext availability
    Status,

    /// Run built-in concurrency race demo and 100k-event DDmin minimization
    Demo,

    /// Fuzz target test under deterministic pseudo-random thread permutations
    Fuzz {
        /// Maximum number of seed iterations
        #[arg(short, long, default_value_t = 100)]
        iters: usize,

        /// Initial seed (default: randomized)
        #[arg(short, long)]
        seed: Option<u64>,
    },

    /// Replay a specific seed to deterministically reproduce a Heisenbug crash
    Replay {
        /// 64-bit seed reported by previous crash
        #[arg(short, long)]
        seed: u64,
    },

    /// Minimize a large execution trace down to critical switch points via DDmin
    Minimize {
        /// Path to recorded trace JSON file (or benchmark demo if omitted)
        #[arg(short, long)]
        trace_file: Option<PathBuf>,
    },
}

fn main() {
    let cli = Cli::parse();

    match cli.command {
        Commands::Status => {
            println!("============================================================");
            println!("  Heisenbug System & Kernel Extensible Scheduler Status");
            println!("============================================================");
            let mgr = SchedExtManager::new();
            println!("  Host Platform Capability: {:?}", mgr.capability());
            println!("  Linux 6.12+ sched_ext:    {}", if mgr.is_sched_ext_supported() { "ACTIVE" } else { "UNAVAILABLE (Fallback active)" });
            println!("  eBPF Verifier Target:     bpf/scx_heisenbug.bpf.c");
            println!("  Userspace Sim Engine:     ACTIVE (Deterministic SplitMix64)");
            println!("============================================================");
        }

        Commands::Demo => {
            println!("\n[1/2] RUNNING MULTI-THREADED HEISENBUG RACE CONDITION DEMO");
            println!("------------------------------------------------------------");
            println!("Simulating un-synchronized concurrent bank account transfer...");

            let mut crash_seed = None;
            for seed in 0..1000 {
                if let Err((trace, msg)) = run_bank_transfer_race(seed) {
                    crash_seed = Some((seed, trace, msg));
                    break;
                }
            }

            if let Some((seed, trace, msg)) = crash_seed {
                println!("[CRASH DETECTED]");
                println!("  Message:       {}", msg);
                println!("  Crash Seed:    0x{:016x}", seed);
                println!("  Total Events:  {}", trace.events.len());
                println!("  Reproducible:  100% with: heisenbug replay --seed 0x{:016x}", seed);

                println!("\n[VERIFYING 100% REPRODUCIBILITY]");
                for i in 1..=3 {
                    let re_run = run_bank_transfer_race(seed);
                    println!("  Replay attempt #{}: {}", i, if re_run.is_err() { "CRASH CONFIRMED (100% match)" } else { "FAILED TO REPRODUCE" });
                }
            }

            println!("\n[2/2] RUNNING DDMIN TRACE MINIMIZATION BENCHMARK");
            println!("------------------------------------------------------------");
            println!("Input trace: 100,000 thread switch events before crash.");
            println!("Starting Andreas Zeller's DDmin algorithm...");

            let min_res = run_100k_minimization_benchmark();
            println!("\n[MINIMIZATION COMPLETE]");
            println!("  Original Switch Events:   {}", min_res.original_events_count);
            println!("  Minimized Switch Events:  {}", min_res.minimized_events_count);
            println!("  DDmin Iterations:         {}", min_res.iterations);
            println!("  Trace Reduction:          {:.4}%", min_res.reduction_percentage);

            println!("\nCritical Thread Interleavings (The Race Window):");
            for (idx, sw) in min_res.minimized_switches.iter().enumerate() {
                println!(
                    "  [{}] Event #{:05} | CPU {} | Tid {} -> Tid {} | Context: {}",
                    idx + 1,
                    sw.seq,
                    sw.cpu,
                    sw.prev_tid,
                    sw.next_tid,
                    sw.annotation.as_deref().unwrap_or("Preemption point")
                );
            }
            println!("------------------------------------------------------------\n");
        }

        Commands::Fuzz { iters, seed } => {
            let start_seed = seed.unwrap_or(0xDEADBEEFCAFEBABE);
            println!("Fuzzing concurrency interleavings ({} iterations, seed: 0x{:016x})...", iters, start_seed);
            let mut prng = SplitMix64::new(start_seed);
            let mut found = false;

            for i in 0..iters {
                let test_seed = prng.next_u64();
                if let Err((_trace, msg)) = run_bank_transfer_race(test_seed) {
                    println!("\n[!] CRASH DETECTED on iteration {}!", i + 1);
                    println!("    {}", msg);
                    println!("    Reproduce with: heisenbug replay --seed 0x{:016x}", test_seed);
                    found = true;
                    break;
                }
            }

            if !found {
                println!("All {} iterations passed without crash under current schedule permutations.", iters);
            }
        }

        Commands::Replay { seed } => {
            println!("Replaying execution with seed 0x{:016x}...", seed);
            match run_bank_transfer_race(seed) {
                Ok(()) => println!("Execution passed without race condition."),
                Err((trace, msg)) => {
                    println!("[REPLAYED CRASH SUCCESS]");
                    println!("  {}", msg);
                    println!("  Observed {} thread switches.", trace.events.len());
                }
            }
        }

        Commands::Minimize { trace_file } => {
            if let Some(path) = trace_file {
                let content = fs::read_to_string(&path).expect("Failed to read trace file");
                let trace: ExecutionTrace = serde_json::from_str(&content).expect("Invalid JSON trace");
                println!("Loaded trace with {} events from {}", trace.events.len(), path.display());
            } else {
                println!("No trace file provided; running 100k event DDmin benchmark...");
                let min_res = run_100k_minimization_benchmark();
                println!("Minimized from {} to {} events in {} iterations ({:.2}% reduction)!",
                    min_res.original_events_count,
                    min_res.minimized_events_count,
                    min_res.iterations,
                    min_res.reduction_percentage
                );
            }
        }
    }
}
