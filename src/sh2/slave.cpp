// SPDX-License-Identifier: GPL-2.0-or-later
// The slave consumes ordered primitives for its exclusive framebuffer row band.
#include "../platform/32x/hardware.hpp"
#include "../render/worker.hpp"
#include "../platform/profile.hpp"
#include "../platform/audio.hpp"
extern "C" int s_main(void) {
    Profile_Init();
    COMM(2)=0x534C;
    uint16_t last=COMM(6),count=0;
    for(;;) {
        Audio_SlavePoll();RendererWorker_Poll();
        uint16_t now=COMM(6);
        if(!(now&1) && now!=last) { last=now;COMM(3)=++count; }
    }
}
