// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <stdint.h>
enum ProfileStage { PROFILE_UPDATE, PROFILE_RESTORE, PROFILE_TRANSFORM,
    PROFILE_SORT, PROFILE_PRIMITIVES, PROFILE_FILL, PROFILE_MASK, PROFILE_UI,
    PROFILE_PALETTE, PROFILE_FLIP, PROFILE_FRAME, PROFILE_STAGE_COUNT };
#ifdef PROFILE
void Profile_Init();
uint16_t Profile_ReadTimer();
void Profile_Accumulate(ProfileStage stage,uint16_t begin);
void Profile_Publish();
struct ProfileScope {
    ProfileStage stage;
    uint16_t begin;
    explicit ProfileScope(ProfileStage s):stage(s),begin(Profile_ReadTimer()) {}
    ~ProfileScope() { Profile_Accumulate(stage,begin); }
};
#else
inline void Profile_Init() {}
inline void Profile_Publish() {}
struct ProfileScope { explicit ProfileScope(ProfileStage) {} };
#endif
