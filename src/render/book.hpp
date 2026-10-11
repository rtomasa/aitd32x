// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "render_api.hpp"
unsigned Book_Pages(int book);
void Book_Draw(Renderer &renderer,int book,unsigned page);
A32X_COLD unsigned Book_LayoutPages(unsigned asset);
A32X_COLD void Book_DrawLayout(Renderer &renderer,unsigned asset,unsigned page,uint8_t color=26);
A32X_COLD void Book_DrawText(Renderer &renderer,int x,int y,const char *text,uint8_t color=4,bool center=false);
A32X_COLD unsigned Book_TextWidth(const char *text);
A32X_COLD unsigned Book_TextHeight();
// Pixel widths use original proportional advances; no temporary text/image buffer.
A32X_COLD void Book_DrawClippedText(Renderer &renderer,int x,int y,const char *text,int width,uint8_t color=15,bool center=false,bool ellipsis=true);
A32X_COLD unsigned Book_DrawLines(Renderer &renderer,int x,int y,const char *text,int width,unsigned rows,uint8_t color=15,bool center=false,unsigned skip=0);
