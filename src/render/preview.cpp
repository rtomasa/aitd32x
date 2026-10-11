// SPDX-License-Identifier: GPL-2.0-or-later
#include "render_api.hpp"
#include "raster.hpp"
#include "divide.hpp"
#include "../../assets/resource_ids.h"

namespace {
// Clip only this presentation path. Gameplay's raster hot loops retain their
// existing full-screen bounds and architecture masks.
static A32X_COLD unsigned Clip(Point *points,unsigned count,Rect rect) {
    Point temporary[MAX_POLY];
    for(unsigned plane=0;plane<4 && count;++plane) {
        unsigned out=0;int edge=plane==0?rect.x1:plane==1?rect.x2:plane==2?rect.y1:rect.y2;
        for(unsigned i=0,j=count-1;i<count;j=i++) {
            Point a=points[j],b=points[i];int av=plane<2?a.x:a.y,bv=plane<2?b.x:b.y;
            bool ain=(plane&1)?av<=edge:av>=edge,bin=(plane&1)?bv<=edge:bv>=edge;
            if(ain!=bin) {
                if(out==MAX_POLY) return 0;
                int d=bv-av;
                temporary[out++]=plane<2?Point{edge,a.y+RenderDivide((b.y-a.y)*(edge-av),d)}:
                                             Point{a.x+RenderDivide((b.x-a.x)*(edge-av),d),edge};
            }
            if(bin) { if(out==MAX_POLY) return 0;temporary[out++]=b; }
        }
        count=out;for(unsigned i=0;i<count;++i) points[i]=temporary[i];
    }
    return count;
}
}
A32X_COLD void Renderer::DrawPreview(int character,int body,int beta,Rect viewport,int distance,int projection_x,int projection_y,Point projection_center) {
    if(body<0 || body>=A32X_MODEL_COUNT) return;
    Actor item={};item.character=character;Actor_SetModel(item,body);
    Actor_Vertices(item,single.vertices);
    const uint8_t *m=item.model.data,*primitives=m+BE32Aligned(m+32);
    unsigned nv=BE16Aligned(m+2),np=BE16Aligned(m+6);
    Vec3 center={0,0,distance};Rotate(center,-60,0,0);Rotate(center,0,-beta,0);
    Rotation rotation=PrepareRotation(60,beta,0);
    int cx=projection_center.x<0?(viewport.x1+viewport.x2)/2:projection_center.x;
    int cy=projection_center.y<0?(viewport.y1+viewport.y2)/2:projection_center.y;
    for(unsigned i=0;i<nv;++i) {
        Vec3 &v=single.vertices[i];v.x+=center.x;v.y+=center.y;v.z+=center.z;
        Rotate(v,rotation);v.z+=128;
        single.projected[i]=v.z>=51?Point{cx+RenderDivide(v.x*projection_x,v.z),cy+RenderDivide(v.y*projection_y,v.z)}:Point{0,0};
    }
    // Share gameplay's stable merge sort and its existing scratch workspace.
    SortFaces(m);
    RasterSurface surface={target,viewport.y1,viewport.y2+1,damage[buffer_index]};
    for(unsigned f=0;f<np;++f) {
        const uint8_t *p=m+BE32Aligned(primitives+ordering.faces[f].index*4);
        surface.material=p[3];
        unsigned n=p[1];Point screen[MAX_POLY];bool near=false;
        for(unsigned j=0;j<n;++j) {
            unsigned index=BE16Aligned(p+6+j*2);if(single.vertices[index].z<51) near=true;
            screen[j]=single.projected[index];
        }
        // No original found-body reaches the near plane at the original
        // inventory or pickup orbit. Reject malformed presentation safely.
        if(near || !n) continue;
        if(p[0]==1) {
            int winding=0;for(unsigned j=1;j+1<n && !winding;++j)
                winding=(screen[j].x-screen[0].x)*(screen[j+1].y-screen[0].y)-(screen[j].y-screen[0].y)*(screen[j+1].x-screen[0].x);
            if(winding<=0) continue;
            Rect bounds={4096,4096,-4096,-4096};
            for(unsigned j=0;j<n;++j) {
                bounds.x1=Min(bounds.x1,screen[j].x);bounds.x2=Max(bounds.x2,screen[j].x);
                bounds.y1=Min(bounds.y1,screen[j].y);bounds.y2=Max(bounds.y2,screen[j].y);
            }
            if(bounds.x2<viewport.x1 || bounds.x1>viewport.x2 || bounds.y2<viewport.y1 || bounds.y1>viewport.y2) continue;
            if(bounds.x1<viewport.x1 || bounds.x2>viewport.x2 || bounds.y1<viewport.y1 || bounds.y2>viewport.y2)
                n=Clip(screen,n,viewport);
            if(n>=3) RasterPrimitive(surface,1,screen,n,p[2],0,p[3]);
        } else if(p[0]==0 && n==2) {
            int dx=screen[1].x-screen[0].x,dy=screen[1].y-screen[0].y,steps=Max(dx<0?-dx:dx,dy<0?-dy:dy);
            for(int j=0;j<=steps;++j) {
                int x=screen[0].x+(steps?RenderDivide(dx*j,steps):0);
                if(x>=viewport.x1 && x<=viewport.x2) RasterSpan(surface,screen[0].y+(steps?RenderDivide(dy*j,steps):0),x,x,p[2]);
            }
        } else {
            int depth=single.vertices[BE16Aligned(p+6)].z;
            int size=p[0]==2?0:p[0]==3?Max(0,RenderDivide(BE16Aligned(p+4)*projection_x,depth)/2):
                     p[0]==7?Max(0,RenderDivide(20*projection_x,depth)/2):1;
            size=Min(120,size);surface.material=p[3];
            for(int y=-size;y<=size;++y) {
                int half=size-(y<0?-y:y)/2;
                RasterSpan(surface,screen[0].y+y,Max(viewport.x1,screen[0].x-half),Min(viewport.x2,screen[0].x+half),p[2]);
            }
        }
    }
    damage[buffer_index]=surface.damage;
}
