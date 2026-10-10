// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "../engine/types.hpp"
struct RasterSurface {
    volatile uint16_t *target;
    int first,last; // exclusive last row; both CPUs own disjoint whole rows.
    Rect damage;
    uint8_t material=0;
    volatile uint8_t *coverage=nullptr; // Optional per-pixel bits, disjoint rows.
};
void RasterCoverageSpan(volatile uint8_t *,int,int,int,bool clear=false,uint8_t material=0);
void RasterSpan(RasterSurface &,int,int,int,uint8_t);
void RasterPolygon(RasterSurface &,const Point *,unsigned,uint8_t);
void RasterTriangle(RasterSurface &,const Point *,uint8_t);
void RasterPolygonGeneral(RasterSurface &,const Point *,unsigned,uint8_t);
void RasterPrimitive(RasterSurface &,unsigned,const Point *,unsigned,uint8_t,int,uint8_t material=0);

void RasterDepthTriangle(RasterSurface &,const Point *,const int *,Rect,uint16_t *,uint8_t,uint8_t);

void RasterDepthPoint(RasterSurface &,Point,int,int,Rect,uint16_t *,uint8_t,uint8_t);
