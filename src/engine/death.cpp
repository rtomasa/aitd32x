// SPDX-License-Identifier: GPL-2.0-or-later
#include "game.hpp"
#include "startup.hpp"
#include "save.hpp"
#include "../render/book.hpp"
#include "../platform/platform_api.hpp"
#include "../platform/audio.hpp"
namespace {
constexpr unsigned PIT=25;
static A32X_COLD void DeathPicture(Game &g) {
    // LIFE's picture blocks the original animation clock. Keep that same
    // separation from the 25 Hz world and decode into the existing background.
    if(g.world.picture_id!=12 || !g.renderer.SetImage(AS_DEATH_PICTURE,AS_GAME_PALETTE)) Platform_Fatal();
    g.startup_phase=STARTUP_DEATH_PICTURE;g.startup_since=g.startup_time;
    g.dirty=true;g.resync_clock=true;
}
static A32X_COLD void DeathEnd(Game &g) {
    // GAME_OVER held for 120 original timer ticks before returning to the
    // menu. Retain the last rendered scene/image during this presentation hold.
    g.startup_phase=STARTUP_DEATH_END;g.startup_since=g.startup_time;
    g.world.music=-2;g.world.next_music=-1;
    Audio_UpdateMusic(g.world.music,g.world.next_music,g.tick);
    g.dirty=true;g.resync_clock=true;
}
}
A32X_COLD void Game::StartDeath() {
    // The original player/enemy LIFE has already selected the death animation.
    // Continue that world rather than constructing a second cinematic world.
    mode=0;paused=help=false;menu=selection=action_selection=book_line=0;
    pending_edges=0;action_blocked=true;
    startup_time=startup_since=startup_transition=0;
    startup_phase=STARTUP_DEATH;startup_next=255;startup_fade=32;startup_palette=AS_GAME_PALETTE;
    world.prompt=world.book=-1;camera=world.camera;ResetCache();
    renderer.full_restore[0]=renderer.full_restore[1]=true;
    dirty=true;resync_clock=true;
    if(world.picture_id>=0) DeathPicture(*this);
    else if(world.finished) DeathEnd(*this);
}
A32X_COLD void Game::DeathAdvance(unsigned elapsed) {
    if(mode || !elapsed) return;
    startup_time+=elapsed;
    unsigned age=startup_time-startup_since;
    if(startup_phase==STARTUP_DEATH_PICTURE && age>(unsigned)Max(0,world.picture_duration)*PIT) {
        world.picture_id=-1;world.picture_duration=0;
        if(world.finished) DeathEnd(*this);
        else {
            startup_phase=STARTUP_DEATH;startup_since=startup_time;
            if(!renderer.SetCamera(world.camera,world.floor,world.room)) Platform_Fatal();
            ResetCache();dirty=true;resync_clock=true;
        }
    } else if(startup_phase==STARTUP_DEATH_END && age>=120*PIT) Init(false);
}
A32X_COLD void Game::DeathUpdate(uint16_t edges) {
    if(edges&(PAD_A|PAD_B|PAD_C|PAD_START)) { Init(false);return; }
    if(startup_phase!=STARTUP_DEATH || world.fault_code) return;
    world.Update(0,false);camera=world.camera;
    Audio_UpdateMusic(world.music,world.next_music,tick);dirty=true;
    if(world.picture_id>=0) DeathPicture(*this);
    else if(world.finished) DeathEnd(*this);
}
A32X_COLD void Game::DeathDraw() {
    if(startup_phase==STARTUP_DEATH || (startup_phase==STARTUP_DEATH_END && renderer.camera.data)) {
        DrawScene();
        DrawMessages();
        if(world.fault_code) {
            renderer.Panel(24,72,AS_UI_STATUS);
            Book_DrawText(renderer,40,84,"Cinematic script error",15);
            Book_DrawText(renderer,40,110,"Start: return to title",15);
        }
    } else {
        // Picture and end hold retain a single decoded backdrop. No image
        // decoding, scene jobs, palette traffic or redraws occur while idle.
        renderer.full_restore[renderer.buffer_index]=true;renderer.Restore();
        renderer.damage[renderer.buffer_index]={0,0,319,199};
    }
    Game_DrawSystem(*this);dirty=false;
}
