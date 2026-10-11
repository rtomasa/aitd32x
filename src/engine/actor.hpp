// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "types.hpp"
enum { MAX_VERTICES=384, MAX_GROUPS=28, MAX_PRIMITIVES=384, MAX_POLY=66 };
// Original model and animation channels are signed words. Keep each live
// bone in that representation: the complete 50-slot original actor pool
// must fit alongside the renderer in 256 KiB of SH2 SDRAM.
struct GroupDelta {
    int16_t x,y,z;
    GroupDelta()=default;
    GroupDelta(int x,int y,int z):x((int16_t)x),y((int16_t)y),z((int16_t)z) {}
    operator Vec3() const { return {x,y,z}; }
};
struct GroupState { int16_t type; GroupDelta delta; };
static_assert(sizeof(GroupState)==8,"Original bone channels must remain compact");
struct Actor {
    Vec3 pos; int alpha,beta,gamma,character;
    int room,floor;
    bool end_frame,end_anim;
    Vec3 collision_min,collision_max;
    Asset model,animation;
    // Animation phase in 1/(ANIMATION_HZ * GAME_HZ) seconds. Keeping the
    // fractional remainder avoids rounding 60/25 at updates or key boundaries.
    unsigned frame,frame_phase,anim_asset;
    GroupState previous[MAX_GROUPS],state[MAX_GROUPS];
    Vec3 last_step;
    bool walking;
};
void Actor_Init(Actor &actor,int character);
void Actor_SetAnimation(Actor &actor,unsigned asset);
void Actor_SetFrame(Actor &actor,unsigned frame);
Vec3 Actor_Advance(Actor &actor,bool repeat=true);
void Actor_SetModel(Actor &actor,int model);
void Actor_Bounds(Actor &actor,int type);
void Actor_Vertices(const Actor &actor,Vec3 *out);
bool Collision_Move(Actor &actor,const Asset &room,Vec3 delta);
bool Camera_Contains(const Asset &camera,int room,int x,int z);

// Gameplay-only scratch; rendering owns a separate workspace.
Vec3 *Actor_GameplayScratch();
