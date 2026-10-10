// SPDX-License-Identifier: GPL-2.0-or-later
// Build-time capture of the same native integer renderer, before camera masks.
#include "../../src/render/render_api.hpp"
#include "../../src/platform/platform_api.hpp"
#include <cstdlib>
static Renderer renderer;
static Actor actor;
static uint16_t pixels[320*200/2];
extern "C" void Platform_Fatal() { std::abort(); }
extern "C" void raster_init(const uint8_t *bank,unsigned size) { Platform_SetAssetBank(bank,size);renderer.target=pixels; }
extern "C" void raster_pose(int character,int body,int floor,int room,int x,int y,int z,int alpha,int beta,int gamma) {
    actor.character=character;actor.floor=floor;actor.room=room;
    actor.pos={x,y,z};actor.alpha=alpha;actor.beta=beta;actor.gamma=gamma;
    Actor_SetModel(actor,body);Actor_Bounds(actor,1);
}
extern "C" unsigned raster_key() { return Renderer_RasterKey(actor); }
extern "C" const void *raster_draw(int floor,int camera,int room,unsigned sentinel) {
    if(!renderer.SetCamera(camera,floor,room)) std::abort();
    for(auto &pixel:pixels) pixel=(uint16_t)(sentinel*257u);
    renderer.damage[0]={320,200,-1,-1};renderer.coverage_mode=false;
    renderer.DrawActor(actor);return pixels;
}
extern "C" int raster_bound(int field) { int v[]={renderer.last_bounds.x1,renderer.last_bounds.y1,renderer.last_bounds.x2,renderer.last_bounds.y2};return v[field]; }
