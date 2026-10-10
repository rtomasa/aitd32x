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
    uint32_t tick,static_signature,dynamic_slots,static_hash[MAX_ACTIVE];
    uint32_t static_slots;
    uint8_t static_rank[MAX_ACTIVE];
    int16_t static_owner[MAX_ACTIVE];
    uint16_t static_quiet_since[MAX_ACTIVE];
    Rect static_bounds[MAX_ACTIVE];
    uint16_t static_span_start[MAX_ACTIVE],static_span_count[MAX_ACTIVE];
    CachedSpan static_spans[3072];
    uint16_t held,pending_edges;
    int mode,camera,character;
    bool paused,help,dirty,resync_clock;
    bool Dynamic(int slot) const { return (dynamic_slots&(1u<<slot))!=0; }
    void ResetCache();
    void RebuildStaticOrder(const int *order,int count);
    void Init();
    void Input(uint16_t pad);
    void InputSnapshot(uint16_t pad,uint16_t pressed) { pending_edges|=pressed;held=pad; }
    void Update();
    void Draw();
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
