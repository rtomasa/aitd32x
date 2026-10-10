// SPDX-License-Identifier: GPL-2.0-or-later
// Same engine and renderer as the ROM; only the output pointer differs.
#include "../src/engine/game.hpp"
#include "../src/engine/save.hpp"
#include "../src/platform/platform_api.hpp"
#include <stdlib.h>
static Game game;
static uint16_t pixels[SCREEN_WIDTH*SCREEN_HEIGHT/2];
extern "C" void Platform_Fatal() { abort(); }
extern "C" void host_init(const uint8_t *bank,unsigned size) {
    Platform_SetAssetBank(bank,size);game.Init();game.renderer.target=pixels+GAME_Y_OFFSET*160;
}
extern "C" void host_tick(unsigned pad) { game.Input(pad);game.Update();game.Draw(); }
extern "C" const void *host_pixels() { return pixels; }
extern "C" const void *host_palette() { return game.renderer.palette; }
// Diagnostic scene placement; never linked into the cartridge.
extern "C" void host_pose(int x,int z,int beta) {
    game.player.pos.x=x;game.player.pos.z=z;game.player.beta=beta;
    game.renderer.full_restore[0]=true;game.Draw();
}
extern "C" int host_state(unsigned field) {
    switch(field) { case 0:return game.tick;case 1:return game.camera;case 2:return game.player.pos.x;
    case 3:return game.player.pos.y;case 4:return game.player.pos.z;case 5:return game.player.beta;
    case 6:return game.mode;case 7:return game.paused;case 8:return game.character;default:return 0; }
}
extern "C" int host_world(unsigned field) {
    World &w=game.world;
    switch(field) { case 0:return w.floor;case 1:return w.room;case 2:return w.camera;case 3:return w.fault_code;
    case 4:return w.fault_life;case 5:return w.fault_pc;case 6:return w.inventory_count;case 7:return w.in_hand;
    case 8:return w.prompt;case 9:return w.peak_active;case 10:return w.camera_target;case 11:return w.ticks;
    case 12:return game.menu;case 13:return w.book;case 14:return w.finished;case 15:return w.music;case 16:return w.next_music;case 17:return game.book_line;default:return 0; }
}
extern "C" int host_object(int object,int field) { return game.world.Get(object,field); }
extern "C" int host_variable(int index) { return index>=0 && index<A32X_VAR_COUNT?game.world.vars[index]:-1; }
extern "C" int host_inventory(int index) { return index>=0 && index<game.world.inventory_count?game.world.inventory[index]:-1; }
extern "C" void host_place(int object,int floor,int room,int x,int y,int z,int beta) {
    int slot=game.world.Slot(object);if(slot<0) return;
    game.world.Stage(slot,floor,room,{x,y,z});game.world.Pose(slot).beta=beta;
}
extern "C" void host_found_life(int object,int action) { game.world.FoundLife(object,action); }
extern "C" void host_take(int object) { game.world.Take(object); }
extern "C" int host_active(int s,int field) {
    if(s<0 || s>=MAX_ACTIVE) return -1;
    ActiveObject &a=game.world.active[s];
    switch(field) { case 0:return a.id;case 1:return a.end_anim;case 2:return a.hard_dec;case 3:return a.hard_col;case 4:return a.value.v[O_TRACK_POS];case 5:return a.mark;case 6:return a.hit_by;case 7:return a.col_by;case 8:return a.col[0];default:return 0; }
}

extern "C" void host_set_object(int id,int field,int value) { game.world.Set(id,field,value); }
extern "C" void host_set_variable(int id,int value) { game.world.vars[id]=value; }
extern "C" void host_drop(int id,int source) { game.world.Drop(id,source); }
extern "C" int host_combat(int s,int field) {
    ActiveObject &a=game.world.active[s];
    switch(field) { case 0:return a.hit_type;case 1:return a.hit_force;case 2:return a.hit;case 3:return a.hit_anim;case 4:return a.hit_frame;case 5:return a.hit_group;default:return 0; }
}
extern "C" void host_draw_fresh() { game.static_signature=0;game.Draw(); }
extern "C" void host_draw_all() {
    game.renderer.full_restore[0]=true;game.renderer.Restore();
    int order[MAX_ACTIVE],count=game.world.DrawList(order);
    for(int i=0;i<count;++i) game.renderer.DrawActor(game.world.Pose(order[i]));
}
extern "C" void host_clear_message() { game.world.message=-1;game.world.prompt=-1;game.world.book=-1;game.menu=0;game.paused=false; }

extern "C" void host_animate(int id,int anim,int type,int next) { int s=game.world.Slot(id);if(s>=0) game.world.Animate(s,anim,type,next); }
extern "C" void host_bounds(int id,int type) { int s=game.world.Slot(id);if(s>=0) game.world.SetBounds(s,type); }

extern "C" int host_effects(int field) {
    if(field==0) return game.world.effect_serial;
    int count=0;for(auto &e:game.world.effects) count+=e.count;
    return count;
}
extern "C" void host_camera(int floor,int room,int camera) {
    game.world.floor=floor;game.world.room=room;game.world.camera=camera;
    game.world.view_changed=true;game.camera=camera;game.static_signature=0;
    game.renderer.SetCamera(camera,floor,room);game.Draw();
}
extern "C" int host_bounds_value(int id,int field) {
    int s=game.world.Slot(id);if(s<0) return 0;
    const Actor &p=game.world.Pose(s);
    int b[]={p.collision_min.x,p.collision_max.x,p.collision_min.y,p.collision_max.y,p.collision_min.z,p.collision_max.z};return b[field];
}

extern "C" void host_draw_cached() { game.Draw(); }
extern "C" void host_draw_painter() {
    game.renderer.SetCamera(game.camera,game.world.floor,game.world.room);
    game.renderer.Restore();
    int order[MAX_ACTIVE],count=game.world.DrawList(order);
    for(int i=0;i<count;++i) game.renderer.DrawActor(game.world.Pose(order[i]));
    game.renderer.DrawEffects(game.world);
}

extern "C" void host_draw_depth(int id) {
 int slot=game.world.Slot(id);if(slot<0)return;const Actor *a=&game.world.Pose(slot);
 game.renderer.ResolveOverlap(&a,1,{0,0,319,199});
}
extern "C" int host_box(int id,int field) {
 int s=game.world.Slot(id);if(s<0)return 0;Bounds b=game.world.Box(s,game.world.room);int v[]={b.lo.x,b.hi.x,b.lo.y,b.hi.y,b.lo.z,b.hi.z};return v[field];
}

extern "C" int host_render_bound(int id,int field) { int slot=game.world.Slot(id);if(slot<0)return -1;Rect r=game.static_bounds[slot];int b[]={r.x1,r.y1,r.x2,r.y2};return b[field]; }
extern "C" int host_draw_order(int i) {int order[MAX_ACTIVE],n=game.world.DrawList(order);return i<n?game.world.active[order[i]].id:-1;}

// Isolated UI captures without waiting for a scripted pickup/death in gameplay.
extern "C" void host_ui(int kind,int value) {
    host_clear_message();game.world.finished=false;game.world.fault_code=0;
    switch(kind) {
    case 0:game.world.message=value;game.world.message_until=game.world.now+100;break;
    case 1:game.world.prompt=value;break;
    case 2:game.menu=1;game.selection=0;break;
    case 3:game.menu=2;game.selection=0;game.action_selection=0;break;
    case 4:game.world.book=value;game.book_line=0;break;
    case 5:game.paused=true;game.menu=3;game.selection=game.action_selection=0;break;
    case 6:game.world.finished=true;game.world.cvars[15]=1;break;
    case 7:game.world.fault_code=1;break;
    }
    game.Draw();
}

// Fixed-prop differential renderer check; never linked into the cartridge.
static CachedSpan parity_spans[4096];
extern "C" unsigned host_prop_draw(int character,int body,int floor,int room,int camera,int x,int y,int z,int alpha,int beta,int gamma,int bounds_type,int sentinel) {
 Actor &a=game.player;a.character=character;a.floor=floor;a.room=room;
 a.pos={x,y,z};a.alpha=alpha;a.beta=beta;a.gamma=gamma;
 Actor_SetModel(a,body);Actor_Bounds(a,bounds_type);
 game.renderer.SetCamera(camera,floor,room);
 for(auto &p:pixels) p=(uint16_t)(sentinel*257u);
 game.renderer.damage[0]={320,200,-1,-1};
 return game.renderer.DrawCachedActor(a,parity_spans,4096);
}
extern "C" const void *host_prop_spans() { return parity_spans; }
extern "C" int host_prop_bound(int n) { Rect r=game.renderer.last_bounds;int v[]={r.x1,r.y1,r.x2,r.y2};return v[n]; }

extern "C" int host_save() { return Game_Save(game); }
extern "C" int host_load() { return Game_Load(game); }

extern "C" void host_delete(int id) { game.world.Delete(id); }
