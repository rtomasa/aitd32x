// SPDX-License-Identifier: GPL-2.0-or-later
#include "../engine/game.hpp"
#include "../engine/startup.hpp"
#include "../platform/platform_api.hpp"
#include "../platform/32x/hardware.hpp"
#include "../platform/32x/frame_stats.hpp"
#include "../platform/profile.hpp"
extern "C" const uint8_t asset_bank[],asset_bank_end[];
static Game game;
static Clock clock_state;
static FrameStats frame_stats;
static unsigned displayed;
// Stable diagnostic layout for emulator / hardware debugger comparison.
extern "C" { volatile int32_t debug_state[32]; }
struct InputSnapshot { uint16_t sequence,pad; };
static InputSnapshot ReadInput() {
    uint16_t first,pad,second;
    do { first=COMM(6);pad=COMM(4);second=COMM(6); } while((first&1) || first!=second);
    return {second,pad};
}
static void Flip() {
    unsigned next=displayed^1;
    VDP_FB=(uint16_t)next;
    while((VDP_FB&1)!=next) { }
    displayed=next;
}
static void InitVideo() {
    while(!(REG16(0x20004000)&0x8000)) { }
    // Packed-pixel, 224 lines on PAL and NTSC. No shift, scaling or line reuse.
    VDP_MODE=1;
    displayed=VDP_FB&1;
    for(int bank=0;bank<2;++bank) {
        for(unsigned i=0;i<256;++i) FRAMEBUFFER[i]=(uint16_t)(0x100+i*160);
        for(unsigned i=256;i<256+SCREEN_WIDTH*SCREEN_HEIGHT/2;++i) FRAMEBUFFER[i]=0;
        Flip();
    }
    game.renderer.target=FRAMEBUFFER+256+GAME_Y_OFFSET*160;
}
static void LoadPalette() {
    while(!(VDP_FB&0x2000)) { } // CRAM writable during blanking.
    for(unsigned i=0;i<256;++i) PALETTE[i]=game.renderer.palette[i];
    game.renderer.palette_changed=false;
}
extern "C" int m_main(void) {
    Platform_SetAssetBank(asset_bank,(uint32_t)(asset_bank_end-asset_bank));
    InitVideo();game.Init();LoadPalette();
    // Slave publishes this after its C entry point, through uncached COMM.
    while(COMM(2)!=0x534C) { }
    unsigned refresh=COMM(7)==50?50:60;
    InputSnapshot initial=ReadInput();
    uint16_t last_toggles=initial.pad>>8;
    clock_state.Init(initial.sequence);
    frame_stats.Init(initial.sequence);
    Profile_Init();
    for(;;) {
        InputSnapshot input=ReadInput();
        int previous_mode=game.mode;
        uint16_t toggles=input.pad>>8;
        game.InputSnapshot(input.pad&255,toggles^last_toggles);last_toggles=toggles;
        // Menu edges follow coherent VBlank input, independently of the
        // fixed 25 Hz world clock and the presentation animation clock.
        game.PresentationInput();
        unsigned elapsed=(uint16_t)(input.sequence-clock_state.last)/2;
        game.StartupAdvance(elapsed*(1500/refresh));
        unsigned ticks=clock_state.Advance(input.sequence,refresh);
        if(ticks) {
            ProfileScope timing(PROFILE_UPDATE);
            for(unsigned i=0;i<ticks;++i) game.Update();
        }
        // Save/load blocks while the world is paused. Discard elapsed wall
        // time before Resume so an input during SRAM I/O cannot fast-forward.
        if(game.resync_clock) { clock_state.Init(ReadInput().sequence);game.resync_clock=false; }
        if(game.mode!=previous_mode) frame_stats.ResetWindow(input.sequence);
        bool game_frame=game.dirty;
        bool stats_changed=frame_stats.Sample(input.sequence,refresh);
        if(game_frame || (game.mode && stats_changed)) {
            {
            ProfileScope timing(PROFILE_FRAME);
            game.renderer.buffer_index=displayed^1;
            game.Draw();
            if(game.renderer.palette_changed) {
                ProfileScope palette(PROFILE_PALETTE);LoadPalette();
            }
            { ProfileScope ui(PROFILE_UI);
              if(game.mode) Renderer_DrawFPS(FRAMEBUFFER+256,frame_stats.fps_tenths,frame_stats.ready);
              else for(unsigned p=0;p<GAME_Y_OFFSET*160;++p) FRAMEBUFFER[256+p]=0;
            }
            { ProfileScope flip(PROFILE_FLIP);Flip(); }
            if(game_frame) frame_stats.Rendered();
            }
            Profile_Publish();
        } else if(game.renderer.palette_changed) {
            // Static startup screens fade through CRAM alone. Their displayed
            // pixels stay valid without another restore, text draw or flip.
            ProfileScope palette(PROFILE_PALETTE);LoadPalette();
        }
        COMM(0)=(uint16_t)((game.mode?0x1000:0x0100)|(game.paused?0x80:0)|(game.camera&15));
        COMM(1)=(uint16_t)game.tick;
        debug_state[0]=(int32_t)game.tick;debug_state[1]=game.camera;
        debug_state[2]=game.player.pos.x;debug_state[3]=game.player.pos.y;debug_state[4]=game.player.pos.z;
        debug_state[5]=game.player.beta;debug_state[6]=game.mode;debug_state[7]=game.paused;
        debug_state[8]=game.character;debug_state[9]=input.sequence;
        debug_state[10]=(int32_t)frame_stats.rendered_total;
        debug_state[11]=frame_stats.ready?(int32_t)frame_stats.fps_tenths:-1;
        debug_state[12]=(int32_t)ticks;
        debug_state[13]=(int32_t)game.player.frame;
        debug_state[14]=(int32_t)game.player.frame_phase;
        debug_state[15]=(int32_t)game.player.anim_asset;
        bool world_active=game.mode || game.startup_phase==STARTUP_ARRIVAL || game.startup_phase==STARTUP_PICTURE || game.startup_phase>=STARTUP_DEATH;
        debug_state[16]=world_active?game.world.floor:0;debug_state[17]=world_active?game.world.room:0;
        debug_state[18]=game.menu;debug_state[19]=world_active?game.world.fault_code:0;
        debug_state[20]=world_active?game.world.fault_life:0;debug_state[21]=world_active?game.world.fault_pc:0;
        debug_state[22]=game.mode?game.world.inventory_count:0;debug_state[23]=game.mode?game.world.in_hand:-1;
        debug_state[24]=game.mode?game.world.prompt:-1;debug_state[25]=game.mode?game.world.peak_active:0;
        debug_state[26]=world_active?game.world.ticks:0;debug_state[27]=game.mode?game.world.vars[90]:game.startup_phase;
        debug_state[28]=game.mode?game.world.vars[21]:0;debug_state[29]=game.mode?game.world.book:-1;
        debug_state[30]=world_active?game.world.finished:0;debug_state[31]=world_active?game.world.camera_target:1;
    }
}
extern "C" void Platform_Fatal(void) {
    COMM(0)=0xE001;
    PALETTE[0]=0;PALETTE[1]=31;
    game.renderer.target=FRAMEBUFFER+256+GAME_Y_OFFSET*160;
    game.renderer.Box(0,0,320,200,0);
    game.renderer.DrawText(40,88,"AITD32X ENGINE ERROR",1);
    game.renderer.DrawText(40,104,"CHECK COMM0 / ASSET BANK",1);
    Flip();for(;;) { }
}
