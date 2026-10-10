// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "../../engine/types.hpp"

// Count completed game draws over elapsed VBlanks, independently of logic ticks.
// Overlay-only refreshes on the title or pause screen do not inflate this rate.
struct FrameStats {
    uint16_t last_sequence;
    unsigned window_frames,window_draws,rendered_total,fps_tenths;
    bool ready;
    void ResetWindow(uint16_t sequence) {
        last_sequence=sequence;window_frames=window_draws=fps_tenths=0;
        ready=false;
    }
    void Init(uint16_t sequence) { rendered_total=0;ResetWindow(sequence); }
    void Rendered() { ++window_draws;++rendered_total; }
    bool Sample(uint16_t sequence,unsigned refresh) {
        window_frames+=(uint16_t)(sequence-last_sequence)/2;
        last_sequence=sequence;
        if(window_frames<refresh) return false;
        fps_tenths=(window_draws*refresh*10+window_frames/2)/window_frames;
        window_frames=window_draws=0;ready=true;
        return true;
    }
};
