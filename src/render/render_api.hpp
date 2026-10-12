// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "../engine/actor.hpp"
struct CachedSpan { uint16_t start,length; };
class World;
struct RasterSurface;
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
    A32X_COLD bool SetCamera(unsigned id,unsigned floor=0,unsigned room_id=0,bool load_palette=true);
    bool SetTitle();
    A32X_COLD bool SetImage(unsigned image,unsigned colors);
    A32X_COLD bool DrawImage(unsigned image,int x=0,int y=0,unsigned width=320,unsigned height=200);
    void Restore();
    void FinishRestore(); // Fence before pixel writes, RAM composition or flip.
    A32X_COLD void BakeBackground();
    void RestoreOriginal(Rect area);
    void BakeRegion(Rect area);
    A32X_COLD unsigned DrawCachedActor(const Actor &actor,CachedSpan *spans,unsigned capacity);
    void DrawCoverage(const CachedSpan *spans,unsigned count,Rect clip={0,0,319,199});
    void DrawCachedCoverage(const Actor &actor,const CachedSpan *spans,unsigned count,Rect bounds,Rect clip);
    // True leaves this actor's camera-space vertices/projection in scratch.
    bool DrawActor(const Actor &a);
    // Original item presentation; shares geometry scratch without a world actor.
    A32X_COLD void DrawPreview(int character,int body,int beta,Rect viewport={8,108,151,191},
                               int distance=24000,int projection_x=400,int projection_y=390,
                               Point projection_center={-1,-1});
    void DrawEffects(const World &world);
    bool ResolveOverlap(const Actor *const *actors,unsigned count,Rect area,const Actor *projected=nullptr);
    void DrawText(int x,int y,const char *s,uint8_t color=1);
    void Span(int y,int x1,int x2,uint8_t color);
    void Box(int x,int y,int w,int h,uint8_t color);
    void Panel(int x,int y,unsigned asset);
private:
    struct ContactContext;
    struct CompactVertex { int16_t x,y,z,sx,sy; };
    static_assert(sizeof(CompactVertex)<=sizeof(Vec3),"Contact conversion must trail ordinary vertices");
    union {
        struct { Vec3 vertices[MAX_VERTICES];Point projected[MAX_VERTICES]; } single;
        CompactVertex combined[768];
        // Vertices are dead once contact commands have been prepared. Bounds
        // reuse their storage until CONTACT/END completes, adding no RAM.
        Rect contact_bounds[MAX_VERTICES];
    };
    struct Face { unsigned index; int32_t depth; };
    union {
        struct { Face faces[MAX_PRIMITIVES],sort_scratch[MAX_PRIMITIVES]; } ordering;
        uint16_t contact_depth[64*64];
    };
    void Polygon(Point *pts,unsigned count,uint8_t color);
    void SortFaces(const uint8_t *model);
    void Triangle(Point *pts,uint8_t color);
    void PolygonGeneral(Point *pts,unsigned count,uint8_t color);
    bool Mask(const Actor &a,Rect bounds);
    bool DepthMask(const Actor &a,Rect tile,uint8_t *bits);
    static void ContactWorker(void *,struct RasterSurface &);
    void ContactTiles(const ContactContext &,struct RasterSurface &,uint16_t *depths);
    A32X_COLD void ContactFallback(const Actor *const *,unsigned,Rect,const unsigned *,const bool *);
    A32X_COLD const uint8_t *CompiledProgram(const Actor &a) const;
    void DrawCompiledActor(const Actor &a,const uint8_t *program,bool *masked=nullptr);
    volatile uint8_t *CoverageBits();
    void BackgroundSpan(int y,int left,int right,bool original=false);
};
// Compose fixed presentation pixels in the existing RAM image. Compressed
// panels and glyphs never need a slow framebuffer readback before upload.
class BackgroundComposition {
    Renderer &renderer;
    volatile uint16_t *output;
    Rect previous_damage[2];
public:
    A32X_COLD explicit BackgroundComposition(Renderer &r);
    A32X_COLD ~BackgroundComposition();
    BackgroundComposition(const BackgroundComposition &)=delete;
    BackgroundComposition &operator=(const BackgroundComposition &)=delete;
};
// Presentation-layer overlay. screen points to physical pixel row zero.
void Renderer_DrawFPS(volatile uint16_t *screen,unsigned fps_tenths,bool ready);

// Geometry-only key; conditional camera masks still use the current actor ZV.
uint32_t Renderer_RasterKey(const Actor &actor);

// Shared by drawing and static-cache invalidation.
bool Renderer_MaskActive(const Actor &actor,const uint8_t *camera,const uint8_t *mask);
