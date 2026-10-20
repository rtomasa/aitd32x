// SPDX-License-Identifier: GPL-2.0-or-later
// Isolated diagnostic entry point; never linked into the release cartridge.
#include "../engine/game.hpp"
#include "../platform/32x/hardware.hpp"
#include "../platform/32x/wait.hpp"
#include "../platform/pixel_words.hpp"
#include "../platform/profile.hpp"
#include "../platform/platform_api.hpp"
#include "../platform/audio.hpp"
#include "../render/worker.hpp"
extern "C" const uint8_t asset_bank[],asset_bank_end[];
extern const unsigned char msx[];
extern "C" volatile uint32_t profile_state[],worker_profile_state[];
extern "C" { volatile uint32_t debug_state[32]; }
static Game game;
static unsigned displayed;
static A32X_COLD uint16_t Sequence() { return COMM(6)&~1u; }
static A32X_COLD void Flip() {
    unsigned next=displayed^1;VDP_FB=next;
    SH2WaitMask16(&VDP_FB,1,next);displayed=next;
}
static A32X_COLD void Palette() {
    SH2WaitMask16(&VDP_FB,0x2000,0x2000);
    for(unsigned i=0;i<256;++i) PALETTE[i]=game.renderer.palette[i];
    game.renderer.palette_changed=false;
}
static A32X_COLD void Draw() {
    game.renderer.buffer_index=displayed^1;
    { ProfileScope timing(PROFILE_FRAME);game.Draw();game.renderer.FinishRestore(); }
    if(game.renderer.palette_changed) Palette();
    { ProfileScope timing(PROFILE_FLIP);Flip(); }
}
static A32X_COLD void Wait(unsigned frames) {
    uint16_t begin=Sequence();
    while(unsigned(uint16_t(Sequence()-begin))/2<frames) asm volatile("nop");
}
static A32X_COLD void Text(int y,const char *s) {
    for(unsigned g=0;s[g] && g<39;++g) for(unsigned r=0;r<8;++r) {
        unsigned bits=msx[(unsigned char)s[g]*8+r];
        for(unsigned p=0;p<4;++p)
            FRAMEBUFFER[256+(y+r)*160+2+g*4+p]=
                (((bits>>(7-p*2))&1)<<8)|((bits>>(6-p*2))&1);
    }
}
static A32X_COLD void Number(int y,const char *label,unsigned value) {
    char line[40],digits[12];unsigned n=0,d=0;
    while(*label && n<25) line[n++]=*label++;
    do { digits[d++]='0'+value%10;value/=10; } while(value);
    line[n++]=' ';while(d) line[n++]=digits[--d];line[n]=0;Text(y,line);
}
static A32X_COLD const char *Name(unsigned which) {
    switch(which) {
    case 0:return "LIVE START 25HZ";
    case 1:return "FROZEN START QUIET";
    case 2:return "FROZEN START 2 VOICES";
    case 3:return "FROZEN NEAR QUIET";
    case 4:return "FROZEN NEAR 2 VOICES";
    default:return "FROZEN FLOOR3 ROOM1 CAM3";
    }
}
static A32X_COLD void Report() {
    PixelFillWords(FRAMEBUFFER+256,320*224/2,0);PALETTE[0]=0;PALETTE[1]=0x7fff;
    Text(0,"AITD32X PROFILE V1 - TICKS TOTAL");Text(10,Name(debug_state[1]));
    Number(22,"CASE",debug_state[1]);Number(32,"DRAWS",debug_state[3]);
    Number(42,"VBLANKS",debug_state[4]);Number(52,"FRC ELAPSED",debug_state[5]);
    Number(62,"WORLD UPDATES",debug_state[6]);Number(72,"FAULT",debug_state[7]);
    static const char *const labels[]={"UPDATE","RESTORE SUBMIT","TRANSFORM","SORT",
        "PRIMITIVES INCL FILL","FILL","MASK","UI","PALETTE","FLIP","DRAW INCL STAGES"};
    for(unsigned i=0;i<PROFILE_STAGE_COUNT;++i) Number(84+i*9,labels[i],debug_state[8+i]);
    Number(185,"QUEUE WAIT",debug_state[19]);Number(195,"WORKER END WAIT",debug_state[20]);
    Number(205,"FPS X10",debug_state[21]);
    // Raw one-pixel barcode for lossless remote screenshot collection. The
    // checksum detects captures during a swap or unexpected scaling/filtering.
    for(unsigned b=0;b<1024;b+=2) {
        unsigned a=(debug_state[b/32]>>(31-b%32))&1;
        unsigned c=(debug_state[(b+1)/32]>>(31-(b+1)%32))&1;
        FRAMEBUFFER[256+(216+b/256)*160+2+(b%256)/2]=(a<<8)|c;
    }
    Flip();
}
static A32X_COLD void Setup(unsigned which) {
    game.Init(false);game.StartGameplay();
    if(which==5) {
        World &w=game.world;w.Init(game.player,0,3,1);
        int slot=w.Slot(1);
        if(slot>=0) w.Stage(slot,3,1,{0,0,0});
        else { w.Set(1,O_FLOOR,3);w.Set(1,O_ROOM,1);w.Set(1,O_X,0);w.Set(1,O_Y,0);w.Set(1,O_Z,0); }
        w.floor=3;w.room=1;w.camera=3;w.RefreshActors();game.camera=3;w.view_changed=true;
    } else {
        game.Update();
        if(which==3 || which==4) {
            int slot=game.world.Slot(1);game.world.Stage(slot,0,0,{3231,0,-3733});
            game.player.beta=0;game.world.camera=game.camera=0;
        }
    }
    game.ResetCache();Audio_Reset();game.dirty=true;Draw();
    if(which==2 || which==4) { Audio_Sample(30,-1,-1);Audio_Sample(31,-1,-1); }
}
extern "C" A32X_COLD int m_main(void) {
    Platform_SetAssetBank(asset_bank,(uint32_t)(asset_bank_end-asset_bank));
    SH2WaitMask16(&REG16(0x20004000),0x8000,0x8000);VDP_MODE=1;displayed=VDP_FB&1;
    for(unsigned b=0;b<2;++b) {
        for(unsigned i=0;i<256;++i) FRAMEBUFFER[i]=0x100+i*160;
        PixelFillWords(FRAMEBUFFER+256,320*224/2,0);Flip();
    }
    game.renderer.target=FRAMEBUFFER+256+GAME_Y_OFFSET*160;
    SH2WaitMask16(&COMM(2),0xffff,0x534c);Profile_Init();RendererWorker_Init();
    unsigned hz=COMM(7)==50?50:60;
    for(;;) for(unsigned which=0;which<6;++which) {
        Setup(which);
        uint16_t warm=Sequence();while(unsigned(uint16_t(Sequence()-warm))/2<hz) { game.dirty=true;Draw(); }
        Profile_Reset();for(unsigned i=0;i<6;++i) worker_profile_state[i]=0;
        Clock clock;uint16_t start=Sequence(),last=Profile_ReadTimer();clock.Init(start);
        unsigned draws=0,total=0,updates=0;
        while(unsigned(uint16_t(Sequence()-start))/2<hz*3) {
            if(which==0) {
                unsigned ticks=clock.Advance(Sequence(),hz);
                { ProfileScope timing(PROFILE_UPDATE);for(unsigned t=0;t<ticks;++t) game.Update(); }
                updates+=ticks;
                if(!game.dirty) continue;
            }
            game.dirty=true;Draw();++draws;
            uint16_t now=Profile_ReadTimer();total+=uint16_t(now-last);last=now;
        }
        unsigned vblanks=uint16_t(Sequence()-start)/2;
        Profile_Publish();Audio_StopSamples();
        debug_state[0]=0;debug_state[1]=which;debug_state[2]=hz;debug_state[3]=draws;
        debug_state[4]=vblanks;debug_state[5]=total;debug_state[6]=updates;debug_state[7]=game.world.fault_code;
        for(unsigned i=0;i<PROFILE_STAGE_COUNT;++i) debug_state[8+i]=profile_state[1+i*2];
        debug_state[19]=worker_profile_state[0];debug_state[20]=worker_profile_state[1];
        debug_state[21]=(draws*hz*10+vblanks/2)/vblanks;
        debug_state[22]=game.world.floor;debug_state[23]=game.world.room;debug_state[24]=game.camera;
        debug_state[25]=game.player.pos.x;debug_state[26]=game.player.pos.y;debug_state[27]=game.player.pos.z;
        debug_state[28]=game.tick;debug_state[29]=game.world.ticks;debug_state[30]=0;
        unsigned checksum=0x41333250;for(unsigned i=1;i<31;++i) checksum^=debug_state[i];
        debug_state[31]=checksum;debug_state[0]=0x41333250;
        Report();Wait(hz*8);
    }
}
extern "C" A32X_COLD void Platform_Fatal() {
    Audio_StopSamples();PixelFillWords(FRAMEBUFFER+256,320*224/2,0);PALETTE[1]=0x7fff;
    Text(32,"PROFILE SETUP FAILED");Flip();for(;;) asm volatile("nop");
}
