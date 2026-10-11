// SPDX-License-Identifier: GPL-2.0-or-later
#include "save.hpp"
#include "startup.hpp"
#include "game.hpp"
#include "../platform/audio.hpp"
#include "../platform/platform_api.hpp"
#include "../render/book.hpp"
// Both journal records must fit even with the complete active-actor pool.
static constexpr unsigned HEADER=24,LIMIT=65536-HEADER;
static constexpr uint32_t MAGIC=0x41495444,LEGACY_FORMAT=0x53313401,FORMAT=0x53313601;
struct Stream {
    bool reading,apply,ok,legacy;unsigned count;uint32_t checksum;
    Stream(bool read,bool change,bool old=false):reading(read),apply(change),ok(true),legacy(old),count(0),checksum(2166136261u) {}
    uint8_t Byte(uint8_t value) {
        if(count==LIMIT) { ok=false;return 0; }
        if(reading) value=Platform_SaveRead();else Platform_SaveWrite(value);
        checksum=(checksum^value)*16777619u;++count;return value;
    }
    unsigned Word(unsigned value,unsigned bytes=4) {
        unsigned result=0;for(unsigned n=bytes;n;--n) result=(result<<8)|Byte((uint8_t)(value>>((n-1)*8)));
        return result;
    }
    template<class T> int Field(T &value,unsigned bytes=4) {
        unsigned v=Word((unsigned)value,bytes);int result=bytes==2?(int16_t)v:bytes==1?(uint8_t)v:(int32_t)v;
        if(reading && apply) value=(T)result;
        return result;
    }
    template<class V> void Vector(V &v,unsigned bytes=4) { Field(v.x,bytes);Field(v.y,bytes);Field(v.z,bytes); }
    void Real(RealValue &v) { Field(v.start);Field(v.end);Field(v.steps);Field(v.since); }
    void Check(bool valid) { if(!valid) ok=false; }
};
static void Object(Stream &s,WorldObject &o) {
    for(int i=0;i<26;++i) {
        int v=s.Field(o.v[i],2);
        if(i==O_SLOT) s.Check(v>=-1 && v<(s.legacy?24:MAX_ACTIVE));
        if(i==O_BODY) s.Check(v>=-1 && v<A32X_MODEL_COUNT);
    }
}
static void Active(Stream &s,ActiveObject &a) {
    Object(s,a.value);for(int &v:a.col) s.Field(v);
#define F(x) s.Field(a.x)
    F(col_by);F(hard_dec);F(hard_col);F(hit);F(hit_by);F(hit_force);F(speed);F(direction);F(mark);F(dyn_flags);F(falling);F(end_anim);F(end_frame);
    F(pending_anim);F(pending_type);F(pending_next);F(hit_anim);F(hit_frame);F(hit_group);F(hit_size);F(hit_type);F(throw_object);F(chrono);F(room_chrono);
    s.Real(a.rotation);s.Real(a.vertical);s.Real(a.speed_change);F(speed_step);
#undef F
}
static void Pose(Stream &s,Actor &a,int body,int character) {
    if(s.reading) {
        a.model=body<0?Asset{}:Platform_ReadAsset(model_assets[character][body]);
        a.character=character;
    }
    s.Vector(a.pos);s.Field(a.alpha);s.Field(a.beta);s.Field(a.gamma);s.Field(a.room);s.Field(a.floor);
    s.Field(a.end_frame,1);s.Field(a.end_anim,1);s.Vector(a.collision_min);s.Vector(a.collision_max);
    int frame=s.Field(a.frame),phase=s.Field(a.frame_phase);
    unsigned anim=s.Word(a.animation.data?a.anim_asset:0xFFFFFFFF);
    if(s.reading) {
        a.anim_asset=anim;a.animation=anim==0xFFFFFFFF?Asset{}:Platform_ReadAsset(anim);
        s.Check(anim==0xFFFFFFFF || (a.animation.data && a.animation.type==6));
        if(a.animation.data) s.Check(frame>=0 && (unsigned)frame<BE16(a.animation.data) && phase>=0);
    }
    s.Vector(a.last_step);s.Field(a.walking,1);
    unsigned groups=a.model.data?BE16(a.model.data+4):0,saved=s.Word(groups,2);
    s.Check(saved==groups && saved<=MAX_GROUPS);
    if(saved>MAX_GROUPS) return;
    for(unsigned i=0;i<saved;++i) for(unsigned j=0;j<2;++j) { GroupState &p=j?a.state[i]:a.previous[i];unsigned bytes=s.legacy?4:2;s.Field(p.type,bytes);s.Vector(p.delta,bytes); }
}
static bool Payload(Stream &s,Game &g) {
    World &w=g.world;int character=s.Field(w.character);s.Check(character==0 || character==1);
    if(character<0 || character>1) return false;
    s.Field(g.tick);int floor=s.Field(w.floor),room=s.Field(w.room),camera=s.Field(w.camera);
    s.Check(floor>=0 && floor<A32X_FLOOR_COUNT);
    if(floor<0 || floor>=A32X_FLOOR_COUNT) return false;
    s.Check(room>=0 && room<room_counts[floor] && camera>=0 && camera<camera_counts[floor]);
#define F(x) s.Field(w.x)
    F(camera_target);F(ticks);F(now);F(rng);F(action);F(music);F(next_music);F(in_hand);F(prompt);F(message);F(book);F(book_type);F(message_until);
    F(inventory_allowed);F(finished);F(peak_active);F(effect_serial);
#undef F
    int items=s.Field(w.inventory_count);s.Check(items>=0 && items<=INVENTORY_CAPACITY);
    for(int &id:w.inventory) s.Field(id);
    for(auto &o:w.objects) Object(s,o);
    for(auto &v:w.vars) s.Field(v,2);
    for(auto &v:w.cvars) s.Field(v,2);
    bool applying=s.apply;
    for(int k=0;k<(s.legacy?24:MAX_ACTIVE);++k) {
        ActiveObject temporary{};Actor dummy{};
        ActiveObject &a=s.reading&&!applying?temporary:w.active[k];
        s.apply=true;int id=s.Field(a.id);s.Check(id>=-1 && id<A32X_OBJECT_COUNT);
        if(id>=0) {
            Active(s,a);int body=a.value.v[O_BODY];
            if(body<-1 || body>=A32X_MODEL_COUNT) return false;
            Actor &p=s.reading&&!applying?dummy:w.Pose(k);
            Pose(s,p,body,character);
        } else if(s.reading) { a={};a.id=-1; }
        s.apply=applying;
    }
    if(s.reading && s.apply && s.legacy) for(int k=24;k<MAX_ACTIVE;++k) { w.active[k]={};w.active[k].id=-1; }
    for(auto &e:w.effects) {
        s.Field(e.since);s.Field(e.duration,2);s.Field(e.floor,2);s.Field(e.room,2);
        int count=s.Field(e.count,1);s.Check(count<=30);s.Field(e.color,1);s.Field(e.mode,1);
        for(auto &v:e.points) { s.Field(v.x,2);s.Field(v.y,2);s.Field(v.z,2); }
    }
    if(!s.legacy) s.Field(w.dark,1);
    else if(s.reading && s.apply) w.dark=!w.cvars[12] && ((floor==2 && room==0 && !w.vars[70]) || (floor==2 && room==6 && !w.vars[85]) || (floor==6 && w.player->room<6 && !w.vars[178]));
    return s.ok;
}
struct Record { uint32_t generation,length,checksum;bool valid,legacy; };
static uint32_t RawRead() { unsigned v=0;for(int i=0;i<4;++i) v=(v<<8)|Platform_SaveRead();return v; }
static void RawWrite(uint32_t v) { for(int i=3;i>=0;--i) Platform_SaveWrite((uint8_t)(v>>(8*i))); }
static Record Inspect(unsigned bank) {
    Record r{};if(!Platform_SaveBegin(bank)) return r;
    uint32_t magic=RawRead(),format=RawRead();r.generation=RawRead();r.length=RawRead();r.checksum=RawRead();unsigned game=RawRead();
    r.legacy=format==LEGACY_FORMAT;
    if(magic==MAGIC && (format==FORMAT || r.legacy) && game==A32X_SAVE_FINGERPRINT && r.length && r.length<=LIMIT) {
        unsigned sum=2166136261u;for(unsigned i=0;i<r.length;++i) sum=(sum^Platform_SaveRead())*16777619u;r.valid=sum==r.checksum;
    }
    Platform_SaveEnd();return r;
}
static int Newest(const Record &a,const Record &b) {
    if(!a.valid) return b.valid?1:-1;
    if(!b.valid) return 0;
    return (int32_t)(b.generation-a.generation)>0?1:0;
}
bool Game_Save(Game &g) {
    g.resync_clock=true;
    if(!g.mode || g.world.finished || g.world.fault_code) return false;
    Record a=Inspect(0),b=Inspect(1);int latest=Newest(a,b);unsigned bank=latest==0?1:0;
    uint32_t generation=latest<0?1:(latest?b.generation:a.generation)+1;
    if(!Platform_SaveBegin(bank)) return false;
    RawWrite(0);Platform_SaveSeek(HEADER);
    Stream s(false,false);bool good=Payload(s,g);Platform_SaveSeek(4);
    RawWrite(FORMAT);RawWrite(generation);RawWrite(s.count);RawWrite(s.checksum);RawWrite(A32X_SAVE_FINGERPRINT);
    if(good) { Platform_SaveSeek(0);RawWrite(MAGIC); }
    Platform_SaveEnd();return good && Inspect(bank).valid;
}
bool Game_Load(Game &g) {
    g.resync_clock=true;
    Record a=Inspect(0),b=Inspect(1);int bank=Newest(a,b);if(bank<0) return false;
    Record r=bank?b:a;
    if(!Platform_SaveBegin(bank)) return false;
    Platform_SaveSeek(HEADER);
    Stream verify(true,false,r.legacy);bool valid=Payload(verify,g)&&verify.count==r.length&&verify.checksum==r.checksum;
    Platform_SaveEnd();if(!valid) return false;
    g.world.player=&g.player;Platform_SaveBegin(bank);Platform_SaveSeek(HEADER);Stream read(true,true,r.legacy);valid=Payload(read,g);Platform_SaveEnd();if(!valid) return false;
    Audio_Reset();Audio_UpdateMusic(g.world.music,g.world.next_music,g.tick);
    g.world.player=&g.player;g.world.pad=0;g.world.click=0;g.world.view_changed=false;g.world.fault_code=0;
    g.world.intro=false;g.world.picture_id=-1;g.world.picture_duration=0;
    g.character=g.world.character;g.camera=g.world.camera;g.mode=1;
    if(g.world.prompt>=0) g.PickupEnter();
    g.paused=true;g.menu=3;g.selection=0;g.action_selection=2;g.book_line=0;
    g.lighting_dark=false;g.renderer.full_restore[0]=g.renderer.full_restore[1]=true;
    g.startup_phase=STARTUP_GAMEPLAY;g.startup_next=255;g.inventory_dirty=true;
    g.held=g.pending_edges=0;g.action_blocked=true;g.ResetCache();g.dirty=true;return true;
}
bool Game_SystemInput(Game &g,unsigned edges) {
    if(!g.mode) {
        if(edges&PAD_B) { if(!Game_Load(g)) { g.menu=4;g.dirty=true; }return true; }
        if(g.menu==4 && edges) { g.menu=0;g.dirty=true;return true; }
        return false;
    }
    if(g.menu!=3) {
        if((edges&PAD_START) && !g.menu && g.world.prompt<0 && g.world.book<0) {
            g.menu=3;g.paused=true;g.selection=g.action_selection=0;g.inventory_dirty=true;g.dirty=true;return true;
        }
        return false;
    }
    if(!edges) return true;
    if(edges&(PAD_START|PAD_B|PAD_C)) { g.menu=0;g.paused=false;g.action_blocked=true;g.ResetCache();if(g.world.prompt>=0) g.PickupEnter();g.dirty=true;return true; }
    if(edges&PAD_DOWN) { g.selection=(g.selection+1)%4;g.action_selection=0; }
    if(edges&PAD_UP) { g.selection=(g.selection+3)%4;g.action_selection=0; }
    if(edges&PAD_A) {
        if(g.selection==0) { g.menu=0;g.paused=false;g.action_blocked=true;g.ResetCache();if(g.world.prompt>=0) g.PickupEnter(); }
        else if(g.selection==1) g.action_selection=Game_Save(g)?1:3;
        else if(g.selection==3) g.Init(false);
        else if(!Game_Load(g)) g.action_selection=4;
    }
    g.dirty=true;return true;
}
void Game_DrawSystem(Game &g) {
    if(g.menu==4) { g.renderer.Panel(24,72,AS_UI_STATUS);Book_DrawText(g.renderer,40,84,"No valid save found",15);Book_DrawText(g.renderer,40,110,"A/B/C/Start: back",4);return; }
    if(g.menu!=3) return;
    g.renderer.Panel(24,48,AS_UI_PAUSE);Book_DrawText(g.renderer,160,60,"Paused",15,true);
    const char *rows[]={GameText(48),GameText(45),GameText(46),"Return to Title"};
    for(int i=0;i<4;++i) {
        int y=80+i*16;if(i==g.selection) g.renderer.Box(38,y,244,16,100);
        Book_DrawClippedText(g.renderer,160,y,rows[i],236,i==g.selection?15:4,true);
    }
    const char *notice[]={"A: choose   B/Start: resume","Game saved","Game loaded","Save failed","No valid save found"};
    Book_DrawClippedText(g.renderer,160,150,notice[g.action_selection],240,15,true);
}
