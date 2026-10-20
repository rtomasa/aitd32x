// SPDX-License-Identifier: GPL-2.0-or-later
// FITD renderer.cpp rotation order: Y, X, Z, using its original Q15 table.
#include "types.hpp"
// SH-2 has no variable arithmetic shift. Bias negative inputs for division's
// truncation toward zero, then sign-extend the high word and rotate bit 15
// into it. The seventeenth quotient bit is retained across the int32_t range.
static inline int TruncateQ15(int value) {
#if defined(__sh__)
    int low_bit;
    __asm__ volatile(
        "cmp/pz %0\n\t"
        "bt 1f\n\t"
        "add %2,%0\n\t"
        "1: mov %0,%1\n\t"
        "shll16 %1\n\t"
        "shll %1\n\t"
        "swap.w %0,%0\n\t"
        "exts.w %0,%0\n\t"
        "rotcl %0"
        : "+r"(value), "=&r"(low_bit) : "r"(32767) : "t");
    return value;
#else
    return value/32768;
#endif
}
void Rotate(Vec3 &v,int a,int b,int c) {
    int x=v.x,y=v.y,z=v.z,t;
    if(b&1023) { t=x; x=TruncateQ15(t*Cos(b)-z*Sin(b)); z=TruncateQ15(t*Sin(b)+z*Cos(b)); }
    if(a&1023) { t=y; y=TruncateQ15(t*Cos(a)-z*Sin(a)); z=TruncateQ15(t*Sin(a)+z*Cos(a)); }
    if(c&1023) { t=x; x=TruncateQ15(t*Cos(c)-y*Sin(c)); y=TruncateQ15(t*Sin(c)+y*Cos(c)); }
    v.x=x;v.y=y;v.z=z;
}
Rotation PrepareRotation(int a,int b,int c) {
    return {Sin(a),Cos(a),Sin(b),Cos(b),Sin(c),Cos(c),
            unsigned((a&1023?1:0)|(b&1023?2:0)|(c&1023?4:0))};
}
void Rotate(Vec3 &v,const Rotation &r) {
    int x=v.x,y=v.y,z=v.z,t;
    if(r.enabled&2) { t=x; x=TruncateQ15(t*r.cy-z*r.sy); z=TruncateQ15(t*r.sy+z*r.cy); }
    if(r.enabled&1) { t=y; y=TruncateQ15(t*r.cx-z*r.sx); z=TruncateQ15(t*r.sx+z*r.cx); }
    if(r.enabled&4) { t=x; x=TruncateQ15(t*r.cz-y*r.sz); y=TruncateQ15(t*r.sz+y*r.cz); }
    v.x=x;v.y=y;v.z=z;
}

void RotateVertices(Vec3 *vertices,unsigned count,const Rotation &r) {
    // Preserve Y, X, Z order and round after each axis, as for one vertex.
    // Select axes and load their coefficients once for the complete range.
    if(r.enabled&2) for(unsigned i=0;i<count;++i) {
        Vec3 &v=vertices[i];int x=v.x,z=v.z;
        v.x=TruncateQ15(x*r.cy-z*r.sy);v.z=TruncateQ15(x*r.sy+z*r.cy);
    }
    if(r.enabled&1) for(unsigned i=0;i<count;++i) {
        Vec3 &v=vertices[i];int y=v.y,z=v.z;
        v.y=TruncateQ15(y*r.cx-z*r.sx);v.z=TruncateQ15(y*r.sx+z*r.cx);
    }
    if(r.enabled&4) for(unsigned i=0;i<count;++i) {
        Vec3 &v=vertices[i];int x=v.x,y=v.y;
        v.x=TruncateQ15(x*r.cz-y*r.sz);v.y=TruncateQ15(x*r.sz+y*r.cz);
    }
}
