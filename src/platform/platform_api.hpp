// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "../engine/types.hpp"
Asset Platform_ReadAsset(unsigned id);
void Platform_SetAssetBank(const uint8_t *data,uint32_t size);
// Optional row metadata indexes 320-pixel camera rows during RLE expansion.
bool Platform_Decode(const Asset &a,uint8_t *dest,uint32_t capacity,
                     uint16_t *row_offsets=nullptr,uint8_t *row_skips=nullptr);
// Decode immutable presentation pixels directly into packed framebuffer words.
// The destination starts on an even pixel; rows can have a wider stride.
A32X_COLD bool Platform_Blit(const Asset &a,volatile uint16_t *dest,unsigned width,
                             unsigned height,unsigned stride=GAME_WIDTH);
// Scoped raw camera-image access. Complete banks keep every fixed resource
// outside the aperture and can retain a page between draws. Legacy banks
// restore bank 1; neither form keeps mapped pointers across page changes.
A32X_COLD Asset Platform_MapImage(const Asset &a);
A32X_COLD void Platform_UnmapImage();
// Offline-compiled ending deltas update only changed pixels in the RAM image.
A32X_COLD bool Platform_ApplyDelta(const Asset &a,uint8_t *dest,uint32_t capacity,Rect &damage);
extern "C" void Platform_Fatal(void);
// Sequential cartridge SRAM transport. Each journal bank contains 65536 bytes.
bool Platform_SaveBegin(unsigned bank);
void Platform_SaveSeek(unsigned offset);
uint8_t Platform_SaveRead();
void Platform_SaveWrite(uint8_t value);
void Platform_SaveEnd();
