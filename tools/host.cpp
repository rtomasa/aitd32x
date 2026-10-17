// SPDX-License-Identifier: GPL-2.0-or-later
// Same engine and renderer as the ROM; only the output pointer differs.
#include "../src/engine/game.hpp"
#include "../src/engine/save.hpp"
#include "../src/platform/platform_api.hpp"
#include <stdlib.h>
static Game game;
static uint16_t pixels[SCREEN_WIDTH*SCREEN_HEIGHT/2];
static uint16_t alternate_pixels[SCREEN_WIDTH*SCREEN_HEIGHT/2];
extern "C" void Platform_Fatal() { abort(); }
extern "C" void host_init(const uint8_t *bank,unsigned size) {
    Platform_SetAssetBank(bank,size);game.renderer.buffer_index=0;game.Init();game.renderer.target=pixels+GAME_Y_OFFSET*160;
}
extern "C" void host_tick(unsigned pad) { game.StartupAdvance(1500/GAME_HZ);game.Input(pad);game.Update();game.Draw(); }
extern "C" int host_startup(unsigned field) {
    switch(field) { case 0:return game.startup_phase;case 1:return game.startup_time;case 2:return game.startup_next;
    case 3:return game.book_line;case 4:return game.world.intro;case 5:return game.world.picture_id;
    case 6:return game.world.picture_duration;case 7:return game.world.cvars[15];default:return 0; }
}
// Direct gameplay fixture for focused existing checks; never linked into ROM.
extern "C" void host_startgame(int character) { game.character=character;game.StartGameplay();game.Draw(); }
extern "C" const void *host_pixels() { return game.renderer.buffer_index?alternate_pixels:pixels; }
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
extern "C" void host_clear_message() {
    if(game.menu || game.world.prompt>=0 || game.world.book>=0) game.ResetCache();
    game.world.message=-1;game.world.prompt=-1;game.world.book=-1;game.menu=0;game.paused=false;
}

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
// Full painter replay through the same contacts/effects/lighting pipeline.
// The oracle owns an independent host instance and changes no world state.
extern "C" void host_draw_uncached_scene() {
    game.renderer.SetCamera(game.camera,game.world.floor,game.world.room);
    game.ResetCache();
    for(int s=0;s<MAX_ACTIVE;++s) {
        game.static_owner[s]=(int16_t)game.world.active[s].id;
        game.static_quiet_since[s]=(uint16_t)game.world.ticks;
        game.dynamic_slots|=uint64_t(1)<<s;
    }
    game.DrawScene();
}
extern "C" uint64_t host_cache_slots(unsigned dynamic) { return dynamic?game.dynamic_slots:game.static_slots; }
// Exercise the same independent framebuffer damage histories as the cartridge.
extern "C" void host_buffer(unsigned bank) {
    game.renderer.buffer_index=bank&1;
    game.renderer.target=(bank&1?alternate_pixels:pixels)+GAME_Y_OFFSET*160;
}
extern "C" const void *host_background() { return game.renderer.background; }
extern "C" unsigned host_cache(unsigned field,unsigned slot) {
    if(field==0) return game.static_signature;
    if(field==1) return game.static_slots;
    if(field==2) return game.dynamic_slots;
    if(field==3) return game.renderer.full_restore[slot&1];
    if(slot>=MAX_ACTIVE) return 0;
    if(field==4) return game.static_hash[slot];
    if(field==5) return (unsigned)game.static_owner[slot];
    if(field==6) return game.static_rank[slot];
    if(field==7) return game.static_span_count[slot];
    if(field==8) return game.static_span_start[slot];
    return 0;
}
// Construct a valid prior bake with the opposite painter order. Geometry and
// masks stay identical, isolating the partial-order repair from gameplay.
extern "C" void host_reverse_static_cache() {
    int order[MAX_ACTIVE],count=game.world.DrawList(order);
    game.renderer.SetCamera(game.camera,game.world.floor,game.world.room);
    game.renderer.Restore();
    uint32_t signature=2166136261u;
    for(int i=count-1;i>=0;--i) {
        int slot=order[i];if(game.Dynamic(slot)) continue;
        game.renderer.DrawActor(game.world.Pose(slot));
        game.static_rank[slot]=(uint8_t)(count-1-i);
        signature=(signature^game.static_hash[slot])*16777619u;
    }
    game.renderer.BakeBackground();game.static_signature=signature;
}
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
// Transformed geometry diagnostics; output has three signed words per vertex.
extern "C" unsigned host_camera_vertices(int id,int32_t *output) {
    int s=game.world.Slot(id);if(s<0 || !game.world.Pose(s).model.data) return 0;
    const Actor &a=game.world.Pose(s);Vec3 *vertices=Actor_GameplayScratch();Actor_Vertices(a,vertices);
    Asset cam=Platform_ReadAsset(floor_cameras[game.world.floor][game.camera]);
    Asset room=game.world.RoomAsset(a.floor,a.room);const uint8_t *c=cam.data,*r=room.data;
    Vec3 translation={(BS16Aligned(c+6)-BS16Aligned(r))*10,(BS16Aligned(r+2)-BS16Aligned(c+8))*10,(BS16Aligned(r+4)-BS16Aligned(c+10))*10};
    Rotation rotation=PrepareRotation(BS16Aligned(c),BS16Aligned(c+2),BS16Aligned(c+4));
    unsigned count=BE16Aligned(a.model.data+2);
    for(unsigned i=0;i<count;++i) {
        Vec3 v={vertices[i].x+a.pos.x-translation.x,vertices[i].y+a.pos.y-translation.y,vertices[i].z+a.pos.z-translation.z};
        Rotate(v,rotation);v.z+=BS16Aligned(c+12);
        output[3*i]=v.x;output[3*i+1]=v.y;output[3*i+2]=v.z;
    }
    return count;
}

extern "C" int host_render_bound(int id,int field) { int slot=game.world.Slot(id);if(slot<0)return -1;Rect r=game.static_bounds[slot];int b[]={r.x1,r.y1,r.x2,r.y2};return b[field]; }
extern "C" int host_draw_order(int i) {int order[MAX_ACTIVE],n=game.world.DrawList(order);return i<n?game.world.active[order[i]].id:-1;}

// Isolated UI captures without waiting for a scripted pickup/death in gameplay.
extern "C" void host_ui(int kind,int value) {
    host_clear_message();game.world.finished=false;game.world.fault_code=0;
    switch(kind) {
    case 0:game.world.message=value;game.world.message_until=game.world.now+100;break;
    case 1:game.world.prompt=value;game.PickupEnter();break;
    case 2:game.InventoryEnter();break;
    case 3:game.InventoryEnter();game.menu=2;game.action_selection=0;break;
    case 4:game.world.book=value;game.book_line=0;break;
    case 5:game.paused=true;game.menu=3;game.selection=game.action_selection=0;game.inventory_dirty=true;break;
    case 6:game.world.finished=true;game.world.cvars[15]=1;break;
    case 7:game.world.fault_code=1;break;
    }
    game.dirty=true;game.Draw();
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

// Independent full-area depth capture for reported character/prop scenes.
extern "C" int host_resolve_pair(int first,int second) {
    int a=game.world.Slot(first),b=game.world.Slot(second);if(a<0 || b<0) return 0;
    const Actor *group[]={&game.world.Pose(a),&game.world.Pose(b)};
    return game.renderer.ResolveOverlap(group,2,{0,0,319,199});
}
// Bounded private scratch for cache-capacity/invalidation diagnostics. Native
// gameplay instead borrows unused bytes from its existing scenery span pool.
extern "C" int host_resolve_cached_pair(int first,int second,unsigned bytes,unsigned key,int reset) {
    alignas(4) static uint8_t scratch[8192];
    if(bytes>sizeof(scratch)) return 0;
    if(reset) for(auto &value:scratch) value=0;
    int a=game.world.Slot(first),b=game.world.Slot(second);if(a<0 || b<0) return 0;
    const Actor *group[]={&game.world.Pose(a),&game.world.Pose(b)};
    ContactCache cache={scratch,bytes,key,2};
    return game.renderer.ResolveOverlap(group,2,{0,0,319,199},nullptr,&cache);
}
extern "C" int host_resolve_group3(int first,int second,int third,int x1,int y1,int x2,int y2) {
    int ids[]={first,second,third};const Actor *group[3];
    for(int i=0;i<3;++i) { int s=game.world.Slot(ids[i]);if(s<0) return 0;group[i]=&game.world.Pose(s); }
    return game.renderer.ResolveOverlap(group,3,{x1,y1,x2,y2});
}
// Exercise contact bookkeeping beyond the old 24-slot bound with a valid
// one-vertex model; all 50 entries fit the existing 768-vertex scratch.
extern "C" int host_check_contact_capacity() {
    alignas(4) uint8_t model[56]={};
    auto word=[&](unsigned p,unsigned v) { model[p]=(uint8_t)(v>>8);model[p+1]=(uint8_t)v; };
    auto dword=[&](unsigned p,unsigned v) { word(p,v>>16);word(p+2,v); };
    word(2,1);word(6,1);dword(20,36);dword(24,42);dword(28,42);dword(32,42);
    dword(42,46);model[46]=2;model[47]=1;model[48]=15;word(50,8);
    Actor actor=game.player;actor.model={model,56,56,6,0};
    const Actor *group[MAX_ACTIVE+1];for(auto &p:group) p=&actor;
    return game.renderer.ResolveOverlap(group,MAX_ACTIVE,{0,0,319,199}) &&
           !game.renderer.ResolveOverlap(group,MAX_ACTIVE+1,{0,0,319,199});
}
extern "C" void host_draw_actor(int id) {
    int slot=game.world.Slot(id);if(slot>=0) game.renderer.DrawActor(game.world.Pose(slot));
}
extern "C" int host_group(int id,int group,int field) {
    int slot=game.world.Slot(id);if(slot<0 || group<0 || group>=MAX_GROUPS) return 0;
    const GroupState &g=game.world.Pose(slot).state[group];
    int values[]={g.type,g.delta.x,g.delta.y,g.delta.z};return field>=0 && field<4?values[field]:0;
}

// Full-house fixtures enter an original world without drawing or advancing
// LIFE. They never touch frontend save files or become part of the cartridge.
extern "C" void host_begin_world(int character,int floor,int room,int camera) {
    game.character=character;game.StartGameplay();
    World &w=game.world;w.Init(game.player,character,floor,room);
    int s=w.Slot(1);if(s>=0) w.Stage(s,floor,room,{0,0,0});
    else {
        w.Set(1,O_FLOOR,floor);w.Set(1,O_ROOM,room);
        w.Set(1,O_X,0);w.Set(1,O_Y,0);w.Set(1,O_Z,0);
    }
    w.floor=floor;w.room=room;w.camera=camera;w.RefreshActors();
    game.camera=camera;w.view_changed=true;game.ResetCache();
}
extern "C" void host_refresh_actors() { game.world.RefreshActors(); }
extern "C" void host_world_tick(unsigned pad,int acting) { game.world.Update((uint16_t)pad,acting!=0); }
extern "C" int host_run_life(int life,int id) {
    int s=game.world.Slot(id);if(s<0) return -1;
    game.world.RunLife(life,s);return game.world.fault_code;
}
extern "C" void host_movemode(int id,int mode,int track) {
    int s=game.world.Slot(id);if(s>=0) game.world.MoveMode(s,mode,track);
}
extern "C" void host_track(int id) { int s=game.world.Slot(id);if(s>=0) game.world.Track(s); }
extern "C" int host_speed(int id) { int s=game.world.Slot(id);return s>=0?game.world.active[s].speed:0; }
extern "C" int host_hit(int victim,int attacker,int force) {
    int v=game.world.Slot(victim),a=game.world.Slot(attacker);if(v<0 || a<0) return 0;
    game.world.active[v].hit_by=a;game.world.active[v].hit_force=force;return 1;
}
extern "C" int host_cvar(int index) { return index>=0 && index<45?game.world.cvars[index]:-1; }
extern "C" void host_set_cvar(int index,int value) { if(index>=0 && index<45) game.world.cvars[index]=(int16_t)value; }
extern "C" int host_dark() { return game.world.dark; }

// Full-game presentation fixtures; never linked into the cartridge.
extern "C" void host_start_ending(int complete) { game.StartEnding(complete!=0);game.Draw(); }
extern "C" void host_advance_presentation(unsigned units) { game.StartupAdvance(units);game.Draw(); }
extern "C" void host_game_over() { game.world.finished=true;game.world.cvars[15]=0; }

extern "C" void host_set_dark(int value) { game.world.dark=value!=0;game.dirty=true; }
