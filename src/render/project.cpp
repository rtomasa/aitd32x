// SPDX-License-Identifier: GPL-2.0-or-later
#include "project.hpp"

Point RenderProject(const Vec3 &v,int focal_x,int focal_y,Point center,bool clamp) {
#if defined(__sh__)
    int32_t x=v.x*focal_x,y;
    const int32_t lo=clamp?-4096:INT32_MIN,hi=clamp?4096:INT32_MAX;
    volatile int32_t *const div=(volatile int32_t *)0xFFFFFF00;
    // SH7604 10.3.2 requires 39 cycles after starting each divide. Count
    // every scheduled instruction as only one cycle, even loads/multiply/
    // taken branches: cache misses and interrupts can only lengthen this.
    // X: load Y, multiply, fetch MACL + 36 NOPs >=39 cycles.
    // Y: add/compare/branch/compare/branch + 34 NOPs >=39 cycles;
    // optional clamp moves add time. No CPU-local DIVU access intervenes.
    asm volatile(
        "mov.l %3,@%2\n\t"
        "mov.l %0,@(4,%2)\n\t"
        "mov.l @(4,%4),%1\n\t"
        "mul.l %5,%1\n\t"
        "sts macl,%1\n\t"
        ".rept 36\n\tnop\n\t.endr\n\t"
        "mov.l @(4,%2),%0\n\t"
        "mov.l %1,@(4,%2)\n\t"
        "add %6,%0\n\t"
        "cmp/gt %9,%0\n\t"
        "bf 1f\n\t"
        "mov %9,%0\n\t"
        "1: cmp/gt %8,%0\n\t"
        "bt 2f\n\t"
        "mov %8,%0\n\t"
        "2: .rept 34\n\tnop\n\t.endr\n\t"
        "mov.l @(4,%2),%1\n\t"
        "add %7,%1"
        : "+&r"(x), "=&r"(y)
        : "r"(div), "r"(v.z), "r"(&v), "r"(focal_y),
          "r"(center.x), "r"(center.y), "r"(lo), "r"(hi)
        : "macl","t","memory");
    return {x,Clamp(y,lo,hi)};
#else
    Point p={center.x+v.x*focal_x/v.z,center.y+v.y*focal_y/v.z};
    if(clamp) { p.x=Clamp(p.x,-4096,4096);p.y=Clamp(p.y,-4096,4096); }
    return p;
#endif
}
