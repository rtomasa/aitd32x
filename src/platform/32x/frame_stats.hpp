// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "../../engine/types.hpp"

// Count completed game draws over elapsed VBlanks, independently of logic ticks.
// Overlay-only refreshes do not inflate this rate. Sample requests a redraw
// only when the displayed value or its readiness changes.
struct FrameStats {
    uint16_t last_sequence;
    unsigned window_frames,window_draws,rendered_total,fps_tenths;
    bool ready,enabled;
    uint8_t repaint_banks; // One refresh per physical bank after toggling.
    void ResetWindow(uint16_t sequence) {
        last_sequence=sequence;window_frames=window_draws=fps_tenths=0;
        ready=false;
    }
    void Init(uint16_t sequence) { enabled=true;repaint_banks=0;rendered_total=0;ResetWindow(sequence); }
    void Toggle(uint16_t sequence) {
        enabled=!enabled;ResetWindow(sequence);repaint_banks=3;
    }
    void Rendered() { if(enabled) { ++window_draws;++rendered_total; } }
    bool Sample(uint16_t sequence,unsigned refresh) {
        if(!enabled) return false;
        window_frames+=(uint16_t)(sequence-last_sequence)/2;
        last_sequence=sequence;
        if(window_frames<refresh) return false;
        unsigned next=(window_draws*refresh*10+window_frames/2)/window_frames;
        bool changed=!ready || next!=fps_tenths;fps_tenths=next;
        window_frames=window_draws=0;ready=true;
        return changed;
    }
};
