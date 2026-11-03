// SPDX-License-Identifier: GPL-2.0-or-later
#include "render_api.hpp"
#include "raster.hpp"
#include "worker.hpp"
#include "divide.hpp"

#if !defined(__sh__)
static unsigned pair_stats[5];
extern "C" unsigned renderer_pair_stats(unsigned field) { return field<5?pair_stats[field]:0; }
#define PAIR_STAT(n) (++pair_stats[n])
#else
#define PAIR_STAT(n) ((void)0)
#endif

unsigned Renderer::PreparePairActor(const Actor &a,unsigned offset,uint16_t *faces,Rect &bounds) {
    const uint8_t *m=a.model.data,*directory=m+BE32Aligned(m+32);
    unsigned count=0;bounds={320,200,-1,-1};
    for(unsigned f=0;f<BE16Aligned(m+6);++f) {
        const uint8_t *p=m+BE32Aligned(directory+f*4);unsigned n=p[1];
        if(!n) continue;
        Rect visible={4096,4096,-4096,-4096};int depth=-32768,winding=0;
        Point first={},previous={};
        for(unsigned v=0;v<n;++v) {
            const CompactVertex &q=combined[offset+BE16Aligned(p+6+v*2)];Point point={q.sx,q.sy};
            depth=Max(depth,q.z);
            visible={Min(visible.x1,point.x),Min(visible.y1,point.y),Max(visible.x2,point.x),Max(visible.y2,point.y)};
            if(!v) first=point;
            else if(v>1 && !winding) winding=(previous.x-first.x)*(point.y-first.y)-(previous.y-first.y)*(point.x-first.x);
            previous=point;
        }
        bool convex=true;
        if(p[0]==1 && n>=3) {
            if(winding<=0) continue;
            // Only proven convex polygons omit their ordinary fill. Other
            // faces keep complete painter coverage underneath contact depth.
            if(n>3) for(unsigned v=0;v<n && convex;++v) {
                unsigned next=v+1==n?0:v+1;
                const CompactVertex &x=combined[offset+BE16Aligned(p+6+v*2)],
                                    &y=combined[offset+BE16Aligned(p+6+next*2)];
                for(unsigned k=0;k<n;++k) {
                    const CompactVertex &z=combined[offset+BE16Aligned(p+6+k*2)];
                    if((y.sx-x.sx)*(z.sy-x.sy)-(y.sy-x.sy)*(z.sx-x.sx)<0) { convex=false;break; }
                }
            }
        }
        else if(p[0]==3 || p[0]==7 || p[0]==6) {
            const CompactVertex &q=combined[offset+BE16Aligned(p+6)];
            int radius=p[0]==6?1:Clamp(RenderDivide((p[0]==3?BE16Aligned(p+4):20)*BS16Aligned(camera.data+14),q.z)/2,0,120);
            visible={visible.x1-radius,visible.y1-radius,visible.x2+radius,visible.y2+radius};
        }
        if(visible.x2<0 || visible.y2<0 || visible.x1>=320 || visible.y1>=200) continue;
        bounds={Min(bounds.x1,Max(0,visible.x1)),Min(bounds.y1,Max(0,visible.y1)),Max(bounds.x2,Min(319,visible.x2)),Max(bounds.y2,Min(199,visible.y2))};
        Face face={f|(convex?0x8000u:0),depth};unsigned j=count++,base=j&~3u;
        while(j>base && ordering.faces[j-1].depth<depth) { ordering.faces[j]=ordering.faces[j-1];--j; }
        ordering.faces[j]=face;
    }
    SortFaceOrder(count);
    for(unsigned i=0;i<count;++i) faces[i]=(uint16_t)ordering.faces[i].index;
    return count;
}

void Renderer::DrawPairActor(const Actor &a,unsigned offset,const uint16_t *faces,unsigned count,Rect bounds,Rect area) {
    const uint8_t *m=a.model.data,*directory=m+BE32Aligned(m+32);
    RasterSurface surface={target,0,GAME_HEIGHT,damage[buffer_index]};surface.deferred=area;
    RendererWorker_Begin(surface);
    for(unsigned f=0;f<count;++f) {
        const uint8_t *p=m+BE32Aligned(directory+(faces[f]&0x7fff)*4);unsigned n=p[1];
        surface.deferred_polygons=(faces[f]&0x8000)!=0;
        Point points[MAX_POLY];
        for(unsigned v=0;v<n;++v) { const CompactVertex &q=combined[offset+BE16Aligned(p+6+v*2)];points[v]={q.sx,q.sy}; }
        if(p[0]==1 && n>=3 && surface.deferred_polygons) {
            bool contained=true;
            for(unsigned v=0;v<n;++v) if(points[v].x<area.x1 || points[v].x>area.x2 || points[v].y<area.y1 || points[v].y>area.y2) { contained=false;break; }
            if(contained) continue;
        }
        const CompactVertex &q=combined[offset+BE16Aligned(p+6)];
        int size=p[0]==3?Max(0,RenderDivide(BE16Aligned(p+4)*BS16Aligned(camera.data+14),q.z)/2):
                 p[0]==7?Max(0,RenderDivide(20*BS16Aligned(camera.data+14),q.z)/2):1;
        size=Min(120,size);
        if(RendererWorker_Submit(p[0],points,n,p[2],size,p[3],surface.deferred_polygons)) RasterPrimitive(surface,p[0],points,n,p[2],size,p[3]);
    }
    RendererWorker_Finish(surface);damage[buffer_index]=surface.damage;
    last_bounds=bounds;
    Mask(a,bounds);
}

bool Renderer::TryDrawContactPair(const Actor &first,const Actor &second,Rect *bounds,Rect guard) {
    PAIR_STAT(0);
    if(coverage_mode || !camera.data || !first.model.data || !second.model.data) return false;
    // Prepared color programs already avoid ordinary geometry work.
    if(CompiledProgram(first) || CompiledProgram(second)) return false;
    unsigned split=BE16Aligned(first.model.data+2),vertices=split+BE16Aligned(second.model.data+2);
    if(vertices>768) return false;
    bool near=false;
    ContactVertices(first,0,false,near);ContactVertices(second,split,false,near);
    // Compact Z must also be exact for the ordinary painter sort/radii.
    for(unsigned v=0;v<vertices;++v) if(combined[v].z==32767) near=true;
    if(near) { PAIR_STAT(2);return false; }
    uint16_t faces[2][MAX_PRIMITIVES];
    unsigned counts[2]={PreparePairActor(first,0,faces[0],bounds[0]),PreparePairActor(second,split,faces[1],bounds[1])};
    for(unsigned i=0;i<2;++i) if(guard.x1<=guard.x2 && guard.y1<=guard.y2 &&
        bounds[i].x1<=guard.x2 && bounds[i].x2>=guard.x1 && bounds[i].y1<=guard.y2 && bounds[i].y2>=guard.y1) return false;
    Rect area={Max(bounds[0].x1,bounds[1].x1),Max(bounds[0].y1,bounds[1].y1),Min(bounds[0].x2,bounds[1].x2),Min(bounds[0].y2,bounds[1].y2)};
    if(area.x1>area.x2 || area.y1>area.y2) { PAIR_STAT(3);return false; }
    // Validate the complete depth program before omitting any ordinary pixels.
    DepthPrimitive *commands=(DepthPrimitive *)Actor_GameplayScratch();unsigned total=0;
    constexpr unsigned capacity=sizeof(Vec3)*MAX_VERTICES/sizeof(DepthPrimitive);
    uint16_t ends[2];
    if(!ContactModel(first,0,area,commands,total,capacity)) { PAIR_STAT(4);return false; }
    ends[0]=(uint16_t)total;
    if(!ContactModel(second,split,area,commands,total,capacity)) { PAIR_STAT(4);return false; }
    ends[1]=(uint16_t)total;
    FinishRestore();
    DrawPairActor(first,0,faces[0],counts[0],bounds[0],area);
    DrawPairActor(second,split,faces[1],counts[1],bounds[1],area);
    const Actor *actors[]={&first,&second};
    DrawContactCommands(actors,2,area,commands,total,ends);
    PAIR_STAT(1);return true;
}
