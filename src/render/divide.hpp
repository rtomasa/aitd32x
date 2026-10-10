// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <stdint.h>
#ifdef __sh__
__attribute__((noinline))
#endif
static int32_t RenderDivide(int32_t numerator,int32_t denominator) {
#ifdef __sh__
    // Each SH-2 uses its own CPU-local DIVU while rendering its assigned rows.
    // SH7604 10.3.2: signed 32/32 division takes 39 cycles. Explicit nops also
    // model that latency on emulators which calculate DIVU results instantly.
    volatile int32_t *const div=(volatile int32_t *)0xFFFFFF00;
    div[0]=denominator;div[1]=numerator;
    asm volatile(".rept 39\n\tnop\n\t.endr" ::: "memory");
    return div[1];
#else
    return numerator/denominator;
#endif
}
