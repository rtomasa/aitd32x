// SPDX-License-Identifier: GPL-2.0-or-later
// Host-only bound: every active slot contains the largest imported skeleton.
#include "../src/engine/game.hpp"
#include "../src/engine/save.hpp"
#include "../src/platform/platform_api.hpp"
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <cassert>
extern "C" const void *host_sram();
extern "C" void Platform_Fatal() { std::abort(); }
static Game game;
int main() {
    FILE *f=std::fopen("assets/bank.bin","rb");assert(f);std::fseek(f,0,SEEK_END);unsigned size=std::ftell(f);std::rewind(f);
    std::vector<uint8_t> bank(size);assert(std::fread(bank.data(),1,size,f)==size);std::fclose(f);Platform_SetAssetBank(bank.data(),size);
    game.Init();game.mode=1;game.world.Init(game.player,0);World &w=game.world;
    int largest=0,groups=0;for(int i=0;i<A32X_MODEL_COUNT;++i) { Asset a=Platform_ReadAsset(model_assets[0][i]);int n=BE16(a.data+4);if(n>groups) { groups=n;largest=i; } }
    ActiveObject reference=w.active[w.Slot(1)];Actor pose=game.player;Actor_SetModel(pose,largest);pose.frame=pose.frame_phase=0;
    for(auto &o:w.objects) o.v[O_SLOT]=-1;
    for(int i=0;i<MAX_ACTIVE;++i) {
        w.active[i]=reference;int id=i?99+i:1;w.active[i].id=id;w.active[i].value.v[O_SLOT]=i;w.active[i].value.v[O_BODY]=largest;
        w.objects[id]=w.active[i].value;w.poses[i]=pose;
    }
    game.player=pose;assert(Game_Save(game));const uint8_t *s=(const uint8_t *)host_sram();unsigned length=BE32(s+12);assert(length<=16360);
    std::vector<uint8_t> payload(s+24,s+24+length);assert(Game_Load(game));assert(Game_Save(game));assert(std::vector<uint8_t>(s+16384+24,s+16384+24+length)==payload);
    // Incompressible synthetic poses must fail before any committed byte is
    // touched, rather than wrapping the small SRAM or destroying recovery.
    std::vector<uint8_t> previous(s,s+32768);uint32_t random=1;
    for(int k=0;k<MAX_ACTIVE;++k) {
        Actor &actor=w.Pose(k);
        for(unsigned i=0;i<(unsigned)groups;++i) for(unsigned j=0;j<2;++j) {
            GroupState &state=j?actor.state[i]:actor.previous[i];
            int16_t values[4];for(auto &v:values) { random=random*1664525u+1013904223u;v=(int16_t)(random>>16); }
            state.type=values[0];state.delta={values[1],values[2],values[3]};
        }
    }
    assert(!Game_Save(game));assert(std::vector<uint8_t>(s,s+32768)==previous);
    std::printf("{\"active_slots\":%d,\"largest_bones\":%d,\"payload_bytes\":%u,\"journal_capacity\":16360,\"exact_roundtrip\":true,\"overflow_preserves_save\":true}\n",MAX_ACTIVE,groups,length);
}
