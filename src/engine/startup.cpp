// SPDX-License-Identifier: GPL-2.0-or-later
#include "../platform/pixel_words.hpp"
#include "game.hpp"
#include "startup.hpp"
#include "save.hpp"
#include "../render/book.hpp"
#include "../platform/platform_api.hpp"
#include "../platform/audio.hpp"
namespace {
constexpr unsigned NONE=255,SECOND=1500,PIT=25;
static A32X_COLD void FadeTo(Game &g,unsigned phase) {
    if(g.startup_next!=NONE) return;
    g.startup_next=(uint8_t)phase;g.startup_transition=g.startup_time;
}
static A32X_COLD unsigned Biography(const Game &g) { return g.character?AS_STARTUP_BIOGRAPHY_1:AS_STARTUP_BIOGRAPHY_0; }
static A32X_COLD const char *StartupText(int id) {
    Asset a=Platform_ReadAsset(AS_STARTUP_TEXT);if(!a.data || a.size<4) return "";
    for(unsigned i=0;i<BE32(a.data);++i) {
        const uint8_t *entry=a.data+4+i*8;
        if(BE16(entry)==(unsigned)id) return (const char*)a.data+BE32(entry+4);
    }
    return "";
}
static A32X_COLD void Palette(Game &g,unsigned level,bool white=false) {
    Asset a=Platform_ReadAsset(g.startup_palette);if(!a.data || a.size!=512) Platform_Fatal();
    for(unsigned i=0;i<256;++i) {
        unsigned c=i?BE16Aligned(a.data+2*i):0;
        uint16_t value=white?0x7fff:(uint16_t)(((c&31)*level/32)|((((c>>5)&31)*level/32)<<5)|((((c>>10)&31)*level/32)<<10));
        if(g.renderer.palette[i]!=value) g.renderer.palette_changed=true;
        g.renderer.palette[i]=value;
    }
}
static A32X_COLD void Portrait(Game &g) {
    g.renderer.FinishRestore();
    int x=g.character?0:160,left=x+10,right=x+148,top=10,bottom=189;
    const uint16_t *source=(const uint16_t *)g.renderer.background;
    for(int y=top;y<=bottom;++y) {
        unsigned first=y*160+left/2;
        PixelCopyWords(g.renderer.target+first,source+first,(right+1)/2-left/2);
        if(!(right&1)) g.renderer.Span(y,right,right,g.renderer.background[y*320+right]);
    }
}
}
A32X_COLD void Game::StartGameplay() {
    Audio_Reset();Actor_Init(player,character);world.Init(player,character);
    mode=1;camera=world.camera;world.view_changed=false;ResetCache();
    menu=selection=action_selection=book_line=0;paused=help=false;action_blocked=true;
    pending_edges=0;startup_phase=STARTUP_GAMEPLAY;startup_next=NONE;dirty=true;resync_clock=true;
}
A32X_COLD void Game::StartupEnter(unsigned phase) {
    renderer.FinishRestore();
    startup_phase=(uint8_t)phase;startup_next=NONE;startup_since=startup_time;startup_fade=0;dirty=true;
    switch(phase) {
    case STARTUP_LOGO:
        Audio_Reset();startup_palette=AS_STARTUP_LOGO_PALETTE;
        if(!renderer.SetImage(AS_STARTUP_LOGO_IMAGE,startup_palette)) Platform_Fatal();
        player.model=Platform_ReadAsset(AS_STARTUP_LOGO_MODEL);player.animation={};player.floor=player.room=0;
        player.alpha=player.beta=player.gamma=0;player.collision_min=player.collision_max={0,0,0};break;
    case STARTUP_FLASH:Audio_Sample(6);break;
    case STARTUP_ROTATE:break;
    case STARTUP_TITLE:startup_palette=AS_TITLE_PALETTE;if(!renderer.SetTitle()) Platform_Fatal();break;
    case STARTUP_CREDITS:
        startup_palette=AS_GAME_PALETTE;book_line=0;
        if(!renderer.SetImage(AS_READ_BACKGROUND_1,startup_palette)) Platform_Fatal();
        break;
    case STARTUP_MENU:
        Audio_Reset();startup_palette=AS_GAME_PALETTE;menu=selection=book_line=0;
        for(auto &pixel:renderer.background) pixel=0;
        renderer.camera=renderer.room=renderer.original_background={};renderer.camera_id=0xffffffffu;
        { BackgroundComposition compose(renderer);renderer.Panel(0,60,AS_UI_STARTUP_MENU); }
        break;
    case STARTUP_CHARACTER:
        startup_palette=AS_GAME_PALETTE;menu=book_line=0;
        if(!renderer.SetImage(AS_STARTUP_SELECTION,startup_palette)) Platform_Fatal();
        break;
    case STARTUP_BIOGRAPHY: {
        book_line=0;
        // Preserve the framed portrait in the existing hidden framebuffer,
        // decode the paper into RAM once, then cache their composed background.
        // Paging and palette fades need no further portrait/frame image blits.
        int x=character?0:160;
        renderer.Panel(x,0,AS_UI_STARTUP_SELECTION);Portrait(*this);
        if(!renderer.SetImage(AS_STARTUP_BACKGROUND,startup_palette)) Platform_Fatal();
        renderer.BakeRegion({x,0,x+159,199});break;
    }
    case STARTUP_ARRIVAL:
        Audio_Reset();Actor_Init(player,character);world.InitIntro(player,character);camera=world.camera;ResetCache();
        startup_palette=AS_GAME_PALETTE;
        if(!renderer.SetCamera(camera,world.floor,world.room)) Platform_Fatal();
        world.view_changed=false;Audio_UpdateMusic(world.music,world.next_music,tick);resync_clock=true;break;
    case STARTUP_PICTURE:if(!renderer.SetImage(AS_STARTUP_PICTURE,AS_GAME_PALETTE)) Platform_Fatal();break;
    case STARTUP_GAMEPLAY:StartGameplay();return;
    default:Platform_Fatal();
    }
    renderer.full_restore[0]=renderer.full_restore[1]=true;
    if(phase!=STARTUP_FLASH && phase!=STARTUP_ROTATE && phase!=STARTUP_PICTURE) Palette(*this,0);
}
A32X_COLD void Game::StartupAdvance(unsigned elapsed) {
    if(startup_phase>=STARTUP_ENDING) { EndingAdvance(elapsed);return; }
    if(startup_phase>=STARTUP_DEATH) { DeathAdvance(elapsed);return; }
    if(mode) { if(world.prompt>=0) PickupAdvance(elapsed);else InventoryAdvance(elapsed);return; }
    if(!elapsed) return;
    startup_time+=elapsed;unsigned age=startup_time-startup_since;
    if(startup_next!=NONE) {
        unsigned age=startup_time-startup_transition;
        if(age>=8*PIT) { StartupEnter(startup_next);return; }
        Palette(*this,startup_fade*(8*PIT-age)/(8*PIT));return;
    }
    if(startup_phase==STARTUP_FLASH) {
        if(startup_fade!=32) Palette(*this,32,true);
        startup_fade=32;
    }
    else {
        unsigned ticks=startup_phase==STARTUP_LOGO?32:16;
        unsigned level=(startup_phase==STARTUP_ROTATE || startup_phase==STARTUP_PICTURE)?32:Min(32,age*32/(ticks*PIT));
        if(level!=startup_fade) Palette(*this,level);
        startup_fade=(uint8_t)level;
    }
    switch(startup_phase) {
    case STARTUP_LOGO:if(age>=(32+180)*PIT) StartupEnter(STARTUP_FLASH);break;
    case STARTUP_FLASH:if(age>=2*PIT) StartupEnter(STARTUP_ROTATE);break;
    case STARTUP_ROTATE:dirty=true;if(age>=142*PIT) FadeTo(*this,STARTUP_TITLE);break;
    case STARTUP_TITLE:if(age>=(16+48)*PIT) FadeTo(*this,STARTUP_CREDITS);break;
    case STARTUP_CREDITS:
        if(age>=5*SECOND) {
            if((unsigned)(book_line+1)<Book_Pages(19)) { ++book_line;startup_since=startup_time;Audio_Sample(49);dirty=true; }
            else FadeTo(*this,STARTUP_MENU);
        }break;
    case STARTUP_PICTURE:
        if(age>=(unsigned)Max(0,world.picture_duration)*PIT) {
            world.picture_id=-1;world.picture_duration=0;startup_phase=STARTUP_ARRIVAL;startup_since=startup_time-16*PIT;
            if(!renderer.SetCamera(world.camera,world.floor,world.room)) Platform_Fatal();
            ResetCache();dirty=true;resync_clock=true;
        }break;
    default:break;
    }
}
A32X_COLD void Game::StartupUpdate(uint16_t edges) {
    if(startup_phase>=STARTUP_ENDING) { EndingUpdate(edges);return; }
    if(startup_phase>=STARTUP_DEATH) { DeathUpdate(edges);return; }
    if(startup_next!=NONE) return;
    if(menu==4) { if(edges) { menu=0;dirty=true; }return; }
    switch(startup_phase) {
    case STARTUP_LOGO:case STARTUP_FLASH:case STARTUP_ROTATE:case STARTUP_TITLE:case STARTUP_CREDITS:
        if(edges) FadeTo(*this,STARTUP_MENU);
        break;
    case STARTUP_MENU: {
        int previous=selection;
        if(edges&PAD_C) character^=1;
        if(edges&PAD_UP) selection=(selection+2)%3;
        if(edges&PAD_DOWN) selection=(selection+1)%3;
        if(previous!=selection) dirty=true;
        if((edges&PAD_B) || ((edges&(PAD_A|PAD_START)) && selection==1)) { if(!Game_Load(*this)) { menu=4;dirty=true; } }
        else if(edges&(PAD_A|PAD_START)) FadeTo(*this,selection==2?STARTUP_LOGO:STARTUP_CHARACTER);
        break;
    }
    case STARTUP_CHARACTER: {
        int previous=character;
        if(edges&PAD_LEFT) character=1;
        if(edges&PAD_RIGHT) character=0;
        if(edges&PAD_C) character^=1;
        if(previous!=character) dirty=true;
        if(edges&PAD_B) FadeTo(*this,STARTUP_MENU);
        else if(edges&(PAD_A|PAD_START)) FadeTo(*this,STARTUP_BIOGRAPHY);
        break;
    }
    case STARTUP_BIOGRAPHY: {
        unsigned pages=Book_LayoutPages(Biography(*this));int previous=book_line;
        if((edges&(PAD_DOWN|PAD_RIGHT)) && (unsigned)(book_line+1)<pages) ++book_line;
        if(edges&(PAD_UP|PAD_LEFT)) book_line=Max(0,book_line-1);
        if(previous!=book_line) { Audio_Sample(49);dirty=true; }
        if(edges&PAD_B) FadeTo(*this,STARTUP_CHARACTER);
        else if(edges&(PAD_A|PAD_START|PAD_C)) {
            if((unsigned)(book_line+1)<pages) { ++book_line;Audio_Sample(49);dirty=true; }
            else FadeTo(*this,STARTUP_ARRIVAL);
        }break;
    }
    case STARTUP_ARRIVAL:
        if(edges&(PAD_A|PAD_B|PAD_C|PAD_START)) { FadeTo(*this,STARTUP_GAMEPLAY);break; }
        world.Update(0,false);camera=world.camera;Audio_UpdateMusic(world.music,world.next_music,tick);dirty=true;
        if(world.fault_code) break;
        if(world.finished) FadeTo(*this,STARTUP_GAMEPLAY);
        else if(world.picture_id>=0) StartupEnter(STARTUP_PICTURE);
        break;
    case STARTUP_PICTURE:if(edges&(PAD_A|PAD_B|PAD_C|PAD_START)) FadeTo(*this,STARTUP_GAMEPLAY);break;
    default:break;
    }
}
A32X_COLD void Game::StartupDraw() {
    if(startup_phase>=STARTUP_ENDING) { EndingDraw();return; }
    if(startup_phase>=STARTUP_DEATH) { DeathDraw();return; }
    Renderer &r=renderer;
    if(startup_phase!=STARTUP_ARRIVAL) r.Restore();
    switch(startup_phase) {
    case STARTUP_ROTATE: {
        unsigned step=Min(142,(startup_time-startup_since)/PIT);int beta=(256-(int)step*8)&1023;
        Vec3 center={0,0,8920+(int)step*50};Rotate(center,-8,0,0);Rotate(center,0,-beta,0);
        Asset room=Platform_ReadAsset(floor_rooms[0][0]);if(!room.data) Platform_Fatal();
        player.pos={center.x-BS16(room.data)*10,center.y+BS16(room.data+2)*10,center.z+BS16(room.data+4)*10};
        uint8_t camera_record[24]={};
        auto word=[&](unsigned offset,unsigned value) { camera_record[offset]=(uint8_t)(value>>8);camera_record[offset+1]=(uint8_t)value; };
        word(0,8);word(2,beta);word(12,128);word(14,500);word(16,490);word(22,24);
        r.camera={camera_record,24,24,4,0};r.room=room;r.Box(0,0,320,141,0);r.DrawActor(player);r.camera=r.room={};break;
    }
    case STARTUP_CREDITS:Book_DrawLayout(r,book_assets[18],book_line);break;
    case STARTUP_MENU:
        r.Box(10,76+selection*16,300,16,100);
        for(int i=0;i<3;++i) Book_DrawText(r,160,76+i*16,i==2?"Replay Intro":StartupText(11+i),i==selection?15:4,true);
        break;
    case STARTUP_CHARACTER:case STARTUP_BIOGRAPHY: {
        int x=character?0:160;
        if(startup_phase==STARTUP_CHARACTER) { r.Panel(x,0,AS_UI_STARTUP_SELECTION);Portrait(*this); }
        if(startup_phase==STARTUP_BIOGRAPHY) {
            Book_DrawLayout(r,Biography(*this),book_line,15);
            if(book_line) Book_DrawText(r,character?172:12,185,"<",15);
            if((unsigned)(book_line+1)<Book_LayoutPages(Biography(*this))) Book_DrawText(r,character?300:140,185,">",15);
        }break;
    }
    case STARTUP_ARRIVAL:
        DrawScene();
        DrawMessages();
        if(world.fault_code) { r.Panel(24,72,AS_UI_STATUS);r.DrawText(40,84,"INTRO SCRIPT ERROR");r.DrawText(40,118,"START:SKIP INTRO"); }
        break;
    default:break;
    }
    Game_DrawSystem(*this);dirty=false;
}
