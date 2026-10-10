// SPDX-License-Identifier: GPL-2.0-or-later
// AITD1 LIFE bytecode; branch offsets are words, evaluation uses the caller.
#include "world.hpp"
#include "../platform/audio.hpp"
#include "../platform/platform_api.hpp"
struct LifeReader {
    World &w;Asset a;int life,pc,caller;bool stopped;
    int Raw() { if(pc<0 || (unsigned)pc*2+2>a.size) { w.Error(life,pc,910);stopped=true;return 0; }return BS16(a.data+2*pc++); }
    void Jump(int d) { pc+=d;if(pc<0 || (unsigned)pc*2>=a.size) { w.Error(life,pc,911);stopped=true; } }
    int VarIndex() { int n=Raw();if(n<0 || n>=A32X_VAR_COUNT) { w.Error(life,pc-1,912);stopped=true;return 0; }return n; }
    int Object() { int n=Raw();if(n<0 || n>=A32X_OBJECT_COUNT) { w.Error(life,pc-1,913);stopped=true;return 0; }return n; }
    int Eval(int depth=0) {
        if(depth>8) { w.Error(life,pc,914);stopped=true;return 0; }
        int code=Raw();if(code==-1) return Raw();if(code==0) return w.vars[VarIndex()];
        int s=caller,id=w.active[caller].id;
        if(code&0x8000) { id=Object();s=w.Slot(id);code&=0x7fff; }
        if(s<0) { if(code==31) return w.Get(id,O_ROOM);if(code==38) return w.Get(id,O_FLOOR);w.Error(life,pc,2000+code);stopped=true;return 0; }
        ActiveObject &actor=w.active[s];Actor &p=w.Pose(s);
        auto worldid=[&](int slot) { return slot<0?-1:w.active[slot].id; };
        switch(code) {
        case 1:return worldid(actor.col[0]);case 2:return actor.hard_dec;case 3:return actor.hard_col;
        case 4:return worldid(actor.hit);case 5:return worldid(actor.hit_by);case 6:return actor.value.v[O_ANIM];
        case 7:return actor.end_anim;case 8:return p.frame;case 9:return actor.end_frame;case 10:return actor.value.v[O_BODY];
        case 11:return actor.mark;case 12:return actor.value.v[O_TRACK];case 13:return (w.now-actor.chrono)/60;case 14:return (w.now-actor.room_chrono)/60;
        case 15:return w.Distance(s,w.Slot(Object()));case 16:return worldid(actor.col_by);
        case 17: { int obj=Eval(depth+1);return obj>=0 && obj<A32X_OBJECT_COUNT && (w.objects[obj].v[O_FOUND_FLAGS]&0x8000)?1:0; }
        case 18:return w.action;case 19:return w.PosRel(s,w.Slot(Object()));
        case 20:return w.pad&PAD_LEFT?4:w.pad&PAD_RIGHT?8:w.pad&PAD_UP?1:w.pad&PAD_DOWN?2:0;
        case 21:return w.click;case 22:return worldid(actor.col[0]>=0?actor.col[0]:actor.col_by);
        case 23:return p.alpha;case 24:return p.beta;case 25:return p.gamma;case 26:return w.in_hand;case 27:return actor.hit_force;
        case 28:return w.camera;
        case 29: { int n=Raw();w.rng=w.rng*1103515245+12345;return n>0?(w.rng>>16)%n:0; }
        case 30:return actor.falling;case 31:return p.room;case 32:return actor.value.v[O_LIFE];
        case 33:return (w.objects[Object()].v[O_FOUND_FLAGS]&0xc000)?1:0;case 34:return p.pos.y;
        case 35: {
            int anim=Raw(),y=Raw();if(anim<0 || anim>=A32X_ANIMATION_COUNT) return 0;
            Asset a=Platform_ReadAsset(animation_assets[w.character][anim]);int stride=8+BE16(a.data+2)*8;Vec3 d={0,y,0};
            for(unsigned i=0;i<BE16(a.data);++i) d.z+=BS16(a.data+4+i*stride+6);
            Rotate(d,0,p.beta,0);Bounds b=w.Box(s);b.lo={b.lo.x+d.x,b.lo.y+d.y,b.lo.z+d.z};b.hi={b.hi.x+d.x,b.hi.y+d.y,b.hi.z+d.z};
            if(w.HardCollision(b,p.floor,p.room)>=0) return 0;
            b.lo.y+=100;b.hi.y+=100;return w.HardCollision(b,p.floor,p.room)>=0?1:0;
        }
        case 36:return w.music;case 37: { int n=Raw();if(n<0 || n>=45) { w.Error(life,pc,915);stopped=true;return 0; }return w.cvars[n]; }
        case 38:return p.floor;case 39:return (w.objects[Object()].v[O_FOUND_FLAGS]&0x1000)?1:0;
        default:w.Error(life,pc,2000+code);stopped=true;return 0;
        }
    }
};
void World::RunLife(int life,int caller,bool found,int depth) {
    if(life<0) return;
    if(life>=A32X_LIFE_COUNT || caller<0 || caller>=MAX_ACTIVE || depth>8) { Error(life,0,916);return; }
    LifeReader r={*this,Platform_ReadAsset(life_assets[life]),life,0,caller,false};int switch_value=0;
    for(int budget=0;budget<2048 && !r.stopped && !fault_code;++budget) {
        int start=r.pc,op=r.Raw(),target=caller,id=active[caller].id;
        if(op&0x8000) { id=r.Object();target=Slot(id);op&=0x7fff; }
        if(op<0 || op>86) { Error(life,start,3000+op);return; }
        auto set=[&](int field,int value) { Set(id,field,value); };
        if(target<0) {
            switch(op) {
            case 3:set(O_BODY,r.Eval());break;
            case 40: { int type=r.Raw()&0x1d1;set(O_FLAGS,(Get(id,O_FLAGS)&~0x1d1)|type);break; }
            case 1:case 2: { int anim=r.Raw(),next=r.Raw();set(O_ANIM,anim);set(O_ANIM_TYPE,op==2?2:0);set(O_NEXT_ANIM,next);break; }
            case 13:set(O_ANIM,r.Raw());set(O_ANIM_TYPE,1);set(O_NEXT_ANIM,-1);break;
            case 15: { int mode=r.Raw(),track=r.Raw();set(O_TRACK_MODE,mode);set(O_TRACK,track);set(O_TRACK_POS,0);break; }
            case 74:set(O_ALPHA,r.Raw());set(O_BETA,r.Raw());set(O_GAMMA,r.Raw());break;
            case 47: { int f=r.Raw(),room=r.Raw(),x=r.Raw(),y=r.Raw(),z=r.Raw();set(O_FLOOR,f);set(O_ROOM,room);set(O_X,x);set(O_Y,y);set(O_Z,z);break; }
            case 54: { int on=r.Raw();set(O_FLAGS,on?Get(id,O_FLAGS)|32:Get(id,O_FLAGS)&~32);break; }
            case 31:set(O_LIFE,r.Raw());break;case 24:set(O_LIFE_MODE,r.Raw());break;
            case 48:set(O_NAME,r.Raw());break;case 55:set(O_FOUND_BODY,r.Raw());break;
            case 49:set(O_FOUND_FLAGS,(Get(id,O_FOUND_FLAGS)&0xe000)|r.Raw());break;
            case 67:set(O_TRACK_POS,r.Raw());break;case 50:set(O_FOUND_LIFE,r.Raw());break;case 28:break;
            default:Error(life,start,4000+op);return;
            }
            continue;
        }
        ActiveObject &a=active[target];Actor &p=Pose(target);
        switch(op) {
        case 0:Track(target);break;
        case 1:case 2: { int anim=r.Raw(),next=r.Raw();if(anim==-1) { a.value.v[O_ANIM]=-1;a.pending_anim=-2; }else Animate(target,anim,op==2?2:0,next);break; }
        case 3:SetBody(target,r.Eval());break;
        case 4:case 5:case 6:case 7:case 8:case 9: { int x=r.Eval(),y=r.Eval(),jump=r.Raw();bool match=op==4?x==y:op==5?x!=y:op==6?x>=y:op==7?x>y:op==8?x<=y:x<y;if(!match) r.Jump(jump);break; }
        case 10: { int jump=r.Raw();r.Jump(jump);break; }case 11:case 12:return;
        case 13:Animate(target,r.Raw(),1,-1);break;
        case 14: {
            int anim[7];for(int i=0;i<7;++i) anim[i]=r.Raw();
            if(a.speed==5) Animate(target,anim[2],1,-1);else if(a.speed==4) Animate(target,anim[1],1,-1);
            else if(a.speed==-1) { if(a.value.v[O_ANIM]==anim[1]) Animate(target,anim[0],0,anim[4]);else if(a.value.v[O_ANIM]==anim[2]) Animate(target,anim[3],0,anim[0]);else Animate(target,anim[4],1,-1); }
            else if(a.speed==0) { if(a.value.v[O_ANIM]==anim[1] || a.value.v[O_ANIM]==anim[2]) Animate(target,anim[3],0,anim[0]);else Animate(target,a.direction==1?anim[6]:a.direction==-1?anim[5]:anim[0],a.direction?0:1,anim[0]); }
            break;
        }
        case 15: { int mode=r.Raw(),track=r.Raw();MoveMode(target,mode,track);break; }
        case 16:case 53: { int anim=r.Raw(),frame=r.Raw(),group=r.Raw(),size=r.Raw(),force=op==16?r.Eval():r.Raw(),next=r.Raw();if(a.value.v[O_ANIM]!=anim && !(a.value.v[O_ANIM_TYPE]&2)) { Animate(target,anim,op==53?2:0,next);a.hit_anim=anim;a.hit_frame=frame;a.hit_group=group;a.hit_size=size;a.hit_force=force;a.hit_type=op==16?1:4; }break; }
        case 17:message=r.Raw();message_until=now+180;break;case 18:message=r.Raw();r.Raw();message_until=now+180;break;
        case 19: { int n=r.VarIndex(),v=r.Eval();vars[n]=v;break; }case 20:++vars[r.VarIndex()];break;case 21:--vars[r.VarIndex()];break;
        case 22:case 23: { int n=r.VarIndex(),v=r.Eval();vars[n]+=op==22?v:-v;break; }
        case 24:a.value.v[O_LIFE_MODE]=r.Raw();break;case 25:switch_value=r.Eval();break;
        case 26: { int v=r.Raw(),jump=r.Raw();if(switch_value!=v) r.Jump(jump);break; }case 28:a.chrono=now;break;
        case 29: { int n=r.Raw();bool match=false;if(n<0 || n>128) { Error(life,start,917);return; }for(int i=0;i<n;++i) if(r.Raw()==switch_value) match=true;int jump=r.Raw();if(!match) r.Jump(jump);break; }
        case 30: { int obj=r.Object();if(prompt<0 && !(objects[obj].v[O_FOUND_FLAGS]&0xc000) && (objects[obj].v[O_TRACK]==0 || now-(uint16_t)objects[obj].v[O_TRACK]>=300)) prompt=obj;break; }
        case 31:a.value.v[O_LIFE]=r.Raw();break;case 32:Delete(r.Object());break;case 33:Take(r.Object(),depth);break;
        case 34:in_hand=r.Raw();break;case 35:book_type=r.Raw();book=r.Raw()+1;r.Raw();Audio_Sample(cvars[0]);break;
        case 36: { int sound=r.Eval(),anim=r.Raw(),frame=r.Raw();if(a.end_frame && a.value.v[O_ANIM]==anim && p.frame==(unsigned)frame) Audio_Sample(sound);break; }case 37:Special(target,r.Raw());break;
        case 38: {
            if(p.model.data) { Vec3 *points=Actor_GameplayScratch();Actor_Vertices(p,points);Vec3 lo={32000,32000,32000},hi={-32000,-32000,-32000};for(unsigned i=0;i<BE16(p.model.data+2);++i) { Vec3 v=points[i];lo={Min(lo.x,v.x),Min(lo.y,v.y),Min(lo.z,v.z)};hi={Max(hi.x,v.x),Max(hi.y,v.y),Max(hi.z,v.z)}; }p.collision_min=lo;p.collision_max=hi; }break;
        }
        case 39:Audio_Sample(r.Eval());break;case 40: { int type=r.Raw()&0x1d1;a.value.v[O_FLAGS]=(a.value.v[O_FLAGS]&~0x1d1)|type;break; }
        case 41:case 86:cvars[15]=1;finished=true;return;case 42:ManualRotate(target,240);break;case 43:r.Raw();break;
        case 44:music=r.Raw();break;case 45:case 56: { int angle=r.Raw(),duration=r.Raw();SetAngle(target,angle,duration,op==56);break; }
        case 46:SetBounds(target,3);break;case 47: { int f=r.Raw(),room=r.Raw(),x=r.Raw(),y=r.Raw(),z=r.Raw();Stage(target,f,room,{x,y,z});break; }
        case 48:set(O_NAME,r.Raw());break;case 49:set(O_FOUND_FLAGS,(Get(id,O_FOUND_FLAGS)&0xe000)|r.Raw());break;case 50:set(O_FOUND_LIFE,r.Raw());break;
        case 51:camera_target=r.Object();break;case 52: { int obj=r.Eval(),mode=r.Raw();Drop(obj,mode);break; }
        case 54:a.dyn_flags=r.Raw()?1:0;break;case 55:set(O_FOUND_BODY,r.Raw());break;case 57:a.rotation.steps=0;break;
        case 58:SetBounds(target,0);break;
        case 59: {
            int obj=r.Object(),x=r.Raw(),y=r.Raw(),z=r.Raw(),room=r.Raw(),f=r.Raw(),alpha=r.Raw(),beta=r.Raw(),gamma=r.Raw();
            int slot=Slot(obj);if(slot>=0) Stage(slot,f,room,{x,y,z});else { Set(obj,O_FLOOR,f);Set(obj,O_ROOM,room);Set(obj,O_X,x);Set(obj,O_Y,y);Set(obj,O_Z,z); }
            Set(obj,O_ALPHA,alpha);Set(obj,O_BETA,beta);Set(obj,O_GAMMA,gamma);objects[obj].v[O_FOUND_FLAGS]=(objects[obj].v[O_FOUND_FLAGS]&~0x8000)|0x4000;
            for(int i=0;i<inventory_count;++i) if(inventory[i]==obj) { for(int j=i;j+1<inventory_count;++j) inventory[j]=inventory[j+1];--inventory_count;break; }
            break;
        }
        case 60: { int n=r.Raw(),v=r.Eval();if(n<0 || n>=45) { Error(life,start,915);return; }cvars[n]=v;break; }
        case 61:SetBounds(target,1);break;case 62:SetBounds(target,2);break;case 63: { int sound=r.Eval(),next=r.Eval();Audio_Sample(sound,next);break; }
        case 85: { int sound=r.Eval(),next=r.Eval();Audio_Sample(sound,next,-1);break; }
        case 64:cvars[13]=r.Raw()?0:-1;break;case 65:r.Raw();break;case 66:inventory_allowed=r.Raw()!=0;break;case 67:set(O_TRACK_POS,r.Raw());break;
        case 68:a.vertical={p.pos.y,p.pos.y-2000,1,now-1};break;case 69:a.speed=r.Raw();break;
        case 70: { int obj=r.Object(),source=r.Object();Drop(obj,source);break; }
        case 71: { int x1=r.Raw(),x2=r.Raw(),y1=r.Raw(),y2=r.Raw(),z1=r.Raw(),z2=r.Raw();p.collision_min={x1,y1,z1};p.collision_max={x2,y2,z2};break; }
        case 72:a.hit_type=8;a.hit_size=r.Raw();a.hit_force=r.Raw();a.hit_group=-1;break;
        case 73:break;case 74:p.alpha=r.Raw();p.beta=r.Raw();p.gamma=r.Raw();break;
        case 75: { int sound=r.Eval(),count=r.Raw();Audio_Sample(sound,-1,count?Max(0,count-1):-1);break; }
        case 76: { int anim=r.Raw(),frame=r.Raw(),group=r.Raw(),obj=r.Object(),range=r.Raw(),force=r.Raw(),next=r.Raw();Animate(target,anim,2,next);if(!range) objects[obj].v[O_GAMMA]-=256;objects[obj].v[O_FOUND_FLAGS]|=0x1000;a.hit_type=6;a.hit_anim=anim;a.hit_frame=frame;a.hit_group=group;a.throw_object=obj;a.hit_size=range;a.hit_force=force;break; }
        case 77:r.Raw();break;case 78:r.Raw();r.Raw();r.Raw();break;case 79:Audio_StopSamples();break;
        case 80: { int m=r.Raw();if(music==-1) music=m;else next_music=m;break; }case 81: { int next=r.Raw();if(music==-1) music=next;else { next_music=next;music=-2; }break; }
        case 82:if(a.hit_type==8) { a.hit_type=0;a.hit_force=0; }break;
        case 83: { int obj=r.Object();p.alpha=Get(obj,O_ALPHA);p.beta=Get(obj,O_BETA);p.gamma=Get(obj,O_GAMMA);break; }
        case 84:finished=true;return;default:Error(life,start,3000+op);return;
        }
        (void)found;
    }
    if(!r.stopped && !fault_code) Error(life,r.pc,918);
}
A32X_COLD void World::FoundLife(int id,int act,int depth) {
    if(id<0 || id>=A32X_OBJECT_COUNT) return;
    int life=objects[id].v[O_FOUND_LIFE];if(life<0) return;
    int saved_action=action;action=act;int s=Slot(id);bool temporary=s<0;
    if(temporary) {
        s=MAX_ACTIVE-1;while(s>=0 && active[s].id>=0) --s;
        if(s<0) { Error(life,0,902);action=saved_action;return; }
        active[s]={};active[s].id=id;active[s].value=objects[id];active[s].value.v[O_BODY]=-1;
        active[s].value.v[O_ANIM]=-1;active[s].value.v[O_FLAGS]=0;active[s].value.v[O_TRACK]=-1;
        active[s].pending_anim=-1;active[s].hit=active[s].hit_by=active[s].col_by=-1;
        Actor &p=Pose(s);p.character=character;p.model=p.animation={0,0,0,0,0};p.pos={0,0,0};p.room=p.floor=-1;p.alpha=p.beta=p.gamma=0;p.frame=0;
    }
    RunLife(life,s,true,depth+1);if(temporary) active[s].id=-1;action=saved_action;
}
