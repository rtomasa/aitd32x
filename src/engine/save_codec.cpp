// SPDX-License-Identifier: GPL-2.0-or-later
#include "save_codec.hpp"
uint8_t SaveCodec::Raw(uint8_t value) {
    if(encoded>=limit) { ok=false;return 0; }
    if(reading) value=Platform_SaveRead();
    else if(!measure) Platform_SaveWrite(value);
    ++encoded;checksum=(checksum^value)*16777619u;return value;
}
void SaveCodec::Packet() {
    if(!tokens) return;
    Raw((uint8_t)flags);for(unsigned i=0;i<packet_bytes;++i) Raw(packet[i]);
    packet_bytes=tokens=flags=0;
}
void SaveCodec::Encode() {
    unsigned best=0,back=0,history=position<WINDOW-LOOK?position:WINDOW-LOOK;
    for(unsigned d=1;d<=history;++d) {
        if(ring[(position-d)&(WINDOW-1)]!=ring[position&(WINDOW-1)]) continue;
        unsigned n=1;
        while(n<queued && ring[(position+n-d)&(WINDOW-1)]==ring[(position+n)&(WINDOW-1)]) ++n;
        if(n>best) { best=n;back=d;if(n==queued) break; }
    }
    if(best>=3) {
        unsigned pair=((back-1)<<6)|(best-3);
        packet[packet_bytes++]=(uint8_t)(pair>>8);packet[packet_bytes++]=(uint8_t)pair;
    } else { best=1;flags|=1u<<tokens;packet[packet_bytes++]=ring[position&(WINDOW-1)]; }
    position+=best;queued-=best;if(++tokens==8) Packet();
}
uint8_t SaveCodec::Byte(uint8_t value) {
    if(!ok) return 0;
    if(!reading) {
        ring[(position+queued)&(WINDOW-1)]=value;
        if(++queued==LOOK) Encode();
        return value;
    }
    if(!remaining) {
        if(!tokens) { flags=Raw();tokens=8; }
        bool literal=flags&1;flags>>=1;--tokens;
        if(literal) { value=Raw();ring[position++&(WINDOW-1)]=value;return value; }
        unsigned pair=Raw();pair=(pair<<8)|Raw();
        distance=(pair>>6)+1;remaining=(pair&63)+3;
        if(distance>position || distance>WINDOW) { ok=false;return 0; }
    }
    value=ring[(position-distance)&(WINDOW-1)];ring[position++&(WINDOW-1)]=value;--remaining;return value;
}
bool SaveCodec::Finish() {
    if(reading) return ok && encoded==limit && !remaining && !flags;
    while(queued) Encode();
    Packet();return ok;
}
