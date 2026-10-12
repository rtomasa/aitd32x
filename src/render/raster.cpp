// SPDX-License-Identifier: GPL-2.0-or-later
#include "../platform/pixel_words.hpp"
#include "raster.hpp"
#include "divide.hpp"
#include "../engine/actor.hpp"
static uint16_t Pair(uint8_t left,uint8_t right) {
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    return (uint16_t)(left|((unsigned)right<<8));
#else
    return (uint16_t)(((unsigned)left<<8)|right);
#endif
}
static inline void StoreSpan(volatile uint16_t *p,int x1,int x2,uint8_t color) {
    if(x1&1) {
        volatile uint8_t *bytes=(volatile uint8_t *)(p+x1/2);
        if(color) bytes[1]=color;
        else p[x1/2]=Pair(bytes[0],color);
        ++x1;
    }
    if(!(x2&1) && x1<=x2) {
        volatile uint8_t *bytes=(volatile uint8_t *)(p+x2/2);
        if(color) bytes[0]=color;
        else p[x2/2]=Pair(color,bytes[1]);
        --x2;
    }
    uint16_t two=Pair(color,color);
    if(x1<=x2) {
        p+=x1/2;
        int count=(x2-x1+1)/2;
        PixelFillWords(p,count,two);
    }
}
void RasterCoverageSpan(volatile uint8_t *bits,int y,int left,int right,bool clear,uint8_t material) {
    if(left>right) return;
    unsigned first=left/8,last=right/8;
    uint8_t pattern=material==2?((y&1)?0xaa:0x55):0xff;
    volatile uint8_t *row=bits+y*40;
    for(unsigned x=first;x<=last;++x) {
        uint8_t mask=pattern;
        if(x==first) mask&=(uint8_t)(0xffu<<(left&7));
        if(x==last) mask&=(uint8_t)(0xffu>>(7-(right&7)));
        if(mask==0xff) row[x]=clear?0:0xff;
        else if(clear) row[x]&=(uint8_t)~mask;
        else row[x]|=mask;
    }
}
static inline void MaterialSpan(volatile uint16_t *p,int y,int left,int right,uint8_t color,uint8_t material,volatile uint8_t *coverage) {
    if(coverage) RasterCoverageSpan(coverage,y,left,right,false,material);
    if(material!=2) { StoreSpan(p,left,right,color);return; }
    // Indexed packed pixels have no alpha unit. A fixed screen-door pattern
    // preserves the scenery through glass, without a blend table in SDRAM.
    for(int x=left+((left+y)&1);x<=right;x+=2) {
        volatile uint16_t *word=p+x/2;
        volatile uint8_t *bytes=(volatile uint8_t *)word;
        if(color) bytes[x&1]=color;
        else *word=(x&1)?Pair(bytes[0],0):Pair(0,bytes[1]);
    }
}
void RasterSpan(RasterSurface &surface,int y,int x1,int x2,uint8_t color) {
    if(y<surface.first || y>=surface.last) return;
    x1=Max(0,x1);x2=Min(GAME_WIDTH-1,x2);if(x1>x2) return;
    Rect &damage_rect=surface.damage;
    damage_rect.x1=Min(damage_rect.x1,x1);damage_rect.x2=Max(damage_rect.x2,x2);
    damage_rect.y1=Min(damage_rect.y1,y);damage_rect.y2=Max(damage_rect.y2,y);
    MaterialSpan(surface.target+y*(GAME_WIDTH/2),y,x1,x2,color,surface.material,surface.coverage);
}

// Keep the original edge direction's truncation correction. Reversing a
// bottom-up edge changes the rounding rule used by the original rasterizer.
struct RasterEdge { int first,last,x,step,error,error_step,denominator; };
static bool MakeEdge(const RasterSurface &surface,const Point &a,const Point &b,RasterEdge &e) {
    int first=Max(surface.first,Min(a.y,b.y)),last=Min(surface.last,Max(a.y,b.y));
    if(first>=last) return false;
    int dy=b.y-a.y,dx=b.x-a.x,den=dy<0?-dy:dy;
    int advance=dy<0?-dx:dx,x,error=0;
    if(first==Min(a.y,b.y)) {
        // The first row is an endpoint: its quotient and remainder are known.
        x=dy<0?b.x:a.x;
    } else {
        int numerator=advance*(first-a.y);
        int q=RenderDivide(numerator,den);error=numerator-q*den;
        if(error<0) { --q;error+=den; }
        x=a.x+q;
    }
    // Narrow edges have a known integer quotient. Avoid waiting on DIVU for
    // the common zero-quotient case; a one-row edge also has an exact slope.
    int step=0;
    if(den==1) step=advance;
    else if(advance>=den || advance<=-den) step=RenderDivide(advance,den);
    int error_step=advance-step*den;
    if(error_step<0) { --step;error_step+=den; }
    // Convert the original direction's ceiling rule into the DDA's initial
    // fractional phase. Subsequent rows then need no separate sign correction:
    // floor(value + (den-1)/den) equals ceil(value) for this integer edge.
    if(dx<0) {
        if(error) { ++x;--error; }
        else error=den-1;
    }
    e={first,last,x,step,error,error_step,den};
    return true;
}
static inline void StepEdge(RasterEdge &e) {
    int x=e.x+e.step,error=e.error+e.error_step;
    if(error>=e.denominator) { ++x;error-=e.denominator; }
    e.x=x;e.error=error;
}
void RasterPolygon(RasterSurface &surface,const Point *p,unsigned n,uint8_t color) {
    if(n==3) RasterTriangle(surface,p,color);
    else if(n>3) RasterPolygonGeneral(surface,p,n,color);
}
void RasterTriangle(RasterSurface &surface,const Point *p,uint8_t color) {
    RasterEdge edges[3];unsigned count=0;
    for(unsigned i=0,j=2;i<3;j=i++) if(MakeEdge(surface,p[j],p[i],edges[count])) ++count;
    if(count<2) return;
    int y=GAME_HEIGHT,last=0;
    for(unsigned i=0;i<count;++i) { y=Min(y,edges[i].first);last=Max(last,edges[i].last); }
    Rect bounds={GAME_WIDTH,GAME_HEIGHT,-1,-1};
    while(y<last) {
        RasterEdge *active[2];unsigned found=0;int end=last;
        for(unsigned i=0;i<count;++i) {
            RasterEdge &e=edges[i];
            if(e.first<=y && y<e.last) { active[found++]=&e;end=Min(end,e.last); }
            else if(e.first>y) end=Min(end,e.first);
        }
        // A triangle has two active edges between consecutive vertex rows.
        if(found==2) {
            RasterEdge &a=*active[0],&b=*active[1];
            volatile uint16_t *row=surface.target+y*(GAME_WIDTH/2);
            for(;y<end;++y,row+=GAME_WIDTH/2) {
                int left=a.x,right=b.x;
                if(left>right) { int t=left;left=right;right=t; }
                left=Max(0,left);right=Min(GAME_WIDTH-1,right);
                if(left<=right) {
                    bounds.x1=Min(bounds.x1,left);bounds.x2=Max(bounds.x2,right);
                    if(bounds.y1==GAME_HEIGHT) bounds.y1=y;
                    bounds.y2=y;
                    MaterialSpan(row,y,left,right,color,surface.material,surface.coverage);
                }
                StepEdge(a);StepEdge(b);
            }
        } else y=end;
    }
    if(bounds.x1<=bounds.x2) {
        Rect &d=surface.damage;
        d.x1=Min(d.x1,bounds.x1);d.x2=Max(d.x2,bounds.x2);
        d.y1=Min(d.y1,bounds.y1);d.y2=Max(d.y2,bounds.y2);
    }
}
void RasterPolygonGeneral(RasterSurface &surface,const Point *p,unsigned n,uint8_t color) {
    RasterEdge edges[MAX_POLY];unsigned edge_count=0;
    int ymin=199,ymax=0;
    for(unsigned i=0;i<n;++i) { ymin=Min(ymin,p[i].y);ymax=Max(ymax,p[i].y); }
    ymin=Max(surface.first,ymin);ymax=Min(surface.last-1,ymax);
    for(unsigned i=0,j=n-1;i<n;j=i++) if(MakeEdge(surface,p[j],p[i],edges[edge_count])) ++edge_count;
    for(int y=ymin;y<=ymax;++y) {
        int intersections[MAX_POLY],count=0;
        for(unsigned i=0;i<edge_count;++i) {
            RasterEdge &e=edges[i];
            if(y>=e.first && y<e.last) {
                int x=e.x;
                unsigned k=count;
                while(k && intersections[k-1]>x) { intersections[k]=intersections[k-1];--k; }
                intersections[k]=x;++count;StepEdge(e);
            }
        }
        for(int i=0;i+1<count;i+=2) RasterSpan(surface,y,intersections[i],intersections[i+1],color);
    }
}
void RasterPrimitive(RasterSurface &surface,unsigned type,const Point *screen,unsigned count,uint8_t color,int size,uint8_t material) {
    surface.material=material;
    if(type==1) RasterPolygon(surface,screen,count,color);
    else if(type==0 && count==2) {
        int dx=screen[1].x-screen[0].x,dy=screen[1].y-screen[0].y,steps=Max(dx<0?-dx:dx,dy<0?-dy:dy);
        for(int i=0;i<=steps;++i) {
            int x=screen[0].x+(steps?dx*i/steps:0);
            RasterSpan(surface,screen[0].y+(steps?dy*i/steps:0),x,x,color);
        }
    } else if(type==2) RasterSpan(surface,screen[0].y,screen[0].x,screen[0].x,color);
    else for(int y=-size;y<=size;++y) {
        int half=size-(y<0?-y:y)/2;
        RasterSpan(surface,screen[0].y+y,screen[0].x-half,screen[0].x+half,color);
    }
}

bool RasterPrepareDepthTriangle(DepthPrimitive &out,const Point *p,const int *q,uint8_t color,uint8_t material) {
    int area=(p[1].x-p[0].x)*(p[2].y-p[0].y)-(p[1].y-p[0].y)*(p[2].x-p[0].x);
    if(area<=0) return false;
    for(unsigned i=0;i<3;++i) { out.x[i]=(int16_t)p[i].x;out.y[i]=(int16_t)p[i].y; }
    out.q=q[0]*256;
    out.dx=RenderDivideWide(((int64_t)(q[1]-q[0])*(p[2].y-p[0].y)-(int64_t)(q[2]-q[0])*(p[1].y-p[0].y))*256,area);
    out.dy=RenderDivideWide(((int64_t)(p[1].x-p[0].x)*(q[2]-q[0])-(int64_t)(p[2].x-p[0].x)*(q[1]-q[0]))*256,area);
    out.kind=1;out.color=color;out.material=material;out.pad=0;
    return true;
}

static void DepthTriangle(RasterSurface &surface,const Point *p,int q,int dx,int dy,Rect tile,uint16_t *depth,uint8_t color,uint8_t material,const uint8_t *mask) {
    int top=Min(p[0].y,Min(p[1].y,p[2].y)),bottom=Max(p[0].y,Max(p[1].y,p[2].y));
    RasterSurface clipped=surface;clipped.first=tile.y1;clipped.last=tile.y2+1;
    RasterEdge edges[3];unsigned count=0;
    for(unsigned i=0,k=2;i<3;k=i++) if(MakeEdge(clipped,p[k],p[i],edges[count])) ++count;
    Rect written={GAME_WIDTH,GAME_HEIGHT,-1,-1};
    for(int y=Max(top,tile.y1);y<=Min(bottom,tile.y2);++y) {
        int a=4096,b=-4096;
        for(unsigned i=0;i<count;++i) { RasterEdge &e=edges[i];if(y>=e.first && y<e.last) { a=Min(a,e.x);b=Max(b,e.x);StepEdge(e); } }
        a=Max(a,tile.x1);b=Min(b,tile.x2);if(a>b) continue;
        int z=q+dx*(a-p[0].x)+dy*(y-p[0].y);
        uint16_t *row=depth+(y-tile.y1)*64;
        int first=GAME_WIDTH,last=-1;
        for(int x=a;x<=b;++x,z+=dx) {
            if(material==2 && ((x+y)&1)) continue;
            unsigned bit=(y-tile.y1)*64+x-tile.x1;
            if(mask && (mask[bit/8]&(1u<<(bit&7)))) continue;
            int value=Clamp((z+128)>>8,1,65535);unsigned index=x-tile.x1;
            if(value<row[index]) continue;
            row[index]=(uint16_t)value;
            volatile uint16_t *word=surface.target+y*160+x/2;
            volatile uint8_t *bytes=(volatile uint8_t *)word;
            if(color) bytes[x&1]=color;
            else *word=(x&1)?Pair(bytes[0],0):Pair(0,bytes[1]);
            if(first==GAME_WIDTH) first=x;
            last=x;
        }
        if(last>=first) { written.x1=Min(written.x1,first);written.x2=Max(written.x2,last);written.y1=Min(written.y1,y);written.y2=y; }
    }
    if(written.x1<=written.x2) { Rect &d=surface.damage;d.x1=Min(d.x1,written.x1);d.x2=Max(d.x2,written.x2);d.y1=Min(d.y1,written.y1);d.y2=Max(d.y2,written.y2); }
}

void RasterDepthTriangle(RasterSurface &surface,const Point *p,const int *q,Rect tile,uint16_t *depth,uint8_t color,uint8_t material,const uint8_t *mask) {
    int left=Min(p[0].x,Min(p[1].x,p[2].x)),right=Max(p[0].x,Max(p[1].x,p[2].x));
    int top=Min(p[0].y,Min(p[1].y,p[2].y)),bottom=Max(p[0].y,Max(p[1].y,p[2].y));
    if(left>tile.x2 || right<tile.x1 || top>tile.y2 || bottom<tile.y1) return;
    DepthPrimitive prepared;
    if(RasterPrepareDepthTriangle(prepared,p,q,color,material))
        DepthTriangle(surface,p,prepared.q,prepared.dx,prepared.dy,tile,depth,color,material,mask);
}

A32X_COLD Rect RasterDepthBounds(const DepthPrimitive &p) {
    int left=p.x[0],right=left,top=p.y[0],bottom=top;
    unsigned count=p.kind==1?3:p.kind==0?2:1;
    for(unsigned i=1;i<count;++i) { left=Min(left,p.x[i]);right=Max(right,p.x[i]);top=Min(top,p.y[i]);bottom=Max(bottom,p.y[i]); }
    if(p.kind==2) { left-=p.dx;right+=p.dx;top-=p.dx;bottom+=p.dx; }
    return {left,top,right,bottom};
}
void RasterDepthPrimitive(RasterSurface &surface,const DepthPrimitive &p,Rect tile,uint16_t *depth,const uint8_t *mask) {
    Rect bounds=RasterDepthBounds(p);
    if(bounds.x1>tile.x2 || bounds.x2<tile.x1 || bounds.y1>tile.y2 || bounds.y2<tile.y1) return;
    RasterDepthVisible(surface,p,tile,depth,mask);
}
void RasterDepthVisible(RasterSurface &surface,const DepthPrimitive &p,Rect tile,uint16_t *depth,const uint8_t *mask) {
    if(p.kind==1) {
        Point points[]={{p.x[0],p.y[0]},{p.x[1],p.y[1]},{p.x[2],p.y[2]}};
        DepthTriangle(surface,points,p.q,p.dx,p.dy,tile,depth,p.color,p.material,mask);
    } else if(p.kind==0) {
        int dx=p.x[1]-p.x[0],dy=p.y[1]-p.y[0],steps=p.dy;
        for(int t=0;t<=steps;++t) {
            Point point={p.x[0]+(steps?dx*t/steps:0),p.y[0]+(steps?dy*t/steps:0)};
            RasterDepthPoint(surface,point,p.q+(steps?p.dx*t/steps:0),0,tile,depth,p.color,p.material,mask);
        }
    } else RasterDepthPoint(surface,{p.x[0],p.y[0]},p.q,p.dx,tile,depth,p.color,p.material,mask);
}

void RasterDepthPoint(RasterSurface &surface,Point p,int q,int size,Rect tile,uint16_t *depth,uint8_t color,uint8_t material,const uint8_t *mask) {
    for(int y=Max(tile.y1,p.y-size);y<=Min(tile.y2,p.y+size);++y) {
        int dy=y-p.y;if(dy<0) dy=-dy;int half=size-dy/2;
        for(int x=Max(tile.x1,p.x-half);x<=Min(tile.x2,p.x+half);++x) {
            if(material==2 && ((x+y)&1)) continue;
            unsigned bit=(y-tile.y1)*64+x-tile.x1;
            if(mask && (mask[bit/8]&(1u<<(bit&7)))) continue;
            uint16_t &old=depth[(y-tile.y1)*64+x-tile.x1];
            if(q<old) continue;
            old=(uint16_t)q;
            volatile uint16_t *word=surface.target+y*160+x/2;volatile uint8_t *bytes=(volatile uint8_t *)word;
            if(color) bytes[x&1]=color;else *word=(x&1)?Pair(bytes[0],0):Pair(0,bytes[1]);
            Rect &d=surface.damage;d.x1=Min(d.x1,x);d.x2=Max(d.x2,x);d.y1=Min(d.y1,y);d.y2=Max(d.y2,y);
        }
    }
}
