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
// Scoped raw intro-image access. Bind cameras before mapping; only fixed
// rendering resources outside the aperture may be read until UnmapImage.
A32X_COLD Asset Platform_MapImage(const Asset &a);
A32X_COLD void Platform_UnmapImage();
extern "C" void Platform_Fatal(void);
// Sequential cartridge SRAM transport. Each journal bank contains 65536 bytes.
bool Platform_SaveBegin(unsigned bank);
void Platform_SaveSeek(unsigned offset);
uint8_t Platform_SaveRead();
void Platform_SaveWrite(uint8_t value);
void Platform_SaveEnd();
