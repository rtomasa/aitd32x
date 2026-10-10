// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <stdint.h>
#include <stddef.h>

enum { SCREEN_WIDTH=320, SCREEN_HEIGHT=224, GAME_WIDTH=320, GAME_HEIGHT=200,
       GAME_X_OFFSET=0, GAME_Y_OFFSET=12, GAME_HZ=25,
       ANIMATION_HZ=60 }; // Original DOS PIT: 1,193,182 / 19,886 = 60.0011 Hz.
enum Pad { PAD_UP=1, PAD_DOWN=2, PAD_LEFT=4, PAD_RIGHT=8,
           PAD_B=16, PAD_C=32, PAD_A=64, PAD_START=128 };
inline int Min(int a,int b) { return a<b?a:b; }
inline int Max(int a,int b) { return a>b?a:b; }
inline int Clamp(int a,int lo,int hi) { return Max(lo,Min(a,hi)); }
inline uint16_t BE16(const uint8_t *p) { return (uint16_t)((p[0]<<8)|p[1]); }
inline int16_t BS16(const uint8_t *p) { return (int16_t)BE16(p); }
inline uint32_t BE32(const uint8_t *p) { return ((uint32_t)BE16(p)<<16)|BE16(p+2); }
// Native model/animation/camera records have even-aligned word fields. Keep
// the byte readers above for formats which do not provide that guarantee.
inline uint16_t BE16Aligned(const uint8_t *p) {
#if defined(__sh__)
    typedef uint16_t AssetWord __attribute__((may_alias));
    return *(const AssetWord *)p;
#else
    return BE16(p);
#endif
}
inline int16_t BS16Aligned(const uint8_t *p) { return (int16_t)BE16Aligned(p); }
inline uint32_t BE32Aligned(const uint8_t *p) { return ((uint32_t)BE16Aligned(p)<<16)|BE16Aligned(p+2); }
struct Vec3 { int32_t x,y,z; };
struct Point { int32_t x,y; };
struct Rect { int x1,y1,x2,y2; };
struct Asset { const uint8_t *data; uint32_t size,unpacked; uint16_t type,flags; };

// The original 1024-entry FITD Q15 table is generated from its pinned source.
extern const int16_t sine_table[1024];
inline int Sin(int a) { return sine_table[a&1023]; }
inline int Cos(int a) { return sine_table[(a+256)&1023]; }
void Rotate(Vec3 &v,int a,int b,int c);
// Reuse one set of exact FITD table values for each group or camera.
struct Rotation { int sx,cx,sy,cy,sz,cz; unsigned enabled; };
Rotation PrepareRotation(int a,int b,int c);
void Rotate(Vec3 &v,const Rotation &rotation);

#if defined(__sh__)
#define A32X_COLD __attribute__((section(".romcode")))
#else
#define A32X_COLD
#endif
