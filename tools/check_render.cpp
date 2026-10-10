// SPDX-License-Identifier: GPL-2.0-or-later
#include "../src/render/render_api.hpp"
#include "../src/render/raster.hpp"
#include "../src/engine/world.hpp"
#include "../src/platform/platform_api.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <vector>
extern "C" void Platform_Fatal() { std::abort(); }
static void Put16(uint8_t *p,unsigned v) { p[0]=v>>8;p[1]=v; }
static void Put32(uint8_t *p,unsigned v) { Put16(p,v>>16);Put16(p+2,v); }
static unsigned Count(const uint8_t *p,unsigned n,uint8_t color) {
    unsigned result=0;for(unsigned i=0;i<n;++i) result+=p[i]==color;return result;
}
static void Require(bool ok,const char *message) {
    if(!ok) { std::fprintf(stderr,"%s\n",message);std::exit(1); }
}
int main() {
    // A single type-2 eye primitive, with a camera that makes its projected
    // footprint directly observable. Exercise the real rasterizer and restore.
    uint8_t model[114]={},camera[24]={},room[32]={};
    Put16(model+2,1);Put16(model+6,1);
    Put32(model+20,36);Put32(model+24,44);Put32(model+28,44);Put32(model+32,44);
    Put32(model+44,48);model[48]=2;model[49]=1;model[50]=7;Put16(model+52,0);
    Put16(camera+14,200);Put16(camera+16,200);Put32(camera+20,24);
    uint16_t physical[SCREEN_WIDTH*SCREEN_HEIGHT/2]={};
    Renderer renderer{};
    renderer.target=physical+GAME_Y_OFFSET*160;
    renderer.camera={camera,sizeof(camera),sizeof(camera),3,0};
    renderer.room={room,sizeof(room),sizeof(room),4,0};
    renderer.full_restore[0]=true;
    Actor actor{};actor.model={model,sizeof(model),sizeof(model),5,0};
    actor.pos.z=2000;renderer.Restore();renderer.DrawActor(actor);
    Require(Count((uint8_t *)renderer.target,GAME_WIDTH*GAME_HEIGHT,7)==1,"type-2 point grew into a near-camera billboard");
    actor.pos.z=8000;renderer.Restore();renderer.DrawActor(actor);
    Require(Count((uint8_t *)renderer.target,GAME_WIDTH*GAME_HEIGHT,7)==1,"type-2 point left stale pixels at a different depth");
    // Dog eyes are spheres (type 3), rather than player type-2 points.
    model[48]=3;Put16(model+52,16);
    for(int distance: {2000,8000}) {
        actor.pos.z=distance;renderer.full_restore[0]=true;renderer.Restore();renderer.DrawActor(actor);
        Require(Count((uint8_t*)renderer.target,GAME_WIDTH*GAME_HEIGHT,7)==1,"small sphere eye retained the three-pixel minimum");
    }
    uint8_t before[GAME_WIDTH*GAME_HEIGHT];std::memcpy(before,(const void *)renderer.target,sizeof(before));
    Renderer_DrawFPS(physical,126,true);
    Require(!std::memcmp(before,(const void *)renderer.target,sizeof(before)),"FPS overlay changed game pixels");
    const uint8_t *pixels=(const uint8_t *)physical;
    Require(Count(pixels,12*320,1)>0,"FPS text was not visible");
    for(unsigned y=0;y<12;++y) for(unsigned x=0;x<320;++x)
        if(!(y>=2 && y<10 && x>=4 && x<68)) Require(pixels[y*320+x]==0,"FPS text escaped its border rectangle");
    Require(Count(pixels+212*320,12*320,0)==12*320,"bottom border was changed");
    // The same material pattern must cross the dual-CPU split without a seam.
    uint16_t all[GAME_WIDTH*GAME_HEIGHT/2],split[GAME_WIDTH*GAME_HEIGHT/2];
    for(unsigned i=0;i<GAME_WIDTH*GAME_HEIGHT/2;++i) all[i]=split[i]=0x0505;
    Point glass[]={{10,95},{30,95},{30,110},{10,110}};
    Rect empty={320,200,-1,-1};
    RasterSurface a={all,0,200,empty},b={split,0,100,empty},c={split,100,200,empty};
    RasterPrimitive(a,1,glass,4,9,0,2);RasterPrimitive(b,1,glass,4,9,0,2);RasterPrimitive(c,1,glass,4,9,0,2);
    Require(!std::memcmp(all,split,sizeof all),"transparent glass changed across CPU row split");
    const uint8_t *g=(const uint8_t *)all;
    for(int y=96;y<109;++y) for(int x=11;x<30;++x) Require(g[y*320+x]==(((x+y)&1)?5:9),"glass did not preserve alternating scenery pixels");
    // Intersecting arm/chair triangles: front order changes across the image.
    Point triangle[]={{8,8},{56,8},{8,56}};int arm[]={900,100,900},chair[]={500,500,500};
    Rect tile={0,0,63,63};uint16_t depth[64*64]={};
    for(unsigned i=0;i<GAME_WIDTH*GAME_HEIGHT/2;++i) all[i]=split[i]=0;
    RasterSurface d={all,0,200,empty};
    RasterDepthTriangle(d,triangle,chair,tile,depth,5,0);RasterDepthTriangle(d,triangle,arm,tile,depth,7,0);
    std::memset(depth,0,sizeof depth);RasterSurface e={split,0,200,empty};
    RasterDepthTriangle(e,triangle,arm,tile,depth,7,0);RasterDepthTriangle(e,triangle,chair,tile,depth,5,0);
    for(int y=0;y<200;++y) for(int x=0;x<320;++x) {
        // At x=32 the surfaces intersect exactly; either coplanar color is
        // valid under the renderer's LEQUAL tie rule.
        if(x!=32) Require(((uint8_t*)all)[y*320+x]==((uint8_t*)split)[y*320+x],"noncoplanar polygons depend on actor draw order");
    }
    Require(((uint8_t *)all)[16*320+16]==7 && ((uint8_t *)all)[16*320+44]==5,"depth did not separate the front and back portions of a limb");
    // Coverage is captured while shading, including black opaque pixels and
    // glass holes. An independent monochrome draw is the footprint oracle.
    uint8_t bits[8000]={},split_bits[8000]={};
    std::memset(all,0,sizeof all);std::memset(split,0,sizeof split);
    uint16_t mono[GAME_WIDTH*GAME_HEIGHT/2]={};
    RasterSurface recorded={all,0,200,empty,0,bits},upper={split,0,100,empty,0,split_bits},lower={split,100,200,empty,0,split_bits},oracle={mono,0,200,empty};
    Point opaque[]={{19,91},{48,91},{48,106},{19,106}};
    Point glass_capture[]={{12,95},{55,95},{55,111},{12,111}};
    for(auto *s:{&recorded,&upper,&lower}) { RasterPrimitive(*s,1,opaque,4,0,0,0);RasterPrimitive(*s,1,glass_capture,4,9,0,2); }
    RasterPrimitive(oracle,1,opaque,4,1,0,0);RasterPrimitive(oracle,1,glass_capture,4,1,0,2);
    Require(!std::memcmp(all,split,sizeof all) && !std::memcmp(bits,split_bits,sizeof bits),"colored coverage changed across the CPU split");
    for(unsigned i=0;i<64000;++i) Require(bool(bits[i/8]&(1u<<(i&7)))==bool(((uint8_t*)mono)[i]),"captured coverage lost black pixels or glass transparency");
    // Masks must use original camera pixels even after static props are baked.
    // Raw camera masks and black pixels; compressed cameras are rejected.
    uint8_t masked_camera[78]={};std::memcpy(masked_camera,camera,24);
    Put16(masked_camera+18,1);Put32(masked_camera+20,24);
    Put16(masked_camera+28,1);Put32(masked_camera+36,40);
    Put16(masked_camera+40,1);Put16(masked_camera+42,3);
    Put32(masked_camera+44,52);Put32(masked_camera+48,60);
    Put16(masked_camera+52,-1000);Put16(masked_camera+54,-1000);
    Put16(masked_camera+56,1000);Put16(masked_camera+58,1000);
    for(int y=99;y<=101;++y) { uint8_t *s=masked_camera+60+6*(y-99);Put16(s,y);Put16(s+2,159);Put16(s+4,161); }
    std::vector<uint8_t> original(64000,3);original[100*320+160]=0;
    for(bool compressed:{false,true}) {
        Put16(masked_camera+18,1);Put16(masked_camera+28,1);
        std::vector<uint8_t> encoded;
        if(compressed) for(unsigned i=0;i<original.size();) {
            unsigned n=1;while(n<255 && i+n<original.size() && original[i+n]==original[i]) ++n;
            encoded.push_back(n);encoded.push_back(original[i]);i+=n;
        } else encoded=original;
        std::vector<uint8_t> bank(112,0);Put32(bank.data(),0x41333258);Put32(bank.data()+4,2);Put32(bank.data()+8,6);
        auto asset=[&](unsigned id,const uint8_t *bytes,unsigned size,unsigned unpacked,unsigned flags) {
            while(bank.size()&3) bank.push_back(0);
            unsigned offset=bank.size();bank.insert(bank.end(),bytes,bytes+size);
            uint8_t *e=bank.data()+16+16*id;Put32(e,offset);Put32(e+4,size);Put32(e+8,unpacked);Put16(e+14,flags);
        };
        uint8_t pal[512]={};asset(0,pal,512,512,0);asset(3,room,sizeof(room),sizeof(room),0);
        asset(4,masked_camera,sizeof(masked_camera),sizeof(masked_camera),0);asset(5,encoded.data(),encoded.size(),64000,compressed);
        Put32(bank.data()+12,bank.size());Platform_SetAssetBank(bank.data(),bank.size());
        if(compressed) { Require(!renderer.SetCamera(0),"compressed camera unexpectedly accepted");continue; }
        Require(renderer.SetCamera(0),"mask background asset did not load");
        for(int y=99;y<=101;++y) for(int x=159;x<=161;++x) renderer.background[y*320+x]=9;
        renderer.Restore();model[48]=3;Put16(model+52,20);actor.pos.z=2000;renderer.DrawActor(actor);
        const uint8_t *p=(const uint8_t *)renderer.target;
        for(int y=99;y<=101;++y) for(int x=159;x<=161;++x) Require(p[y*320+x]==original[y*320+x],"mask repainted a baked prop over the actor");
        CachedSpan spans[200];renderer.SetCamera(0);renderer.Restore();
        unsigned n=renderer.DrawCachedActor(actor,spans,200);
        Require(n==0,"architectural mask left covered pixels in the static silhouette");
        // Remove the mask and use a black sphere: its coverage must survive
        // even though its pixel value equals the background's transparent zero.
        Put16(masked_camera+18,0);std::memcpy(bank.data()+BE32(bank.data()+16+4*16),masked_camera,sizeof(masked_camera));
        renderer.SetCamera(0);renderer.Restore();model[50]=0;
        n=renderer.DrawCachedActor(actor,spans,200);Require(n==3,"black sphere silhouette was not captured during its colored draw");
        for(unsigned i=0;i<n;++i) Require(spans[i].length==3,"sphere silhouette span width changed");
        model[50]=7;
        // Retain the room view for SPECIAL visibility, without its mask.
        Put16(masked_camera+18,1);Put16(masked_camera+28,0);
        std::memcpy(bank.data()+BE32(bank.data()+16+4*16),masked_camera,sizeof(masked_camera));
        // Real SPECIAL hit/death creation and projected raster footprints.
        World world{};world.active[0].id=0;world.poses[0].floor=world.poses[0].room=0;
        world.rng=77;world.Special(0,1);Require(world.effects[0].color==80 && world.rng==77,"hit effect did not use the red palette or changed gameplay RNG");
        world.effects[0].count=1;world.effects[0].points[0]={0,0,1000};
        renderer.SetCamera(0);renderer.Restore();renderer.DrawEffects(world);
        Require(Count((const uint8_t*)renderer.target,64000,80)==25,"hit particle footprint changed");
        world.effects[0].count=0;world.Special(0,0);world.effects[0].count=1;
        for(int distance:{1000,5000,10000}) {
            world.effects[0].points[0]={0,0,(int16_t)distance};renderer.Restore();renderer.DrawEffects(world);
            unsigned expected=distance==1000?441:distance==5000?81:9;
            Require(Count((const uint8_t*)renderer.target,64000,192)==expected,"death particle was not three times the original projected width/height");
        }
    }
    std::puts("Eyes, FPS border, glass CPU split, contact depth, raw masks and compressed-camera rejection, colored static coverage, red hits and enlarged death particles passed");
}
