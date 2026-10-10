// SPDX-License-Identifier: GPL-2.0-or-later
#include "actor.hpp"
static bool Free(const Actor &a,const Asset &room,int x,int z) {
    const uint8_t *r=room.data,*b=r+BE32(r+16);
    const Vec3 &lo=a.collision_min,&hi=a.collision_max;
    for(unsigned i=0;i<BE16(r+8);++i,b+=16) {
        // FITD AsmCheckListCol tests all hard-col boxes, including type 9.
        // Their script-visible HARD_COL parameters are deferred with the VM.
        if(x+lo.x<BS16(b+2) && x+hi.x>BS16(b) && z+lo.z<BS16(b+10) && z+hi.z>BS16(b+8) &&
           a.pos.y+lo.y<BS16(b+6) && a.pos.y+hi.y>BS16(b+4)) return false;
    }
    return true;
}
bool Collision_Move(Actor &a,const Asset &room,Vec3 delta) {
    Vec3 old=a.pos;
    // Small substeps avoid crossing a thin wall when running or catching up ticks.
    int steps=Max(1,(Max(delta.x<0?-delta.x:delta.x,delta.z<0?-delta.z:delta.z)+31)/32);
    for(int i=1;i<=steps;++i) {
        int dx=delta.x*i/steps-delta.x*(i-1)/steps;
        int dz=delta.z*i/steps-delta.z*(i-1)/steps;
        if(Free(a,room,a.pos.x+dx,a.pos.z)) a.pos.x+=dx;
        if(Free(a,room,a.pos.x,a.pos.z+dz)) a.pos.z+=dz;
    }
    return old.x!=a.pos.x || old.z!=a.pos.z;
}
bool Camera_Contains(const Asset &camera,int room,int x,int z) {
    const uint8_t *c=camera.data,*views=c+BE32(c+20);
    x/=10;z/=10;
    for(unsigned v=0;v<BE16(c+18);++v) {
        const uint8_t *view=views+16*v;
        if(BE16(view)!=(unsigned)room) continue;
        const uint8_t *p=c+BE32(view+8);
        for(unsigned j=0;j<BE16(view+2);++j) {
            unsigned n=BE16(p);p+=2;bool inside=false;
            for(unsigned i=0,k=n-1;i<n;k=i++) {
                int ax=BS16(p+i*4),az=BS16(p+i*4+2),bx=BS16(p+k*4),bz=BS16(p+k*4+2);
                if((bx-ax)*(z-az)==(bz-az)*(x-ax) && x>=Min(ax,bx) && x<=Max(ax,bx) && z>=Min(az,bz) && z<=Max(az,bz)) return true;
                if(((az>z)!=(bz>z)) && x < ax+(bx-ax)*(z-az)/(bz-az)) inside=!inside;
            }
            if(inside) return true;
            p+=n*4;
        }
    }
    return false;
}
