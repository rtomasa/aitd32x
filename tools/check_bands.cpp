// SPDX-License-Identifier: GPL-2.0-or-later
// Verify disjoint whole-row raster ownership against an unsplit surface.
// Compile with -I<project> and <project>/src/render/raster.cpp only.
#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include "src/render/raster.hpp"

struct Primitive {
    unsigned type,count;
    std::array<Point,4> points;
    uint8_t color;
    int size;
};
using Case=std::vector<Primitive>;
static constexpr unsigned words=GAME_WIDTH*GAME_HEIGHT/2,guard=16;
using Buffer=std::array<uint16_t,words+guard*2>;
static constexpr Rect empty={GAME_WIDTH,GAME_HEIGHT,-1,-1};
static uint32_t random_state=0x32a17d06;
static uint32_t Random() {
    random_state^=random_state<<13;random_state^=random_state>>17;
    random_state^=random_state<<5;return random_state;
}
static int Coordinate(int low,int high) { return low+int(Random()%unsigned(high-low+1)); }
static bool SameRect(const Rect &a,const Rect &b) {
    return a.x1==b.x1 && a.y1==b.y1 && a.x2==b.x2 && a.y2==b.y2;
}
static bool IsEmpty(const Rect &r) { return r.x1>r.x2 || r.y1>r.y2; }
static void Fail(unsigned index,int split,const char *reason) {
    std::fprintf(stderr,"case %u split %d: %s\n",index,split,reason);std::exit(1);
}
static void Initialize(Buffer &buffer,unsigned index) {
    buffer.fill(0x55aa);
    // Nonzero, unequal adjacent bytes expose read/modify/write endpoint errors.
    for(unsigned i=0;i<words;++i) buffer[guard+i]=uint16_t((i*73+(i/160)*11+index*37)^0xa7c3);
}
static void CheckGuards(const Buffer &buffer,unsigned index,int split) {
    for(unsigned i=0;i<guard;++i)
        if(buffer[i]!=0x55aa || buffer[guard+words+i]!=0x55aa)
            Fail(index,split,"framebuffer guard changed");
}
static void Draw(RasterSurface &surface,const Primitive &p) {
    RasterPrimitive(surface,p.type,p.points.data(),p.count,p.color,p.size);
}
static Primitive Make(unsigned type,std::initializer_list<Point> points,uint8_t color,int size=0) {
    Primitive p={type,unsigned(points.size()),{},color,size};
    std::copy(points.begin(),points.end(),p.points.begin());return p;
}

int main() {
    std::vector<Case> cases;
    const uint8_t colors[]={0,1,255};
    const Point triangles[][3]={
        {{10,10},{50,10},{30,140}},{{10,10},{50,140},{30,140}},
        {{20,20},{20,20},{80,170}},{{40,-4096},{40,4096},{40,66}},
        {{-4096,-4096},{4096,199},{0,4096}},{{-4096,0},{4096,0},{160,200}},
        {{318,197},{319,199},{320,200}},{{-7,-13},{11,117},{5,7}}
    };
    for(const auto &shape:triangles) for(unsigned reversed=0;reversed<2;++reversed)
        for(uint8_t color:colors) {
            Primitive p=Make(1,{shape[0],shape[1],shape[2]},color);
            if(reversed) std::swap(p.points[1],p.points[2]);
            cases.push_back({p});
        }
    const Point quads[][4]={
        {{-4096,-4096},{4096,-4096},{4096,4096},{-4096,4096}},
        {{3,-1},{319,0},{160,66},{3,200}},
        {{12,1},{300,199},{300,1},{12,199}},
        {{100,100},{100,100},{100,100},{100,100}}
    };
    for(const auto &shape:quads) for(unsigned reversed=0;reversed<2;++reversed)
        for(uint8_t color:colors) {
            Primitive p=Make(1,{shape[0],shape[1],shape[2],shape[3]},color);
            if(reversed) std::reverse(p.points.begin(),p.points.end());
            cases.push_back({p});
        }
    const Point lines[][2]={
        {{-4096,-4096},{4096,4096}},{{4096,-4096},{-4096,4096}},
        {{0,100},{319,100}},{{1,-4096},{1,4096}},
        {{319,199},{319,199}},{{1,66},{318,66}},
        {{-100,-1},{400,-1}},{{-100,200},{400,200}}
    };
    for(const auto &shape:lines) for(uint8_t color:colors)
        cases.push_back({Make(0,{shape[0],shape[1]},color)});
    const Point points[]={{0,0},{1,1},{318,66},{319,100},{0,199},{319,200},{-1,100},{4096,-4096}};
    for(Point point:points) for(uint8_t color:colors) cases.push_back({Make(2,{point},color)});
    const Point sphere_centers[]={{0,0},{1,66},{160,100},{319,199},{160,-5},{160,205},{-4096,66},{4096,100}};
    for(unsigned i=0;i<8;++i) for(uint8_t color:colors)
        cases.push_back({Make(7,{sphere_centers[i]},color,i%3==0?0:i%3==1?17:255)});
    for(unsigned i=0;i<40;++i) {
        Primitive p={1,i%3==0?4u:3u,{},colors[i%3],0};
        int low=i%7==0?-4096:-50,high_x=i%7==0?4096:370,high_y=i%7==0?4096:250;
        for(unsigned j=0;j<p.count;++j) p.points[j]={Coordinate(low,high_x),Coordinate(low,high_y)};
        if(i%5==0) p.points[1].y=p.points[0].y;
        if(i%11==0) p.points[2]=p.points[1];
        cases.push_back({p});
    }
    // Ordered overlaps check accumulated damage and repeated endpoint words.
    for(unsigned i=0;i<16;++i) {
        int y=int(i)*13-1;
        cases.push_back({
            Make(1,{{-7,-3},{160,100},{319,203}},colors[i%3]),
            Make(1,{{1,y},{318,y},{318,y+41},{1,y+41}},0),
            Make(0,{{319,0},{0,199}},255),
            Make(2,{{int(i&1)+159,y}},0),
            Make(7,{{int(i&1)+159,y+17}},1,19)
        });
    }
    if(cases.size()!=200) { std::fprintf(stderr,"unexpected case count %zu\n",cases.size());return 1; }
    constexpr int splits[]={0,1,66,100,199,200};
    Buffer full,banded,initial;
    unsigned comparisons=0,primitive_calls=0;
    for(unsigned index=0;index<cases.size();++index) {
        Initialize(initial,index);full=initial;
        RasterSurface whole={full.data()+guard,0,GAME_HEIGHT,empty};
        for(const Primitive &p:cases[index]) { Draw(whole,p);++primitive_calls; }
        CheckGuards(full,index,-1);
        for(int split:splits) {
            banded=initial;
            RasterSurface top={banded.data()+guard,0,split,empty};
            RasterSurface bottom={banded.data()+guard,split,GAME_HEIGHT,empty};
            for(const Primitive &p:cases[index]) {
                Draw(top,p);++primitive_calls;
                if(std::memcmp(banded.data()+guard+split*160,initial.data()+guard+split*160,
                               size_t(GAME_HEIGHT-split)*GAME_WIDTH))
                    Fail(index,split,"upper band wrote a lower row");
                CheckGuards(banded,index,split);
            }
            for(const Primitive &p:cases[index]) {
                Draw(bottom,p);++primitive_calls;
                if(std::memcmp(banded.data()+guard,full.data()+guard,size_t(split)*GAME_WIDTH))
                    Fail(index,split,"lower band changed an upper row");
                CheckGuards(banded,index,split);
            }
            if(std::memcmp(full.data()+guard,banded.data()+guard,words*2))
                Fail(index,split,"banded pixels differ from full surface");
            Rect combined={Min(top.damage.x1,bottom.damage.x1),Min(top.damage.y1,bottom.damage.y1),
                           Max(top.damage.x2,bottom.damage.x2),Max(top.damage.y2,bottom.damage.y2)};
            if(!SameRect(whole.damage,combined)) Fail(index,split,"band damage union differs");
            if(!IsEmpty(top.damage) && (top.damage.y1<0 || top.damage.y2>=split))
                Fail(index,split,"upper damage escaped its band");
            if(!IsEmpty(bottom.damage) && (bottom.damage.y1<split || bottom.damage.y2>=GAME_HEIGHT))
                Fail(index,split,"lower damage escaped its band");
            ++comparisons;
        }
    }
    std::printf("cases=%zu splits=6 comparisons=%u primitive_calls=%u pixels/damage/ownership/guards=ok\n",
                cases.size(),comparisons,primitive_calls);
}
