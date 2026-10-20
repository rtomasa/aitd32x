// SPDX-License-Identifier: GPL-2.0-or-later
#include "../platform/pixel_words.hpp"
#include "render_api.hpp"
#include "../engine/world.hpp"
#include "divide.hpp"
#include "project.hpp"
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
    const uint8_t *tests=camera+BE32Aligned(mask+4);
    for(unsigned t=0;t<BE16Aligned(mask);++t) {
        const uint8_t *b=tests+t*8;
        if(x1>=BS16Aligned(b) && z1>=BS16Aligned(b+2) && x2<=BS16Aligned(b+4) && z2<=BS16Aligned(b+6)) return true;
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
A32X_COLD const uint8_t *Renderer::CompiledProgram(const Actor &a) const {
    // Skeletons and arbitrary moved poses always use the regular renderer.
    if(!camera.data || !a.model.data || BE16Aligned(a.model.data+4)) return nullptr;
    Asset asset=Platform_ReadAsset(AS_STATIC_RASTERS);
    if(!asset.data || asset.size<4 || !BE32Aligned(asset.data)) return nullptr;
    uint32_t key=Renderer_RasterKey(a);
    unsigned left=0,right=BE32Aligned(asset.data);
    while(left<right) {
        unsigned mid=(left+right)/2;const uint8_t *entry=asset.data+4+mid*12;
        unsigned view=BE32Aligned(entry),pose=BE32Aligned(entry+4);
        if(view<camera_id || (view==camera_id && pose<key)) left=mid+1;
        else right=mid;
    }
    if(left==BE32Aligned(asset.data)) return nullptr;
    const uint8_t *entry=asset.data+4+left*12;
    if(BE32Aligned(entry)!=camera_id || BE32Aligned(entry+4)!=key) return nullptr;
    return asset.data+BE32Aligned(entry+8);
}
void Renderer::DrawCompiledActor(const Actor &a,const uint8_t *program,bool *masked) {
    Rect bounds={BS16Aligned(program),BS16Aligned(program+2),BS16Aligned(program+4),BS16Aligned(program+6)};
    FinishRestore();
    RasterSurface surface={target,0,GAME_HEIGHT,damage[buffer_index]};
    if(masked) {
        // The stored color spans already describe the exact silhouette,
        // including black and glass holes. Only architectural erasures need
        // bitmap recording; start with all pixels allowed inside the bounds.
        volatile uint16_t *words=(volatile uint16_t *)CoverageBits();
        for(int y=Max(0,bounds.y1);y<=Min(199,bounds.y2);++y)
            if(bounds.x1<=bounds.x2) {
                unsigned first=Max(0,bounds.x1)/16,last=Min(319,bounds.x2)/16;
                PixelFillWords(words+y*20+first,last-first+1,0xffff);
            }
    }
    unsigned count=BE32Aligned(program+8);program+=12;
    for(unsigned i=0;i<count;++i,program+=6) {
        unsigned start=BE16Aligned(program);int y=start/320,x=start-y*320;
        RasterSpan(surface,y,x,x+BE16Aligned(program+2)-1,program[4]);
    }
    damage[buffer_index]=surface.damage;last_bounds=bounds;
    bool erased=Mask(a,bounds);if(masked) *masked=erased;
}
#endif
A32X_COLD bool Renderer::SetCamera(unsigned id,unsigned floor,unsigned room_id,bool load_palette) {
    FinishRestore();
    if(floor>=A32X_FLOOR_COUNT || id>=camera_counts[floor] || room_id>=room_counts[floor]) return false;
    coverage_mode=false;
    camera=Platform_ReadAsset(floor_cameras[floor][id]);room=Platform_ReadAsset(floor_rooms[floor][room_id]);
    Asset bg=Platform_ReadAsset(floor_backgrounds[floor][id]),pal=Platform_ReadAsset(AS_GAME_PALETTE);
    if(!camera.data || !room.data || pal.size!=512 || bg.unpacked!=sizeof(background) ||
       (bg.flags!=0 && bg.flags!=0x8000)) return false;
    // Raw banked camera originals remain available during a scoped scene draw;
    // the RAM restore image can use the same scenery cache as gameplay.
    if(!Platform_Decode(bg,background,sizeof(background))) return false;
    original_background=bg;
    if(load_palette) for(unsigned i=0;i<256;++i) {
        uint16_t color=i?BE16Aligned(pal.data+i*2):0;
        if(palette[i]!=color) palette_changed=true;
        palette[i]=color;
    }
    camera_id=(floor<<8)|id;
    full_restore[0]=full_restore[1]=true;
    return true;
}
bool Renderer::SetTitle() {
    return SetImage(AS_TITLE,AS_TITLE_PALETTE);
}
A32X_COLD bool Renderer::SetImage(unsigned image,unsigned colors) {
    FinishRestore();
    coverage_mode=false;
    Asset bg=Platform_ReadAsset(image),pal=Platform_ReadAsset(colors);
    if(!pal.data || pal.size!=512 || pal.flags || bg.type!=2 || bg.unpacked!=sizeof(background) || !Platform_Decode(bg,background,sizeof(background))) return false;
    camera=room={};original_background=bg;camera_id=0xffffffffu;
    for(unsigned i=0;i<256;++i) palette[i]=BE16Aligned(pal.data+i*2);
    palette[0]=0;full_restore[0]=full_restore[1]=true;palette_changed=true;
    return true;
}
A32X_COLD bool Renderer::DrawImage(unsigned image,int x,int y,unsigned width,unsigned height) {
    FinishRestore();
    Asset a=Platform_ReadAsset(image);
    if(a.type==13) {
        if(!a.data || a.size<4 || a.unpacked<4 || (a.flags!=0 && a.flags!=3 && a.flags!=4)) return false;
        width=BE16Aligned(a.data);height=BE16Aligned(a.data+2);
        a={a.data+4,a.size-4,a.unpacked-4,a.type,(uint16_t)(a.flags==3?1:a.flags==4?2:0)};
    } else if(a.type!=2) return false;
    if(x<0 || (x&1) || y<0 || x>GAME_WIDTH || y>GAME_HEIGHT || width>(unsigned)(GAME_WIDTH-x) || height>(unsigned)(GAME_HEIGHT-y)) return false;
    if(target==(volatile uint16_t *)background && x==0 && width==GAME_WIDTH) {
        // Full-width RAM compositions are contiguous. Decode bytes directly,
        // avoiding framebuffer-style read/modify/write for every literal.
        if(!Platform_Decode(a,background+y*GAME_WIDTH,width*height)) return false;
    } else if(!Platform_Blit(a,target+y*(GAME_WIDTH/2)+x/2,width,height)) return false;
    Rect &d=damage[buffer_index];
    d={Min(d.x1,x),Min(d.y1,y),Max(d.x2,x+(int)width-1),Max(d.y2,y+(int)height-1)};
    return true;
}
void Renderer::Restore() {
    ProfileScope timing(PROFILE_RESTORE);
    // Word writes can write palette index zero. Byte writes of zero on the 32X
    // framebuffer are transparent and cannot restore a black background pixel.
    const uint16_t *source=(const uint16_t *)background;
    Rect d=full_restore[buffer_index]?Rect{0,0,319,199}:damage[buffer_index];
    int split=RendererWorker_Restore(target,source,d);
    for(int y=d.y1;y<split;++y) {
        unsigned i=y*160+d.x1/2,last=y*160+d.x2/2;
        if(d.x1>d.x2) break;
        PixelCopyWords(target+i,source+i,last-i+1);
    }
    full_restore[buffer_index]=false;
    damage[buffer_index]={320,200,-1,-1};
}
A32X_COLD void Renderer::FinishRestore() { RendererWorker_WaitRestore(); }
A32X_COLD BackgroundComposition::BackgroundComposition(Renderer &r):renderer(r),output(r.target) {
    renderer.FinishRestore();
    previous_damage[0]=r.damage[0];previous_damage[1]=r.damage[1];
    renderer.target=(volatile uint16_t *)renderer.background;
    renderer.damage[renderer.buffer_index]={320,200,-1,-1};
}
A32X_COLD BackgroundComposition::~BackgroundComposition() {
    Rect area=renderer.damage[renderer.buffer_index];
    renderer.target=output;
    for(unsigned bank=0;bank<2;++bank) {
        Rect old=previous_damage[bank];
        renderer.damage[bank]={Min(old.x1,area.x1),Min(old.y1,area.y1),Max(old.x2,area.x2),Max(old.y2,area.y2)};
        if(area.x1==0 && area.y1==0 && area.x2==319 && area.y2==199) renderer.full_restore[bank]=true;
    }
}
void Renderer::BakeBackground() {
    FinishRestore();
    // FITD's background incrustation: static actors become part of the restore
    // image. Finish the slave queue before reading this framebuffer back.
    uint16_t *destination=(uint16_t *)background;
    // SetCamera already supplied the untouched pixels. Copy back only the
    // words covered by static drawing, including masks and black pixels.
    const Rect &d=damage[buffer_index];
    if(d.x1<=d.x2 && d.y1<=d.y2) for(int y=d.y1;y<=d.y2;++y) {
        unsigned first=y*160+d.x1/2,last=y*160+d.x2/2;
        PixelCopyWords(destination+first,target+first,last-first+1);
    }
    damage[buffer_index]={320,200,-1,-1};
    full_restore[buffer_index]=false;full_restore[buffer_index^1]=true;
}
A32X_COLD void Renderer::RestoreOriginal(Rect area) {
    for(int y=area.y1;y<=area.y2;++y) BackgroundSpan(y,area.x1,area.x2,true);
}
A32X_COLD void Renderer::BakeRegion(Rect area) {
    FinishRestore();
    // The caller expands to whole words and encloses every redrawn prop.
    uint16_t *destination=(uint16_t *)background;
    for(int y=area.y1;y<=area.y2;++y) {
        unsigned first=y*160+area.x1/2,last=y*160+area.x2/2;
        PixelCopyWords(destination+first,target+first,last-first+1);
    }
    damage[buffer_index]={320,200,-1,-1};
    // The other physical bank needs this region restored on its next use.
    Rect &d=damage[buffer_index^1];
    d={Min(d.x1,area.x1),Min(d.y1,area.y1),Max(d.x2,area.x2),Max(d.y2,area.y2)};
}
volatile uint8_t *Renderer::CoverageBits() {
    uintptr_t address=(uintptr_t)contact_depth;
#if defined(__sh__)
    address|=0x20000000u;
#endif
    return (volatile uint8_t *)address;
}
static A32X_COLD bool CacheSpan(CachedSpan *spans,unsigned capacity,unsigned &count,int y,int first,int end) {
    if(first>=end) return true;
    unsigned start=y*320+first;
    if(count && spans[count-1].start+spans[count-1].length==start && spans[count-1].start/320==(unsigned)y) {
        spans[count-1].length+=(uint16_t)(end-first);return true;
    }
    if(count==capacity) return false;
    spans[count++]={(uint16_t)start,(uint16_t)(end-first)};return true;
}
static A32X_COLD bool CacheRun(volatile const uint8_t *bits,int y,int left,int limit,CachedSpan *spans,unsigned capacity,unsigned &count) {
    if(!bits) return CacheSpan(spans,capacity,count,y,left,limit);
    int start=-1;
    auto finish=[&](int end) {
        bool fits=start<0 || CacheSpan(spans,capacity,count,y,start,end);
        start=-1;return fits;
    };
    for(int x=left;x<limit;) {
        int end=Min(limit,(x|7)+1);
        unsigned mask=(1u<<(end-x))-1,value=(bits[y*40+x/8]>>(x&7))&mask;
        if(!value) { if(!finish(x)) return false; }
        else if(value==mask) { if(start<0) start=x; }
        else for(int i=x;i<end;++i,value>>=1) {
            if(value&1) { if(start<0) start=i; }
            else if(!finish(i)) return false;
        }
        x=end;
    }
    return finish(limit);
}
A32X_COLD unsigned Renderer::DrawCachedActor(const Actor &actor,CachedSpan *spans,unsigned capacity) {
#ifndef AITD_RASTER_BUILD
    if(const uint8_t *program=CompiledProgram(actor)) {
        bool masked;
        coverage_mode=true;DrawCompiledActor(actor,program,&masked);coverage_mode=false;
        volatile const uint8_t *bits=masked?CoverageBits():nullptr;
        unsigned count=0,total=BE32Aligned(program+8);program+=12;
        for(unsigned i=0;i<total;) {
            unsigned start=BE16Aligned(program),end=start+BE16Aligned(program+2),y=start/320;
            program+=6;++i;
            // Color changes do not split coverage. Merge adjacent spans on
            // this row before subtracting any current architectural masks.
            while(i<total && BE16Aligned(program)==end && end/320==y) {
                end+=BE16Aligned(program+2);program+=6;++i;
            }
            if(!CacheRun(bits,y,start-y*320,end-y*320,spans,capacity,count)) return 65535;
        }
        return count;
    }
#endif
    // The normal colored draw records its silhouette in sort scratch after
    // face indices have moved to the stack. No second monochrome draw/readback.
    coverage_mode=true;DrawActor(actor);coverage_mode=false;
    Rect bounds=last_bounds;
    bounds={Max(0,bounds.x1),Max(0,bounds.y1),Min(319,bounds.x2),Min(199,bounds.y2)};
    if(bounds.x1>bounds.x2 || bounds.y1>bounds.y2) return 0;
    volatile const uint8_t *bits=CoverageBits();unsigned count=0;
    for(int y=bounds.y1;y<=bounds.y2;++y)
        if(!CacheRun(bits,y,bounds.x1,bounds.x2+1,spans,capacity,count)) return 65535;
    return count;
}
void Renderer::DrawCoverage(const CachedSpan *spans,unsigned count,Rect clip) {
    for(unsigned i=0;i<count;++i) {
        unsigned start=spans[i].start;int y=start/320,x=start-y*320;
        if(y>=clip.y1 && y<=clip.y2) BackgroundSpan(y,Max(x,clip.x1),Min(x+spans[i].length-1,clip.x2));
    }
}
void Renderer::DrawCachedCoverage(const Actor &actor,const CachedSpan *spans,unsigned count,Rect bounds,Rect clip) {
    DrawCoverage(spans,count,clip);
    // A cached actor writes architectural background as well as colored
    // pixels. Replay both, confined to the area overwritten by earlier actors;
    // a whole-bounds mask could otherwise erase untouched foreground scenery.
    bounds={Max(bounds.x1,clip.x1),Max(bounds.y1,clip.y1),Min(bounds.x2,clip.x2),Min(bounds.y2,clip.y2)};
    if(bounds.x1<=bounds.x2 && bounds.y1<=bounds.y2) Mask(actor,bounds);
}
void Renderer::Span(int y,int x1,int x2,uint8_t color) {
    FinishRestore();
    RasterSurface surface={target,0,GAME_HEIGHT,damage[buffer_index]};
    RasterSpan(surface,y,x1,x2,color);damage[buffer_index]=surface.damage;
}

void Renderer::BackgroundSpan(int y,int left,int right,bool original) {
    FinishRestore();
    if(left>right) return;
    if(coverage_mode && original) RasterCoverageSpan(CoverageBits(),y,left,right,true);
    Rect &d=damage[buffer_index];
    d.x1=Min(d.x1,left);d.x2=Max(d.x2,right);d.y1=Min(d.y1,y);d.y2=Max(d.y2,y);
    volatile uint16_t *p=target+y*160;
    const uint8_t *source=background+y*320;
    if(original && original_background.data && !original_background.flags) {
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
    const uint16_t *words=(const uint16_t *)source;
    if(left<=right) PixelCopyWords(p+left/2,words+left/2,(right-left+1)/2);
}
A32X_COLD void Renderer::Box(int x,int y,int w,int h,uint8_t color) {
    int first=Max(0,y),last=Min(GAME_HEIGHT,y+h),left=Max(0,x),right=Min(GAME_WIDTH-1,x+w-1);
    if(first>=last || left>right) return;
    FinishRestore();
    if(left==0 && right==GAME_WIDTH-1) {
        PixelFillWords(target+first*160,(last-first)*160,Pair(color,color));
        Rect &d=damage[buffer_index];
        d={Min(d.x1,left),Min(d.y1,first),Max(d.x2,right),Max(d.y2,last-1)};
    } else {
        RasterSurface surface={target,0,GAME_HEIGHT,damage[buffer_index]};
        for(int j=first;j<last;++j) RasterSpan(surface,j,left,right,color);
        damage[buffer_index]=surface.damage;
    }
}
void Renderer::Panel(int x,int y,unsigned asset) {
    FinishRestore();
    Asset panel=Platform_ReadAsset(asset);
    if(panel.flags==3 || panel.flags==4) {
        if(!DrawImage(asset,x,y)) Platform_Fatal();
        return;
    }
    const int w=BE16Aligned(panel.data),h=BE16Aligned(panel.data+2);
    const uint16_t *source=(const uint16_t *)(panel.data+4);
    // Importer supplies even widths; all UI positions are even and on screen.
    // Word copies also clear black pixels on the 32X framebuffer.
    for(int row=0;row<h;++row) {
        volatile uint16_t *out=target+(y+row)*160+x/2;
        PixelCopyWords(out,source,w/2);source+=w/2;
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
    FinishRestore();
    ProfileScope timing(PROFILE_FILL);
    RasterSurface surface={target,0,GAME_HEIGHT,damage[buffer_index]};
    RasterPolygon(surface,p,n,color);damage[buffer_index]=surface.damage;
}
void Renderer::Triangle(Point *p,uint8_t color) {
    FinishRestore();
    RasterSurface surface={target,0,GAME_HEIGHT,damage[buffer_index]};
    RasterTriangle(surface,p,color);damage[buffer_index]=surface.damage;
}
void Renderer::PolygonGeneral(Point *p,unsigned n,uint8_t color) {
    FinishRestore();
    RasterSurface surface={target,0,GAME_HEIGHT,damage[buffer_index]};
    RasterPolygonGeneral(surface,p,n,color);damage[buffer_index]=surface.damage;
}
unsigned Renderer::SortFaces(const uint8_t *m,Rect *bounds,const Rect *deferred) {
    const uint8_t *prim=m+BE32Aligned(m+32);unsigned np=BE16Aligned(m+6),count=0;
    for(unsigned i=0;i<np;++i) {
        const uint8_t *p=m+BE32Aligned(prim+i*4);int depth=-32768;
        if(bounds && p[0]==1 && p[1]>=3) {
            Rect visible={4096,4096,-4096,-4096};bool rejected=false;int winding=0;
            Point first={},previous={};
            for(unsigned v=0;v<p[1];++v) {
                unsigned index=BE16Aligned(p+6+v*2);int z=single.vertices[index].z;
                if(z<=100) { rejected=true;break; }
                depth=Max(depth,z);Point point=single.projected[index];
                visible={Min(visible.x1,point.x),Min(visible.y1,point.y),Max(visible.x2,point.x),Max(visible.y2,point.y)};
                if(!v) first=point;
                else if(v>1 && !winding) winding=(previous.x-first.x)*(point.y-first.y)-(previous.y-first.y)*(point.x-first.x);
                previous=point;
            }
            if(rejected || winding<=0 || visible.x2<0 || visible.y2<0 || visible.x1>=320 || visible.y1>=200) continue;
            *bounds={Min(bounds->x1,Max(0,visible.x1)),Min(bounds->y1,Max(0,visible.y1)),Max(bounds->x2,Min(319,visible.x2)),Max(bounds->y2,Min(199,visible.y2))};
            if(deferred && p[1]==3 && visible.x1>=deferred->x1 && visible.x2<=deferred->x2 &&
               visible.y1>=deferred->y1 && visible.y2<=deferred->y2) continue;
        } else for(unsigned v=0;v<p[1];++v) depth=Max(depth,single.vertices[BE16Aligned(p+6+v*2)].z);
        Face face={i,depth};unsigned j=count++,base=j&~3u;
        while(j>base && ordering.faces[j-1].depth<depth) { ordering.faces[j]=ordering.faces[j-1];--j; }
        ordering.faces[j]=face;
    }
    np=count;
    Face *source=ordering.faces,*dest=ordering.sort_scratch;
    for(unsigned width=4;width<np;width*=2) {
        for(unsigned base=0;base<np;base+=width*2) {
            unsigned middle=Min(base+width,np),end=Min(base+width*2,np);
            unsigned left=base,right=middle,out=base;
            while(left<middle && right<end) {
                if(source[left].depth>=source[right].depth) dest[out++]=source[left++];
                else dest[out++]=source[right++];
            }
            while(left<middle) dest[out++]=source[left++];
            while(right<end) dest[out++]=source[right++];
        }
        Face *old=source;source=dest;dest=old;
    }
    if(source!=ordering.faces) for(unsigned i=0;i<np;++i) ordering.faces[i]=source[i];
    return np;
}
bool Renderer::DrawActor(const Actor &a,const Rect *deferred) {
    last_bounds={320,200,-1,-1};
    if(!camera.data || !a.model.data) return false;
#ifndef AITD_RASTER_BUILD
    if(const uint8_t *program=CompiledProgram(a)) { DrawCompiledActor(a,program);return false; }
#endif
    {
    ProfileScope timing(PROFILE_TRANSFORM);
    Actor_Vertices(a,single.vertices);
    }
    Asset actor_room=Platform_ReadAsset(floor_rooms[a.floor][a.room]);
    if(!actor_room.data) actor_room=room;
    const uint8_t *c=camera.data,*r=actor_room.data,*m=a.model.data,*prim=m+BE32Aligned(m+32);
    Vec3 translation={(BS16Aligned(c+6)-BS16Aligned(r))*10,(BS16Aligned(r+2)-BS16Aligned(c+8))*10,(BS16Aligned(r+4)-BS16Aligned(c+10))*10};
    unsigned nv=BE16Aligned(m+2),np=BE16Aligned(m+6);
    const int focal_depth=BS16Aligned(c+12),focal_x=BS16Aligned(c+14),focal_y=BS16Aligned(c+16);
    {
    ProfileScope timing(PROFILE_TRANSFORM);
    Rotation rotation=PrepareRotation(BS16Aligned(c),BS16Aligned(c+2),BS16Aligned(c+4));
    for(unsigned i=0;i<nv;++i) {
        Vec3 &v=single.vertices[i];v.x+=a.pos.x-translation.x;v.y+=a.pos.y-translation.y;v.z+=a.pos.z-translation.z;
        Rotate(v,rotation);v.z+=focal_depth;
        if(v.z>100) single.projected[i]=RenderProject(v,focal_x,focal_y,{160,100});
    }
    }
    // Stable far-to-near ordering. No z-buffer consumes SDRAM.
    Rect bounds={320,200,-1,-1};
    {
    ProfileScope timing(PROFILE_SORT);
    np=SortFaces(m,&bounds,deferred);
    }
    uint16_t face_order[MAX_PRIMITIVES];
    RasterSurface surface={target,0,GAME_HEIGHT,damage[buffer_index]};
    if(deferred) surface.deferred=*deferred;
    if(coverage_mode) {
        for(unsigned i=0;i<np;++i) face_order[i]=(uint16_t)ordering.faces[i].index;
        surface.coverage=CoverageBits();
        volatile uint16_t *words=(volatile uint16_t *)surface.coverage;
        for(unsigned i=0;i<4000;++i) words[i]=0;
    }
    RendererWorker_Begin(surface);
    {
    ProfileScope timing(PROFILE_PRIMITIVES);
    for(unsigned f=0;f<np;++f) {
        unsigned index=coverage_mode?face_order[f]:ordering.faces[f].index;
        const uint8_t *p=m+BE32Aligned(prim+index*4);unsigned n=p[1];uint8_t color=p[2];
        Point screen[MAX_POLY];
        unsigned count=n;int size=1;
        if(p[0]==1 && n>=3) {
            // SortFaces already rejected near/back-facing/off-screen polygons
            // and included their bounds. Copy only the accepted projection.
            for(unsigned i=0;i<n;++i) screen[i]=single.projected[BE16Aligned(p+6+i*2)];
        } else {
            bool rejected=false;Rect visible={4096,4096,-4096,-4096};
            for(unsigned i=0;i<n;++i) {
                unsigned vertex=BE16Aligned(p+6+i*2);
                if(single.vertices[vertex].z<=100) { rejected=true;break; }
                screen[i]=single.projected[vertex];
                visible.x1=Min(visible.x1,screen[i].x);visible.x2=Max(visible.x2,screen[i].x);
                visible.y1=Min(visible.y1,screen[i].y);visible.y2=Max(visible.y2,screen[i].y);
            }
            if(rejected || !n) continue;
            int depth=single.vertices[BE16Aligned(p+6)].z;
            size=p[0]==3?Max(0,RenderDivide(BE16Aligned(p+4)*focal_x,depth)/2):p[0]==7?Max(0,RenderDivide(20*focal_x,depth)/2):1;
            size=Min(120,size);
            if(p[0]==3 || p[0]==7 || p[0]==6) { visible.x1-=size;visible.x2+=size;visible.y1-=size;visible.y2+=size; }
            if(visible.x2<0 || visible.y2<0 || visible.x1>=320 || visible.y1>=200) continue;
            bounds={Min(bounds.x1,Max(0,visible.x1)),Min(bounds.y1,Max(0,visible.y1)),Max(bounds.x2,Min(319,visible.x2)),Max(bounds.y2,Min(199,visible.y2))};
        }
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
    return true;
}
// poly_spans() stores camera masks in ascending row order. Seek the first
// intersecting row instead of rescanning every mask row for each depth tile.
static A32X_COLD const uint8_t *MaskRow(const uint8_t *sp,unsigned count,int y) {
    unsigned first=0,last=count;
    while(first<last) {
        unsigned middle=(first+last)/2;
        if(BE16Aligned(sp+middle*6)<y) first=middle+1;
        else last=middle;
    }
    return sp+first*6;
}
bool Renderer::Mask(const Actor &a,Rect bounds) {
    ProfileScope timing(PROFILE_MASK);
    const uint8_t *c=camera.data,*views=c+BE32Aligned(c+20);bool erased=false;
    bounds.x1=Clamp(bounds.x1,0,319);bounds.x2=Clamp(bounds.x2,0,319);
    bounds.y1=Clamp(bounds.y1,0,199);bounds.y2=Clamp(bounds.y2,0,199);
    // AITD1 masks are conditional on the entire actor ZV lying in a test rectangle.
    for(unsigned i=0;i<BE16Aligned(c+18);++i) {
        const uint8_t *v=views+16*i;if(BE16Aligned(v)!=(unsigned)a.room) continue;
        const uint8_t *m=c+BE32Aligned(v+12);
        for(unsigned j=0;j<BE16Aligned(v+4);++j) {
            const uint8_t *mask=m+j*12;
            if(!Renderer_MaskActive(a,c,mask)) continue;
            const uint8_t *sp=c+BE32Aligned(mask+8);
            const uint8_t *end=sp+BE16Aligned(mask+2)*6;
            for(sp=MaskRow(sp,BE16Aligned(mask+2),bounds.y1);sp<end && BE16Aligned(sp)<=bounds.y2;sp+=6) {
                int y=BE16Aligned(sp),left=Max(bounds.x1,BE16Aligned(sp+2)),right=Min(bounds.x2,BE16Aligned(sp+4));
                if(y<bounds.y1 || y>bounds.y2 || left>right) continue;
                erased=true;
                BackgroundSpan(y,left,right,true);
            }
        }
    }
    return erased;
}

static A32X_COLD void DepthMaskRows(const uint8_t *c,const uint8_t *mask,Rect tile,uint8_t *bits,bool &any) {
    const uint8_t *sp=c+BE32Aligned(mask+8),*end=sp+BE16Aligned(mask+2)*6;
    for(sp=MaskRow(sp,BE16Aligned(mask+2),tile.y1);sp<end && BE16Aligned(sp)<=tile.y2;sp+=6) {
        int y=BE16Aligned(sp),left=Max(tile.x1,BE16Aligned(sp+2)),right=Min(tile.x2,BE16Aligned(sp+4));
        if(left>right) continue;
        if(!any) {
            uint32_t *words=(uint32_t *)bits;
            for(unsigned k=0;k<128;++k) words[k]=0;
            any=true;
        }
        unsigned first=left-tile.x1,last=right-tile.x1;
        uint8_t *row=bits+(y-tile.y1)*8;
        for(unsigned b=first/8;b<=last/8;++b) {
            unsigned value=255;
            if(b==first/8) value&=255u<<(first&7);
            if(b==last/8) value&=255u>>(7-(last&7));
            if(value==255) row[b]=255;else row[b]|=(uint8_t)value;
        }
    }
}
A32X_COLD void Renderer::PrepareContactMask(const Actor &a,ContactMask &out) {
    out={};const uint8_t *c=camera.data,*views=c+BE32Aligned(c+20),*view=nullptr;
    for(unsigned i=0;i<BE16Aligned(c+18);++i) if(BE16Aligned(views+i*16)==(unsigned)a.room) {
        // Unusual duplicate room records keep the generic mask path.
        if(view) return;
        view=views+i*16;
    }
    if(!view || BE16Aligned(view+4)>32) return;
    out.records=c+BE32Aligned(view+12);
    for(unsigned i=0;i<BE16Aligned(view+4);++i)
        if(Renderer_MaskActive(a,c,out.records+i*12)) out.active|=uint32_t(1)<<i;
}
bool Renderer::DepthMask(const Actor &a,Rect tile,uint8_t *bits,const ContactMask *prepared) {
    const uint8_t *c=camera.data,*views=c+BE32Aligned(c+20);bool any=false;
    if(prepared && prepared->records) {
        const uint8_t *record=prepared->records;
        for(uint32_t active=prepared->active;active;active>>=1,record+=12)
            if(active&1) DepthMaskRows(c,record,tile,bits,any);
        return any;
    }
    for(unsigned i=0;i<BE16Aligned(c+18);++i) {
        const uint8_t *view=views+16*i;if(BE16Aligned(view)!=(unsigned)a.room) continue;
        const uint8_t *m=c+BE32Aligned(view+12);
        for(unsigned j=0;j<BE16Aligned(view+4);++j) {
            const uint8_t *mask=m+j*12;if(!Renderer_MaskActive(a,c,mask)) continue;
            DepthMaskRows(c,mask,tile,bits,any);
        }
    }
    return any;
}

void Renderer::DrawEffects(const World &world) {
    const uint8_t *c=camera.data;
    Rotation rotation=PrepareRotation(BS16Aligned(c),BS16Aligned(c+2),BS16Aligned(c+4));
    for(const auto &e:world.effects) {
        if(!e.count || e.floor!=world.floor) continue;
        bool visible=false;const uint8_t *views=c+BE32Aligned(c+20);
        for(unsigned i=0;i<BE16Aligned(c+18);++i) if(BE16Aligned(views+16*i)==(unsigned)e.room) visible=true;
        if(!visible) continue;
        Asset r=world.RoomAsset(e.floor,e.room);if(!r.data) continue;
        Vec3 translation={(BS16Aligned(c+6)-BS16Aligned(r.data))*10,(BS16Aligned(r.data+2)-BS16Aligned(c+8))*10,(BS16Aligned(r.data+4)-BS16Aligned(c+10))*10};
        unsigned age=world.now-e.since;
        for(unsigned i=0;i<e.count;++i) {
            const auto &q=e.points[i];
            Vec3 v={q.x-translation.x,q.y-translation.y-(int)age*(e.mode==1?2:6),q.z-translation.z};
            v.x+=((int)(i%5)-2)*(int)age;v.z+=((int)(i%7)-3)*(int)age;
            Rotate(v,rotation);v.z+=BS16Aligned(c+12);if(v.z<51) continue;
            Point screen=RenderProject(v,BS16Aligned(c+14),BS16Aligned(c+16),{160,100},false);
            int x=screen.x,y=screen.y;
            int radius=Clamp(RenderDivide((e.mode==0?50:20)*BS16Aligned(c+14),v.z)/2,0,3);
            // Triple the projected diameter, including one-pixel distant points.
            if(e.mode==0) radius=3*radius+1;
            if(((i+age/12)&3)!=0 || age<e.duration/2) Box(x-radius,y-radius,2*radius+1,2*radius+1,e.color+(i&3));
        }
    }
}

// Shared contact inputs are immutable until the worker Finish fence. SH7604
// writes are write-through; only the slave reads them through uncached aliases.
// Each CPU clears and exclusively owns its half of the depth scratch.
struct Renderer::ContactContext {
    Renderer *renderer;
    const Actor *const *actors;
    const DepthPrimitive *commands;
    const Rect *bounds;
    const uint16_t *ends;
    const ContactMask *masks;
    unsigned count;
    Rect area;
    bool uncached;
};
#if !defined(__sh__)
static unsigned contact_stats[8];
extern "C" unsigned renderer_contact_stats(unsigned field) { return field<8?contact_stats[field]:0; }
#endif
template<class T> static T *ContactRead(T *p) {
#if defined(__sh__)
    return (T *)((uintptr_t)p|0x20000000u);
#else
    return p;
#endif
}
void Renderer::ContactWorker(void *data,RasterSurface &surface) {
    ContactContext context=*ContactRead((ContactContext *)data);
    context.actors=ContactRead(context.actors);context.commands=ContactRead(context.commands);
    context.bounds=ContactRead(context.bounds);
    context.ends=ContactRead(context.ends);context.uncached=true;
    context.masks=ContactRead(context.masks);
    uint16_t *depths=context.renderer->contact_depth+64*32;
    ContactRead(context.renderer)->ContactTiles(context,surface,depths);
}
void Renderer::ContactTiles(const ContactContext &context,RasterSurface &surface,uint16_t *depths) {
    Rect area=context.area;area.y1=Max(area.y1,surface.first);area.y2=Min(area.y2,surface.last-1);
    for(int y=area.y1;y<=area.y2;y+=32) for(int x=area.x1;x<=area.x2;x+=64) {
        Rect tile={x,y,Min(x+63,area.x2),Min(y+31,area.y2)};
        for(unsigned j=0;j<(unsigned)(tile.y2-tile.y1+1)*64;++j) depths[j]=0;
        unsigned begin=0;
        for(unsigned i=0;i<context.count;++i) {
            unsigned end=context.ends[i];if(begin==end) continue;
            const Actor *actor=context.actors[i];if(context.uncached) actor=ContactRead(actor);
            uint32_t blocked[128];
            const uint8_t *mask=nullptr;bool mask_ready=false;
            for(unsigned f=begin;f<end;++f) {
                const Rect &bounds=context.bounds[f];
                if(bounds.x1>tile.x2 || bounds.x2<tile.x1 || bounds.y1>tile.y2 || bounds.y2<tile.y1) continue;
                // Architectural masks are needed only if this actor actually
                // contributes a primitive to the tile. Read them once then.
                if(!mask_ready) { mask=DepthMask(*actor,tile,(uint8_t *)blocked,context.masks+i)?(uint8_t *)blocked:nullptr;mask_ready=true; }
                RasterDepthVisible(surface,context.commands[f],tile,depths,mask);
            }
            begin=end;
        }
    }
}

void Renderer::ContactVertices(const Actor &a,unsigned offset,bool reused,bool &near) {
    const uint8_t *c=camera.data;
    Rotation rotation=PrepareRotation(BS16Aligned(c),BS16Aligned(c+2),BS16Aligned(c+4));
    Vec3 *vertices=Actor_GameplayScratch();
    Vec3 translation={};
    if(!reused) {
        Actor_Vertices(a,vertices);
        Asset r=Platform_ReadAsset(floor_rooms[a.floor][a.room]);
        translation={(BS16Aligned(c+6)-BS16Aligned(r.data))*10,(BS16Aligned(r.data+2)-BS16Aligned(c+8))*10,(BS16Aligned(r.data+4)-BS16Aligned(c+10))*10};
    }
    for(unsigned v=0;v<BE16Aligned(a.model.data+2);++v) {
        Vec3 q;
        if(reused) q=single.vertices[v];
        else {
            q={vertices[v].x+a.pos.x-translation.x,vertices[v].y+a.pos.y-translation.y,vertices[v].z+a.pos.z-translation.z};
            Rotate(q,rotation);q.z+=BS16Aligned(c+12);
        }
        if(q.z<=100) near=true;
        CompactVertex &out=combined[offset+v];out.x=Clamp(q.x,-32768,32767);out.y=Clamp(q.y,-32768,32767);out.z=Clamp(q.z,-32768,32767);
        if(q.z>100) { Point p=reused?single.projected[v]:RenderProject(q,BS16Aligned(c+14),BS16Aligned(c+16),{160,100});out.sx=p.x;out.sy=p.y; }
    }
    // Ordinary groups reuse camera-space X for reciprocal depth computed
    // once per vertex. Near-rejected groups use their valid vertices only
    // in the fallback path and compute those depths there.
    if(!near) for(unsigned v=0;v<BE16Aligned(a.model.data+2);++v) { CompactVertex &q=combined[offset+v];q.x=(int16_t)RenderDivide(1<<20,q.z); }
}

bool Renderer::ContactModel(const Actor &a,unsigned offset,Rect area,DepthPrimitive *commands,unsigned &total,unsigned capacity) {
    const uint8_t *c=camera.data;
    const uint8_t *m=a.model.data,*directory=m+BE32Aligned(m+32);
    for(unsigned f=0;f<BE16Aligned(m+6);++f) {
        const uint8_t *p=m+BE32Aligned(directory+4*f);unsigned n=p[1];
        if(p[0]!=1) {
            const CompactVertex &v=combined[offset+BE16Aligned(p+6)];
            DepthPrimitive out={};out.x[0]=v.sx;out.y[0]=v.sy;out.q=v.x;out.color=p[2];out.material=p[3];
            Rect bounds={v.sx,v.sy,v.sx,v.sy};
            if(p[0]==0 && n==2) {
                const CompactVertex &b=combined[offset+BE16Aligned(p+8)];
                out.kind=0;out.x[1]=b.sx;out.y[1]=b.sy;out.dx=b.x-v.x;
                int dx=b.sx-v.sx,dy=b.sy-v.sy;out.dy=Max(dx<0?-dx:dx,dy<0?-dy:dy);
                bounds={Min(v.sx,b.sx),Min(v.sy,b.sy),Max(v.sx,b.sx),Max(v.sy,b.sy)};
            } else {
                out.kind=2;int size=p[0]==3?RenderDivide(BE16Aligned(p+4)*BS16Aligned(c+14),v.z)/2:p[0]==7?RenderDivide(20*BS16Aligned(c+14),v.z)/2:p[0]==6?1:0;
                out.dx=Clamp(size,0,120);bounds={v.sx-out.dx,v.sy-out.dx,v.sx+out.dx,v.sy+out.dx};
            }
            if(bounds.x1>area.x2 || bounds.x2<area.x1 || bounds.y1>area.y2 || bounds.y2<area.y1) continue;
            if(total==capacity) return false;
            commands[total++]=out;continue;
        }
        if(n<3) continue;
        Point screen[MAX_POLY];int q[MAX_POLY];
        for(unsigned v=0;v<n;++v) { const CompactVertex &a=combined[offset+BE16Aligned(p+6+2*v)];screen[v]={a.sx,a.sy};q[v]=a.x; }
        int winding=0;
        for(unsigned v=1;v+1<n && !winding;++v)
            winding=(screen[v].x-screen[0].x)*(screen[v+1].y-screen[0].y)-(screen[v].y-screen[0].y)*(screen[v+1].x-screen[0].x);
        if(winding<=0) continue;
        for(unsigned v=1;v+1<n;++v) {
            Point triangle[]={screen[0],screen[v],screen[v+1]};int inv[]={q[0],q[v],q[v+1]};
            Rect bounds={Min(triangle[0].x,Min(triangle[1].x,triangle[2].x)),Min(triangle[0].y,Min(triangle[1].y,triangle[2].y)),
                         Max(triangle[0].x,Max(triangle[1].x,triangle[2].x)),Max(triangle[0].y,Max(triangle[1].y,triangle[2].y))};
            if(bounds.x1>area.x2 || bounds.x2<area.x1 || bounds.y1>area.y2 || bounds.y2<area.y1) continue;
            if(total==capacity) return false;
            if(RasterPrepareDepthTriangle(commands[total],triangle,inv,p[2],p[3])) ++total;
        }
    }
    return true;
}

struct __attribute__((may_alias)) ContactCacheHeader {
    uint32_t magic,key,actors_low,actors_high;
    uint16_t count,ends[MAX_ACTIVE];
};
bool Renderer::ResolveOverlap(const Actor *const *actors,unsigned count,Rect area,const Actor *projected,const ContactCache *cache) {
    if(count>MAX_ACTIVE) return false;
    ContactCacheHeader *header=nullptr;DepthPrimitive *program=nullptr;
    unsigned cache_capacity=0;bool cache_ready=false;
    if(cache && cache->actors && cache->data && !((uintptr_t)cache->data&3) && cache->size>=sizeof(ContactCacheHeader)+sizeof(DepthPrimitive)) {
        header=(ContactCacheHeader *)cache->data;program=(DepthPrimitive *)(header+1);
        cache_capacity=(cache->size-sizeof(*header))/sizeof(DepthPrimitive);
        bool matching=header->key==cache->key && header->count==count &&
                      header->actors_low==(uint32_t)cache->actors && header->actors_high==(uint32_t)(cache->actors>>32);
        cache_ready=header->magic==0x43445031u && matching;
        // Remember a program that did not fit until its key/allocation changes;
        // scarce spare storage must not cause a failed full preparation per draw.
        if(matching && header->magic==0x43445030u) {
            header=nullptr;
#if !defined(__sh__)
            ++contact_stats[7];
#endif
        }
        unsigned previous=0;
        for(unsigned i=0;cache_ready && i<count;++i) {
            unsigned end=header->ends[i];
            cache_ready=end>=previous && end<=cache_capacity && ((cache->actors&(uint64_t(1)<<i)) || end==previous);
            previous=end;
        }
    }
    uint64_t skipped=cache_ready?cache->actors:0;
#if !defined(__sh__)
    if(cache_ready) ++contact_stats[4];
#endif
    unsigned offsets[MAX_ACTIVE],used=0,reused=count;bool near[MAX_ACTIVE]={};
    for(unsigned i=0;i<count;++i) if(actors[i]==projected) { reused=i;break; }
    if(reused<count && (skipped&(uint64_t(1)<<reused))) reused=count;
    // Convert the live ordinary projection first, at offset zero. Compact
    // writes trail source vertices and cannot reach the projected-point tail.
    // Other actors then occupy the rest of the union without clobbering it.
    if(reused<count) { offsets[reused]=0;used=BE16Aligned(projected->model.data+2); }
    for(unsigned i=0;i<count;++i) if(i!=reused) { offsets[i]=used;used+=BE16Aligned(actors[i]->model.data+2); }
    // Two maximum-size source models fit; larger groups retain painter order.
    if(used>768) return false;
    Vec3 *vertices=Actor_GameplayScratch();
    for(unsigned pass=0;pass<count;++pass) {
        unsigned i=reused<count?(pass==0?reused:pass<=reused?pass-1:pass):pass;
        if(!(skipped&(uint64_t(1)<<i))) ContactVertices(*actors[i],offsets[i],i==reused,near[i]);
    }
    area={Max(0,area.x1),Max(0,area.y1),Min(319,area.x2),Min(199,area.y2)};
    if(area.x1>area.x2 || area.y1>area.y2) return true;
    // Prepare visible faces once, before either CPU draws. The former gameplay
    // vertex workspace is no longer needed after the transforms above.
    // Unusual near-clipped or oversized command groups retain the old path.
    for(unsigned i=0;i<count;++i) if(near[i]) {
        for(unsigned j=0;j<count;++j) if(skipped&(uint64_t(1)<<j)) ContactVertices(*actors[j],offsets[j],false,near[j]);
#if !defined(__sh__)
        ++contact_stats[1];
#endif
        FinishRestore();ContactFallback(actors,count,area,offsets,near);return true;
    }
    DepthPrimitive *commands=(DepthPrimitive *)vertices;
    constexpr unsigned capacity=sizeof(Vec3)*MAX_VERTICES/sizeof(DepthPrimitive);
    static_assert(capacity<=MAX_VERTICES,"Contact bounds must cover every prepared command");
    unsigned total=0;uint16_t ends[MAX_ACTIVE];
    if(header && !cache_ready) {
        unsigned cached_total=0;header->magic=0;bool complete=true;
        for(unsigned i=0;i<count;++i) {
            if((cache->actors&(uint64_t(1)<<i)) &&
               !ContactModel(*actors[i],offsets[i],{0,0,319,199},program,cached_total,cache_capacity)) { complete=false;break; }
            header->ends[i]=(uint16_t)cached_total;
        }
        header->key=cache->key;header->count=(uint16_t)count;
        header->actors_low=(uint32_t)cache->actors;header->actors_high=(uint32_t)(cache->actors>>32);
        header->magic=complete?0x43445031u:0x43445030u;cache_ready=complete;
        if(complete) {
#if !defined(__sh__)
            ++contact_stats[5];
#endif
        }
#if !defined(__sh__)
        else ++contact_stats[6];
#endif
    }
    for(unsigned i=0;i<count;++i) {
        if(cache_ready && (cache->actors&(uint64_t(1)<<i))) {
            unsigned first=i?header->ends[i-1]:0;
            for(unsigned f=first;f<header->ends[i];++f) {
                Rect b=RasterDepthBounds(program[f]);
                if(b.x1>area.x2 || b.x2<area.x1 || b.y1>area.y2 || b.y2<area.y1) continue;
                if(total==capacity) goto fallback;
                commands[total++]=program[f];
            }
        } else if(!ContactModel(*actors[i],offsets[i],area,commands,total,capacity)) goto fallback;
        ends[i]=(uint16_t)total;
    }
    {
#if !defined(__sh__)
        ++contact_stats[0];contact_stats[3]=Max(contact_stats[3],total);
#endif
        RasterSurface surface={target,0,GAME_HEIGHT,damage[buffer_index]};
        // All commands now own their projection/depth data. Preserve combined
        // vertices for every fallback above, then reuse them for tile culling.
        for(unsigned f=0;f<total;++f) contact_bounds[f]=RasterDepthBounds(commands[f]);
        ContactMask masks[MAX_ACTIVE];
        for(unsigned i=0;i<count;++i) PrepareContactMask(*actors[i],masks[i]);
        ContactContext context={this,actors,commands,contact_bounds,ends,masks,count,area,false};
        bool parallel=area.y2-area.y1>=15 && total>=12;
        FinishRestore();
        if(parallel) RendererWorker_Contact(surface,ContactWorker,&context,RendererWorker_ContactSplit(area.y1,area.y2+1));
        ContactTiles(context,surface,contact_depth);
        if(parallel) RendererWorker_Finish(surface);
        damage[buffer_index]=surface.damage;
    }
    return true;
fallback:
    FinishRestore();
    for(unsigned i=0;i<count;++i) if(skipped&(uint64_t(1)<<i)) ContactVertices(*actors[i],offsets[i],false,near[i]);
#if !defined(__sh__)
    ++contact_stats[2];
#endif
    ContactFallback(actors,count,area,offsets,near);
    return true;
}

A32X_COLD void Renderer::ContactFallback(const Actor *const *actors,unsigned count,Rect area,const unsigned *offsets,const bool *near) {
    const uint8_t *c=camera.data;
    // A 64 x 64 depth tile reuses primitive-sort scratch; it adds only
    // 2 KiB to SDRAM instead of allocating a full-screen Z buffer.
    // Cached scenery still handles normal frames; only contact regions pay
    // for per-pixel depth and every vertex is transformed once for the group.
    uint16_t *depths=contact_depth;
    area={Max(0,area.x1),Max(0,area.y1),Min(319,area.x2),Min(199,area.y2)};
    RasterSurface surface={target,0,GAME_HEIGHT,damage[buffer_index]};
    ContactMask masks[MAX_ACTIVE];
    for(unsigned i=0;i<count;++i) PrepareContactMask(*actors[i],masks[i]);
    for(int y=area.y1;y<=area.y2;y+=64) for(int x=area.x1;x<=area.x2;x+=64) {
        Rect tile={x,y,Min(x+63,area.x2),Min(y+63,area.y2)};
        for(unsigned j=0;j<64*64;++j) depths[j]=0;
        for(unsigned i=0;i<count;++i) {
            // Clip each model before it contributes depth. Restoring a prop's
            // mask after the whole group would erase an unmasked nearer actor.
            uint32_t blocked[128];
            const uint8_t *mask=DepthMask(*actors[i],tile,(uint8_t *)blocked,masks+i)?(uint8_t *)blocked:nullptr;
            const uint8_t *m=actors[i]->model.data,*directory=m+BE32Aligned(m+32);
            for(unsigned f=0;f<BE16Aligned(m+6);++f) {
                const uint8_t *p=m+BE32Aligned(directory+4*f);unsigned n=p[1];
                if(p[0]!=1) {
                    const CompactVertex &v=combined[offsets[i]+BE16Aligned(p+6)];if(v.z<=100) continue;
                    int size=p[0]==3?RenderDivide(BE16Aligned(p+4)*BS16Aligned(c+14),v.z)/2:p[0]==7?RenderDivide(20*BS16Aligned(c+14),v.z)/2:p[0]==6?1:0;
                    int inv=near[i]?RenderDivide(1<<20,v.z):v.x;
                    if(p[0]==0 && n==2) {
                        const CompactVertex &b=combined[offsets[i]+BE16Aligned(p+8)];if(b.z<=100) continue;
                        int dx=b.sx-v.sx,dy=b.sy-v.sy,steps=Max(dx<0?-dx:dx,dy<0?-dy:dy),end=near[i]?RenderDivide(1<<20,b.z):b.x;
                        for(int t=0;t<=steps;++t) { Point point={v.sx+(steps?dx*t/steps:0),v.sy+(steps?dy*t/steps:0)};RasterDepthPoint(surface,point,inv+(steps?(end-inv)*t/steps:0),0,tile,depths,p[2],p[3],mask); }
                    } else RasterDepthPoint(surface,{v.sx,v.sy},inv,Clamp(size,0,120),tile,depths,p[2],p[3],mask);
                    continue;
                }
                if(n<3) continue;
                // The contact path must preserve the same whole-face near
                // rejection as ordinary and precompiled world rendering.
                bool rejected=false;
                for(unsigned v=0;v<n;++v) if(combined[offsets[i]+BE16Aligned(p+6+2*v)].z<=100) { rejected=true;break; }
                if(rejected) continue;
                Point screen[MAX_POLY];int q[MAX_POLY];unsigned size=n;
                for(unsigned v=0;v<n;++v) { const CompactVertex &a=combined[offsets[i]+BE16Aligned(p+6+2*v)];screen[v]={a.sx,a.sy};q[v]=near[i]?RenderDivide(1<<20,a.z):a.x; }
                int winding=0;
                for(unsigned v=1;v+1<size && !winding;++v)
                    winding=(screen[v].x-screen[0].x)*(screen[v+1].y-screen[0].y)-(screen[v].y-screen[0].y)*(screen[v+1].x-screen[0].x);
                if(winding<=0) continue;
                for(unsigned v=1;v+1<size;++v) { Point triangle[]={screen[0],screen[v],screen[v+1]};int inv[]={q[0],q[v],q[v+1]};RasterDepthTriangle(surface,triangle,inv,tile,depths,p[2],p[3],mask); }
            }
        }
    }
    damage[buffer_index]=surface.damage;
}
