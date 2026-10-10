// SPDX-License-Identifier: GPL-2.0-or-later
#include "render_api.hpp"
#include "../engine/world.hpp"
#include "divide.hpp"
#include "raster.hpp"
#include "worker.hpp"
#include "../platform/platform_api.hpp"
#include "../platform/profile.hpp"
#ifndef AITD_RESOURCE_IDS
#define AITD_RESOURCE_IDS "../../assets/resource_ids.h"
#endif
#include AITD_RESOURCE_IDS
extern const unsigned char msx[];
static uint16_t Pair(uint8_t left,uint8_t right) {
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    return (uint16_t)(left|((unsigned)right<<8));
#else
    return (uint16_t)(((unsigned)left<<8)|right);
#endif
}
bool Renderer_MaskActive(const Actor &a,const uint8_t *camera,const uint8_t *mask) {
    int x1=(a.collision_min.x+a.pos.x)/10,x2=(a.collision_max.x+a.pos.x)/10;
    int z1=(a.collision_min.z+a.pos.z)/10,z2=(a.collision_max.z+a.pos.z)/10;
    const uint8_t *tests=camera+BE32(mask+4);
    for(unsigned t=0;t<BE16(mask);++t) {
        const uint8_t *b=tests+t*8;
        if(x1>=BS16(b) && z1>=BS16(b+2) && x2<=BS16(b+4) && z2<=BS16(b+6)) return true;
    }
    return false;
}
uint32_t Renderer_RasterKey(const Actor &a) {
    uint32_t key=2166136261u;
    const int values[]={(int)(a.model.data-Platform_ReadAsset(AS_GAME_PALETTE).data),
        a.floor,a.room,a.pos.x,a.pos.y,a.pos.z,a.alpha,a.beta,a.gamma};
    for(int v:values) key=(key^(uint32_t)v)*16777619u;
    return key;
}
#ifndef AITD_RASTER_BUILD
bool Renderer::DrawCompiledActor(const Actor &a) {
    // Skeletons and arbitrary moved poses always use the regular renderer.
    if(BE16(a.model.data+4)) return false;
    Asset asset=Platform_ReadAsset(AS_STATIC_RASTERS);
    if(!asset.data || asset.size<4 || !BE32(asset.data)) return false;
    uint32_t key=Renderer_RasterKey(a);
    unsigned left=0,right=BE32(asset.data);
    while(left<right) {
        unsigned mid=(left+right)/2;const uint8_t *entry=asset.data+4+mid*12;
        unsigned view=BE32(entry),pose=BE32(entry+4);
        if(view<camera_id || (view==camera_id && pose<key)) left=mid+1;
        else right=mid;
    }
    if(left==BE32(asset.data)) return false;
    const uint8_t *entry=asset.data+4+left*12;
    if(BE32(entry)!=camera_id || BE32(entry+4)!=key) return false;
    const uint8_t *program=asset.data+BE32(entry+8);
    Rect bounds={BS16(program),BS16(program+2),BS16(program+4),BS16(program+6)};
    RasterSurface surface={target,0,GAME_HEIGHT,damage[buffer_index]};
    if(coverage_mode) {
        surface.coverage=CoverageBits();
        volatile uint16_t *words=(volatile uint16_t *)surface.coverage;
        for(unsigned i=0;i<4000;++i) words[i]=0;
    }
    unsigned count=BE32(program+8);program+=12;
    for(unsigned i=0;i<count;++i,program+=6) {
        unsigned start=BE16(program);int y=start/320,x=start-y*320;
        RasterSpan(surface,y,x,x+BE16(program+2)-1,program[4]);
    }
    damage[buffer_index]=surface.damage;last_bounds=bounds;Mask(a,bounds);
    return true;
}
#endif
bool Renderer::SetCamera(unsigned id,unsigned floor,unsigned room_id) {
    if(floor>=A32X_FLOOR_COUNT || id>=camera_counts[floor] || room_id>=room_counts[floor]) return false;
    coverage_mode=false;
    camera=Platform_ReadAsset(floor_cameras[floor][id]);room=Platform_ReadAsset(floor_rooms[floor][room_id]);
    Asset bg=Platform_ReadAsset(floor_backgrounds[floor][id]),pal=Platform_ReadAsset(AS_GAME_PALETTE);
    if(!camera.data || !room.data || pal.size!=512 || bg.unpacked!=sizeof(background) || bg.flags!=0) return false;
    // Camera images are raw; masks can read their rows directly from ROM.
    if(!Platform_Decode(bg,background,sizeof(background))) return false;
    original_background=bg;
    for(unsigned i=0;i<256;++i) {
        uint16_t color=i?BE16(pal.data+i*2):0;
        if(palette[i]!=color) palette_changed=true;
        palette[i]=color;
    }
    camera_id=(floor<<8)|id;
    full_restore[0]=full_restore[1]=true;
    return true;
}
bool Renderer::SetTitle() {
    coverage_mode=false;
    Asset bg=Platform_ReadAsset(AS_TITLE),pal=Platform_ReadAsset(AS_TITLE_PALETTE);
    if(pal.size!=512 || bg.unpacked!=sizeof(background) || !Platform_Decode(bg,background,sizeof(background))) return false;
    for(unsigned i=0;i<256;++i) palette[i]=BE16(pal.data+i*2);
    palette[0]=0;full_restore[0]=full_restore[1]=true;palette_changed=true;
    return true;
}
void Renderer::Restore() {
    ProfileScope timing(PROFILE_RESTORE);
    // Word writes can write palette index zero. Byte writes of zero on the 32X
    // framebuffer are transparent and cannot restore a black background pixel.
    const uint16_t *source=(const uint16_t *)background;
    if(full_restore[buffer_index]) {
        for(unsigned i=0;i<sizeof(background)/2;i+=4) {
            target[i]=source[i];target[i+1]=source[i+1];
            target[i+2]=source[i+2];target[i+3]=source[i+3];
        }
        full_restore[buffer_index]=false;
    } else {
        const Rect &d=damage[buffer_index];
        for(int y=d.y1;y<=d.y2;++y) for(int x=d.x1/2;x<=d.x2/2;++x) {
            int i=y*160+x;target[i]=source[i];
        }
    }
    damage[buffer_index]={320,200,-1,-1};
}
void Renderer::BakeBackground() {
    // FITD's background incrustation: static actors become part of the restore
    // image. Finish the slave queue before reading this framebuffer back.
    uint16_t *destination=(uint16_t *)background;
    // SetCamera already supplied the untouched pixels. Copy back only the
    // words covered by static drawing, including masks and black pixels.
    const Rect &d=damage[buffer_index];
    if(d.x1<=d.x2 && d.y1<=d.y2) for(int y=d.y1;y<=d.y2;++y) {
        unsigned first=y*160+d.x1/2,last=y*160+d.x2/2;
        for(unsigned i=first;i<=last;++i) destination[i]=target[i];
    }
    damage[buffer_index]={320,200,-1,-1};
    full_restore[buffer_index]=false;full_restore[buffer_index^1]=true;
}
volatile uint8_t *Renderer::CoverageBits() {
    uintptr_t address=(uintptr_t)contact_depth;
#if defined(__sh__)
    address|=0x20000000u;
#endif
    return (volatile uint8_t *)address;
}
unsigned Renderer::DrawCachedActor(const Actor &actor,CachedSpan *spans,unsigned capacity) {
    // The normal colored draw records its silhouette in sort scratch after
    // face indices have moved to the stack. No second monochrome draw/readback.
    coverage_mode=true;DrawActor(actor);coverage_mode=false;
    Rect bounds=last_bounds;
    bounds={Max(0,bounds.x1),Max(0,bounds.y1),Min(319,bounds.x2),Min(199,bounds.y2)};
    if(bounds.x1>bounds.x2 || bounds.y1>bounds.y2) return 0;
    volatile const uint8_t *bits=CoverageBits();unsigned count=0;
    for(int y=bounds.y1;y<=bounds.y2;++y) {
        int start=-1,limit=bounds.x2+1;
        auto finish=[&](int end) {
            if(start<0) return true;
            if(count==capacity) return false;
            spans[count++]={(uint16_t)(y*320+start),(uint16_t)(end-start)};
            start=-1;return true;
        };
        for(int x=bounds.x1;x<limit;) {
            int end=Min(limit,(x|7)+1);
            unsigned mask=(1u<<(end-x))-1;
            unsigned value=(bits[y*40+x/8]>>(x&7))&mask;
            // Shared bitmap reads cost bus cycles. Read each byte once;
            // empty/solid runs skip all eight individual pixel probes.
            if(!value) { if(!finish(x)) return 65535; }
            else if(value==mask) { if(start<0) start=x; }
            else for(int i=x;i<end;++i,value>>=1) {
                if(value&1) { if(start<0) start=i; }
                else if(!finish(i)) return 65535;
            }
            x=end;
        }
        if(!finish(limit)) return 65535; // Safe normal-draw fallback.
    }
    return count;
}
void Renderer::DrawCoverage(const CachedSpan *spans,unsigned count,Rect clip) {
    for(unsigned i=0;i<count;++i) {
        unsigned start=spans[i].start;int y=start/320,x=start-y*320;
        if(y>=clip.y1 && y<=clip.y2) BackgroundSpan(y,Max(x,clip.x1),Min(x+spans[i].length-1,clip.x2));
    }
}
void Renderer::Span(int y,int x1,int x2,uint8_t color) {
    RasterSurface surface={target,0,GAME_HEIGHT,damage[buffer_index]};
    RasterSpan(surface,y,x1,x2,color);damage[buffer_index]=surface.damage;
}

void Renderer::BackgroundSpan(int y,int left,int right,bool original) {
    if(left>right) return;
    if(coverage_mode && original) RasterCoverageSpan(CoverageBits(),y,left,right,true);
    Rect &d=damage[buffer_index];
    d.x1=Min(d.x1,left);d.x2=Max(d.x2,right);d.y1=Min(d.y1,y);d.y2=Max(d.y2,y);
    volatile uint16_t *p=target+y*160;
    const uint8_t *source=background+y*320;
    if(original && original_background.data) {
        source=original_background.data+y*GAME_WIDTH;
    }
    if(left&1) {
        volatile uint8_t *bytes=(volatile uint8_t *)(p+left/2);
        if(source[left]) bytes[1]=source[left];
        else p[left/2]=Pair(bytes[0],0);
        ++left;
    }
    if(!(right&1) && left<=right) {
        volatile uint8_t *bytes=(volatile uint8_t *)(p+right/2);
        if(source[right]) bytes[0]=source[right];
        else p[right/2]=Pair(0,bytes[1]);
        --right;
    }
    for(int x=left/2;left<=right && x<=right/2;++x) p[x]=Pair(source[x*2],source[x*2+1]);
}
void Renderer::Box(int x,int y,int w,int h,uint8_t color) {
    for(int j=Max(0,y);j<Min(GAME_HEIGHT,y+h);++j) Span(j,x,x+w-1,color);
}
void Renderer::Panel(int x,int y,unsigned asset) {
    Asset panel=Platform_ReadAsset(asset);
    const int w=BE16(panel.data),h=BE16(panel.data+2);
    const uint16_t *source=(const uint16_t *)(panel.data+4);
    // Importer supplies even widths; all UI positions are even and on screen.
    // Word copies also clear black pixels on the 32X framebuffer.
    for(int row=0;row<h;++row) {
        volatile uint16_t *out=target+(y+row)*160+x/2;
        for(int col=0;col<w/2;++col) out[col]=*source++;
    }
    Rect &d=damage[buffer_index];
    d={Min(d.x1,x),Min(d.y1,y),Max(d.x2,x+w-1),Max(d.y2,y+h-1)};
}
void Renderer::DrawText(int x,int y,const char *s,uint8_t color) {
    while(*s) {
        const unsigned char *f=msx+((unsigned char)*s++)*8;
        for(int row=0;row<8;++row) for(int col=0;col<8;++col)
            if(f[row]&(128>>col)) Span(y+row,x+col,x+col,color);
        x+=8;
    }
}
void Renderer::Polygon(Point *p,unsigned n,uint8_t color) {
    ProfileScope timing(PROFILE_FILL);
    RasterSurface surface={target,0,GAME_HEIGHT,damage[buffer_index]};
    RasterPolygon(surface,p,n,color);damage[buffer_index]=surface.damage;
}
void Renderer::Triangle(Point *p,uint8_t color) {
    RasterSurface surface={target,0,GAME_HEIGHT,damage[buffer_index]};
    RasterTriangle(surface,p,color);damage[buffer_index]=surface.damage;
}
void Renderer::PolygonGeneral(Point *p,unsigned n,uint8_t color) {
    RasterSurface surface={target,0,GAME_HEIGHT,damage[buffer_index]};
    RasterPolygonGeneral(surface,p,n,color);damage[buffer_index]=surface.damage;
}
static Vec3 ClipNear(Vec3 a,Vec3 b) {
    int dz=b.z-a.z;
    return {a.x+RenderDivide((b.x-a.x)*(51-a.z),dz),a.y+RenderDivide((b.y-a.y)*(51-a.z),dz),51};
}
void Renderer::DrawActor(const Actor &a) {
    last_bounds={320,200,-1,-1};
    if(!camera.data || !a.model.data) return;
#ifndef AITD_RASTER_BUILD
    if(DrawCompiledActor(a)) return;
#endif
    {
    ProfileScope timing(PROFILE_TRANSFORM);
    Actor_Vertices(a,single.vertices);
    }
    Asset actor_room=Platform_ReadAsset(floor_rooms[a.floor][a.room]);
    if(!actor_room.data) actor_room=room;
    const uint8_t *c=camera.data,*r=actor_room.data,*m=a.model.data,*prim=m+BE32(m+32);
    Vec3 translation={(BS16(c+6)-BS16(r))*10,(BS16(r+2)-BS16(c+8))*10,(BS16(r+4)-BS16(c+10))*10};
    unsigned nv=BE16(m+2),np=BE16(m+6);
    const int focal_depth=BS16(c+12),focal_x=BS16(c+14),focal_y=BS16(c+16);
    {
    ProfileScope timing(PROFILE_TRANSFORM);
    Rotation rotation=PrepareRotation(BS16(c),BS16(c+2),BS16(c+4));
    for(unsigned i=0;i<nv;++i) {
        Vec3 &v=single.vertices[i];v.x+=a.pos.x-translation.x;v.y+=a.pos.y-translation.y;v.z+=a.pos.z-translation.z;
        Rotate(v,rotation);v.z+=focal_depth;
        if(v.z>=51) single.projected[i]={Clamp(160+RenderDivide(v.x*focal_x,v.z),-4096,4096),Clamp(100+RenderDivide(v.y*focal_y,v.z),-4096,4096)};
    }
    }
    // Stable far-to-near ordering. No z-buffer consumes SDRAM.
    {
    ProfileScope timing(PROFILE_SORT);
    for(unsigned i=0;i<np;++i) {
        const uint8_t *p=m+BE32(prim+i*4);int depth=-32768;
        for(unsigned v=0;v<p[1];++v) depth=Max(depth,single.vertices[BE16(p+6+v*2)].z);
        // Sort four-face runs before merging to avoid the smallest merge passes.
        Face face={i,depth};unsigned j=i,base=i&~3u;
        while(j>base && ordering.faces[j-1].depth<depth) { ordering.faces[j]=ordering.faces[j-1];--j; }
        ordering.faces[j]=face;
    }
    Face *source=ordering.faces,*dest=ordering.sort_scratch;
    for(unsigned width=4;width<np;width*=2) {
        for(unsigned base=0;base<np;base+=width*2) {
            unsigned middle=Min(base+width,np),end=Min(base+width*2,np);
            unsigned left=base,right=middle,out=base;
            while(left<middle && right<end) {
                // Equal depths retain the original primitive order.
                if(source[left].depth>=source[right].depth) dest[out++]=source[left++];
                else dest[out++]=source[right++];
            }
            while(left<middle) dest[out++]=source[left++];
            while(right<end) dest[out++]=source[right++];
        }
        Face *old=source;source=dest;dest=old;
    }
    if(source!=ordering.faces) for(unsigned i=0;i<np;++i) ordering.faces[i]=source[i];
    }
    uint16_t face_order[MAX_PRIMITIVES];
    RasterSurface surface={target,0,GAME_HEIGHT,damage[buffer_index]};
    if(coverage_mode) {
        for(unsigned i=0;i<np;++i) face_order[i]=(uint16_t)ordering.faces[i].index;
        surface.coverage=CoverageBits();
        volatile uint16_t *words=(volatile uint16_t *)surface.coverage;
        for(unsigned i=0;i<4000;++i) words[i]=0;
    }
    RendererWorker_Begin(surface);
    Rect bounds={320,200,-1,-1};
    {
    ProfileScope timing(PROFILE_PRIMITIVES);
    for(unsigned f=0;f<np;++f) {
        unsigned index=coverage_mode?face_order[f]:ordering.faces[f].index;
        const uint8_t *p=m+BE32(prim+index*4);unsigned n=p[1];uint8_t color=p[2];
        Vec3 clipped[MAX_POLY];unsigned count=0;
        Point screen[MAX_POLY];
        bool near_clipped=false;
        for(unsigned i=0;i<n;++i) if(single.vertices[BE16(p+6+i*2)].z<51) near_clipped=true;
        if(!near_clipped) {
            count=n;
            for(unsigned i=0;i<n;++i) screen[i]=single.projected[BE16(p+6+i*2)];
        } else if(p[0]==1) {
            for(unsigned i=0,j=n-1;i<n;j=i++) {
                Vec3 u=single.vertices[BE16(p+6+j*2)],v=single.vertices[BE16(p+6+i*2)];
                if((u.z>=51)!=(v.z>=51)) clipped[count++]=ClipNear(u,v);
                if(v.z>=51) clipped[count++]=v;
            }
        } else {
            for(unsigned i=0;i<n;++i) if(single.vertices[BE16(p+6+i*2)].z>=51) clipped[count++]=single.vertices[BE16(p+6+i*2)];
        }
        if(!count) continue;
        for(unsigned i=0;i<count;++i) {
            if(near_clipped) screen[i]={Clamp(160+RenderDivide(clipped[i].x*focal_x,clipped[i].z),-4096,4096),Clamp(100+RenderDivide(clipped[i].y*focal_y,clipped[i].z),-4096,4096)};

        }
        int depth=near_clipped?clipped[0].z:single.vertices[BE16(p+6)].z;
        int size=p[0]==3?Max(0,RenderDivide(BE16(p+4)*focal_x,depth)/2):p[0]==7?Max(0,RenderDivide(20*focal_x,depth)/2):1;
        size=Min(120,size);
        // Models contain both sides of doors and their handles. Cull the
        // side facing away before painter ordering can expose its latch.
        if(p[0]==1 && count>=3) {
            int winding=0;
            for(unsigned i=1;i+1<count && !winding;++i) winding=(screen[i].x-screen[0].x)*(screen[i+1].y-screen[0].y)-(screen[i].y-screen[0].y)*(screen[i+1].x-screen[0].x);
            if(winding<=0) continue;
        }
        Rect visible={4096,4096,-4096,-4096};
        for(unsigned i=0;i<count;++i) { visible.x1=Min(visible.x1,screen[i].x);visible.x2=Max(visible.x2,screen[i].x);visible.y1=Min(visible.y1,screen[i].y);visible.y2=Max(visible.y2,screen[i].y); }
        if(p[0]==3 || p[0]==7 || p[0]==6) { visible.x1-=size;visible.x2+=size;visible.y1-=size;visible.y2+=size; }
        if(visible.x2<0 || visible.y2<0 || visible.x1>=320 || visible.y1>=200) continue;
        bounds={Min(bounds.x1,Max(0,visible.x1)),Min(bounds.y1,Max(0,visible.y1)),Max(bounds.x2,Min(319,visible.x2)),Max(bounds.y2,Min(199,visible.y2))};
        bool master_rows=RendererWorker_Submit(p[0],screen,count,color,size,p[3]);
        if(master_rows && p[0]==1) {
            ProfileScope timing(PROFILE_FILL);
            RasterPrimitive(surface,p[0],screen,count,color,size,p[3]);
        } else if(master_rows) RasterPrimitive(surface,p[0],screen,count,color,size,p[3]);
    }
    }
    RendererWorker_Finish(surface);damage[buffer_index]=surface.damage;
    last_bounds=bounds;
    // Build-time captures record unmasked geometry; runtime applies masks
    // with the current collision bounds after replaying its prepared spans.
#ifndef AITD_RASTER_BUILD
    Mask(a,bounds);
#endif
}
void Renderer::Mask(const Actor &a,Rect bounds) {
    ProfileScope timing(PROFILE_MASK);
    const uint8_t *c=camera.data,*views=c+BE32(c+20);
    bounds.x1=Clamp(bounds.x1,0,319);bounds.x2=Clamp(bounds.x2,0,319);
    bounds.y1=Clamp(bounds.y1,0,199);bounds.y2=Clamp(bounds.y2,0,199);
    // AITD1 masks are conditional on the entire actor ZV lying in a test rectangle.
    for(unsigned i=0;i<BE16(c+18);++i) {
        const uint8_t *v=views+16*i;if(BE16(v)!=(unsigned)a.room) continue;
        const uint8_t *m=c+BE32(v+12);
        for(unsigned j=0;j<BE16(v+4);++j) {
            const uint8_t *mask=m+j*12;
            if(!Renderer_MaskActive(a,c,mask)) continue;
            const uint8_t *sp=c+BE32(mask+8);
            for(unsigned k=0;k<BE16(mask+2);++k,sp+=6) {
                int y=BE16(sp),left=Max(bounds.x1,BE16(sp+2)),right=Min(bounds.x2,BE16(sp+4));
                if(y<bounds.y1 || y>bounds.y2) continue;
                BackgroundSpan(y,left,right,true);
            }
        }
    }
}

bool Renderer::DepthMask(const Actor &a,Rect tile,uint8_t *bits) {
    const uint8_t *c=camera.data,*views=c+BE32(c+20);bool any=false;
    for(unsigned i=0;i<BE16(c+18);++i) {
        const uint8_t *view=views+16*i;if(BE16(view)!=(unsigned)a.room) continue;
        const uint8_t *m=c+BE32(view+12);
        for(unsigned j=0;j<BE16(view+4);++j) {
            const uint8_t *mask=m+j*12;if(!Renderer_MaskActive(a,c,mask)) continue;
            const uint8_t *sp=c+BE32(mask+8);
            for(unsigned k=0;k<BE16(mask+2);++k,sp+=6) {
                int y=BE16(sp),left=Max(tile.x1,BE16(sp+2)),right=Min(tile.x2,BE16(sp+4));
                if(y<tile.y1 || y>tile.y2 || left>right) continue;
                any=true;
                for(int x=left;x<=right;++x) { unsigned bit=(y-tile.y1)*64+x-tile.x1;bits[bit/8]|=1u<<(bit&7); }
            }
        }
    }
    return any;
}

void Renderer::DrawEffects(const World &world) {
    const uint8_t *c=camera.data;
    Rotation rotation=PrepareRotation(BS16(c),BS16(c+2),BS16(c+4));
    for(const auto &e:world.effects) {
        if(!e.count || e.floor!=world.floor) continue;
        bool visible=false;const uint8_t *views=c+BE32(c+20);
        for(unsigned i=0;i<BE16(c+18);++i) if(BE16(views+16*i)==(unsigned)e.room) visible=true;
        if(!visible) continue;
        Asset r=world.RoomAsset(e.floor,e.room);if(!r.data) continue;
        Vec3 translation={(BS16(c+6)-BS16(r.data))*10,(BS16(r.data+2)-BS16(c+8))*10,(BS16(r.data+4)-BS16(c+10))*10};
        unsigned age=world.now-e.since;
        for(unsigned i=0;i<e.count;++i) {
            const auto &q=e.points[i];
            Vec3 v={q.x-translation.x,q.y-translation.y-(int)age*(e.mode==1?2:6),q.z-translation.z};
            v.x+=((int)(i%5)-2)*(int)age;v.z+=((int)(i%7)-3)*(int)age;
            Rotate(v,rotation);v.z+=BS16(c+12);if(v.z<51) continue;
            int x=160+RenderDivide(v.x*BS16(c+14),v.z),y=100+RenderDivide(v.y*BS16(c+16),v.z);
            int radius=Clamp(RenderDivide((e.mode==0?50:20)*BS16(c+14),v.z)/2,0,3);
            // Triple the projected diameter, including one-pixel distant points.
            if(e.mode==0) radius=3*radius+1;
            if(((i+age/12)&3)!=0 || age<e.duration/2) Box(x-radius,y-radius,2*radius+1,2*radius+1,e.color+(i&3));
        }
    }
}

bool Renderer::ResolveOverlap(const Actor *const *actors,unsigned count,Rect area) {
    unsigned offsets[24],used=0;bool near[24]={};
    for(unsigned i=0;i<count;++i) { offsets[i]=used;used+=BE16(actors[i]->model.data+2); }
    // Two maximum-size source models fit; larger groups retain painter order.
    if(used>768) return false;
    const uint8_t *c=camera.data;Rotation rotation=PrepareRotation(BS16(c),BS16(c+2),BS16(c+4));
    Vec3 *vertices=Actor_GameplayScratch();
    for(unsigned i=0;i<count;++i) {
        const Actor &a=*actors[i];Actor_Vertices(a,vertices);
        Asset r=Platform_ReadAsset(floor_rooms[a.floor][a.room]);
        Vec3 translation={(BS16(c+6)-BS16(r.data))*10,(BS16(r.data+2)-BS16(c+8))*10,(BS16(r.data+4)-BS16(c+10))*10};
        for(unsigned v=0;v<BE16(a.model.data+2);++v) {
            Vec3 q={vertices[v].x+a.pos.x-translation.x,vertices[v].y+a.pos.y-translation.y,vertices[v].z+a.pos.z-translation.z};
            Rotate(q,rotation);q.z+=BS16(c+12);if(q.z<51) near[i]=true;
            CompactVertex &out=combined[offsets[i]+v];out.x=Clamp(q.x,-32768,32767);out.y=Clamp(q.y,-32768,32767);out.z=Clamp(q.z,-32768,32767);
            if(q.z>=51) { out.sx=Clamp(160+RenderDivide(q.x*BS16(c+14),q.z),-4096,4096);out.sy=Clamp(100+RenderDivide(q.y*BS16(c+16),q.z),-4096,4096); }
        }
        // Camera-space X is only needed for near clipping. For ordinary
        // groups, reuse it for reciprocal depth computed once per vertex.
        if(!near[i]) for(unsigned v=0;v<BE16(a.model.data+2);++v) { CompactVertex &q=combined[offsets[i]+v];q.x=(int16_t)RenderDivide(1<<20,q.z); }
    }
    // A 64 x 64 depth tile reuses primitive-sort scratch; it adds only
    // 2 KiB to SDRAM instead of allocating a full-screen Z buffer.
    // Cached scenery still handles normal frames; only contact regions pay
    // for per-pixel depth and every vertex is transformed once for the group.
    uint16_t *depths=contact_depth;
    area={Max(0,area.x1),Max(0,area.y1),Min(319,area.x2),Min(199,area.y2)};
    RasterSurface surface={target,0,GAME_HEIGHT,damage[buffer_index]};
    for(int y=area.y1;y<=area.y2;y+=64) for(int x=area.x1;x<=area.x2;x+=64) {
        Rect tile={x,y,Min(x+63,area.x2),Min(y+63,area.y2)};
        for(unsigned j=0;j<64*64;++j) depths[j]=0;
        for(unsigned i=0;i<count;++i) {
            // Clip each model before it contributes depth. Restoring a prop's
            // mask after the whole group would erase an unmasked nearer actor.
            uint32_t blocked[128]={};
            const uint8_t *mask=DepthMask(*actors[i],tile,(uint8_t *)blocked)?(uint8_t *)blocked:nullptr;
            const uint8_t *m=actors[i]->model.data,*directory=m+BE32(m+32);
            for(unsigned f=0;f<BE16(m+6);++f) {
                const uint8_t *p=m+BE32(directory+4*f);unsigned n=p[1];
                if(p[0]!=1) {
                    const CompactVertex &v=combined[offsets[i]+BE16(p+6)];if(v.z<51) continue;
                    int size=p[0]==3?RenderDivide(BE16(p+4)*BS16(c+14),v.z)/2:p[0]==7?RenderDivide(20*BS16(c+14),v.z)/2:p[0]==6?1:0;
                    int inv=near[i]?RenderDivide(1<<20,v.z):v.x;
                    if(p[0]==0 && n==2) {
                        const CompactVertex &b=combined[offsets[i]+BE16(p+8)];if(b.z<51) continue;
                        int dx=b.sx-v.sx,dy=b.sy-v.sy,steps=Max(dx<0?-dx:dx,dy<0?-dy:dy),end=near[i]?RenderDivide(1<<20,b.z):b.x;
                        for(int t=0;t<=steps;++t) { Point point={v.sx+(steps?dx*t/steps:0),v.sy+(steps?dy*t/steps:0)};RasterDepthPoint(surface,point,inv+(steps?(end-inv)*t/steps:0),0,tile,depths,p[2],p[3],mask); }
                    } else RasterDepthPoint(surface,{v.sx,v.sy},inv,Clamp(size,0,120),tile,depths,p[2],p[3],mask);
                    continue;
                }
                if(n<3) continue;
                // Near-crossing contacts use the same clipping plane as the
                // regular renderer. Store reciprocal depth after clipping.
                Vec3 clipped[MAX_POLY];Point screen[MAX_POLY];int q[MAX_POLY];unsigned size=0;
                bool clipped_near=false;
                for(unsigned v=0;v<n;++v) if(combined[offsets[i]+BE16(p+6+2*v)].z<51) clipped_near=true;
                if(clipped_near) {
                    for(unsigned v=0,k=n-1;v<n;k=v++) {
                        const CompactVertex &a=combined[offsets[i]+BE16(p+6+2*k)],&b=combined[offsets[i]+BE16(p+6+2*v)];
                        Vec3 u={a.x,a.y,a.z},w={b.x,b.y,b.z};
                        if((u.z>=51)!=(w.z>=51)) clipped[size++]=ClipNear(u,w);
                        if(w.z>=51) clipped[size++]=w;
                    }
                    for(unsigned v=0;v<size;++v) { Vec3 &a=clipped[v];screen[v]={Clamp(160+RenderDivide(a.x*BS16(c+14),a.z),-4096,4096),Clamp(100+RenderDivide(a.y*BS16(c+16),a.z),-4096,4096)};q[v]=RenderDivide(1<<20,a.z); }
                } else {
                    size=n;
                    for(unsigned v=0;v<n;++v) { const CompactVertex &a=combined[offsets[i]+BE16(p+6+2*v)];screen[v]={a.sx,a.sy};q[v]=near[i]?RenderDivide(1<<20,a.z):a.x; }
                }
                int winding=0;
                for(unsigned v=1;v+1<size && !winding;++v)
                    winding=(screen[v].x-screen[0].x)*(screen[v+1].y-screen[0].y)-(screen[v].y-screen[0].y)*(screen[v+1].x-screen[0].x);
                if(winding<=0) continue;
                for(unsigned v=1;v+1<size;++v) { Point triangle[]={screen[0],screen[v],screen[v+1]};int inv[]={q[0],q[v],q[v+1]};RasterDepthTriangle(surface,triangle,inv,tile,depths,p[2],p[3],mask); }
            }
        }
    }
    damage[buffer_index]=surface.damage;
    return true;
}
