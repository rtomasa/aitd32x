// SPDX-License-Identifier: GPL-2.0-or-later
#include "../platform/profile.hpp"
#include "../platform/32x/hardware.hpp"
#ifdef PROFILE
// SH7604 manual sections 11.2.6 and 11.3: phi/128, upper byte first.
// A scope must finish within one 16-bit wrap (~356 ms at 23.01 MHz).
static volatile uint8_t *const frt=(volatile uint8_t *)0xFFFFFE10;
static uint32_t elapsed[PROFILE_STAGE_COUNT],calls[PROFILE_STAGE_COUNT];
extern "C" { volatile uint32_t profile_state[3+2*PROFILE_STAGE_COUNT]; }
void Profile_Init() {
    frt[0]=1; // No timer interrupts.
    frt[1]=0; // Never clear FRC on compare match.
    frt[6]=2; // Internal clock / 128.
    frt[2]=0;frt[3]=0;
}
uint16_t Profile_ReadTimer() {
    unsigned high=frt[2];unsigned low=frt[3];
    return (uint16_t)((high<<8)|low);
}
void Profile_Accumulate(ProfileStage stage,uint16_t begin) {
    elapsed[stage]+=(uint16_t)(Profile_ReadTimer()-begin);++calls[stage];
}
void Profile_Publish() {
    // Published only after a completed frame; readers run between emulator slices.
    for(unsigned i=0;i<PROFILE_STAGE_COUNT;++i) {
        profile_state[1+i*2]=elapsed[i];profile_state[2+i*2]=calls[i];
    }
    profile_state[1+2*PROFILE_STAGE_COUNT]=Profile_ReadTimer();
    profile_state[2+2*PROFILE_STAGE_COUNT]=COMM(6);
    ++profile_state[0];
}
#endif
