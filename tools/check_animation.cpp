// SPDX-License-Identifier: GPL-2.0-or-later
// Original-data timing checks, independent of the renderer and collision.
#include "../src/engine/game.hpp"
#include "../src/platform/platform_api.hpp"
#include "../assets/resource_ids.h"
#include <cstdio>
#include <cstdlib>
#include <vector>
extern "C" void Platform_Fatal() { std::abort(); }
static void Require(bool ok,const char *message) {
    if(!ok) { std::fprintf(stderr,"%s\n",message);std::exit(1); }
}
int main() {
    FILE *f=std::fopen("assets/bank.bin","rb");Require(f,"missing asset bank");
    std::fseek(f,0,SEEK_END);long size=std::ftell(f);std::rewind(f);
    std::vector<uint8_t> bank(size);Require(std::fread(bank.data(),1,size,f)==(unsigned long)size,"short asset bank");std::fclose(f);
    Platform_SetAssetBank(bank.data(),size);
    struct Case { int character;unsigned animation,ticks,loops;int z; };
    // Durations and displacements measured from original LISTANIM/LISTANI2.
    Case cases[]={{0,player_walk_assets[0],275,6,-8214},
                  {1,player_walk_assets[1],50,1,-1467},
                  {0,player_run_assets[0],25,1,-2049},
                  {1,player_run_assets[1],25,1,-2196}};
    for(const Case &c:cases) {
        Actor a{};Actor_Init(a,c.character);Actor_SetAnimation(a,c.animation);a.beta=0;
        Vec3 sum{};unsigned loops=0,previous=0;
        for(unsigned tick=0;tick<c.ticks;++tick) {
            Vec3 d=Actor_Advance(a);sum.x+=d.x;sum.y+=d.y;sum.z+=d.z;
            if(a.frame<previous)++loops;
            previous=a.frame;
        }
        Require(sum.x==0 && sum.y==0 && sum.z==c.z,"original root displacement changed");
        Require(loops==c.loops && a.frame==0 && a.frame_phase==0,"animation clock lost fractional time across keys/loops");
    }
    Actor a{};Actor_Init(a,0);Actor_SetAnimation(a,player_walk_assets[0]);a.beta=0;
    int z=0;for(unsigned i=0;i<46;++i)z+=Actor_Advance(a).z;
    Require(z==-1378 && a.frame==0 && a.frame_phase==10,"110/60-second cycle rounded at the 25 Hz update boundary");
    // Same ten seconds with irregular rendering intervals and sequence wrap.
    for(unsigned hz:{50u,60u}) {
        Clock clock;clock.Init(65520);unsigned frame=0,ticks=0;
        Actor b{};Actor_Init(b,1);Actor_SetAnimation(b,player_walk_assets[1]);b.beta=0;z=0;
        while(frame<hz*10) {
            unsigned interval=Min(1+(frame*7)%17,hz*10-frame);frame+=interval;
            unsigned pending=clock.Advance((uint16_t)(65520+2*frame),hz);
            ticks+=pending;while(pending--)z+=Actor_Advance(b).z;
        }
        Require(ticks==250 && z==-7335 && b.frame==0 && b.frame_phase==0,"render stalls or PAL/NTSC changed motion over wall time");
    }
    std::puts("60 Hz animation / 25 Hz logic: original cycle lengths and root totals; fractional key crossing; PAL/NTSC catch-up passed");
}
