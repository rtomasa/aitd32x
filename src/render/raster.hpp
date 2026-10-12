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

// Prepared contact geometry fits in the idle gameplay vertex scratch. Triangle
// gradients are independent of the tile and are calculated only once.
struct __attribute__((may_alias)) DepthPrimitive {
    int16_t x[3],y[3];
    int32_t q,dx,dy;
    uint8_t kind,color,material,pad;
};
bool RasterPrepareDepthTriangle(DepthPrimitive &,const Point *,const int *,uint8_t,uint8_t);
A32X_COLD void RasterDepthPrimitive(RasterSurface &,const DepthPrimitive &,Rect,uint16_t *,const uint8_t *mask=nullptr);
// Caller has intersected the primitive's prepared bounds with this tile.
void RasterDepthVisible(RasterSurface &,const DepthPrimitive &,Rect,uint16_t *,const uint8_t *mask=nullptr);
A32X_COLD Rect RasterDepthBounds(const DepthPrimitive &);

A32X_COLD void RasterDepthTriangle(RasterSurface &,const Point *,const int *,Rect,uint16_t *,uint8_t,uint8_t,const uint8_t *mask=nullptr);

void RasterDepthPoint(RasterSurface &,Point,int,int,Rect,uint16_t *,uint8_t,uint8_t,const uint8_t *mask=nullptr);
