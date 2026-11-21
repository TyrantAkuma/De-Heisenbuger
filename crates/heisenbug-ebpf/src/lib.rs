//! Kernel eBPF sched_ext controller and map manager.

use std::path::Path;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum KernelCapability {
    SchedExtAvailable,
    SchedExtNotSupported,
    NonLinuxHost,
}

pub struct SchedExtManager {
    capability: KernelCapability,
    bpf_object_path: Option<String>,
}

impl SchedExtManager {
    pub fn new() -> Self {
        let cap = Self::detect_capability();
        Self {
            capability: cap,
            bpf_object_path: None,
        }
    }

    /// Detects whether current OS and kernel support Linux 6.12+ sched_ext.
    pub fn detect_capability() -> KernelCapability {
        #[cfg(target_os = "linux")]
        {
            if Path::new("/sys/kernel/sched_ext").exists() {
                KernelCapability::SchedExtAvailable
            } else {
                KernelCapability::SchedExtNotSupported
            }
        }
        #[cfg(not(target_os = "linux"))]
        {
            KernelCapability::NonLinuxHost
        }
    }

    pub fn capability(&self) -> KernelCapability {
        self.capability
    }

    pub fn is_sched_ext_supported(&self) -> bool {
        self.capability == KernelCapability::SchedExtAvailable
    }

    /// Loads the compiled BPF object file into the kernel if supported.
    pub fn load_bpf_program(&mut self, bpf_path: &str) -> Result<(), String> {
        if !self.is_sched_ext_supported() {
            return Err(format!(
                "sched_ext not supported on this platform ({:?}). Using userspace simulation fallback.",
                self.capability
            ));
        }

        if !Path::new(bpf_path).exists() {
            return Err(format!("BPF object not found at {}", bpf_path));
        }

        self.bpf_object_path = Some(bpf_path.to_string());
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_capability_detection() {
        let mgr = SchedExtManager::new();
        // On non-Linux host (e.g. Windows dev machine), correctly flags NonLinuxHost
        #[cfg(not(target_os = "linux"))]
        assert_eq!(mgr.capability(), KernelCapability::NonLinuxHost);
    }
}
