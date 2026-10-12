// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <stdint.h>

// Normal framebuffer word/longword writes include black pixels. Never use
// the overwrite mirror here. Both addresses must be aligned for SH2 mov.l.
// Callers supply word-aligned pointers and a count in words. Forward overlap
// is supported only when the source trails by at least two words (four bytes).
typedef uint32_t PixelLong __attribute__((may_alias));
static inline void PixelCopyWords(volatile uint16_t *to,const volatile uint16_t *from,unsigned count) {
    if(((uintptr_t)to^(uintptr_t)from)&2) {
        while(count--) *to++=*from++;
        return;
    }
    if(count && ((uintptr_t)to&2)) { *to++=*from++;--count; }
    volatile PixelLong *out=(volatile PixelLong *)to;
    const volatile PixelLong *in=(const volatile PixelLong *)from;
    for(;count>=8;count-=8) { *out++=*in++;*out++=*in++;*out++=*in++;*out++=*in++; }
    for(;count>=2;count-=2) *out++=*in++;
    if(count) *(volatile uint16_t *)out=*(const volatile uint16_t *)in;
}
static inline void PixelFillWords(volatile uint16_t *to,unsigned count,uint16_t pair) {
    if(count && ((uintptr_t)to&2)) { *to++=pair;--count; }
    uint32_t four=uint32_t(pair)*0x10001u;
    volatile PixelLong *out=(volatile PixelLong *)to;
    for(;count>=8;count-=8) { *out++=four;*out++=four;*out++=four;*out++=four; }
    for(;count>=2;count-=2) *out++=four;
    if(count) *(volatile uint16_t *)out=pair;
}
