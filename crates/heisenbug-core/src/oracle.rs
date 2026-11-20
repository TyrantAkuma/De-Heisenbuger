//! Process execution oracle and crash detection.

use std::process::Command;

#[derive(Debug, Clone)]
pub struct ProcessOutcome {
    pub exit_code: i32,
    pub is_crash: bool,
    pub stdout: String,
    pub stderr: String,
}

pub struct ProcessOracle;

impl ProcessOracle {
    /// Executes a child process command line and evaluates if it terminated abnormally.
    pub fn run_target(command: &[String], env_vars: &[(&str, &str)]) -> std::io::Result<ProcessOutcome> {
        if command.is_empty() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                "Command array cannot be empty",
            ));
        }

        let mut cmd = Command::new(&command[0]);
        if command.len() > 1 {
            cmd.args(&command[1..]);
        }
        for (k, v) in env_vars {
            cmd.env(k, v);
        }

        let output = cmd.output()?;
        let exit_code = output.status.code().unwrap_or(-1);
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        let stdout = String::from_utf8_lossy(&output.stdout).to_string();

        let is_crash = exit_code != 0
            || stderr.contains("panicked")
            || stderr.contains("SIGSEGV")
            || stderr.contains("SIGABRT")
            || stderr.contains("assertion failed")
            || stderr.contains("Data race detected")
            || stderr.contains("deadlock detected");

        Ok(ProcessOutcome {
            exit_code,
            is_crash,
            stdout,
            stderr,
        })
    }
}
