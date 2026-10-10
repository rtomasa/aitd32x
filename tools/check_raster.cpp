// SPDX-License-Identifier: GPL-2.0-or-later
// Standalone differential coverage check for the v5 scan-conversion changes.
// Compile this file with -I<project>, <project>/src/render/render.cpp and font.cpp.
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <algorithm>
#include <iterator>
#include <inttypes.h>
#include "src/engine/actor.hpp"
#define private public
#include "src/render/render_api.hpp"
#undef private
#include "src/platform/platform_api.hpp"

// These are unused by direct Polygon/Span coverage, but referenced by render.o.
Asset Platform_ReadAsset(unsigned) { return {}; }
void Platform_SetAssetBank(const uint8_t *,uint32_t) {}
bool Platform_Decode(const Asset &,uint8_t *,uint32_t) { return false; }
extern "C" void Platform_Fatal() { std::abort(); }
void Actor_Vertices(const Actor &,Vec3 *) { std::abort(); }

static constexpr uint64_t basis=UINT64_C(14695981039346656037);
static uint64_t Hash(const void *data,size_t size,uint64_t h=basis) {
    const auto *p=static_cast<const uint8_t *>(data);
    while(size--) { h^=*p++;h*=UINT64_C(1099511628211); }
    return h;
}
static uint32_t rng=0x32a17d05;
static uint32_t Random() { rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng; }
static int Coordinate(int low,int high) { return low+int(Random()%unsigned(high-low+1)); }

int main(int argc,char **argv) {
    FILE *out=argc>1?std::fopen(argv[1],"w"):stdout;
    if(!out) { std::perror("raster report");return 1; }
    Renderer r{};
    constexpr unsigned words=GAME_WIDTH*GAME_HEIGHT/2,guard=16;
    uint16_t storage[words+guard*2];
    r.target=storage+guard;
    for(unsigned i=0;i<sizeof(r.background);++i)
        r.background[i]=uint8_t((i*73+(i/320)*11)%256);
    unsigned cases=0,triangles=0,quads=0,span_cases=0;
    uint64_t aggregate=basis;
    auto Begin=[&]() {
        std::fill(std::begin(storage),std::end(storage),uint16_t(0x55aa));
        r.buffer_index=cases&1;
        r.full_restore[r.buffer_index]=true;
        r.damage[r.buffer_index^1]={320,200,-1,-1};
        r.Restore();
    };
    auto Finish=[&](unsigned count,unsigned color) {
        uint64_t pixels=Hash((const void *)r.target,words*2);
        uint64_t damage=Hash(r.damage,sizeof(r.damage));
        aggregate=Hash((const void *)r.target,words*2,aggregate);
        aggregate=Hash(r.damage,sizeof(r.damage),aggregate);
        r.Restore();
        uint64_t restored=Hash((const void *)r.target,words*2);
        if(std::memcmp((const void *)r.target,r.background,words*2)) {
            std::fprintf(stderr,"restore left stale pixels at case %u\n",cases);std::exit(1);
        }
        for(unsigned i=0;i<guard;++i) if(storage[i]!=0x55aa || storage[guard+words+i]!=0x55aa) {
            std::fprintf(stderr,"framebuffer guard changed at case %u\n",cases);std::exit(1);
        }
        std::fprintf(out,"%04u n=%u color=%u pixels=%016" PRIx64 " damage=%016" PRIx64 " restored=%016" PRIx64 "\n",
                     cases,count,color,pixels,damage,restored);
        ++cases;
    };
    auto PolygonCase=[&](Point *points,unsigned n,uint8_t color) {
        Begin();r.Polygon(points,n,color);Finish(n,color);
        if(n==3) ++triangles;else ++quads;
    };
    // Include opposite windings, flat tops/bottoms, duplicate vertices,
    // horizontal/collinear triangles, border-sized slivers and full clipping.
    const Point special[][3]={
        {{10,10},{50,10},{30,40}},{{10,10},{50,40},{30,40}},
        {{20,20},{20,20},{80,70}},{{40,0},{40,199},{40,80}},
        {{-1,-1},{319,0},{0,199}},{{-4096,-4096},{4096,199},{0,4096}},
        {{-4096,0},{4096,0},{160,200}},{{0,-4096},{319,4096},{320,199}},
        {{0,0},{1,1},{0,2}},{{318,197},{319,199},{320,200}},
        {{-10,-10},{-1,-10},{-2,-1}},{{330,30},{500,180},{321,199}},
        {{10,200},{319,200},{150,400}},{{100,199},{101,199},{101,200}},
        {{-7,-13},{11,17},{5,7}},{{2,4},{5,6},{11,10}}
    };
    const uint8_t colors[]={0,1,255};
    const unsigned perm[][3]={{0,1,2},{0,2,1},{1,0,2},{1,2,0},{2,0,1},{2,1,0}};
    for(const auto &shape:special) for(const auto &order:perm) for(uint8_t color:colors) {
        Point p[3]={shape[order[0]],shape[order[1]],shape[order[2]]};PolygonCase(p,3,color);
    }
    for(unsigned i=0;i<720;++i) {
        Point p[3];
        int low=i%8==0?-4096:-40,high_x=i%8==0?4096:360,high_y=i%8==0?4096:240;
        for(auto &v:p) v={Coordinate(low,high_x),Coordinate(low,high_y)};
        if(i%11==0) p[1].y=p[0].y;
        if(i%13==0) p[2]=p[1];
        PolygonCase(p,3,colors[i%3]);
    }
    // Generic path: rectangles, concave quads, crossing quads and clipping.
    for(unsigned i=0;i<100;++i) {
        int x=Coordinate(-70,340),y=Coordinate(-70,220),w=Coordinate(0,160),h=Coordinate(0,140);
        Point p[4]={{x,y},{x+w,y},{x+w,y+h},{x,y+h}};
        if(i%3==0) p[2]={x+w/3,y+h/3};
        if(i%5==0) std::swap(p[1],p[2]);
        if(i&1) std::reverse(std::begin(p),std::end(p));
        PolygonCase(p,4,colors[i%3]);
    }
    const int spans[][3]={{0,0,0},{0,1,1},{1,0,1},{1,1,2},{2,2,3},{2,3,4},
        {3,-3,0},{3,319,323},{4,-4096,4096},{199,318,319},{-1,0,319},{200,0,319}};
    for(const auto &span:spans) for(uint8_t color:colors) {
        Begin();r.Span(span[0],span[1],span[2],color);Finish(2,color);++span_cases;
    }
    // Consecutive overlapping primitives verify a cumulative damage union.
    for(uint8_t color:colors) {
        Point p[3]={{-7,-3},{60,80},{3,140}},q[3]={{40,30},{170,10},{318,190}};
        Begin();r.Polygon(p,3,color);r.Polygon(q,3,uint8_t(color^255));Finish(6,color);
    }
    if(out!=stdout) std::fclose(out);
    std::fprintf(stderr,"cases=%u triangles=%u quads=%u spans=%u aggregate=%016" PRIx64 " restore/guards=ok\n",
                 cases,triangles,quads,span_cases,aggregate);
}
