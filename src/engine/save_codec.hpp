// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "../platform/platform_api.hpp"

// Bounded streaming LZSS: eight flag bits (LSB first), then literal bytes or
// big-endian (distance-1:10, length-3:6) pairs. A set flag means literal.
// No heap or full-save buffer; the same 1 KiB ring serves encode and decode.
struct SaveCodec {
    static constexpr unsigned WINDOW=1024,LOOK=66;
    uint8_t ring[WINDOW],packet[16];
    unsigned position=0,queued=0,packet_bytes=0,tokens=0,flags=0;
    unsigned remaining=0,distance=0,encoded=0,checksum=2166136261u,limit;
    bool reading,measure,ok=true;
    SaveCodec(bool read,bool dry,unsigned size):limit(size),reading(read),measure(dry) {}
    A32X_COLD uint8_t Raw(uint8_t value=0);
    A32X_COLD void Packet();
    A32X_COLD void Encode();
    A32X_COLD uint8_t Byte(uint8_t value);
    A32X_COLD bool Finish();
};
