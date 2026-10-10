// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "raster.hpp"
void RendererWorker_Begin(RasterSurface &);
bool RendererWorker_Submit(unsigned,const Point *,unsigned,uint8_t,int,uint8_t material=0);
void RendererWorker_Finish(RasterSurface &);
void RendererWorker_Poll(); // slave only, executes at most one ordered command.
