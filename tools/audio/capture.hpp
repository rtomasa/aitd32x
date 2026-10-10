// Host-only capture adapter for pinned FITD music driver.
#pragma once
#include <cstdint>
#include <cassert>
#include <cstring>
using u8=uint8_t;using u16=uint16_t;using s16=int16_t;using uint8=uint8_t;using int16=int16_t;
inline uint16_t READ_LE_U16(const uint8_t *p) { return p[0]|(p[1]<<8); }
inline uint32_t READ_LE_U32(const uint8_t *p) { return p[0]|(p[1]<<8)|(p[2]<<16)|(p[3]<<24); }
extern "C" void capture_opl(int reg,int value);
inline void YM3812Write(int,int port,int value) { static int reg; if(!port) reg=value; else capture_opl(reg,value); }
inline void YM3812Init(int,int,int) {}
inline void YM3812UpdateOne(int,int16_t *,int) {}
inline void YM3812Shutdown() {}

#define ASSERT assert
