// SPDX-License-Identifier: GPL-2.0-or-later
#include "platform_api.hpp"
static const uint8_t *bank;
static uint32_t bank_size,bank_count;
void Platform_SetAssetBank(const uint8_t *data,uint32_t size) {
    bank=data; bank_size=size; bank_count=0;
    if(size>=16 && BE32(data)==0x41333258 && BE32(data+4)==2 && BE32(data+12)==size) {
        uint32_t n=BE32(data+8);
        if(n<=(size-16)/16) bank_count=n;
    }
}
Asset Platform_ReadAsset(unsigned id) {
    Asset a={0,0,0,0,0};
    if(id>=bank_count) return a;
    const uint8_t *e=bank+16+16*id;
    uint32_t off=BE32(e),size=BE32(e+4);
    if((off&3) || off>bank_size || size>bank_size-off) return a;
    a.data=bank+off; a.size=size; a.unpacked=BE32(e+8);
    a.type=BE16(e+12); a.flags=BE16(e+14);
    return a;
}
bool Platform_Decode(const Asset &a,uint8_t *dest,uint32_t capacity,uint16_t *row_offsets,uint8_t *row_skips) {
    if(!a.data || a.unpacked>capacity) return false;
    if(a.flags==0) {
        if(a.unpacked!=a.size) return false;
        uint32_t i=0;
        if(!(((uintptr_t)a.data|(uintptr_t)dest)&1)) {
            const uint16_t *source=(const uint16_t *)a.data;
            uint16_t *target=(uint16_t *)dest;
            for(;i+8<=a.size;i+=8) {
                *target++=*source++;*target++=*source++;
                *target++=*source++;*target++=*source++;
            }
            for(;i+2<=a.size;i+=2) *target++=*source++;
        }
        for(;i<a.size;++i) dest[i]=a.data[i];
        return true;
    }
    if(a.flags!=1 || (a.size&1)) return false;
    if((row_offsets || row_skips) && (!row_offsets || !row_skips || a.size>65535 || a.unpacked!=GAME_WIDTH*GAME_HEIGHT)) return false;
    uint32_t out=0;
    unsigned row=0;
    for(uint32_t i=0;i<a.size;i+=2) {
        unsigned n=a.data[i];
        if(!n || n>a.unpacked-out) return false;
        // Index each camera row as it is decoded. A row can begin inside a
        // run; retain that run's byte offset and the number of skipped pixels.
        if(row_offsets) while(row<GAME_HEIGHT && row*GAME_WIDTH<out+n) {
            row_offsets[row]=(uint16_t)i;row_skips[row]=(uint8_t)(row*GAME_WIDTH-out);++row;
        }
        uint8_t color=a.data[i+1],*p=dest+out;out+=n;
        if((uintptr_t)p&1) { *p++=color;--n; }
        uint16_t pair=(uint16_t)(color*257u),*words=(uint16_t *)p;
        for(;n>=8;n-=8) { *words++=pair;*words++=pair;*words++=pair;*words++=pair; }
        for(;n>=2;n-=2) *words++=pair;
        if(n) *(uint8_t *)words=color;
    }
    return out==a.unpacked;
}
