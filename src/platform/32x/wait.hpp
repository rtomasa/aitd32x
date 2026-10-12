// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <stdint.h>
#if defined(__sh__)
// Mark the polled address as modified in the delay slot. PicoDrive must keep
// executing these inter-CPU waits rather than treating them as sleep loops.
// The memory clobber also fences command payloads around completion flags.
static inline void SH2WaitEqual32(const volatile uint32_t *address,uint32_t value) {
    uint32_t sample;
    asm volatile("1: mov.l @%0,%1\n\tcmp/eq %2,%1\n\tbf/s 1b\n\tadd #0,%0"
        : "+&r"(address), "=&r"(sample) : "r"(value) : "t","memory");
}
static inline void SH2WaitMask16(const volatile uint16_t *address,uint32_t mask,uint32_t value) {
    uint32_t sample;
    asm volatile("1: mov.w @%0,%1\n\textu.w %1,%1\n\tand %2,%1\n\tcmp/eq %3,%1\n\tbf/s 1b\n\tadd #0,%0"
        : "+&r"(address), "=&r"(sample) : "r"(mask), "r"(value) : "t","memory");
}
static inline void SH2WaitQueue(const volatile uint32_t *read,uint32_t written,uint32_t capacity) {
    uint32_t sample,difference;
    // Subtraction remains unsigned and wrap-safe, like the producer's test.
    asm volatile("1: mov.l @%0,%1\n\tmov %3,%2\n\tsub %1,%2\n\tcmp/hs %4,%2\n\tbt/s 1b\n\tadd #0,%0"
        : "+&r"(read), "=&r"(sample), "=&r"(difference)
        : "r"(written), "r"(capacity) : "t","memory");
}
#endif
