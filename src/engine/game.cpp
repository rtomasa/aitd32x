// SPDX-License-Identifier: GPL-2.0-or-later
#include "game.hpp"
#include "save.hpp"
#include "startup.hpp"
#include "../render/book.hpp"
#include "../platform/audio.hpp"
#include "../platform/platform_api.hpp"
namespace {
// The original image is immutable while the existing RAM image holds baked
// scenery. Intro metadata, models and audio are outside the mapper aperture.
struct OriginalImage {
    Renderer &renderer;Asset source;
    OriginalImage(Renderer &r):renderer(r),source(r.original_background) {
        if(source.flags&0x8000) {
            renderer.original_background=Platform_MapImage(source);
            if(!renderer.original_background.data) Platform_Fatal();
        }
    }
    ~OriginalImage() {
        if(source.flags&0x8000) {
            renderer.original_background=source;Platform_UnmapImage();
        }
    }
};
}
static A32X_COLD void Number(char *s,unsigned n) {
    char reverse[12];int count=0;do { reverse[count++]=(char)('0'+n%10);n/=10; }while(n);
    for(int i=0;i<count;++i) s[i]=reverse[count-1-i];
    s[count]=0;
}
static A32X_COLD int TextLines(Renderer &r,int x,int y,const char *text,int width,int rows,int skip=0) {
    int line=0;while(*text) {
        while(*text=='\r' || *text==' ') ++text;
        char output[40];int n=0,last_space=-1;const char *start=text;
        while(*text && *text!='\n' && *text!='\r' && n<width) { output[n]=*text++;if(output[n]==' ') last_space=n;++n; }
        if(n==width && *text && *text!='\n' && *text!='\r' && last_space>0) { n=last_space;text=start+n+1; }
        else if(*text=='\r') { ++text;if(*text=='\n') ++text; }
        else if(*text=='\n') ++text;
        output[n]=0;
        if(line>=skip && line<skip+rows) r.DrawText(x,y+(line-skip)*10,output);
        ++line;
        if(line>=skip+rows) break;
    }
    return line;
}
static A32X_COLD int InventoryActions(const World &w,int object,int *bits) {
    int count=0;unsigned flags=(uint16_t)w.objects[object].v[O_FOUND_FLAGS];
    for(int bit=0;bit<11;++bit) if(flags&(1u<<bit)) bits[count++]=bit;
    return count;
}
void Game::ResetCache() {
    static_signature=dynamic_slots=static_slots=0;for(auto &hash:static_hash) hash=0;
    for(int s=0;s<MAX_ACTIVE;++s) { static_owner[s]=-1;static_quiet_since[s]=0; }
}
A32X_COLD void Game::RebuildStaticOrder(const int *order,int count) {
    Rect area={320,200,-1,-1};
    auto include=[&](Rect b) {
        b={Max(0,b.x1),Max(0,b.y1),Min(319,b.x2),Min(199,b.y2)};
        if(b.x1>b.x2 || b.y1>b.y2) return;
        area={Min(area.x1,b.x1&~1),Min(area.y1,b.y1),Max(area.x2,b.x2|1),Max(area.y2,b.y2)};
    };
    auto intersects=[&](Rect b) { return b.x1<=area.x2 && b.x2>=area.x1 && b.y1<=area.y2 && b.y2>=area.y1; };
    // Only inversions of intersecting static footprints can change the bake.
    // Include mask writes too: an empty coverage list can still erase pixels.
    for(int i=0;i<count;++i) {
        int s=order[i];if(Dynamic(s)) continue;
        for(int j=i+1;j<count;++j) {
            int t=order[j];if(Dynamic(t) || static_rank[s]<static_rank[t]) continue;
            const Rect &a=static_bounds[s],&b=static_bounds[t];
            include({Max(a.x1,b.x1),Max(a.y1,b.y1),Min(a.x2,b.x2),Min(a.y2,b.y2)});
        }
    }
    renderer.Restore();
    if(area.x1>area.x2 || area.y1>area.y2) return;
    // Whole-actor replay avoids changing raster rounding at a clip boundary.
    // Expand to a fixed point so no replay or mask can write outside the bake.
    uint32_t redraw=0;
    bool expanded;
    do {
        expanded=false;
        for(int i=0;i<count;++i) {
            int s=order[i];if(Dynamic(s) || (redraw&(1u<<s)) || !intersects(static_bounds[s])) continue;
            redraw|=1u<<s;include(static_bounds[s]);expanded=true;
        }
    } while(expanded);
    renderer.RestoreOriginal(area);
    for(int i=0;i<count;++i) if(redraw&(1u<<order[i])) renderer.DrawActor(world.Pose(order[i]));
    renderer.BakeRegion(area);
}
A32X_COLD void Game::Init(bool boot) {
    Audio_Reset();ResetCache();
    tick=0;static_signature=0;held=pending_edges=0;mode=0;camera=0;character=0;paused=false;help=false;dirty=true;resync_clock=true;
    menu=selection=action_selection=book_line=0;action_blocked=false;
    world.intro=false;world.picture_id=-1;world.picture_duration=0;
    Actor_Init(player,character);Asset spawn=Platform_ReadAsset(AS_PLAYER_SPAWN);
    if(spawn.size!=16) Platform_Fatal();
    player.pos={BS16(spawn.data),BS16(spawn.data+2),BS16(spawn.data+4)};player.beta=BS16(spawn.data+8);
    startup_time=startup_since=startup_transition=0;StartupEnter(boot?STARTUP_LOGO:STARTUP_MENU);
}
void Game::Input(uint16_t pad) { pending_edges|=pad&~held;held=pad; }
void Game::Update() {
    ++tick;uint16_t edges=pending_edges;pending_edges=0;
    if(!mode) {
        StartupUpdate(edges);return;
    }
    if(Game_SystemInput(*this,edges)) return;
    if(!(held&PAD_A)) action_blocked=false;
    if(world.fault_code || world.finished) {
        if(edges&PAD_START) Init(false);
        return;
    }
    if(world.prompt>=0) {
        if(edges&PAD_A) { int object=world.prompt;world.prompt=-1;world.Take(object);action_blocked=true; }
        else if(edges&(PAD_C|PAD_B)) { world.objects[world.prompt].v[O_TRACK]=(int16_t)Max(1,world.now);world.prompt=-1;action_blocked=true; }
        dirty=true;return;
    }
    if(world.book>=0) {
        if(!edges) return;
        int previous=book_line;
        if(edges&(PAD_A|PAD_C)) { world.book=-1;book_line=0;action_blocked=true;Audio_Sample(world.cvars[0]); }
        else {
            unsigned pages=Book_Pages(world.book);
            if((edges&(PAD_DOWN|PAD_RIGHT|PAD_B)) && book_line+1<(int)pages) ++book_line;
            if(edges&(PAD_UP|PAD_LEFT)) book_line=Max(0,book_line-1);
            if(previous!=book_line) Audio_Sample(world.cvars[0]);
        }
        dirty=true;return;
    }
    if(menu) {
        if(!edges) return;
        if(edges&(PAD_C|PAD_B|PAD_START)) { if(menu==2) menu=1;else menu=0;action_blocked=true;dirty=true;return; }
        if(menu==1) {
            if(edges&PAD_DOWN) selection=(selection+1)%Max(1,world.inventory_count);
            if(edges&PAD_UP) selection=(selection+Max(1,world.inventory_count)-1)%Max(1,world.inventory_count);
            if((edges&PAD_A) && world.inventory_count) { menu=2;action_selection=0; }
        } else {
            int bits[11],object=world.inventory[selection],count=InventoryActions(world,object,bits);
            if(edges&PAD_DOWN) action_selection=(action_selection+1)%Max(1,count);
            if(edges&PAD_UP) action_selection=(action_selection+Max(1,count)-1)%Max(1,count);
            if((edges&PAD_A) && count) { world.FoundLife(object,1<<bits[action_selection]);menu=0;book_line=0;action_blocked=true; }
        }
        dirty=true;return;
    }
    if(edges&PAD_START) { paused=!paused;dirty=true; }
    if(paused) return;
    if((edges&PAD_C) && world.inventory_allowed) { menu=1;selection=0;dirty=true;return; }
    world.Update(held,(held&PAD_A) && !action_blocked);
    Audio_UpdateMusic(world.music,world.next_music,tick);
    camera=world.camera;
    if(world.view_changed) {
        // A room link can retain the same camera and scenery. Bind its room
        // without dropping the bake; load a changed view once, when drawing.
        if(renderer.camera.data!=Platform_ReadAsset(floor_cameras[world.floor][camera]).data) ResetCache();
        renderer.room=world.RoomAsset(world.floor,world.room);world.view_changed=false;
    }
    dirty=true;
}
void Game::DrawScene() {
    if(renderer.camera_id!=((unsigned)world.floor<<8 | (unsigned)camera)) ResetCache();
    renderer.room=world.RoomAsset(world.floor,world.room);world.view_changed=false;
    // Active slots are recycled between rooms. Movement/cache history
    // belongs to the object that occupied a slot, not its next occupant.
    bool cache_geometry_changed=false;
    for(int s=0;s<MAX_ACTIVE;++s) if(static_owner[s]!=world.active[s].id) {
        if(static_slots&(1u<<s)) cache_geometry_changed=true;
        static_owner[s]=(int16_t)world.active[s].id;static_hash[s]=0;
        static_quiet_since[s]=(uint16_t)world.ticks;dynamic_slots&=~(1u<<s);
    }
    int order[MAX_ACTIVE],count=world.DrawList(order);
    uint32_t signature=2166136261u,scene_signature=2166136261u,next_static_slots=0;
    auto hash=[&](int value) { signature=(signature^(uint32_t)value)*16777619u; };
    for(int i=0;i<count;++i) {
        int s=order[i];
        const Actor &a=world.Pose(s);
        int flags=world.active[s].value.v[O_FLAGS];
        // Intro doors retain F_ANIMATED while idle with no animation asset.
        // Track their complete pose like other scenery; any scripted movement
        // invalidates the bake and keeps them dynamic until they settle.
        if((flags&F_MOVABLE) || ((flags&F_ANIMATED) && !(world.intro && !a.animation.data))) {
            dynamic_slots|=1u<<s;static_quiet_since[s]=(uint16_t)world.ticks;continue;
        }
        signature=2166136261u;
        hash(world.active[s].id);hash(world.active[s].value.v[O_BODY]);
        hash(a.floor);hash(a.room);hash(a.pos.x);hash(a.pos.y);hash(a.pos.z);hash(a.alpha);hash(a.beta);hash(a.gamma);
        // Collision boxes affect drawing only through camera mask tests.
        // LIFE can resize a box without changing any active mask; hashing
        // those raw coordinates caused repeated full-room rebuilds.
        const uint8_t *c=Platform_ReadAsset(floor_cameras[world.floor][camera]).data,*views=c+BE32(c+20);
        for(unsigned v=0;v<BE16(c+18);++v) {
            const uint8_t *view=views+v*16;if(BE16(view)!=(unsigned)a.room) continue;
            const uint8_t *m=c+BE32(view+12);
            for(unsigned j=0;j<BE16(view+4);++j) hash(Renderer_MaskActive(a,c,m+j*12));
        }
        // Actor_Vertices overrides group zero with the actor angles above.
        // Its animation state cannot affect geometry or invalidate the bake.
        for(unsigned g=1;g<BE16(a.model.data+4);++g) { hash(a.state[g].type);hash(a.state[g].delta.x);hash(a.state[g].delta.y);hash(a.state[g].delta.z); }
        // LIFE toggles pushed props between moving and stationary flags.
        // Keep them out of the bake while their pose changes, then cache
        // a settled door/prop after one second of unchanged world time.
        if(static_hash[s] && static_hash[s]!=signature) {
            dynamic_slots|=1u<<s;static_quiet_since[s]=(uint16_t)world.ticks;
        }
        if((static_slots&(1u<<s)) && static_hash[s]!=signature) cache_geometry_changed=true;
        static_hash[s]=signature;
        if(Dynamic(s)) {
            if((uint16_t)(world.ticks-static_quiet_since[s])<GAME_HZ) continue;
            dynamic_slots&=~(1u<<s);
        }
        // Bounds also drive painter order. Track the resulting static
        // order, rather than invalidating for every raw bound change.
        next_static_slots|=1u<<s;
        scene_signature=(scene_signature^signature)*16777619u;
    }
    signature=scene_signature;
    bool reordered=signature!=static_signature && static_signature && !cache_geometry_changed && static_slots==next_static_slots;
    // Camera decoding maps and restores its source page. Finish it before
    // retaining the raw original for architectural masks and cache repairs.
    if(signature!=static_signature && !reordered) {
        if(!renderer.SetCamera(camera,world.floor,world.room,mode!=0)) Platform_Fatal();
    }
    if(renderer.original_background.flags&0x8000) {
        for(int i=0;i<count;++i) if(world.Pose(order[i]).floor!=world.floor) Platform_Fatal();
    }
    OriginalImage original(renderer);
    if(reordered) {
        RebuildStaticOrder(order,count);static_signature=signature;
    } else if(signature!=static_signature) {
        renderer.Restore();
        unsigned used=0;
        for(int i=0;i<count;++i) if(!Dynamic(order[i])) {
            int slot=order[i];static_span_start[slot]=used;
            unsigned n=renderer.DrawCachedActor(world.Pose(slot),static_spans+used,3072-used);
            static_bounds[slot]=renderer.last_bounds;static_span_count[slot]=n;if(n!=65535) used+=n;
        }
        renderer.BakeBackground();static_signature=signature;
    } else renderer.Restore();
    static_slots=next_static_slots;
    for(int i=0;i<count;++i) if(!Dynamic(order[i])) static_rank[order[i]]=(uint8_t)i;
    Rect dynamic_bounds={320,200,-1,-1};
    for(int i=0;i<count;++i) {
        int slot=order[i];
        if(Dynamic(slot)) {
            renderer.DrawActor(world.Pose(slot));Rect b=renderer.last_bounds;static_bounds[slot]=b;
            dynamic_bounds={Min(dynamic_bounds.x1,b.x1),Min(dynamic_bounds.y1,b.y1),Max(dynamic_bounds.x2,b.x2),Max(dynamic_bounds.y2,b.y2)};
        } else {
            // A cached prop in front of an animated actor must keep the
            // original painter ordering. Redraw only overlapping props.
            Rect b=static_bounds[slot];
            if(b.x1<=dynamic_bounds.x2 && b.x2>=dynamic_bounds.x1 && b.y1<=dynamic_bounds.y2 && b.y2>=dynamic_bounds.y1) {
                if(static_span_count[slot]==65535) renderer.DrawActor(world.Pose(slot));
                else renderer.DrawCoverage(static_spans+static_span_start[slot],static_span_count[slot]);
            }
        }
    }
    // A rotating hatch or door can straddle the character's depth even
    // while the character is idle. Resolve nearby prop intersections for
    // every character pose, including the reach of search/push limbs.
    // The original arrival uses its scripted painter order and camera masks.
    for(int i=0;!world.intro && i<count;++i) {
        int s=order[i];if(!(world.active[s].value.v[O_FLAGS]&F_ANIMATED) || (world.active[s].value.v[O_FLAGS]&F_MOVABLE)) continue;
        if(!(world.active[s].value.v[O_FLAGS]&F_TRIGGER)) continue;
        Bounds a=world.Box(s,world.room);uint32_t group_mask=1u<<s;Rect area={320,200,-1,-1};
        for(int j=0;j<count;++j) {
            int t=order[j];int flags=world.active[t].value.v[O_FLAGS];
            if(t==s || (flags&F_FOUNDABLE) || ((flags&F_ANIMATED) && (flags&F_TRIGGER) && !(flags&F_MOVABLE))) continue;
            Bounds b=world.Box(t,world.room);
            // Flat floor patches cannot occlude a reaching limb.
            if(b.hi.y-b.lo.y<=20) continue;
            if(a.lo.x>b.hi.x+300 || a.hi.x<b.lo.x-300 || a.lo.y>b.hi.y+100 || a.hi.y<b.lo.y-100 || a.lo.z>b.hi.z+300 || a.hi.z<b.lo.z-300) continue;
            Rect x=static_bounds[s],y=static_bounds[t];Rect overlap={Max(x.x1,y.x1),Max(x.y1,y.y1),Min(x.x2,y.x2),Min(x.y2,y.y2)};
            if(overlap.x1>overlap.x2 || overlap.y1>overlap.y2) continue;
            group_mask|=1u<<t;
            area={Min(area.x1,overlap.x1),Min(area.y1,overlap.y1),Max(area.x2,overlap.x2),Max(area.y2,overlap.y2)};
        }
        if(area.x1>area.x2 || area.y1>area.y2) continue;
        const Actor *group[MAX_ACTIVE];unsigned members=0;
        for(int j=0;j<count;++j) if(group_mask&(1u<<order[j])) group[members++]=&world.Pose(order[j]);
        if(!renderer.ResolveOverlap(group,members,area)) continue;
        // Disjoint foreground models keep their ordinary painter position;
        // they need no depth pass alongside this intersecting group.
        for(int j=i+1;j<count;++j) {
            int t=order[j];if(group_mask&(1u<<t)) continue;Rect b=static_bounds[t];
            if(b.x1>area.x2 || b.x2<area.x1 || b.y1>area.y2 || b.y2<area.y1) continue;
            if(Dynamic(t) || static_span_count[t]==65535) renderer.DrawActor(world.Pose(t));
            else renderer.DrawCoverage(static_spans+static_span_start[t],static_span_count[t],area);
        }
    }
    renderer.DrawEffects(world);
}
void Game::Draw() {
    if(!mode) { StartupDraw();return; }
    if(mode && world.book>=0 && menu<3) { Book_Draw(renderer,world.book,book_line);dirty=false;return; }
    {
        DrawScene();
        if(world.message>=0 && world.now<world.message_until && !menu && world.prompt<0 && world.book<0) {
            renderer.Panel(8,158,AS_UI_MESSAGE);TextLines(renderer,20,170,GameText(world.message),35,2);
        }
        if(world.prompt>=0) {
            renderer.Panel(24,61,AS_UI_PROMPT);renderer.DrawText(40,73,"YOU FOUND:");
            TextLines(renderer,40,87,GameText(world.objects[world.prompt].v[O_NAME]),30,3);
            renderer.DrawText(40,121,"A:TAKE   C:LEAVE");
        }
        if(menu==1 || menu==2) {
            renderer.Panel(16,16,AS_UI_INVENTORY);renderer.DrawText(32,28,"INVENTORY");
            char health[12];Number(health,(unsigned)Max(0,world.vars[21]));renderer.DrawText(208,28,"HEALTH");renderer.DrawText(264,28,health);
            if(menu==1) {
                int start=Max(0,selection-7);
                for(int i=start;i<Min(start+10,world.inventory_count);++i) {
                    int y=44+(i-start)*12;renderer.DrawText(28,y,i==selection?">":" ");
                    TextLines(renderer,40,y,GameText(world.objects[world.inventory[i]].v[O_NAME]),31,1);
                }
                renderer.DrawText(32,172,"A:SELECT   C:RETURN");
            } else {
                int object=world.inventory[selection],bits[11],count=InventoryActions(world,object,bits);
                TextLines(renderer,32,44,GameText(world.objects[object].v[O_NAME]),32,2);
                for(int i=0;i<count;++i) { int y=72+i*10;renderer.DrawText(28,y,i==action_selection?">":" ");TextLines(renderer,40,y,GameText(bits[i]+23),31,1); }
                renderer.DrawText(32,172,"A:CHOOSE   C:BACK");
            }
        }
        if(world.book>=0) Book_Draw(renderer,world.book,book_line);
        if(paused && menu!=3) { renderer.Panel(24,48,AS_UI_PAUSE);renderer.DrawText(40,60,"PAUSED"); }
        if(world.fault_code) {
            renderer.Panel(24,72,AS_UI_STATUS);renderer.DrawText(40,84,"SCRIPT ERROR");
            char code[12];Number(code,world.fault_life);renderer.DrawText(40,96,"LIFE");renderer.DrawText(88,96,code);
            Number(code,world.fault_pc);renderer.DrawText(136,96,"WORD");renderer.DrawText(184,96,code);
            renderer.DrawText(40,118,"START:MENU");
        }
        if(world.finished) { renderer.Panel(24,72,AS_UI_STATUS);renderer.DrawText(40,88,world.cvars[15]?"YOU DIED":"END OF THIS BUILD");renderer.DrawText(40,112,"START:MENU"); }
    }
    Game_DrawSystem(*this);
    dirty=false;
}
