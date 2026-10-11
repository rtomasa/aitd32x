// SPDX-License-Identifier: GPL-2.0-or-later
#include "game.hpp"
#include "startup.hpp"
#include "../platform/platform_api.hpp"
#include "../platform/audio.hpp"
namespace {
constexpr unsigned FRAME_TIME=5*25;
static A32X_COLD void ResumeEscape(Game &g) {
    g.mode=1;g.startup_phase=STARTUP_GAMEPLAY;g.world.picture_id=-1;
    // After Pregzt is killed, LIFE intentionally stops changing LIGHT.
    // The escape resumes in daylight rather than retaining the cave mask.
    if(g.world.cvars[12]) g.world.dark=false;
    g.pending_edges=0;g.action_blocked=true;g.ResetCache();
    g.renderer.full_restore[0]=g.renderer.full_restore[1]=true;
    g.dirty=true;g.resync_clock=true;
}
}
A32X_COLD void Game::StartEnding(bool complete) {
    mode=0;menu=selection=action_selection=book_line=0;paused=help=false;
    pending_edges=0;world.prompt=world.book=world.picture_id=-1;
    startup_phase=complete?STARTUP_ENDING_END:STARTUP_ENDING;
    startup_time=startup_since=startup_transition=0;startup_next=255;
    if(complete) {
        world.music=-2;world.next_music=-1;Audio_UpdateMusic(world.music,world.next_music,tick);
    } else if(!renderer.SetImage(ending_frame_assets[0],AS_ENDING_PALETTE)) Platform_Fatal();
    dirty=true;resync_clock=true;
}
A32X_COLD void Game::EndingAdvance(unsigned elapsed) {
    if(!elapsed) return;
    startup_time+=elapsed;
    if(startup_phase==STARTUP_ENDING_END) {
        if(startup_time>=120*25) Init(false);
        return;
    }
    while(startup_time-startup_since>=FRAME_TIME) {
        startup_since+=FRAME_TIME;
        if(++book_line>=A32X_ENDING_FRAME_COUNT) { ResumeEscape(*this);return; }
        Rect changed={320,200,-1,-1};
        if(!Platform_ApplyDelta(Platform_ReadAsset(ending_frame_assets[book_line]),renderer.background,sizeof(renderer.background),changed)) Platform_Fatal();
        // Each physical bank retains its own outstanding changes.
        for(auto &area:renderer.damage)
            area={Min(area.x1,changed.x1),Min(area.y1,changed.y1),Max(area.x2,changed.x2),Max(area.y2,changed.y2)};
        dirty=true;
    }
}
A32X_COLD void Game::EndingUpdate(uint16_t edges) {
    if(!(edges&(PAD_A|PAD_B|PAD_C|PAD_START))) return;
    if(startup_phase==STARTUP_ENDING_END) Init(false);
    else ResumeEscape(*this);
}
A32X_COLD void Game::EndingDraw() {
    if(startup_phase==STARTUP_ENDING_END) { DrawScene();DrawMessages(); }
    else renderer.Restore();
    dirty=false;
}
