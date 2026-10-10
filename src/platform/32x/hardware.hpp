// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <stdint.h>
#define REG16(a) (*(volatile uint16_t *)(a))
#define REG32(a) (*(volatile uint32_t *)(a))
#define COMM(n) REG16(0x20004020+2*(n))
#define VDP_MODE REG16(0x20004100)
#define VDP_FB REG16(0x2000410A)
#define FRAMEBUFFER ((volatile uint16_t *)0x24000000)
#define PALETTE ((volatile uint16_t *)0x20004200)

