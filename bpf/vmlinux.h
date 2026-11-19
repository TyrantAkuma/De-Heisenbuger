/* Minimal vmlinux.h header for Linux 6.12+ sched_ext eBPF programs */
#ifndef __VMLINUX_H__
#define __VMLINUX_H__

typedef unsigned char __u8;
typedef unsigned short __u16;
typedef unsigned int __u32;
typedef unsigned long long __u64;
typedef signed int __s32;
typedef signed long long __s64;

typedef __u8  u8;
typedef __u16 u16;
typedef __u32 u32;
typedef __u64 u64;
typedef __s32 s32;
typedef __s64 s64;

#define BPF_MAP_TYPE_HASH 1
#define BPF_MAP_TYPE_ARRAY 2
#define BPF_MAP_TYPE_RINGBUF 27

#define SCX_DSQ_GLOBAL 0
#define SCX_DSQ_LOCAL 1
#define SCX_SLICE_DFL 5000000ULL /* 5 ms default slice */

#define SCX_ENQ_LOCAL (1ULL << 0)
#define SCX_ENQ_LAST  (1ULL << 1)

#define SEC(name) __attribute__((section(name), used))

struct task_struct {
    __u32 pid;
    __u32 tgid;
    int on_cpu;
    __u64 scx_slice;
    void *scx_dsq;
};

struct sched_ext_ops {
    s32 (*select_cpu)(struct task_struct *p, s32 prev_cpu, u64 wake_flags);
    void (*enqueue)(struct task_struct *p, u64 enq_flags);
    void (*dequeue)(struct task_struct *p, u64 deq_flags);
    void (*dispatch)(s32 cpu, struct task_struct *prev);
    void (*runnable)(struct task_struct *p, u64 enq_flags);
    void (*running)(struct task_struct *p);
    void (*stopping)(struct task_struct *p, bool runnable);
    void (*quiescent)(struct task_struct *p, u64 deq_flags);
    s32 (*init_task)(struct task_struct *p, void *args);
    void (*exit_task)(struct task_struct *p, void *args);
    s32 (*init)(void);
    void (*exit)(void *args);
    char name[64];
};

#endif /* __VMLINUX_H__ */
