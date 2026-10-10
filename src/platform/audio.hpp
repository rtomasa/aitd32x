// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "../engine/types.hpp"
void Audio_Sample(int id,int next=-1,int repeat=0);
void Audio_StopSamples();
void Audio_Reset();
void Audio_Music(int id);
bool Audio_MusicPlaying();
void Audio_UpdateMusic(int &music,int &next,uint32_t tick);
void Audio_SlavePoll();
extern "C" void Audio_PWMInterrupt();
