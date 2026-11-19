/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * scx_heisenbug.bpf.c: Linux 6.12+ sched_ext eBPF scheduler for
 * deterministic thread interleaving and race condition reproduction.
 */

#include "vmlinux.h"
#include "scx_common.h"

char _license[] SEC("license") = "GPL";

/* Mock BPF helper stubs for standalone compilation verification */
extern void *bpf_map_lookup_elem(void *map, const void *key) __attribute__((weak));
extern long bpf_map_update_elem(void *map, const void *key, const void *value, u64 flags) __attribute__((weak));
extern void *bpf_ringbuf_reserve(void *ringbuf, u64 size, u64 flags) __attribute__((weak));
extern void bpf_ringbuf_submit(void *data, u64 flags) __attribute__((weak));
extern u64 bpf_ktime_get_ns(void) __attribute__((weak));
extern void scx_bpf_dispatch(struct task_struct *p, u64 dsq_id, u64 slice, u64 enq_flags) __attribute__((weak));
extern struct task_struct *scx_bpf_dsq_pop(u64 dsq_id) __attribute__((weak));
extern u32 scx_bpf_dsq_nr_queued(u64 dsq_id) __attribute__((weak));

/* BPF Maps */

/* Target process TGIDs to monitor */
struct {
    __u32 type;
    __u32 key_size;
    __u32 value_size;
    __u32 max_entries;
} target_pids SEC(".maps") = {
    .type = BPF_MAP_TYPE_HASH,
    .key_size = sizeof(u32),
    .value_size = sizeof(u32),
    .max_entries = SCX_HEISENBUG_MAX_PIDS,
};

/* Scheduler runtime configuration */
struct {
    __u32 type;
    __u32 key_size;
    __u32 value_size;
    __u32 max_entries;
} sched_config SEC(".maps") = {
    .type = BPF_MAP_TYPE_ARRAY,
    .key_size = sizeof(u32),
    .value_size = sizeof(struct sched_config_val),
    .max_entries = 1,
};

/* Pre-computed replay execution plan */
struct {
    __u32 type;
    __u32 key_size;
    __u32 value_size;
    __u32 max_entries;
} replay_plan SEC(".maps") = {
    .type = BPF_MAP_TYPE_ARRAY,
    .key_size = sizeof(u32),
    .value_size = sizeof(u32),
    .max_entries = SCX_HEISENBUG_MAX_REPLAY_EVENTS,
};

/* Ringbuffer for streaming thread switch events to userspace */
struct {
    __u32 type;
    __u32 max_entries;
} events_ringbuf SEC(".maps") = {
    .type = BPF_MAP_TYPE_RINGBUF,
    .max_entries = 16 * 1024 * 1024,
};

/*
 * Bit-for-bit SplitMix64 PRNG generator.
 * Advances state and returns 64-bit pseudo-random value.
 */
static __always_inline u64 splitmix64_next(u64 *state)
{
    u64 z = (*state += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}

/* Check if task is part of monitored TGID */
static __always_inline bool is_monitored_task(struct task_struct *p)
{
    u32 tgid = p->tgid;
    if (!bpf_map_lookup_elem)
        return false;
    u32 *val = (u32 *)bpf_map_lookup_elem(&target_pids, &tgid);
    return val != (void *)0;
}

/* Emit switch event to ringbuffer */
static __always_inline void emit_event(u32 tgid, u32 prev_tid, u32 next_tid, u32 cpu, u64 event_id)
{
    if (!bpf_ringbuf_reserve || !bpf_ringbuf_submit)
        return;

    struct sched_event *ev = (struct sched_event *)bpf_ringbuf_reserve(&events_ringbuf, sizeof(*ev), 0);
    if (!ev)
        return;

    ev->timestamp_ns = bpf_ktime_get_ns ? bpf_ktime_get_ns() : 0;
    ev->event_id = event_id;
    ev->tgid = tgid;
    ev->prev_tid = prev_tid;
    ev->next_tid = next_tid;
    ev->cpu = cpu;
    ev->flags = 0;

    bpf_ringbuf_submit(ev, 0);
}

/* Sched_ext select_cpu: Route monitored threads cleanly */
s32 scx_heisenbug_select_cpu(struct task_struct *p, s32 prev_cpu, u64 wake_flags)
{
    /* Keep affinity stable to observe cache line & store buffer races deterministically */
    return prev_cpu;
}

/* Sched_ext enqueue: Place tasks into target DSQ */
void scx_heisenbug_enqueue(struct task_struct *p, u64 enq_flags)
{
    if (!is_monitored_task(p)) {
        /* Pass-through non-target tasks to default global runqueue */
        if (scx_bpf_dispatch)
            scx_bpf_dispatch(p, SCX_DSQ_GLOBAL, SCX_SLICE_DFL, enq_flags);
        return;
    }

    /* Enqueue into custom Heisenbug DSQ for seed-driven scheduling */
    if (scx_bpf_dispatch)
        scx_bpf_dispatch(p, HEISEN_DSQ_BASE, SCX_SLICE_DFL, enq_flags);
}

/* Sched_ext dispatch: The core deterministic dispatch engine */
void scx_heisenbug_dispatch(s32 cpu, struct task_struct *prev)
{
    u32 key = 0;
    if (!bpf_map_lookup_elem)
        return;

    struct sched_config_val *cfg = (struct sched_config_val *)bpf_map_lookup_elem(&sched_config, &key);
    if (!cfg)
        return;

    if (cfg->mode == SCX_MODE_BYPASS)
        return;

    if (!scx_bpf_dsq_nr_queued || !scx_bpf_dsq_pop || !scx_bpf_dispatch)
        return;

    u32 queued = scx_bpf_dsq_nr_queued(HEISEN_DSQ_BASE);
    if (queued == 0)
        return;

    struct task_struct *selected = (void *)0;

    if (cfg->mode == SCX_MODE_FUZZ) {
        /* Deterministic pseudo-random dispatch using SplitMix64 */
        u64 rand = splitmix64_next(&cfg->prng_state);
        u32 target_idx = (u32)(rand % queued);

        /* Pop chosen task from DSQ */
        for (u32 i = 0; i <= target_idx; i++) {
            struct task_struct *task = scx_bpf_dsq_pop(HEISEN_DSQ_BASE);
            if (!task)
                break;
            if (i == target_idx) {
                selected = task;
            } else {
                /* Put back remaining tasks */
                scx_bpf_dispatch(task, HEISEN_DSQ_BASE, SCX_SLICE_DFL, 0);
            }
        }
    } else if (cfg->mode == SCX_MODE_REPLAY) {
        /* Replay exact pre-planned thread order */
        u32 step = (u32)cfg->current_step;
        u32 *expected_tid = (u32 *)bpf_map_lookup_elem(&replay_plan, &step);
        if (expected_tid) {
            /* Find matching thread in DSQ */
            for (u32 i = 0; i < queued; i++) {
                struct task_struct *task = scx_bpf_dsq_pop(HEISEN_DSQ_BASE);
                if (!task)
                    break;
                if (task->pid == *expected_tid && !selected) {
                    selected = task;
                } else {
                    scx_bpf_dispatch(task, HEISEN_DSQ_BASE, SCX_SLICE_DFL, 0);
                }
            }
            cfg->current_step++;
        }
    }

    if (selected) {
        cfg->event_counter++;
        emit_event(selected->tgid, prev ? prev->pid : 0, selected->pid, (u32)cpu, cfg->event_counter);
        scx_bpf_dispatch(selected, SCX_DSQ_LOCAL, SCX_SLICE_DFL, 0);
    }
}

void scx_heisenbug_running(struct task_struct *p)
{
    /* Hook when task begins running on CPU */
}

void scx_heisenbug_stopping(struct task_struct *p, bool runnable)
{
    /* Hook when task stops running */
}

s32 scx_heisenbug_init(void)
{
    return 0;
}

void scx_heisenbug_exit(void *args)
{
}

/* Link with Linux 6.12+ sched_ext subsystem */
SEC(".struct_ops.link")
struct sched_ext_ops scx_heisenbug_ops = {
    .select_cpu = scx_heisenbug_select_cpu,
    .enqueue    = scx_heisenbug_enqueue,
    .dispatch   = scx_heisenbug_dispatch,
    .running    = scx_heisenbug_running,
    .stopping   = scx_heisenbug_stopping,
    .init       = scx_heisenbug_init,
    .exit       = scx_heisenbug_exit,
    .name       = "scx_heisenbug",
};
