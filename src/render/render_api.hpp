// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "../engine/actor.hpp"
struct CachedSpan { uint16_t start,length; };
class World;
class Renderer {
public:
    uint8_t background[GAME_WIDTH*GAME_HEIGHT];
    uint16_t palette[256];
    Asset camera,room,original_background;
    volatile uint16_t *target; // Points at logical (0,0); the platform adds (0,12).
    unsigned camera_id;
    unsigned buffer_index;
    bool palette_changed,coverage_mode;
    bool full_restore[2];
    Rect damage[2],last_bounds;
    bool SetCamera(unsigned id,unsigned floor=0,unsigned room_id=0);
    bool SetTitle();
    void Restore();
    void BakeBackground();
    unsigned DrawCachedActor(const Actor &actor,CachedSpan *spans,unsigned capacity);
    void DrawCoverage(const CachedSpan *spans,unsigned count,Rect clip={0,0,319,199});
    void DrawActor(const Actor &a);
    void DrawEffects(const World &world);
    bool ResolveOverlap(const Actor *const *actors,unsigned count,Rect area);
    void DrawText(int x,int y,const char *s,uint8_t color=1);
    void Span(int y,int x1,int x2,uint8_t color);
    void Box(int x,int y,int w,int h,uint8_t color);
    void Panel(int x,int y,unsigned asset);
private:
    struct CompactVertex { int16_t x,y,z,sx,sy; };
    union {
        struct { Vec3 vertices[MAX_VERTICES];Point projected[MAX_VERTICES]; } single;
        CompactVertex combined[768];
    };
    struct Face { unsigned index; int32_t depth; };
    union {
        struct { Face faces[MAX_PRIMITIVES],sort_scratch[MAX_PRIMITIVES]; } ordering;
        uint16_t contact_depth[64*64];
    };
    void Polygon(Point *pts,unsigned count,uint8_t color);
    void Triangle(Point *pts,uint8_t color);
    void PolygonGeneral(Point *pts,unsigned count,uint8_t color);
    void Mask(const Actor &a,Rect bounds);
    bool DrawCompiledActor(const Actor &a);
    volatile uint8_t *CoverageBits();
    void BackgroundSpan(int y,int left,int right,bool original=false);
};
// Presentation-layer overlay. screen points to physical pixel row zero.
void Renderer_DrawFPS(volatile uint16_t *screen,unsigned fps_tenths,bool ready);

// Geometry-only key; conditional camera masks still use the current actor ZV.
uint32_t Renderer_RasterKey(const Actor &actor);

// Shared by drawing and static-cache invalidation.
bool Renderer_MaskActive(const Actor &actor,const uint8_t *camera,const uint8_t *mask);
