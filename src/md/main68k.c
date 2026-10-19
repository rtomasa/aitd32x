// SPDX-License-Identifier: GPL-2.0-or-later
// Controller, SRAM and autonomous YM2612/PSG music supervisor.
#include "common.h"
extern uint16_t read_joypad(uint8_t player);
#define RAM_CODE __attribute__((section(".data")))
static uint32_t music_pointer,music_commands;
static uint16_t pal_audio;static uint8_t frequency_high[6];
static uint16_t fade_frames,fade_length,fade_gain;static uint8_t levels[32];
static uint16_t music_high,music_wait,music_phase,music_active,save_active;
static uint16_t music_bank;
static uint16_t extended_mapper;
#define SSF_CTRL (*(volatile uint16_t *)0xA130F0)
#define SSF_ROM_32X 0xC000 /* protected control write, 32X mode, page 0, ROM read-only */
#define SSF_LAST_ROM_PAGE 29 /* reserve pages 30/31 for the cartridge OS and SRAM */

RAM_CODE void MapperInit(void) {
    volatile uint8_t *rv=(volatile uint8_t *)0xA15107;
    uint8_t previous=*rv;*rv=previous|1;
    uint16_t slot;
    for(slot=1;slot<8;++slot) *(volatile uint16_t *)(0xA130F0+slot*2)=slot;
    // Extended SSF can remap bank 0; standard SSF2 (including PicoDrive)
    // ignores its protected high byte and only disables conventional SRAM.
    // Compare immutable ROM bytes with the same physical page in bank 2.
    SSF_CTRL=0x8002;
    const volatile uint16_t *first=(const volatile uint16_t *)0x001000;
    const volatile uint16_t *second=(const volatile uint16_t *)0x101000;
    extended_mapper=1;
    for(slot=0;slot<128;++slot) if(first[slot]!=second[slot]) { extended_mapper=0;break; }
    SSF_CTRL=SSF_ROM_32X;
    *rv=previous;
}
RAM_CODE void FMWrite(uint16_t port,uint16_t reg,uint16_t value) {
    volatile uint8_t *ym=(volatile uint8_t *)0xA04000;
    while(ym[0]&0x80) { }
    if(reg>=0x40 && reg<=0x4F) { levels[port*16+reg-0x40]=(uint8_t)value;value+=fade_gain;if(value>127) value=127; }
    if(reg>=0xA4 && reg<=0xA6) frequency_high[port*3+reg-0xA4]=(uint8_t)value;
    if(pal_audio && reg>=0xA0 && reg<=0xA2) {
        uint16_t high=frequency_high[port*3+reg-0xA0];
        uint16_t fn=(uint32_t)(((high&7)<<8)|value)*10092/10000;
        FMWrite(port,reg+4,(high&0x38)|(fn>>8));value=fn&255;
    }
    ym[port*2]=(uint8_t)reg;
    ym[port*2+1]=(uint8_t)value;
}
static uint16_t psg_channel;static uint8_t psg_low,psg_levels[4];
RAM_CODE void PSGWrite(uint16_t value) {
    if((value&0x90)==0x90) {
        uint16_t c=(value>>5)&3,v=(value&15);psg_levels[c]=v;
        v+=fade_gain/8;if(v>15) v=15;value=(value&0xF0)|v;
    }
    if(value&0x80) {
        psg_channel=(value>>4)&7;
        if(pal_audio && psg_channel<6 && !(psg_channel&1)) { psg_low=(uint8_t)value;return; }
    } else if(pal_audio && psg_channel<6 && !(psg_channel&1)) {
        uint16_t period=(((value&63)<<4)|(psg_low&15));period=(uint32_t)period*9909/10000;
        if(!period) period=1;
        *(volatile uint8_t *)0xC00011=(psg_low&0xF0)|(period&15);value=period>>4;
    }
    *(volatile uint8_t *)0xC00011=(uint8_t)value;
}
RAM_CODE uint16_t ROMByte(void) {
    uint32_t offset=music_pointer++;
    if(offset<0x80000) return *(volatile uint8_t *)(0x880000+offset);
    uint16_t bank=(uint16_t)(offset>>20);
    // The 68000 music reader alone owns this window. Most consecutive stream
    // bytes share a bank; change its register only when crossing/selecting one.
    if(bank!=music_bank) { *(volatile uint16_t *)0xA15104=bank;music_bank=bank; }
    return *(volatile uint8_t *)(0x900000+(offset&0xFFFFF));
}
RAM_CODE uint32_t ROMLong(void) {
    uint32_t value=0;uint16_t i;for(i=0;i<4;i++) value=(value<<8)|ROMByte();return value;
}
RAM_CODE void MusicSilence(void) {
    uint16_t c,p,r;
    // Key-off alone can leave a converted instrument with RR=0 sounding
    // indefinitely. Explicitly mute every operator on stop/track end.
    for(p=0;p<2;p++) for(r=0;r<16;r++) if((r&3)!=3) FMWrite(p,0x40+r,127);
    for(c=0;c<6;c++) FMWrite(0,0x28,c<3?c:c+1);
    for(c=0;c<4;c++) *(volatile uint8_t *)0xC00011=0x9F|(c<<5);
    music_active=0;
}
RAM_CODE void MusicPump(void) {
    while(music_active && music_commands && !music_wait) {
        uint16_t port=ROMByte(),reg=ROMByte(),value=ROMByte();music_commands--;
        if(port<2) FMWrite(port,reg,value);
        else if(port==2) PSGWrite(value);
        else if(port==4) { MusicSilence();return; }
        if(music_commands) music_wait=ROMByte();else MusicSilence();
    }
}
RAM_CODE void MusicStart(void) {
    MusicSilence();fade_frames=fade_gain=0;(void)ROMLong();music_commands=ROMLong();music_phase=0;
    if(music_commands) { music_active=1;music_wait=ROMByte();MusicPump(); }
}
RAM_CODE void MusicFrame(uint16_t refresh) {
    if(!music_active || save_active) return;
    if(fade_frames) {
        uint16_t previous=fade_gain;fade_frames--;fade_gain=(uint32_t)(fade_length-fade_frames)*127/fade_length;
        if(!fade_frames) { MusicSilence();return; }
        if((fade_frames&3)==0 && fade_gain!=previous) {
            uint16_t p,r;for(p=0;p<2;p++) for(r=0;r<16;r++) if((r&3)!=3) FMWrite(p,0x40+r,levels[p*16+r]);
            for(p=0;p<4;p++) PSGWrite(0x90|(p<<5)|psg_levels[p]);
        }
    }
    music_phase+=294;
    while(music_phase>=refresh*5) {
        music_phase-=refresh*5;if(music_wait) music_wait--;MusicPump();
    }
}
RAM_CODE void ServiceMusic(void) {
    volatile uint16_t *comm=(volatile uint16_t *)MARS_COMM0;
    uint16_t op=comm[0],value=comm[1];
    if(op<0x5010 || op>0x5014) return;
    if(op==0x5010) music_high=value;
    else if(op==0x5011) { music_pointer=((uint32_t)music_high<<16)|value;MusicStart(); }
    else if(op==0x5012) { fade_frames=fade_length=value; }
    else if(op==0x5013) { MusicSilence();fade_gain=fade_frames=0; }
    else if(op==0x5014) value=music_active;
    comm[1]=value;comm[0]=0x5FFF;
}
// Both backends expose 32 KiB on the odd byte lane. Extended SSF places it
// in page 31's upper 256 KiB. Batch two bytes per SH2 exchange, but use two
// byte bus cycles: MiSTer's conventional SRAM has no high byte lane.
// Borrow bank 4 only while RV stalls SH2 cartridge reads, restoring it and
// write protection before acknowledgement. Never write/probe ROM contents.
static uint32_t save_cursor,save_base;
RAM_CODE uint16_t SaveWord(uint16_t value,uint16_t write) {
    volatile uint8_t *rv=(volatile uint8_t *)0xA15107;
    uint8_t previous=*rv;*rv=previous|1;
    if(extended_mapper) {
        SSF_CTRL=write?0xA000:0x8000; // MD access, enable writes only for this word.
        *(volatile uint16_t *)0xA130F8=31;
    } else *(volatile uint8_t *)0xA130F1=write?1:3;
    if(save_cursor+1<save_base+16384) {
        volatile uint8_t *byte=(volatile uint8_t *)((extended_mapper?0x240001:0x200001)+save_cursor*2);
        if(write) { byte[0]=(uint8_t)(value>>8);byte[2]=(uint8_t)value; }
        else value=((uint16_t)byte[0]<<8)|byte[2];
    } else value=0xffff;
    if(extended_mapper) {
        *(volatile uint16_t *)0xA130F8=4;
        SSF_CTRL=SSF_ROM_32X;
    } else *(volatile uint8_t *)0xA130F1=2;
    *rv=previous;
    save_cursor+=2;return value;
}
RAM_CODE void ServiceSave(void) {
    volatile uint16_t *comm=(volatile uint16_t *)MARS_COMM0;
    uint16_t op=comm[0];if(op<0x5001 || op>0x5005) return;
    uint16_t value=comm[1];
    switch(op) {
    case 0x5001:save_active=1;save_base=(uint32_t)(value&1)*16384;save_cursor=save_base;value=0x5341;break;
    case 0x5002:save_cursor=save_base+value;break;
    case 0x5003:value=SaveWord(0,0);break;
    case 0x5004:(void)SaveWord(value,1);break;
    case 0x5005:music_bank=0xffff;save_active=0;break;
    }
    comm[1]=value;comm[0]=0x5FFF;
}
RAM_CODE void ServiceMapper(void) {
    volatile uint16_t *comm=(volatile uint16_t *)MARS_COMM0;
    uint16_t op=comm[0];if(op!=0x5020 && op!=0x5021) return;
    uint16_t bank=op==0x5020?comm[1]:1;
    if(!save_active && bank<=SSF_LAST_ROM_PAGE) {
        // Mapper registers are driven from MD RAM while RV briefly transfers
        // cartridge access to the 68000. SH2 code and audio assets are outside
        // the selected 512 KiB aperture; RV returns before the acknowledgement.
        volatile uint8_t *dreq=(volatile uint8_t *)0xA15107;
        uint8_t previous=*dreq;*dreq=previous|1;
        *(volatile uint8_t *)0xA130F3=(uint8_t)bank;
        *dreq=previous;comm[1]=0x424B;
    } else comm[1]=0;
    comm[0]=0x5FFF;
}
RAM_CODE void main(void) {
    volatile uint16_t *const comm=(volatile uint16_t *)MARS_COMM0;
    volatile uint16_t *const status=(volatile uint16_t *)VDP_CTRL_PORT;
    uint16_t sequence=0;music_bank=0xffff;
    *(volatile uint16_t *)Z80_BUS_REQ=0x100;
    // YM2612 writes require Z80 reset released and its bus granted to 68000.
    *(volatile uint16_t *)Z80_RESET=0x100;
    while(*(volatile uint16_t *)Z80_BUS_REQ&0x100) { }
    MusicSilence();
    uint16_t previous1=0,previous2=0,toggle1=0,toggle2=0;
    comm[7]=(*(volatile uint8_t *)(IO_BASE+1)&0x40)?50:60;
    comm[6]=0;pal_audio=comm[7]==50;
    for(;;) {
        while(*status&8) { ServiceSave();ServiceMusic();ServiceMapper(); }
        while(!(*status&8)) { ServiceSave();ServiceMusic();ServiceMapper(); }
        comm[6]=sequence+1; // Odd = snapshot being written.
        uint16_t pad1=read_joypad(0)&0xFF,pad2=read_joypad(1)&0xFF;
        toggle1^=pad1&~previous1;toggle2^=pad2&~previous2;
        previous1=pad1;previous2=pad2;
        // High byte toggles on each press. A release during a slow render
        // still leaves a detectable press event for the next SH-2 snapshot.
        comm[4]=pad1|(toggle1<<8);
        comm[5]=pad2|(toggle2<<8);
        sequence+=2;
        comm[6]=sequence; // Even = both pads committed.
        MusicFrame(comm[7]);
    }
}
