// SPDX-License-Identifier: GPL-2.0-or-later
// Bounded, allocation-free adaptation of FITD object/main/track/actorList.
#include "world.hpp"
#include "../platform/platform_api.hpp"
static int Abs(int x) { return x<0?-x:x; }
static bool Intersect(const Bounds &a,const Bounds &b) {
    return a.lo.x<b.hi.x && a.hi.x>b.lo.x && a.lo.y<b.hi.y && a.hi.y>b.lo.y && a.lo.z<b.hi.z && a.hi.z>b.lo.z;
}
static bool Escaping(int lo,int hi,int a,int b,int delta) {
    return lo<b && hi>a && ((delta<0 && hi-a<=b-lo) || (delta>0 && b-lo<=hi-a));
}
static Bounds ReadBox(const uint8_t *p) { return {{BS16(p),BS16(p+4),BS16(p+8)},{BS16(p+2),BS16(p+6),BS16(p+10)}}; }
static Bounds Offset(Bounds b,Vec3 d) { b.lo={b.lo.x+d.x,b.lo.y+d.y,b.lo.z+d.z};b.hi={b.hi.x+d.x,b.hi.y+d.y,b.hi.z+d.z};return b; }
static void Clear(void *p,unsigned n) { uint8_t *b=(uint8_t*)p;while(n--) *b++=0; }
Asset World::RoomAsset(int f,int r) const {
    if(f<0 || f>=A32X_FLOOR_COUNT || r<0 || r>=room_counts[f]) return {0,0,0,0,0};
    return Platform_ReadAsset(floor_rooms[f][r]);
}
int World::Slot(int id) const { return id>=0 && id<A32X_OBJECT_COUNT?objects[id].v[O_SLOT]:-1; }
int World::Get(int id,int word) const {
    if(id<0 || id>=A32X_OBJECT_COUNT || word<0 || word>=26) return -1;
    int s=Slot(id);
    if(s>=0 && (word==O_BODY || word==O_FLAGS || (word>=O_X && word!=O_FLOOR_LIFE && word!=O_TRACK_POS))) {
        const Actor &p=active[s].id==1?*player:poses[s];
        if(word==O_X) return p.pos.x;
        if(word==O_Y) return p.pos.y;
        if(word==O_Z) return p.pos.z;
        if(word==O_ALPHA) return p.alpha;
        if(word==O_BETA) return p.beta;
        if(word==O_GAMMA) return p.gamma;
        if(word==O_FRAME) return p.frame;
        return active[s].value.v[word];
    }
    return objects[id].v[word];
}
void World::Set(int id,int word,int value) {
    if(id<0 || id>=A32X_OBJECT_COUNT || word<1 || word>=26) { Error(-1,word,901);return; }
    int s=Slot(id);
    if(s>=0 && (word==O_BODY || word==O_FLAGS || (word>=O_X && word!=O_FLOOR_LIFE && word!=O_TRACK_POS))) {
        active[s].value.v[word]=(int16_t)value;
        Actor &p=Pose(s);
        if(word==O_BODY) Actor_SetModel(p,value);
        if(word==O_X) p.pos.x=value;
        if(word==O_Y) p.pos.y=value;
        if(word==O_Z) p.pos.z=value;
        if(word==O_ALPHA) p.alpha=value;
        if(word==O_BETA) p.beta=value;
        if(word==O_GAMMA) p.gamma=value;
        if(word==O_FLOOR) p.floor=value;
        if(word==O_ROOM) p.room=value;
    } else objects[id].v[word]=(int16_t)value;
}
void World::Error(int life,int pc,int code) { if(!fault_code) { fault_life=life;fault_pc=pc;fault_code=code; } }
Vec3 World::InRoom(Vec3 p,int source,int dest) const {
    if(source==dest) return p;
    Asset a=RoomAsset(floor,source),b=RoomAsset(floor,dest);if(!a.data || !b.data) return p;
    p.x-=(BS16(b.data)-BS16(a.data))*10;p.y+=(BS16(b.data+2)-BS16(a.data+2))*10;p.z+=(BS16(b.data+4)-BS16(a.data+4))*10;return p;
}
Bounds World::Box(int s,int relative_room) const {
    const Actor &a=active[s].id==1?*player:poses[s];Bounds b={a.collision_min,a.collision_max};
    Vec3 pos=a.pos;if(relative_room>=0) pos=InRoom(pos,a.room,relative_room);return Offset(b,pos);
}
bool World::Visible(int r) const {
    if(r==room) return true;
    Asset cam=Platform_ReadAsset(floor_cameras[floor][camera]);
    const uint8_t *v=cam.data+BE32(cam.data+20);
    for(unsigned i=0;i<BE16(cam.data+18);++i) if(BE16(v+16*i)==(unsigned)r) return true;
    Asset a=RoomAsset(floor,room);const uint8_t *b=a.data+BE32(a.data+20);
    for(unsigned i=0;i<BE16(a.data+10);++i,b+=16) if(BE16(b+14)==0 && BS16(b+12)==r) return true;
    return false;
}
A32X_COLD void World::Init(Actor &protagonist,int selected,int initial_floor,int initial_room,int target) {
    player=&protagonist;character=selected;floor=initial_floor;room=initial_room;camera_target=target;intro=initial_floor==7;
    Asset initial=RoomAsset(floor,room);
    if(!initial.data || !BE16(initial.data+6)) Platform_Fatal();
    // Camera numbers are global within the floor. The original arrival starts
    // in room 1's first view (camera 3), rather than floor 7's camera zero.
    camera=BE16(initial.data+BE32(initial.data+12));
    ticks=now=0;rng=1;action=click=pad=0;music=next_music=-1;
    inventory_count=0;in_hand=-1;prompt=message=book=-1;message_until=0;
    picture_id=-1;picture_duration=0;
    for(auto &e:effects) e.count=0;
    effect_serial=0;
    inventory_allowed=true;view_changed=true;finished=false;dark=false;fault_code=fault_life=fault_pc=peak_active=0;
    for(int s=0;s<MAX_ACTIVE;++s) { Clear(&active[s],sizeof(active[s]));active[s].id=-1; }
    Asset o=Platform_ReadAsset(AS_OBJECTS),v=Platform_ReadAsset(AS_VARS_INITIAL),c=Platform_ReadAsset(AS_DEFINES_INITIAL);
    if(o.size!=A32X_OBJECT_COUNT*52 || v.size!=A32X_VAR_COUNT*2 || c.size!=90) Platform_Fatal();
    for(int i=0;i<A32X_OBJECT_COUNT;++i) {
        for(int j=0;j<26;++j) objects[i].v[j]=BS16(o.data+i*52+j*2);
        objects[i].v[O_SLOT]=-1;objects[i].v[O_FLAGS]|=32;
    }
    for(int i=0;i<A32X_VAR_COUNT;++i) vars[i]=BS16(v.data+i*2);
    for(int i=0;i<45;++i) cvars[i]=BS16(c.data+i*2);
    cvars[8]=(int16_t)selected;
    RefreshActors();
}
A32X_COLD void World::Activate(int id,int s) {
    ActiveObject &a=active[s];Clear(&a,sizeof a);a.id=id;a.value=objects[id];objects[id].v[O_SLOT]=(int16_t)s;
    a.value.v[O_FLAGS]&=~32;
    a.dyn_flags=(objects[id].v[O_FLAGS]&32)?1:0;
    a.pending_anim=-1;a.pending_next=-1;a.hit=a.hit_by=a.col_by=a.hard_dec=a.hard_col=-1;
    for(int i=0;i<3;++i) a.col[i]=-1;
    a.mark=-1;a.chrono=a.room_chrono=now;
    a.end_frame=1;a.end_anim=a.value.v[O_ANIM]<0?1:0;
    Actor &p=Pose(s);p.character=character;p.floor=a.value.v[O_FLOOR];p.room=a.value.v[O_ROOM];
    p.pos={a.value.v[O_X],a.value.v[O_Y],a.value.v[O_Z]};
    p.alpha=a.value.v[O_ALPHA];p.beta=a.value.v[O_BETA];p.gamma=a.value.v[O_GAMMA];
    Actor_SetModel(p,a.value.v[O_BODY]);SetBounds(s,a.value.v[O_ZV]);
    p.animation={0,0,0,0,0};p.frame=p.frame_phase=0;p.last_step={0,0,0};p.walking=false;p.end_frame=p.end_anim=false;
    int anim=a.value.v[O_ANIM];
    if(anim<0 && !(a.value.v[O_FLAGS]&F_DRAWABLE)) a.value.v[O_FLAGS]&=~F_ANIMATED;
    if(anim>=0 && p.model.data) {
        Actor_SetAnimation(p,animation_assets[character][anim]);Actor_SetFrame(p,Max(0,a.value.v[O_FRAME]));
        // FITD InitObjet enables every installed animation, including the
        // later-floor monsters and props whose original flags start at zero.
        a.value.v[O_FLAGS]|=F_ANIMATED;
    }
}
void World::Deactivate(int s) {
    ActiveObject &a=active[s];if(a.id<0) return;
    Actor &p=Pose(s);WorldObject &o=objects[a.id];
    for(int i=1;i<26;++i) if(i==O_BODY || i==O_FLAGS || (i>=O_X && i!=O_FLOOR_LIFE)) o.v[i]=(int16_t)Get(a.id,i);
    o.v[O_TRACK_POS]=a.value.v[O_TRACK_POS];o.v[O_FLAGS]=(a.value.v[O_FLAGS]&~F_BOXIFY)|(a.dyn_flags?32:0);
    o.v[O_X]=p.pos.x;o.v[O_Y]=p.pos.y;o.v[O_Z]=p.pos.z;o.v[O_SLOT]=-1;a.id=-1;
}
void World::RefreshActors() {
    // Room visibility is fixed throughout this refresh. Read the camera and
    // adjoining-room lists once, retaining the original object/slot scan order.
    uint32_t visible_rooms=0;
    auto include=[&](int r) { if((unsigned)r<32) visible_rooms|=1u<<r; };
    include(room);
    Asset cam=Platform_ReadAsset(floor_cameras[floor][camera]);
    const uint8_t *views=cam.data+BE32(cam.data+20);
    for(unsigned i=0;i<BE16(cam.data+18);++i) include(BE16(views+16*i));
    Asset current=RoomAsset(floor,room);const uint8_t *links=current.data+BE32(current.data+20);
    for(unsigned i=0;i<BE16(current.data+10);++i,links+=16)
        if(BE16(links+14)==0) include(BS16(links+12));
    // Preserve the original behavior for any future room IDs outside the
    // compact fast path, including negative script values.
    auto visible=[&](int r) { return (unsigned)r<32?(visible_rooms&(1u<<r))!=0:Visible(r); };
    for(int s=0;s<MAX_ACTIVE;++s) if(active[s].id>=0) {
        const int16_t *v=active[s].value.v;bool keep=false;
        if(v[O_FLOOR]==floor) {
            if(v[O_LIFE]>=0) keep=v[O_LIFE_MODE]==0 || (v[O_LIFE_MODE]==1 && v[O_ROOM]==room) || (v[O_LIFE_MODE]==2 && visible(v[O_ROOM]));
            else keep=visible(v[O_ROOM]);
        }
        if(!keep) Deactivate(s);
    }
    for(int id=0;id<A32X_OBJECT_COUNT;++id) {
        const int16_t *v=objects[id].v;if(v[O_SLOT]>=0 || v[O_FLOOR]!=floor) continue;
        bool eligible=v[O_LIFE]>=0 ? (v[O_LIFE_MODE]==0 || (v[O_LIFE_MODE]==1 && v[O_ROOM]==room) || (v[O_LIFE_MODE]==2 && visible(v[O_ROOM]))) : visible(v[O_ROOM]);
        if(!eligible) continue;
        int s=0;while(s<MAX_ACTIVE && active[s].id>=0) ++s;
        if(s==MAX_ACTIVE) { Error(-1,id,902);return; }Activate(id,s);
    }
    int count=0;for(int s=0;s<MAX_ACTIVE;++s) if(active[s].id>=0) ++count;peak_active=Max(count,peak_active);
}
A32X_COLD void World::SetBody(int s,int body) {
    ActiveObject &a=active[s];if(body==a.value.v[O_BODY]) return;
    Actor &p=Pose(s);GroupState old[MAX_GROUPS];unsigned ng=p.model.data?BE16(p.model.data+4):0;
    for(unsigned i=0;i<ng;++i) old[i]=p.state[i];
    a.value.v[O_BODY]=(int16_t)body;Actor_SetModel(p,body);
    if(p.model.data) for(unsigned i=0;i<(unsigned)Min(ng,BE16(p.model.data+4));++i) p.state[i]=p.previous[i]=old[i];
}
A32X_COLD void World::SetBounds(int s,int type) {
    Actor &p=Pose(s);Actor_Bounds(p,type);
    if(type!=4) return;
    Asset r=RoomAsset(p.floor,p.room);if(!r.data) return;
    const uint8_t *b=r.data+BE32(r.data+16);
    for(unsigned i=0;i<BE16(r.data+8);++i,b+=16) if(BE16(b+14)==9 && BS16(b+12)==objects[active[s].id].v[O_NAME]) {
        Bounds box=ReadBox(b);p.pos={(box.lo.x+box.hi.x)/2,(box.lo.y+box.hi.y)/2,(box.lo.z+box.hi.z)/2};
        p.collision_min={box.lo.x-p.pos.x,box.lo.y-p.pos.y,box.lo.z-p.pos.z};p.collision_max={box.hi.x-p.pos.x,box.hi.y-p.pos.y,box.hi.z-p.pos.z};break;
    }
}
void World::Animate(int s,int anim,int type,int next) {
    if(s<0) return;
    ActiveObject &a=active[s];
    if(anim>=A32X_ANIMATION_COUNT || anim< -1) { Error(-1,anim,903);return; }
    if(anim==-1) { a.pending_anim=-2;return; }
    bool animated=(a.value.v[O_FLAGS]&F_ANIMATED)!=0;
    if(!animated) {
        // Original static props start at a key pose, without blending from
        // unrelated bind geometry (notably cupboard doors and chest lids).
        Actor &p=Pose(s);
        unsigned frame=anim==a.value.v[O_ANIM]?p.frame:0;
        if(p.model.data) { Actor_SetAnimation(p,animation_assets[character][anim]);Actor_SetFrame(p,frame); }
    }
    if(anim==a.value.v[O_ANIM]) { a.value.v[O_FLAGS]|=F_ANIMATED;a.value.v[O_ANIM_TYPE]=type;a.value.v[O_NEXT_ANIM]=next;return; }
    if(animated && ((a.value.v[O_ANIM_TYPE]&2) || (a.pending_type&2))) return;
    a.pending_anim=anim;a.pending_type=type;a.pending_next=next;
    a.value.v[O_FLAGS]|=F_ANIMATED;
}
void World::MoveMode(int s,int mode,int track) {
    ActiveObject &a=active[s];a.value.v[O_TRACK_MODE]=mode;
    if(mode==2 || mode==3) { a.value.v[O_TRACK]=track;a.mark=-1;if(mode==3) a.value.v[O_TRACK_POS]=0; }
}
void World::Stage(int s,int f,int r,Vec3 p) {
    ActiveObject &a=active[s];
    if(a.id==camera_target && !RoomAsset(f,r).data) { Error(-1,r,921);return; }
    a.value.v[O_FLOOR]=f;a.value.v[O_ROOM]=r;Actor &pose=Pose(s);pose.floor=f;pose.room=r;pose.pos=p;
    if(a.id==camera_target && (floor!=f || room!=r)) { floor=f;room=r;camera=0;view_changed=true; }
}
int World::HardCollision(const Bounds &box,int f,int r) const {
    Asset a=RoomAsset(f,r);if(!a.data) return -1;const uint8_t *b=a.data+BE32(a.data+16);
    for(unsigned i=0;i<BE16(a.data+8);++i,b+=16) if(Intersect(box,ReadBox(b))) return (int)i;
    return -1;
}
int World::Distance(int a,int b) const {
    if(b<0 || active[b].id<0) return 32000;
    const Actor &p=active[a].id==1?*player:poses[a],&q=active[b].id==1?*player:poses[b];Vec3 v=InRoom(q.pos,q.room,p.room);
    return Abs(p.pos.x-v.x)+Abs(p.pos.y-v.y)+Abs(p.pos.z-v.z);
}
int World::PosRel(int a,int b) const {
    if(b<0 || active[b].id<0) return 0;
    const Actor &p=active[a].id==1?*player:poses[a];Bounds x=Box(a),y=Box(b,p.room);
    int beta=p.beta&1023,counter=3;
    if(beta>=128 && beta<384) counter=2;
    if(beta>=384 && beta<640) counter=1;
    if(beta>=640 && beta<896) counter=0;
    int cx=(y.lo.x+y.hi.x)/2,cz=(y.lo.z+y.hi.z)/2;
    if(x.hi.z>=cz && x.lo.z<=cz) { if(x.hi.x<cx) ++counter;else if(x.lo.x<=cx) return 0;else counter+=3; }
    else if(x.hi.x>=cx || x.lo.x<=cx) { if(x.hi.z<cz) counter+=2;else if(x.lo.z<=cz) return 0; }
    else return 0;
    static const int table[8]={4,1,8,2,4,1,8,0};return table[counter];
}
void World::MoveActor(int s,Vec3 d,bool push) {
    ActiveObject &a=active[s];Actor &p=Pose(s);
    int steps=Max(1,(Max(Abs(d.x),Abs(d.z))+31)/32);
    for(int n=1;n<=steps;++n) {
        Vec3 change=d;
        if(steps>1) change={d.x*n/steps-d.x*(n-1)/steps,d.y*n/steps-d.y*(n-1)/steps,d.z*n/steps-d.z*(n-1)/steps};
        Bounds candidate=Offset(Box(s),change);int h=HardCollision(candidate,p.floor,p.room);
        if(h>=0) {
            Asset r=RoomAsset(p.floor,p.room);const uint8_t *box=r.data+BE32(r.data+16)+16*h;
            if(BE16(box+14)==9) a.hard_col=BS16(box+12);else if(BE16(box+14)==3) a.hard_col=255;
            else if(!a.dyn_flags) a.hard_col=1;
            if(a.dyn_flags) {
                Bounds old=Box(s);const uint8_t *boxes=r.data+BE32(r.data+16);
                for(unsigned k=0;k<BE16(r.data+8);++k) {
                    Bounds wall=ReadBox(boxes+16*k);
                    if(Intersect(Offset(old,{change.x,0,0}),wall) && !Escaping(old.lo.x,old.hi.x,wall.lo.x,wall.hi.x,change.x)) change.x=0;
                    if(Intersect(Offset(old,{change.x,0,change.z}),wall) && !Escaping(old.lo.z,old.hi.z,wall.lo.z,wall.hi.z,change.z)) change.z=0;
                }
                // Fall/climb handlers own vertical movement in the original engine.
            }
        }
        candidate=Offset(Box(s),change);
        int num=0;
        for(int t=0;t<MAX_ACTIVE;++t) if(t!=s && active[t].id>=0 && Pose(t).floor==p.floor && Intersect(candidate,Box(t,p.room))) {
            if(num<3) a.col[num++]=t;
            active[t].col_by=s;
            if(active[t].value.v[O_FLAGS]&F_FOUNDABLE) {
                int id=active[t].id;if(a.value.v[O_TRACK_MODE]==1 && !(objects[id].v[O_FOUND_FLAGS]&0x1000) && prompt<0 && (objects[id].v[O_TRACK]==0 || now-(uint16_t)objects[id].v[O_TRACK]>=300)) prompt=id;
                continue;
            }
            bool blocked=a.dyn_flags!=0;
            if(push && (active[t].value.v[O_FLAGS]&F_MOVABLE)) {
                Bounds moved=Offset(Box(t),change);bool free=HardCollision(moved,Pose(t).floor,Pose(t).room)<0;
                for(int u=0;u<MAX_ACTIVE && free;++u) if(u!=s && u!=t && active[u].id>=0 && Pose(u).floor==p.floor && Intersect(moved,Box(u,Pose(t).room))) free=false;
                if(free) { Pose(t).pos.x+=change.x;Pose(t).pos.z+=change.z;active[t].value.v[O_FLAGS]|=F_ANIMATED;blocked=false; }
            }
            if(blocked && (change.x || change.z)) {
                Bounds obstruction=Box(t,p.room);
                Bounds old=Box(s);bool can_escape=!(active[t].value.v[O_FLAGS]&F_ANIMATED);
                if(Intersect(Offset(old,{change.x,0,0}),obstruction) && !(can_escape && Escaping(old.lo.x,old.hi.x,obstruction.lo.x,obstruction.hi.x,change.x))) change.x=0;
                if(Intersect(Offset(old,{change.x,0,change.z}),obstruction) && !(can_escape && Escaping(old.lo.z,old.hi.z,obstruction.lo.z,obstruction.hi.z,change.z))) change.z=0;
            }
        }
        p.pos.x+=change.x;p.pos.y+=change.y;p.pos.z+=change.z;
    }
}
static int AngleValue(RealValue &r,int value,uint32_t now) {
    if(!r.steps) return value;
    unsigned elapsed=now-r.since;
    if(elapsed>=(unsigned)r.steps) { r.steps=0;return r.end&1023; }
    int delta=((r.end-r.start+512)&1023)-512;return (r.start+delta*(int)elapsed/r.steps)&1023;
}
void World::SetAngle(int s,int angle,int duration,bool alpha) {
    ActiveObject &a=active[s];int &value=alpha?Pose(s).alpha:Pose(s).beta;
    if(value==angle) return;
    if(!a.rotation.steps || a.rotation.end!=angle) a.rotation={value,angle,Max(1,duration),now};
    value=duration==0?angle:AngleValue(a.rotation,value,now);
}
void World::ManualRotate(int s,int duration) {
    ActiveObject &a=active[s];int direction=(pad&PAD_LEFT)?1:(pad&PAD_RIGHT)?-1:0;
    if(!direction) { a.direction=0;a.rotation.steps=0;return; }
    if(a.direction!=direction) a.rotation.steps=0;
    a.direction=direction;
    if(!a.rotation.steps) a.rotation={Pose(s).beta,Pose(s).beta+direction*256,a.speed?duration:duration/2,now};
    Pose(s).beta=AngleValue(a.rotation,Pose(s).beta,now);
}
void World::Aim(int s,Vec3 goal,int duration,int turn) {
    Actor &p=Pose(s);int dx=goal.x-p.pos.x,dz=goal.z-p.pos.z;
    auto side=[&](int beta) { Vec3 v={0,0,1000};Rotate(v,0,beta,0);int cross=v.x*dz-v.z*dx;return cross==0?0:cross>0?1:-1; };
    int mn=side(p.beta-4),mx=side(p.beta+4),direction=(mx==-1 && mn==1)?side(p.beta):((mx+mn+1)>>1);
    // FITD's cross-product test is ambiguous for an exactly opposite goal.
    // Choose a turn so entering a track with walking momentum cannot stall.
    if(!direction && (dx || dz)) { Vec3 forward={0,0,-1000};Rotate(forward,0,p.beta,0);if(forward.x*dx+forward.z*dz<0) direction=1; }
    ActiveObject &a=active[s];
    if(!a.rotation.steps || a.direction!=direction) a.rotation={p.beta,p.beta-direction*turn,duration,now};
    a.direction=direction;if(!direction) a.rotation.steps=0;else p.beta=AngleValue(a.rotation,p.beta,now);
}
void World::Track(int s) {
    ActiveObject &a=active[s];Actor &p=Pose(s);int mode=a.value.v[O_TRACK_MODE];
    if(mode==1) {
        ManualRotate(s,60);a.speed=(pad&PAD_UP)?((pad&PAD_B)?5:4):(pad&PAD_DOWN)?-1:0;return;
    }
    if(mode==2) {
        int target=Slot(a.value.v[O_TRACK]);if(target<0) { a.speed=a.direction=0;return; }
        Vec3 goal=InRoom(Pose(target).pos,Pose(target).room,p.room);
        if(Pose(target).room!=p.room) {
            Asset r=RoomAsset(p.floor,p.room);const uint8_t *b=r.data+BE32(r.data+20);
            for(unsigned i=0;i<BE16(r.data+10);++i,b+=16) if(BE16(b+14)==4) { Bounds box=ReadBox(b);goal={(box.lo.x+box.hi.x)/2,(box.lo.y+box.hi.y)/2,(box.lo.z+box.hi.z)/2};if(BS16(b+12)==Pose(target).room) break; }
        }
        Aim(s,goal,60,256);a.speed=4;return;
    }
    if(mode!=3 || a.value.v[O_TRACK]<0) return;
    int track=a.value.v[O_TRACK];if(track>=A32X_TRACK_COUNT) { Error(-1,track,904);return; }
    Asset asset=Platform_ReadAsset(track_assets[track]);int pc=a.value.v[O_TRACK_POS];
    auto word=[&](int offset) { if(pc+offset<0 || (unsigned)(pc+offset)*2+2>asset.size) { Error(-1,pc,905);return 0; }return (int)BS16(asset.data+(pc+offset)*2); };
    int op=word(0),advance=0;
    switch(op) {
    case 0: Stage(s,p.floor,word(1),{word(2),word(3),word(4)});a.speed=a.direction=a.rotation.steps=0;advance=5;break;
    case 1: { Vec3 goal=InRoom({word(2),0,word(3)},word(1),p.room);if(Abs(goal.x-p.pos.x)+Abs(goal.z-p.pos.z)<400) advance=4;else Aim(s,goal,15,64);break; }
    case 2: a.speed=0;a.value.v[O_TRACK]=-1;MoveMode(s,0,0);break;
    case 3: a.value.v[O_TRACK_POS]=0;break;
    case 4: a.mark=word(1);advance=2;break;
    case 5: a.speed=4;advance=1;break;
    case 6: a.speed=5;advance=1;break;
    case 7: a.speed=0;advance=1;break;
    case 9: { int beta=word(1);a.direction=(((p.beta-beta)&1023)>512)?1:-1;SetAngle(s,beta,120);if(p.beta==beta) { a.direction=0;advance=2; }break; }
    case 10: a.dyn_flags&=~1;advance=1;break;
    case 11: a.dyn_flags|=1;advance=1;break;
    case 13: a.value.v[O_FLAGS]&=~F_TRIGGER;advance=1;break;
    case 14: a.value.v[O_FLAGS]|=F_TRIGGER;advance=1;break;
    case 15: { Vec3 goal=InRoom({word(2),word(3),word(4)},word(1),p.room);if(p.pos.y==goal.y && Abs(goal.x-p.pos.x)+Abs(goal.z-p.pos.z)<400) advance=6;
        else { if(!a.vertical.steps) a.vertical={p.pos.y,goal.y,Max(1,word(5)),now};Aim(s,goal,60,256); }break; }
    case 16: objects[a.id].v[O_X]=p.pos.x;objects[a.id].v[O_Y]=p.pos.y;objects[a.id].v[O_Z]=p.pos.z;advance=1;break;
    case 17:case 18: {
        Vec3 goal={word(1),word(2),word(3)};WorldObject &o=objects[a.id];
        if(Abs(p.pos.y-goal.y)>100) {
            int denominator=(op==17?goal.x-o.v[O_X]:goal.z-o.v[O_Z]);int n=(op==17?p.pos.x-o.v[O_X]:p.pos.z-o.v[O_Z]);
            if(!denominator) { Error(-1,pc,906);break; }p.pos.y=o.v[O_Y]+(goal.y-o.v[O_Y])*n/denominator;Aim(s,goal,60,256);
        } else { p.pos.y=goal.y;advance=4; }break;
    }
    case 19: p.alpha=word(1);p.beta=word(2);p.gamma=word(3);a.direction=0;advance=4;break;
    default: Error(-1,pc,1000+op);break;
    }
    a.value.v[O_TRACK_POS]+=advance;
}
void World::Advance(int s) {
    ActiveObject &a=active[s];Actor &p=Pose(s);
    if(a.pending_anim!=-1) {
        int next=a.pending_anim;a.pending_anim=-1;
        if(next==-2) { a.pending_type=0;a.pending_next=-1;a.end_frame=0;a.end_anim=1;a.value.v[O_FLAGS]=(a.value.v[O_FLAGS]|F_DRAWABLE|F_BOXIFY)&~F_ANIMATED;return; }
        a.value.v[O_ANIM]=next;a.value.v[O_ANIM_TYPE]=a.pending_type;a.value.v[O_NEXT_ANIM]=a.pending_next;
        a.pending_type=0;a.pending_next=-1;a.end_anim=0;
        if(p.model.data) Actor_SetAnimation(p,animation_assets[character][next]);
    }
    Vec3 d={0,0,0};a.end_frame=0;
    if(a.value.v[O_ANIM]>=0 && p.model.data && p.animation.data) {
        d=Actor_Advance(p,(a.value.v[O_ANIM_TYPE]&1)!=0);a.end_frame=p.end_frame;a.end_anim=p.end_anim;
        if(a.end_anim && !(a.value.v[O_ANIM_TYPE]&1)) {
            a.value.v[O_ANIM_TYPE]&=~2;Animate(s,a.value.v[O_NEXT_ANIM],1,-1);
        }
    }
    d.y=0; // FITD vertical displacement belongs to YHandler, not animation roots.
    if(a.value.v[O_ANIM]<0 && a.speed && a.speed_change.steps) {
        unsigned elapsed=Min(now-a.speed_change.since,(unsigned)a.speed_change.steps);
        int value=a.speed_change.end*(int)elapsed/a.speed_change.steps;
        d.z+=value-a.speed_step;a.speed_step=value;
        if(elapsed==(unsigned)a.speed_change.steps) { a.speed_change.since=now;a.speed_step=0; }
        Rotate(d,0,p.beta,0);
    }
    if(a.vertical.steps) {
        unsigned elapsed=now-a.vertical.since;
        int y=elapsed>=(unsigned)a.vertical.steps?a.vertical.end:a.vertical.start+(a.vertical.end-a.vertical.start)*(int)elapsed/a.vertical.steps;
        d.y=y-p.pos.y;if(elapsed>=(unsigned)a.vertical.steps) a.vertical.steps=0;
    }
    if(a.hit_type==9) { p.pos.x+=d.x;p.pos.y+=d.y;p.pos.z+=d.z; }
    else MoveActor(s,d);
    if(!a.vertical.steps && (a.value.v[O_FLAGS]&F_FALLABLE)) {
        Bounds below=Offset(Box(s),{0,100,0});bool supported=HardCollision(below,p.floor,p.room)>=0;
        for(int t=0;t<MAX_ACTIVE && !supported;++t) if(t!=s && active[t].id>=0 && Pose(t).floor==p.floor && Intersect(below,Box(t,p.room))) supported=true;
        if(p.pos.y< -10 && !supported) { a.vertical={p.pos.y,p.pos.y+2000,40,now};a.falling=1; }
        else a.falling=0;
    }
    // MoveActor already reports the original stationary overlaps. Thrown
    // objects bypass it, so only that path needs a separate stationary scan.
    if(a.hit_type==9 && !d.x && !d.y && !d.z) {
        int num=0;for(int t=0;t<MAX_ACTIVE && num<3;++t) if(t!=s && active[t].id>=0 && Pose(t).floor==p.floor && Intersect(Box(s),Box(t,p.room))) { a.col[num++]=t;active[t].col_by=s; }
    }
}
void World::Zones(int s) {
    Actor &p=Pose(s);Asset r=RoomAsset(p.floor,p.room);if(!r.data) return;
    const uint8_t *b=r.data+BE32(r.data+20);
    for(unsigned i=0;i<BE16(r.data+10);++i,b+=16) {
        Bounds box=ReadBox(b);
        if(p.pos.x<box.lo.x || p.pos.x>box.hi.x || p.pos.y<box.lo.y || p.pos.y>box.hi.y || p.pos.z<box.lo.z || p.pos.z>box.hi.z) continue;
        int parameter=BS16(b+12),type=BE16(b+14);
        if(type==0) { Vec3 pos=InRoom(p.pos,p.room,parameter);Stage(s,p.floor,parameter,pos);active[s].room_chrono=now; }
        if(type==9 || type==10) active[s].hard_dec=parameter;
        if(type==10) { int life=objects[active[s].id].v[O_FLOOR_LIFE];if(life>=0) active[s].value.v[O_LIFE]=life; }
        return;
    }
}
void World::Combat(int s) {
    ActiveObject &a=active[s];Actor &p=Pose(s);if(!a.hit_type) return;
    if(a.hit_type==9) {
        WorldObject &o=objects[a.id];Vec3 old={o.v[O_X],o.v[O_Y],o.v[O_Z]};
        int distance=Max(Abs(p.pos.x-old.x),Abs(p.pos.z-old.z));
        int steps=Max(1,(distance+99)/100);Vec3 previous=old;
        for(int n=0;n<=steps;++n) {
            Vec3 point={old.x+(p.pos.x-old.x)*n/steps,old.y,old.z+(p.pos.z-old.z)*n/steps};
            Bounds range={{point.x-200,point.y-200,point.z-200},{point.x+200,point.y+200,point.z+200}};
            for(int t=0;t<MAX_ACTIVE;++t) if(t!=s && active[t].id>=0 && Pose(t).floor==p.floor && Intersect(range,Box(t,p.room))) {
                if(active[t].id==o.v[O_ALPHA]) { o.v[O_X]=p.pos.x;o.v[O_Y]=p.pos.y;o.v[O_Z]=p.pos.z;return; }
                if(active[t].id==cvars[11]) { o.v[O_ALPHA]=active[t].id;p.beta=(p.beta+512)&1023;p.pos=previous;o.v[O_X]=p.pos.x;o.v[O_Y]=p.pos.y;o.v[O_Z]=p.pos.z;return; }
                a.hit=t;active[t].hit_by=s;active[t].hit_force=a.hit_force;StopThrow(s,previous);return;
            }
            Asset room=RoomAsset(p.floor,p.room);const uint8_t *zone=room.data+BE32(room.data+20);bool stop=false;
            for(unsigned z=0;z<BE16(room.data+10);++z,zone+=16) {
                Bounds box=ReadBox(zone);int type=BE16(zone+14);
                if(point.x>=box.lo.x && point.x<=box.hi.x && point.y>=box.lo.y && point.y<=box.hi.y && point.z>=box.lo.z && point.z<=box.hi.z) { stop=type==0 || type==10;break; }
            }
            if(stop || HardCollision(range,p.floor,p.room)>=0) { StopThrow(s,previous);return; }
            previous=point;
        }
        o.v[O_X]=p.pos.x;o.v[O_Y]=p.pos.y;o.v[O_Z]=p.pos.z;return;
    }
    if(a.value.v[O_ANIM]!=a.hit_anim && a.hit_type!=8 && a.hit_type!=7) { if(a.pending_anim!=a.hit_anim) a.hit_type=0;return; }
    if(a.hit_type==1 || a.hit_type==4) { if((int)ScriptFrame(s)==a.hit_frame) a.hit_type=a.hit_type==1?2:5;return; }
    Vec3 point={0,0,0};
    if(p.model.data && a.hit_group>=0 && a.hit_group<BE16(p.model.data+4)) {
        // Shared scratch; avoid a 6 KiB array on the SH2 combat stack.
        Vec3 *vertices=Actor_GameplayScratch();Actor_Vertices(p,vertices);
        const uint8_t *group=p.model.data+BE32(p.model.data+24)+a.hit_group*16;point=vertices[BE16(group+4)];
    }
    point.x+=p.pos.x;point.y+=p.pos.y;point.z+=p.pos.z;
    if(a.hit_type==6) {
        WorldObject &o=objects[a.throw_object];
        Asset model=Platform_ReadAsset(model_assets[character][o.v[O_BODY]]);
        Bounds box=ReadBox(model.data+8);box=Offset(box,point);
        if(HardCollision(box,p.floor,p.room)>=0) { Drop(a.throw_object,a.id);a.hit_type=0;return; }
        if((int)ScriptFrame(s)!=a.hit_frame) return;
        for(int i=0;i<inventory_count;++i) if(inventory[i]==a.throw_object) {
            for(int j=i;j+1<inventory_count;++j) inventory[j]=inventory[j+1];
            --inventory_count;break;
        }
        o.v[O_X]=point.x;o.v[O_Y]=point.y;o.v[O_Z]=point.z;o.v[O_ROOM]=p.room;o.v[O_FLOOR]=p.floor;
        o.v[O_ALPHA]=p.alpha;o.v[O_BETA]=(p.beta+512)&1023;o.v[O_FOUND_FLAGS]&=0x3fff;
        o.v[O_FLAGS]=(o.v[O_FLAGS]|0x85)&~32;a.hit_type=7;return;
    }
    if(a.hit_type==7) {
        int slot=Slot(a.throw_object);if(slot<0) return;
        ActiveObject &item=active[slot];Actor &pose=Pose(slot);WorldObject &o=objects[item.id];
        pose.pos=point;Actor_Bounds(pose,1);item.value.v[O_FLAGS]=(item.value.v[O_FLAGS]|F_ANIMATED)&~F_BOXIFY;
        o.v[O_X]=point.x;o.v[O_Y]=point.y;o.v[O_Z]=point.z;o.v[O_ALPHA]=a.id;
        item.dyn_flags=0;item.hit_type=9;item.hit_size=100;item.hit_force=a.hit_force;item.hit_group=-1;
        item.speed=3000;item.speed_change={0,3000,60,now};item.speed_step=0;a.hit_type=0;return;
    }
    if(a.hit_type==8) return; // Original HIT_OBJECT has no GereFrappe action.
    int range=a.hit_size;Bounds hitbox={{point.x-range,point.y-range,point.z-range},{point.x+range,point.y+range,point.z+range}};
    if(a.hit_type==5) {
        Vec3 step={0,0,-range*2};Rotate(step,0,p.beta,0);
        for(int n=0;n<250;++n) {
            hitbox=Offset(hitbox,step);
            if(HardCollision(hitbox,p.floor,p.room)>=0) break;
            bool hit=false;
            for(int t=0;t<MAX_ACTIVE;++t) if(t!=s && active[t].id>=0 && Pose(t).floor==p.floor && Intersect(hitbox,Box(t,p.room))) { a.hit=t;active[t].hit_by=s;active[t].hit_force=a.hit_force;hit=true;break; }
            if(hit) break;
        }
        a.hit_type=0;return;
    }
    for(int t=0;t<MAX_ACTIVE;++t) if(t!=s && active[t].id>=0 && Pose(t).floor==p.floor && Intersect(hitbox,Box(t,p.room))) {
        a.hit=t;active[t].hit_by=s;active[t].hit_force=a.hit_force;
        if(active[t].value.v[O_FLAGS]&F_ANIMATED) { a.hit_type=0;break; }
    }
}
void World::Update(uint16_t controller,bool acting) {
    if(fault_code || finished) return;
    pad=controller;click=acting?1:0;action=acting?0x2000:0;++ticks;now=ticks*ANIMATION_HZ/GAME_HZ;
    for(auto &e:effects) if(e.count && now-e.since>=e.duration) e.count=0;
    if(in_hand>=0) FoundLife(in_hand,action);
    for(int s=0;s<MAX_ACTIVE;++s) if(active[s].id>=0) {
        ActiveObject &a=active[s];a.end_frame=0;a.col_by=a.hit=a.hit_by=a.hard_dec=a.hard_col=-1;
        for(int i=0;i<3;++i) a.col[i]=-1;
    }
    for(int s=0;s<MAX_ACTIVE;++s) if(active[s].id>=0 && Pose(s).floor==floor) {
        if(active[s].value.v[O_FLAGS]&F_ANIMATED) Advance(s);
        if(active[s].value.v[O_FLAGS]&F_TRIGGER) Zones(s);
        if(active[s].hit_type) Combat(s);
    }
    int previous_floor=floor;
    for(int s=0;s<MAX_ACTIVE && !fault_code;++s) if(active[s].id>=0 && active[s].value.v[O_LIFE]>=0 && active[s].value.v[O_LIFE_MODE]!=-1) {
        RunLife(active[s].value.v[O_LIFE],s);if(floor!=previous_floor) break;
    }
    int target=Slot(camera_target);
    if(target>=0 && RoomAsset(Pose(target).floor,Pose(target).room).data) {
        Actor &p=Pose(target);
        if(floor!=p.floor || room!=p.room) { floor=p.floor;room=p.room;camera=0;view_changed=true; }
        Asset r=RoomAsset(floor,room);const uint8_t *ids=r.data+BE32(r.data+12);unsigned count=BE16(r.data+6);
        Asset current_camera={};
        if((unsigned)camera<camera_counts[floor]) current_camera=Platform_ReadAsset(floor_cameras[floor][camera]);
        bool current=false;
        if(current_camera.data && current_camera.type==3)
            for(unsigned i=0;i<count;++i) if(BE16(ids+2*i)==(unsigned)camera) current=true;
        if(!current || !Camera_Contains(current_camera,room,p.pos.x+(p.collision_min.x+p.collision_max.x)/2,p.pos.z+(p.collision_min.z+p.collision_max.z)/2)) {
            // Keep the last valid view across uncovered zone edges. FITD does
            // this too; defaulting to ids[0] can select a neighbouring room.
            int chosen=current?camera:-1,best=32000;
            Bounds zv=Box(target);int x=(zv.lo.x/10+zv.hi.x/10)*5,z=(zv.lo.z/10+zv.hi.z/10)*5;
            for(unsigned i=0;i<count;++i) {
                int id=BE16(ids+2*i);if((unsigned)id>=camera_counts[floor]) continue;
                Asset cam=Platform_ReadAsset(floor_cameras[floor][id]);
                // Reject missing or malformed views before inspecting them.
                if(!cam.data || cam.type!=3) continue;
                if(chosen<0) chosen=id;
                if(!Camera_Contains(cam,room,x,z)) continue;
                int angle=Abs(p.beta+((BS16(cam.data+2)+512)&1023));
                if(angle<best) { best=angle;chosen=id; }
            }
            if(chosen<0) { Error(-1,room,920);return; }
            if(chosen!=camera) { camera=chosen;view_changed=true; }
        }
    }
    for(int s=0;s<MAX_ACTIVE;++s) if(active[s].id>=0 && (active[s].value.v[O_FLAGS]&F_MOVABLE) && active[s].value.v[O_ANIM]<0 && active[s].col_by<0) active[s].value.v[O_FLAGS]&=~F_ANIMATED;
    RefreshActors();
}
void World::Delete(int id) {
    if(id<0 || id>=A32X_OBJECT_COUNT) { Error(-1,id,907);return; }
    int s=Slot(id);if(s>=0) Deactivate(s);
    objects[id].v[O_ROOM]=objects[id].v[O_FLOOR]=-1;
    if(objects[id].v[O_FOUND_BODY]>=0) objects[id].v[O_FOUND_FLAGS]=(objects[id].v[O_FOUND_FLAGS]&~0x8000)|0x4000;
    for(int i=0;i<inventory_count;++i) if(inventory[i]==id) { for(int j=i;j+1<inventory_count;++j) inventory[j]=inventory[j+1];--inventory_count;break; }
}
A32X_COLD void World::Take(int id,int depth) {
    if(id<0 || id>=A32X_OBJECT_COUNT || inventory_count>=INVENTORY_CAPACITY-1) return;
    for(int i=0;i<inventory_count;++i) if(inventory[i]==id) return;
    int weight=objects[id].v[O_TRACK_POS];for(int i=0;i<inventory_count;++i) weight+=objects[inventory[i]].v[O_TRACK_POS];
    if(weight>cvars[2]) { message=101;message_until=now+180;return; }
    if(!inventory_count) inventory[0]=id;
    else { for(int i=inventory_count;i>1;--i) inventory[i]=inventory[i-1];inventory[1]=id; }
    ++inventory_count;
    FoundLife(id,0x800,depth+1);
    int s=Slot(id);if(s>=0) Deactivate(s);
    objects[id].v[O_FOUND_FLAGS]=(objects[id].v[O_FOUND_FLAGS]&0xbfff)|0x8000;
    objects[id].v[O_ROOM]=objects[id].v[O_FLOOR]=-1;
}
A32X_COLD void World::Drop(int id,int source) {
    if(id<0 || id>=A32X_OBJECT_COUNT || source<0 || source>=A32X_OBJECT_COUNT) return;
    WorldObject &o=objects[id];
    int16_t values[9];
    for(int field=O_X;field<=O_ROOM;++field) values[field-O_X]=(int16_t)Get(source,field);
    int s=Slot(id);if(s>=0) Deactivate(s);
    for(int field=O_X;field<=O_ROOM;++field) o.v[field]=values[field-O_X];
    for(int i=0;i<inventory_count;++i) if(inventory[i]==id) {
        for(int j=i;j+1<inventory_count;++j) inventory[j]=inventory[j+1];
        --inventory_count;break;
    }
    o.v[O_FLAGS]|=F_FOUNDABLE;o.v[O_FOUND_FLAGS]=(o.v[O_FOUND_FLAGS]&~0x8000)|0x4000;
    if(in_hand==id) in_hand=2;
    RefreshActors();
}
void World::StopThrow(int s,Vec3 position) {
    ActiveObject &a=active[s];Actor &p=Pose(s);Actor_Bounds(p,1);
    int y=(p.pos.y/2000)*2000;
    // Original backwards search, bounded so a malformed room cannot hang SH2.
    bool found=false;
    for(int step=0;step<=20000 && !found;step+=100) {
        Vec3 d={0,0,-step};Rotate(d,0,p.beta+512,0);
        Vec3 candidate={position.x+d.x,y,position.z+d.z};
        Bounds box=Offset({p.collision_min,p.collision_max},candidate);
        if(HardCollision(box,p.floor,p.room)>=0) continue;
        if(y< -500 && HardCollision(Offset(box,{0,100,0}),p.floor,p.room)<0) { y+=2000;step-=100;continue; }
        p.pos=candidate;found=true;
    }
    if(!found) { Error(-1,a.id,919);return; }
    p.gamma=0;a.hit_type=a.speed=0;
    a.value.v[O_FLAGS]=(a.value.v[O_FLAGS]|F_DRAWABLE|F_BOXIFY)&~F_ANIMATED;
    objects[a.id].v[O_FOUND_FLAGS]=(objects[a.id].v[O_FOUND_FLAGS]|0x4000)&~0x1000;
}
// Bounds constraints execute from ROM to retain the fixed SDRAM budget.
A32X_COLD __attribute__((noinline)) static void ConstrainDrawOrder(const World &world,int *order,int count,
                                        const int *nearest,const int *farthest,Vec3 camera_position) {
    if(count<2) return;
    // The original pair-dependent distance heuristic can form cycles: a third
    // model can stop insertion sorting from putting two wholly separated
    // depth ranges in their required order. Retain that stable order as a
    // preference, then honor unambiguous bounds across the complete list.
    uint64_t predecessors[MAX_ACTIVE]={};uint64_t remaining=0;bool changed=false;
    for(int i=0;i<count;++i) remaining|=uint64_t(1)<<order[i];
    for(int i=0;i<count;++i) for(int j=i+1;j<count;++j) {
        int a=order[i],b=order[j],first=-1,last=-1;
        // Equal, zero-thickness depth planes have no required precedence.
        if(nearest[a]>=farthest[b] && nearest[b]<farthest[a]) { first=a;last=b; }
        else if(nearest[b]>=farthest[a] && nearest[a]<farthest[b]) { first=b;last=a; }
        else {
            Bounds x=world.Box(a,world.room),y=world.Box(b,world.room);
            auto plane=[](int alo,int ahi,int blo,int bhi,int camera) {
                if((alo>=bhi && blo<alo && camera<alo) ||
                   (ahi<=blo && bhi>ahi && camera>ahi)) return 1;
                if((blo>=ahi && alo<blo && camera<blo) ||
                   (bhi<=alo && ahi>bhi && camera>bhi)) return -1;
                return 0;
            };
            int precedence=plane(x.lo.y,x.hi.y,y.lo.y,y.hi.y,camera_position.y);
            if(!precedence) {
                // A window behind pushed furniture can have an overlapping
                // camera-depth range while a world-axis plane still separates
                // their surfaces. A third actor must not defeat that order.
                int horizontal=plane(x.lo.x,x.hi.x,y.lo.x,y.hi.x,camera_position.x);
                int longitudinal=plane(x.lo.z,x.hi.z,y.lo.z,y.hi.z,camera_position.z);
                // Opposite axis preferences belong to diagonally separated
                // boxes; retain the existing order instead of forcing both.
                if(!horizontal || !longitudinal || horizontal==longitudinal)
                    precedence=horizontal?horizontal:longitudinal;
            }
            if(precedence) { first=precedence>0?a:b;last=precedence>0?b:a; }
        }
        if(first>=0) { predecessors[last]|=uint64_t(1)<<first;changed|=last==a; }
    }
    if(!changed) return;
    for(int i=0;i<count;++i) {
        int next=i;
        while(next<count && (predecessors[order[next]]&remaining)) ++next;
        if(next==count) {
            // Camera depth intervals are acyclic. A cycle can only involve
            // world-axis preferences for intersecting intervals; break those
            // preference deterministically while preserving all depth edges.
            for(next=i;next<count;++next) {
                int s=order[next];bool blocked=false;
                for(int j=i;j<count && !blocked;++j) {
                    int t=order[j];
                    blocked=t!=s && nearest[t]>=farthest[s] && nearest[s]<farthest[t];
                }
                if(!blocked) break;
            }
        }
        int s=order[next];for(int j=next;j>i;--j) order[j]=order[j-1];order[i]=s;
        remaining&=~(uint64_t(1)<<s);
    }
}
int World::DrawList(int *order) const {
    Asset cam=Platform_ReadAsset(floor_cameras[floor][camera]),r=RoomAsset(floor,room);const uint8_t *views=cam.data+BE32(cam.data+20);
    int count=0;for(int s=0;s<MAX_ACTIVE;++s) if(active[s].id>=0 && Get(active[s].id,O_BODY)>=0) {
        bool viewed=false;for(unsigned i=0;i<BE16(cam.data+18);++i) if(BE16(views+16*i)==(unsigned)Get(active[s].id,O_ROOM)) viewed=true;
        if(viewed) order[count++]=s;
    }
    Vec3 camera_position={(BS16(cam.data+6)-BS16(r.data))*10,(BS16(r.data+2)-BS16(cam.data+8))*10,(BS16(r.data+4)-BS16(cam.data+10))*10};
    Rotation view_rotation=PrepareRotation(BS16(cam.data),BS16(cam.data+2),BS16(cam.data+4));
    int farthest[MAX_ACTIVE],nearest[MAX_ACTIVE];
    for(int i=0;i<count;++i) {
        int s=order[i];Bounds box=Box(s,room);nearest[s]=0x7fffffff;farthest[s]=-0x7fffffff;
        for(int corner=0;corner<8;++corner) {
            Vec3 v={(corner&1?box.hi.x:box.lo.x)-camera_position.x,
                    (corner&2?box.hi.y:box.lo.y)-camera_position.y,
                    (corner&4?box.hi.z:box.lo.z)-camera_position.z};
            Rotate(v,view_rotation);nearest[s]=Min(nearest[s],v.z);farthest[s]=Max(farthest[s],v.z);
        }
    }
    auto closer=[&](int left,int right) {
        Bounds a=Box(left,room),b=Box(right,room);int d1=0,d2=0;
        // Vertically separated surfaces have an unambiguous order along a
        // shared camera ray. Floor panels must stay below standing objects,
        // even when their horizontal distance puts them nearer the camera.
        if(a.lo.y>=b.hi.y && b.lo.y<a.lo.y && camera_position.y<a.lo.y) return false;
        if(b.lo.y>=a.hi.y && a.lo.y<b.lo.y && camera_position.y<b.lo.y) return true;
        if(a.hi.y<=b.lo.y && b.hi.y>a.hi.y && camera_position.y>a.hi.y) return false;
        if(b.hi.y<=a.lo.y && a.hi.y>b.hi.y && camera_position.y>b.hi.y) return true;
        // A distant door can be nearer on one world axis while its whole
        // surface lies behind the player along the actual camera direction.
        if(nearest[left]>=farthest[right]) return false;
        if(nearest[right]>=farthest[left]) return true;
        // Mounted windows share the floor scene with the player. Height
        // buckets can put their glass in front despite greater camera distance.
        {
            auto overlap=[](int a,int b,int c,int d) { return a<=d && b>=c; };
            bool x=overlap(a.lo.x,a.hi.x,b.lo.x,b.hi.x),z=overlap(a.lo.z,a.hi.z,b.lo.z,b.hi.z);
            if(!x && !z) { d1=Abs(camera_position.x-(a.lo.x+a.hi.x)/2)+Abs(camera_position.z-(a.lo.z+a.hi.z)/2);d2=Abs(camera_position.x-(b.lo.x+b.hi.x)/2)+Abs(camera_position.z-(b.lo.z+b.hi.z)/2); }
            else { if(z) { d1=Min(Abs(camera_position.x-a.lo.x),Abs(camera_position.x-a.hi.x));d2=Min(Abs(camera_position.x-b.lo.x),Abs(camera_position.x-b.hi.x)); }
                if(x) { d1+=Min(Abs(camera_position.z-a.lo.z),Abs(camera_position.z-a.hi.z));d2+=Min(Abs(camera_position.z-b.lo.z),Abs(camera_position.z-b.hi.z)); } }
        }
        return d1<d2;
    };
    for(int i=1;i<count;++i) { int s=order[i],j=i;while(j>0 && closer(order[j-1],s)) { order[j]=order[j-1];--j; }order[j]=s; }
    ConstrainDrawOrder(*this,order,count,nearest,farthest,camera_position);
    return count;
}
A32X_COLD const char *GameText(int id) {
    Asset a=Platform_ReadAsset(AS_TEXT);if(!a.data || a.size<4) return "";
    for(unsigned i=0;i<BE32(a.data);++i) { const uint8_t *e=a.data+4+i*8;if(BE16(e)==(unsigned)id) return (const char*)a.data+BE32(e+4); }
    return "";
}

void World::Special(int slot,int mode) {
    if(mode!=0 && mode!=1 && mode!=4) return;
    Effect *effect=nullptr;
    for(auto &e:effects) if(!e.count) { effect=&e;break; }
    if(!effect) effect=&effects[0];
    Effect &e=*effect;Actor &p=Pose(slot);
    e.floor=p.floor;e.room=p.room;e.since=now;e.duration=mode==0?120:mode==4?90:30;
    e.count=mode==0?30:12;e.color=mode==1?80:192;e.mode=mode;
    ++effect_serial;
    // Presentation RNG is separate: particles must not change LIFE RND choices.
    uint32_t seed=effect_serial*1664525u+now;
    auto random=[&](int lo,int hi) { seed=seed*1664525u+1013904223u;return lo+(int)((seed>>16)%(unsigned)Max(1,hi-lo)); };
    for(unsigned i=0;i<e.count;++i) {
        e.points[i]={(int16_t)(p.pos.x+random(p.collision_min.x,p.collision_max.x)),
                     (int16_t)(p.pos.y+random(p.collision_min.y,p.collision_max.y)),
                     (int16_t)(p.pos.z+random(p.collision_min.z,p.collision_max.z))};
    }
}
