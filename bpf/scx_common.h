/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Common header shared between eBPF kernel program and userspace Rust controller.
 */

#ifndef __SCX_COMMON_H__
#define __SCX_COMMON_H__

#ifdef __KERNEL__
typedef __u8  u8;
typedef __u16 u16;
typedef __u32 u32;
typedef __u64 u64;
typedef __s32 s32;
typedef __s64 s64;
#else
#include <stdint.h>
typedef uint8_t  u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int32_t  s32;
typedef int64_t  s64;
#endif

#define SCX_HEISENBUG_MAX_REPLAY_EVENTS 131072
#define SCX_HEISENBUG_MAX_PIDS          1024

/* Operating Modes */
#define SCX_MODE_BYPASS  0
#define SCX_MODE_FUZZ    1
#define SCX_MODE_REPLAY  2

/* Custom Dispatch Queue IDs */
#define HEISEN_DSQ_BASE 0x1000ULL

/* Configuration shared via BPF array map */
struct sched_config_val {
    u64 seed;
    u64 prng_state;
    u32 mode;
    u32 flags;
    u64 event_counter;
    u64 current_step;
};

/* Event emitted over BPF ringbuffer for every scheduling transition */
struct sched_event {
    u64 timestamp_ns;
    u64 event_id;
    u32 tgid;
    u32 prev_tid;
    u32 next_tid;
    u32 cpu;
    u32 flags;
};

#endif /* __SCX_COMMON_H__ */
