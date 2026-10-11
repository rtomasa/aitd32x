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
    inventory_dirty=true;
    world.intro=false;world.picture_id=-1;world.picture_duration=0;
    Actor_Init(player,character);Asset spawn=Platform_ReadAsset(AS_PLAYER_SPAWN);
    if(spawn.size!=16) Platform_Fatal();
    player.pos={BS16(spawn.data),BS16(spawn.data+2),BS16(spawn.data+4)};player.beta=BS16(spawn.data+8);
    startup_time=startup_since=startup_transition=0;StartupEnter(boot?STARTUP_LOGO:STARTUP_MENU);
}
void Game::Input(uint16_t pad) { pending_edges|=pad&~held;held=pad; }
A32X_COLD void Game::PresentationInput() {
    // UI edges need no simulation tick. Gameplay action input remains queued
    // for the independent 25 Hz world; each presentation edge is consumed once.
    if(pending_edges && HandlePresentationInput(pending_edges)) pending_edges=0;
}
A32X_COLD bool Game::HandlePresentationInput(uint16_t edges) {
    if(!mode) {
        if(startup_phase>STARTUP_BIOGRAPHY) return false;
        StartupUpdate(edges);return true;
    }
    if(Game_SystemInput(*this,edges)) return true;
    if(world.fault_code || world.finished || (world.cvars[15] && !paused && !menu)) return false;
    if(world.prompt>=0) {
        PickupUpdate(edges);return true;
    }
    if(world.book>=0) {
        if(!edges) return true;
        int previous=book_line;
        if(edges&(PAD_A|PAD_C)) { world.book=-1;book_line=0;action_blocked=true;ResetCache();Audio_Sample(world.cvars[0]); }
        else {
            unsigned pages=Book_Pages(world.book);
            if((edges&(PAD_DOWN|PAD_RIGHT|PAD_B)) && book_line+1<(int)pages) ++book_line;
            if(edges&(PAD_UP|PAD_LEFT)) book_line=Max(0,book_line-1);
            if(previous!=book_line) Audio_Sample(world.cvars[0]);
        }
        dirty=true;return true;
    }
    if(menu==1 || menu==2) { InventoryUpdate(edges);return true; }
    if(paused) return true;
    if((edges&PAD_C) && world.inventory_allowed) { InventoryEnter();return true; }
    return false;
}
void Game::Update() {
    ++tick;uint16_t edges=pending_edges;pending_edges=0;
    if(!mode) { StartupUpdate(edges);return; }
    if(HandlePresentationInput(edges)) return;
    if(!(held&PAD_A)) action_blocked=false;
    if(world.cvars[15] && !world.fault_code && !paused && !menu) { StartDeath();return; }
    if(world.fault_code || world.finished) {
        if(edges&PAD_START) Init(false);
        return;
    }
    world.Update(held,(held&PAD_A) && !action_blocked);
    Audio_UpdateMusic(world.music,world.next_music,tick);
    if(world.cvars[15] && !world.fault_code) { StartDeath();return; }
    if(world.prompt>=0) PickupEnter();
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
        if((flags&F_MOVABLE) || ((flags&F_ANIMATED) && !((world.intro || startup_phase>=STARTUP_DEATH) && !a.animation.data))) {
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
    for(int i=0;!world.intro && startup_phase<STARTUP_DEATH && i<count;++i) {
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
A32X_COLD void Game::DrawMessages() {
    if(world.message>=0 && world.now<world.message_until)
        Book_DrawText(renderer,160,184,GameText(world.message),16,true);
}
void Game::Draw() {
    if(!mode) { StartupDraw();return; }
    if(menu==3) {
        if(inventory_dirty) {
            // Freeze the already paused room once. Later option changes only
            // replace the opaque menu rectangle in the same RAM image.
            DrawScene();renderer.BakeBackground();inventory_dirty=false;
        }
        if(dirty) { BackgroundComposition composition(renderer);Game_DrawSystem(*this); }
        renderer.Restore();dirty=false;return;
    }
    if(world.book>=0 && menu<3) {
        if(dirty) { BackgroundComposition composition(renderer);Book_Draw(renderer,world.book,book_line); }
        renderer.Restore();dirty=false;return;
    }
    if(world.prompt>=0) { PickupDraw();return; }
    if(menu==1 || menu==2) { InventoryDraw();return; }
    {
        DrawScene();
        if(world.message>=0 && world.now<world.message_until && !menu && world.prompt<0 && world.book<0) {
            DrawMessages();
        }
        if(world.book>=0) Book_Draw(renderer,world.book,book_line);
        if(paused && menu!=3) { renderer.Panel(24,48,AS_UI_PAUSE);Book_DrawText(renderer,40,60,"Paused",15); }
        if(world.fault_code) {
            renderer.Panel(24,72,AS_UI_STATUS);renderer.DrawText(40,84,"SCRIPT ERROR");
            char code[12];Number(code,world.fault_life);renderer.DrawText(40,96,"LIFE");renderer.DrawText(88,96,code);
            Number(code,world.fault_pc);renderer.DrawText(136,96,"WORD");renderer.DrawText(184,96,code);
            renderer.DrawText(40,118,"START:MENU");
        }
        if(world.finished) { renderer.Panel(24,72,AS_UI_STATUS);Book_DrawText(renderer,40,84,world.cvars[15]?GameText(40):"End of this build",15);Book_DrawText(renderer,40,110,"Start: return to title",15); }
    }
    Game_DrawSystem(*this);
    dirty=false;
}
