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

#ifdef __sh__
__attribute__((noinline))
#endif
static inline int32_t RenderDivideWide(int64_t numerator,int32_t denominator) {
#ifdef __sh__
    // SH7604 10.2/10.3: writing DVDNTL starts signed 64/32 division.
    // Preserve C's truncation (including the existing narrowing cast) for
    // exceptional gradients whose quotient does not fit the hardware result.
    uint64_t magnitude=numerator<0?0-(uint64_t)numerator:(uint64_t)numerator;
    uint32_t divisor=denominator<0?0-(uint32_t)denominator:(uint32_t)denominator;
    // Check before issuing DIVU: some cores saturate without reporting OVF.
    if(magnitude>=((uint64_t)divisor<<31)) return (int32_t)(numerator/denominator);
    volatile int32_t *const div=(volatile int32_t *)0xFFFFFF00;
    div[0]=denominator;div[2]=0;
    div[4]=(int32_t)((uint64_t)numerator>>32);div[5]=(int32_t)numerator;
    asm volatile(".rept 39\n\tnop\n\t.endr" ::: "memory");
    return div[5];
#else
    return (int32_t)(numerator/denominator);
#endif
}
