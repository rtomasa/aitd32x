// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "../engine/types.hpp"
#include "divide.hpp"

struct RasterLineStep;
static A32X_COLD __attribute__((noinline)) void RasterLineInit(RasterLineStep &,int,int,int);

// Exact start + delta*t/steps with C's signed truncation, including reversed
// lines. Keep the remainder relative to the offset, not the starting value.
// Only a depth slope larger than one needs a division, once at setup.
struct RasterLineStep {
    int value,step,error,remainder,denominator;
    RasterLineStep(int start,int delta,int steps) { RasterLineInit(*this,start,delta,steps); }
    void Advance() {
        value+=step;error+=remainder;
        if(error>=denominator) { ++value;error-=denominator; }
        else if(error<=-denominator) { --value;error+=denominator; }
    }
};

static A32X_COLD void RasterLineInit(RasterLineStep &out,int start,int delta,int steps) {
    int denominator=steps?steps:1,step=0;
    if(delta==denominator) step=1;
    else if(delta==-denominator) step=-1;
    else if(delta>denominator || delta<-denominator) step=RenderDivide(delta,denominator);
    out.value=start;out.step=step;out.error=0;
    out.remainder=delta-step*denominator;out.denominator=denominator;
}
