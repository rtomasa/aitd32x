// SPDX-License-Identifier: GPL-2.0-or-later
#include "../src/engine/game.hpp"
#include "../src/platform/32x/frame_stats.hpp"
#include <cstdio>
int main() {
    const unsigned rates[]={50,60};
    for(unsigned hz:rates) {
        Clock clock;clock.Init(65520);unsigned ticks=0;
        for(unsigned frame=1;frame<=hz*60*20;++frame)
            ticks+=clock.Advance((uint16_t)(65520+2*frame),hz);
        if(ticks!=25*60*20) {
            std::fprintf(stderr,"%u Hz: incorrect tick scheduling or counter wrap\n",hz);
            return 1;
        }
        FrameStats stats;stats.Init(65520);
        clock.Init(65520);
        for(unsigned frame=1;frame<=hz*4;++frame) {
            uint16_t sequence=(uint16_t)(65520+2*frame);
            if(clock.Advance(sequence,hz)) stats.Rendered();
            stats.Sample(sequence,hz);
        }
        if(!stats.ready || stats.fps_tenths!=250 || stats.rendered_total!=100) {
            std::fprintf(stderr,"%u Hz: render FPS is incorrect\n",hz);return 1;
        }
        for(unsigned frame=hz*4+1;frame<=hz*6;++frame)
            stats.Sample((uint16_t)(65520+2*frame),hz);
        if(stats.fps_tenths!=0) {
            std::fprintf(stderr,"idle FPS did not return to zero\n");return 1;
        }
    }
    std::puts("PAL and NTSC: 25 Hz clock with wrap; FPS counts draws, not refresh rate");
}
