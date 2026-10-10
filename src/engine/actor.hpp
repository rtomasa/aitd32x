// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "types.hpp"
enum { MAX_VERTICES=384, MAX_GROUPS=40, MAX_PRIMITIVES=384, MAX_POLY=66 };
struct GroupState { int type; Vec3 delta; };
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
