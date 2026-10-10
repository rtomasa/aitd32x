// SPDX-License-Identifier: GPL-2.0-or-later
#include "platform_api.hpp"
#if defined(__sh__)
#include "32x/hardware.hpp"
static uint16_t Command(uint16_t op,uint16_t arg=0) {
    COMM(1)=arg;COMM(0)=op;
    while(COMM(0)!=0x5FFF) { __asm__ volatile("nop; nop; nop; nop"); }
    return COMM(1);
}
static unsigned read_word,write_word;static bool read_pending,write_pending;
static void Flush() { if(write_pending) { Command(0x5004,write_word<<8);write_pending=false; } }
bool Platform_SaveBegin(unsigned bank) { read_pending=write_pending=false;return Command(0x5001,bank)==0x5341; }
void Platform_SaveSeek(unsigned offset) { Flush();read_pending=false;Command(0x5002,offset); }
uint8_t Platform_SaveRead() {
    if(read_pending) { read_pending=false;return (uint8_t)read_word; }
    read_word=Command(0x5003);read_pending=true;return (uint8_t)(read_word>>8);
}
void Platform_SaveWrite(uint8_t value) {
    if(write_pending) { Command(0x5004,(write_word<<8)|value);write_pending=false; }
    else { write_word=value;write_pending=true; }
}
void Platform_SaveEnd() { Flush();read_pending=false;Command(0x5005); }
#else
// Host diagnostics emulate the same persistent byte store across Game::Init.
static uint8_t sram[131072];static unsigned cursor;
bool Platform_SaveBegin(unsigned bank) { cursor=(bank&1)*65536;return bank<2; }
void Platform_SaveSeek(unsigned offset) { cursor=(cursor&65536)+(offset&65535); }
uint8_t Platform_SaveRead() { return sram[(cursor++)&131071]; }
void Platform_SaveWrite(uint8_t value) { sram[(cursor++)&131071]=value; }
void Platform_SaveEnd() {}
extern "C" const void *host_sram() { return sram; }
#endif
