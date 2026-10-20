// SPDX-License-Identifier: GPL-2.0-or-later
// Animation/group semantics adapted from FITD hqr.cpp, anim.cpp, renderer.cpp.
#include "actor.hpp"
#include "../platform/platform_api.hpp"
#ifndef AITD_RESOURCE_IDS
#define AITD_RESOURCE_IDS "../../assets/resource_ids.h"
#endif
#include AITD_RESOURCE_IDS

static unsigned Groups(const Actor &a) { return BE16Aligned(a.model.data+4); }
static unsigned AnimGroups(const Actor &a) { return BE16Aligned(a.animation.data+2); }
static const uint8_t *Key(const Actor &a,unsigned frame) {
    return a.animation.data+4+frame*(8+AnimGroups(a)*8);
}
static GroupState ReadState(const uint8_t *p) {
    GroupState s={BS16Aligned(p),{BS16Aligned(p+2),BS16Aligned(p+4),BS16Aligned(p+6)}}; return s;
}
void Actor_SetModel(Actor &a,int model) {
    a.model={0,0,0,0,0};
    if(model<0) return;
    if(model>=A32X_MODEL_COUNT) Platform_Fatal();
    a.model=Platform_ReadAsset(model_assets[a.character][model]);
    if(!a.model.data || BE16Aligned(a.model.data+2)>MAX_VERTICES || Groups(a)>MAX_GROUPS || BE16Aligned(a.model.data+6)>MAX_PRIMITIVES) Platform_Fatal();
    const uint8_t *gp=a.model.data+BE32Aligned(a.model.data+24);
    for(unsigned i=0;i<Groups(a);++i) a.state[i]=a.previous[i]=ReadState(gp+16*i+8);
}
void Actor_Bounds(Actor &a,int type) {
    a.collision_min={-100,-2000,-100};a.collision_max={100,0,100};
    if(!a.model.data) return;
    const uint8_t *m=a.model.data;
    Vec3 lo={BS16Aligned(m+8),BS16Aligned(m+12),BS16Aligned(m+16)},hi={BS16Aligned(m+10),BS16Aligned(m+14),BS16Aligned(m+18)};
    if(type==0 || type==2) {
        int extent=type==2?(hi.x+hi.z)/2:Max(hi.x-lo.x,hi.z-lo.z)/2;
        lo.x=lo.z=-extent;hi.x=hi.z=extent;
    } else if(type==3) {
        Rotation rotation=PrepareRotation(a.alpha,a.beta,a.gamma);
        Vec3 mn={32000,32000,32000},mx={-32000,-32000,-32000};
        for(int i=0;i<8;++i) {
            Vec3 v={(i&1)?hi.x:lo.x,(i&2)?hi.y:lo.y,(i&4)?hi.z:lo.z};Rotate(v,rotation);
            mn={Min(mn.x,v.x),Min(mn.y,v.y),Min(mn.z,v.z)};mx={Max(mx.x,v.x),Max(mx.y,v.y),Max(mx.z,v.z)};
        }
        lo=mn;hi=mx;
    }
    a.collision_min=lo;a.collision_max=hi;
}
A32X_COLD void Actor_Init(Actor &a,int character) {
    a.character=character;a.alpha=a.gamma=0;a.beta=0;a.room=a.floor=0;
    Actor_SetModel(a,12);Actor_Bounds(a,2);
    a.frame=0;a.frame_phase=0;a.last_step={0,0,0};a.walking=false;
    a.end_frame=a.end_anim=false;
    Actor_SetAnimation(a,player_idle_assets[character]);
}
void Actor_SetAnimation(Actor &a,unsigned asset) {
    for(unsigned i=0;i<(a.model.data?Groups(a):0);++i) a.previous[i]=a.state[i];
    a.end_frame=a.end_anim=false;
    a.animation=Platform_ReadAsset(asset);a.anim_asset=asset;
    if(!a.animation.data || a.animation.size<4 || !BE16Aligned(a.animation.data) || AnimGroups(a)>MAX_GROUPS || a.animation.size!=4+BE16Aligned(a.animation.data)*(8+AnimGroups(a)*8)) Platform_Fatal();
    a.frame=0;a.frame_phase=0;a.last_step={0,0,0};
}
A32X_COLD void Actor_SetFrame(Actor &a,unsigned frame) {
    a.frame=frame%BE16Aligned(a.animation.data);a.frame_phase=0;a.last_step={0,0,0};
    const uint8_t *key=Key(a,a.frame);
    for(unsigned i=0;i<(unsigned)Min(Groups(a),AnimGroups(a));++i)
        a.state[i]=a.previous[i]=ReadState(key+8+i*8);
}
static int Blend(int a,int b,int n,int d,bool angle) {
    int diff=b-a;
    if(angle) { diff=(diff+512)&1023; diff-=512; }
    if(!diff) return a;
    return a+diff*n/d;
}
Vec3 Actor_Advance(Actor &a,bool repeat) {
    a.end_frame=a.end_anim=false;
    if(!a.model.data || !a.animation.data) return {0,0,0};
    unsigned remaining=ANIMATION_HZ;
    Vec3 change={0,0,0};
    while(remaining) {
        const uint8_t *k=Key(a,a.frame);
        unsigned duration=Max(1,BE16Aligned(k))*GAME_HZ;
        unsigned advance=Min(remaining,duration-a.frame_phase);
        a.frame_phase+=advance;remaining-=advance;
        unsigned n=a.frame_phase,count=Min(Groups(a),AnimGroups(a));
        for(unsigned i=0;i<count;++i) {
            GroupState next=ReadState(k+8+i*8),prev=a.previous[i];
            a.state[i].type=next.type;
            bool angle=next.type==0;
            a.state[i].delta={Blend(prev.delta.x,next.delta.x,n,duration,angle),Blend(prev.delta.y,next.delta.y,n,duration,angle),Blend(prev.delta.z,next.delta.z,n,duration,angle)};
        }
        Vec3 step={BS16Aligned(k+2)*(int)n/(int)duration,BS16Aligned(k+4)*(int)n/(int)duration,BS16Aligned(k+6)*(int)n/(int)duration};
        change.x+=step.x-a.last_step.x;change.y+=step.y-a.last_step.y;change.z+=step.z-a.last_step.z;
        a.last_step=step;
        if(a.frame_phase==duration) {
            for(unsigned i=0;i<Groups(a);++i) a.previous[i]=a.state[i];
            a.end_frame=true;
            if(a.frame+1==BE16Aligned(a.animation.data)) {
                a.end_anim=true;
                if(!repeat) { a.frame_phase=duration;break; }
            }
            a.frame=(a.frame+1)%BE16Aligned(a.animation.data);a.frame_phase=0;a.last_step={0,0,0};
        }
    }
    Rotate(change,0,a.beta,0);return change;
}
static void RotateGroup(const uint8_t *groups,unsigned ng,unsigned i,Vec3 *out,const Rotation &rotation,unsigned depth=0) {
    if(i>=ng || depth>=ng) return;
    const uint8_t *g=groups+i*16;
    unsigned start=BE16Aligned(g),count=BE16Aligned(g+2);int num=(int8_t)g[7];
    RotateVertices(out+start,count,rotation);
    // FITD applies a parent's rotation to all its descendants before translating anchors.
    for(unsigned j=i+1;j<ng;++j) if((int8_t)groups[j*16+6]==num) RotateGroup(groups,ng,j,out,rotation,depth+1);
}
void Actor_Vertices(const Actor &a,Vec3 *out) {
    const uint8_t *m=a.model.data,*v=m+BE32Aligned(m+20),*groups=m+BE32Aligned(m+24),*order=m+BE32Aligned(m+28);
    unsigned nv=BE16Aligned(m+2),ng=Groups(a);
    for(unsigned i=0;i<nv;++i) out[i]={BS16Aligned(v+i*6),BS16Aligned(v+i*6+2),BS16Aligned(v+i*6+4)};
    for(unsigned n=0;n<ng;++n) {
        unsigned i=BE16Aligned(order+n*2);const uint8_t *g=groups+i*16;
        GroupState s=a.state[i];if(i==0) s={0,{a.alpha,a.beta,a.gamma}};
        unsigned start=BE16Aligned(g),count=BE16Aligned(g+2);
        if(s.type==0) { Rotation rotation=PrepareRotation(s.delta.x,s.delta.y,s.delta.z);if(rotation.enabled) RotateGroup(groups,ng,i,out,rotation); }
        else for(unsigned j=0;j<count;++j) {
            Vec3 &p=out[start+j];
            if(s.type==1) { p.x+=s.delta.x;p.y+=s.delta.y;p.z+=s.delta.z; }
            else if(s.type==2) { p.x=p.x*(s.delta.x+256)/256;p.y=p.y*(s.delta.y+256)/256;p.z=p.z*(s.delta.z+256)/256; }
        }
    }
    for(unsigned i=0;i<ng;++i) {
        const uint8_t *g=groups+i*16; unsigned start=BE16Aligned(g),count=BE16Aligned(g+2),base=BE16Aligned(g+4);
        Vec3 anchor=out[base];
        for(unsigned j=0;j<count;++j) { out[start+j].x+=anchor.x;out[start+j].y+=anchor.y;out[start+j].z+=anchor.z; }
    }
    if(!ng) { Rotation rotation=PrepareRotation(a.alpha,a.beta,a.gamma);RotateVertices(out,nv,rotation); }
}

Vec3 *Actor_GameplayScratch() { static Vec3 points[MAX_VERTICES];return points; }
