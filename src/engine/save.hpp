// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
struct Game;
// One user slot, two journal copies. Saves contain no pointers or renderer data.
bool Game_Save(Game &game);
bool Game_Load(Game &game);
bool Game_SystemInput(Game &game,unsigned edges);
void Game_DrawSystem(Game &game);
