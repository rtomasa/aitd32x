// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "../engine/types.hpp"
Asset Platform_ReadAsset(unsigned id);
void Platform_SetAssetBank(const uint8_t *data,uint32_t size);
// Optional row metadata indexes 320-pixel camera rows during RLE expansion.
bool Platform_Decode(const Asset &a,uint8_t *dest,uint32_t capacity,
                     uint16_t *row_offsets=nullptr,uint8_t *row_skips=nullptr);
extern "C" void Platform_Fatal(void);
// Sequential cartridge SRAM transport. Each journal bank contains 65536 bytes.
bool Platform_SaveBegin(unsigned bank);
void Platform_SaveSeek(unsigned offset);
uint8_t Platform_SaveRead();
void Platform_SaveWrite(uint8_t value);
void Platform_SaveEnd();
