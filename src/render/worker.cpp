// SPDX-License-Identifier: GPL-2.0-or-later
#include "worker.hpp"
#include "../engine/actor.hpp"
#include "../platform/profile.hpp"
#if defined(__sh__)
// All shared storage uses cache-through SDRAM; cached aliases are never read.
// SH7604 manual 8.5.3 requires coherent flags / payloads between processors.
#ifdef PROFILE
extern "C" { volatile uint32_t worker_profile_state[6]; }
#endif
namespace {
constexpr unsigned capacity=8;
enum Kind { CONTACT=0,BEGIN=1,PRIMITIVE=2,END=3 };
struct Command {
    uint32_t header,argument;
    Point points[MAX_POLY];
};
struct Shared {
    uint32_t written,read,completed;
    Rect damage;
    Command commands[capacity];
};
static Shared storage;
static unsigned frame_token;
static RasterSurface slave_surface;
static Point slave_points[MAX_POLY]; // avoids the slave's 4 KiB stack limit.
static volatile Shared &SharedState() {
    return *(volatile Shared *)((uintptr_t)&storage|0x20000000u);
}
static inline void Barrier() { asm volatile("":::"memory"); }
static inline void PollPause() {
    // Space shared-RAM reads. PicoDrive's polling detector can otherwise sleep
    // on the terminal read after the slave has already published completion.
    // The real SH2 also avoids hammering the shared bus while waiting.
    asm volatile(".rept 24\n\tnop\n\t.endr" ::: "memory");
}
static volatile Command &Acquire() {
    volatile Shared &s=SharedState();
    if(s.written-s.read>=capacity) {
#ifdef PROFILE
        uint16_t begin=Profile_ReadTimer();
#endif
        while(s.written-s.read>=capacity) { PollPause(); }
#ifdef PROFILE
        worker_profile_state[0]+=(uint16_t)(Profile_ReadTimer()-begin);
#endif
    }
    return s.commands[s.written&(capacity-1)];
}
static void Publish() {
    Barrier();volatile Shared &s=SharedState();s.written=s.written+1;
}
}
void RendererWorker_Begin(RasterSurface &surface) {
    // The master owns [0,100); the slave owns [100,200). Every primitive reaches
    // both owners in painter order. Whole-row ownership also protects the read /
    // modify / write needed for transparent framebuffer byte stores of zero.
    volatile Command &c=Acquire();c.header=uint32_t(BEGIN)<<30;c.argument=(uintptr_t)surface.target;
    c.points[0].x=(uintptr_t)surface.coverage;
    Publish();surface.last=GAME_HEIGHT/2;
}
bool RendererWorker_Submit(unsigned type,const Point *points,unsigned count,uint8_t color,int size,uint8_t material) {
    int first=points[0].y,last=first;
    if(type==1 || (type==0 && count==2)) for(unsigned i=1;i<count;++i) {
        first=Min(first,points[i].y);last=Max(last,points[i].y);
    } else if(type!=2) { first-=size;last+=size; }
    if(last<GAME_HEIGHT/2 || first>=GAME_HEIGHT) return first<GAME_HEIGHT/2 && last>=0;
    volatile Command &c=Acquire();c.header=(uint32_t(PRIMITIVE)<<30)|(type<<16)|(unsigned(material)<<24)|(count<<8)|color;c.argument=(unsigned)size;
    for(unsigned i=0;i<count;++i) { c.points[i].x=points[i].x;c.points[i].y=points[i].y; }
    Publish();return first<GAME_HEIGHT/2 && last>=0;
}
void RendererWorker_Contact(RasterSurface &surface,void (*draw)(void *,RasterSurface &),void *context,int split) {
    volatile Command &c=Acquire();c.header=uint32_t(CONTACT)<<30;c.argument=(uintptr_t)draw;
    c.points[0].x=(uintptr_t)context;c.points[0].y=(uintptr_t)surface.target;
    c.points[1].x=split;c.points[1].y=surface.last;
    Publish();surface.last=split;
}
void RendererWorker_Finish(RasterSurface &surface) {
    volatile Shared &s=SharedState();volatile Command &c=Acquire();
    unsigned token=++frame_token;c.header=uint32_t(END)<<30;c.argument=token;Publish();
#ifdef PROFILE
    uint16_t begin=Profile_ReadTimer();
#endif
    while(s.completed!=token) { PollPause(); }
#ifdef PROFILE
    worker_profile_state[1]+=(uint16_t)(Profile_ReadTimer()-begin);++worker_profile_state[2];
#endif
    Barrier();Rect &d=surface.damage;
    d.x1=Min(d.x1,s.damage.x1);d.x2=Max(d.x2,s.damage.x2);
    d.y1=Min(d.y1,s.damage.y1);d.y2=Max(d.y2,s.damage.y2);
}
void RendererWorker_Poll() {
    volatile Shared &s=SharedState();unsigned read=s.read;
    if(read==s.written) return;
    Barrier();volatile Command &c=s.commands[read&(capacity-1)];
    unsigned header=c.header,argument=c.argument;
    unsigned kind=header>>30,type=(header>>16)&255,count=(header>>8)&255;
    uintptr_t coverage=kind==BEGIN?(uintptr_t)c.points[0].x:0;
    uintptr_t context=0,target=0;int first=0,last=0;
    if(kind==CONTACT) {
        context=(uintptr_t)c.points[0].x;target=(uintptr_t)c.points[0].y;
        first=c.points[1].x;last=c.points[1].y;
    }
    uint8_t color=(uint8_t)header;
    if(kind==PRIMITIVE) for(unsigned i=0;i<count;++i) {
        slave_points[i].x=c.points[i].x;slave_points[i].y=c.points[i].y;
    }
    // Release the ring entry only after its payload has been copied. It can be
    // reused while this command draws from private slave scratch.
    Barrier();s.read=read+1;
    if(kind==CONTACT) {
        slave_surface={(volatile uint16_t *)target,first,last,{320,200,-1,-1}};
        ((void (*)(void *,RasterSurface &))argument)((void *)context,slave_surface);
#ifdef PROFILE
        ++worker_profile_state[5];
#endif
    }
    else if(kind==BEGIN) slave_surface={(volatile uint16_t *)argument,GAME_HEIGHT/2,GAME_HEIGHT,{320,200,-1,-1},0,(volatile uint8_t *)coverage};
    else if(kind==PRIMITIVE) {
#ifdef PROFILE
        uint16_t begin=Profile_ReadTimer();
#endif
        RasterPrimitive(slave_surface,type,slave_points,count,color,(int)argument,(header>>24)&63);
#ifdef PROFILE
        worker_profile_state[3]+=(uint16_t)(Profile_ReadTimer()-begin);++worker_profile_state[4];
#endif
    }
    else if(kind==END) {
        s.damage.x1=slave_surface.damage.x1;s.damage.y1=slave_surface.damage.y1;
        s.damage.x2=slave_surface.damage.x2;s.damage.y2=slave_surface.damage.y2;
        Barrier();s.completed=argument;
    }
}
#else
void RendererWorker_Begin(RasterSurface &) {}
bool RendererWorker_Submit(unsigned,const Point *,unsigned,uint8_t,int,uint8_t) { return true; }
void RendererWorker_Finish(RasterSurface &) {}
void RendererWorker_Contact(RasterSurface &,void (*)(void *,RasterSurface &),void *,int) {}
void RendererWorker_Poll() {}
#endif
