// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "../render/render_api.hpp"
#include "world.hpp"
struct Game {
    Renderer renderer;
    Actor player;
    World world;
    int menu,selection,action_selection,book_line;
    bool action_blocked;
    uint32_t tick,static_signature,static_hash[MAX_ACTIVE];
    uint64_t dynamic_slots;
    uint64_t static_slots;
    uint8_t static_rank[MAX_ACTIVE];
    int16_t static_owner[MAX_ACTIVE];
    uint16_t static_quiet_since[MAX_ACTIVE];
    Rect static_bounds[MAX_ACTIVE];
    uint16_t static_span_start[MAX_ACTIVE],static_span_count[MAX_ACTIVE];
    CachedSpan static_spans[3072];
    uint16_t held,pending_edges;
    int mode,camera,character;
    bool paused,help,dirty,resync_clock;
    bool inventory_dirty,lighting_dark;
    // Presentation time is in 1/1500 s, independent of the 25 Hz world.
    uint32_t startup_time,startup_since,startup_transition;
    uint16_t startup_palette;
    uint8_t startup_phase,startup_next,startup_fade;
    bool Dynamic(int slot) const { return (dynamic_slots&(uint64_t(1)<<slot))!=0; }
    void ResetCache();
    void RebuildStaticOrder(const int *order,int count);
    void Init(bool boot=true);
    void Input(uint16_t pad);
    void InputSnapshot(uint16_t pad,uint16_t pressed) { pending_edges|=pressed;held=pad; }
    A32X_COLD void PresentationInput();
    A32X_COLD bool HandlePresentationInput(uint16_t edges);
    void Update();
    void DrawScene();
    A32X_COLD void DrawMessages();
    A32X_COLD Rect PrepareLighting(const int *order,int count,Point &center);
    A32X_COLD void DrawLighting(Rect restored,Rect light,Point center);
    void Draw();
    A32X_COLD void StartupEnter(unsigned phase);
    A32X_COLD void StartupAdvance(unsigned elapsed);
    A32X_COLD void StartupUpdate(uint16_t edges);
    A32X_COLD void StartupDraw();
    A32X_COLD void StartGameplay();
    A32X_COLD void InventoryEnter();
    A32X_COLD void InventoryUpdate(uint16_t edges);
    A32X_COLD void InventoryAdvance(unsigned elapsed);
    A32X_COLD void InventoryDraw();
    A32X_COLD void PickupEnter();
    A32X_COLD void PickupAdvance(unsigned elapsed);
    A32X_COLD void PickupUpdate(uint16_t edges);
    A32X_COLD void PickupDraw();
    A32X_COLD void StartDeath();
    A32X_COLD void DeathUpdate(uint16_t edges);
    A32X_COLD void DeathAdvance(unsigned elapsed);
    A32X_COLD void DeathDraw();
    A32X_COLD void StartEnding(bool complete=false);
    A32X_COLD void EndingUpdate(uint16_t edges);
    A32X_COLD void EndingAdvance(unsigned elapsed);
    A32X_COLD void EndingDraw();
};
// Region-independent fixed-tick scheduler. A frame counter is measured by MD.
struct Clock {
    unsigned phase;
    uint16_t last;
    void Init(uint16_t frame) { phase=0;last=frame; }
    unsigned Advance(uint16_t sequence,unsigned hz) {
        unsigned elapsed=(uint16_t)(sequence-last)/2;last=sequence;
        phase+=elapsed*GAME_HZ;unsigned ticks=phase/hz;phase%=hz;return ticks;
    }
};
