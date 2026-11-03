// SPDX-License-Identifier: GPL-2.0-or-later
// Independent signed-division oracle for ordinary and contact line stepping.
#include "src/render/line.hpp"
#include <cstdio>
#include <cstdlib>
#include <initializer_list>

int main() {
    unsigned seed=0x32a17d06,comparisons=0;
    auto random=[&]() { seed=seed*1664525u+1013904223u;return seed; };
    auto check=[&](int start,int delta,int steps) {
        RasterLineStep value(start,delta,steps);
        for(int t=0;t<=steps;++t) {
            int expected=start+(steps?int(int64_t(delta)*t/steps):0);
            if(value.value!=expected) {
                std::fprintf(stderr,"line (%d,%d,%d) step %d: %d != %d\n",
                             start,delta,steps,t,value.value,expected);
                std::exit(1);
            }
            ++comparisons;value.Advance();
        }
    };
    for(int steps:{0,1,2,3,63,64,319,4096,8192})
        for(int delta:{-65534,-8192,-319,-1,0,1,319,8192,65534})
            for(int start:{-4096,-1,0,1,4096,65535}) check(start,delta,steps);
    for(unsigned i=0;i<4096;++i) {
        int steps=random()%8193,delta=int(random()%131069)-65534;
        check(int(random()%73728)-4096,delta,steps);
    }
    std::printf("%u exact signed line samples passed\n",comparisons);
}
