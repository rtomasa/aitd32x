// SPDX-License-Identifier: GPL-2.0-or-later
#include "../platform/pixel_words.hpp"
#include "worker.hpp"
#include "../engine/actor.hpp"
#include "../platform/profile.hpp"
#if defined(__sh__)
#include "../platform/32x/wait.hpp"
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
    uint32_t raster_ticks;
    Rect damage;
    Command commands[capacity];
};
static Shared storage;
static unsigned frame_token;
static RasterSurface slave_surface;
static Point slave_points[MAX_POLY]; // avoids the slave's 4 KiB stack limit.
struct Balance { int split=100,votes=0; };
static Balance ordinary_balance,contact_balance;
static uint32_t restore_token,queue_ticks,slave_ticks;
static uint16_t job_begin;
static unsigned job_kind;
static int job_split,job_first,job_last;
static __attribute__((noinline)) uint16_t Timer() {
    volatile uint8_t *const frt=(volatile uint8_t *)0xFFFFFE10;
    unsigned high,low,check;
    do { high=frt[2];low=frt[3];check=frt[2]; } while(high!=check);
    return (uint16_t)((high<<8)|low);
}
static A32X_COLD void Adapt(uint32_t master,uint32_t slave) {
    // Ignore tiny jobs and allow a 25% imbalance before changing ownership.
    // Three agreeing samples damp scene/interrupt noise; all changes happen
    // after END, when no processor can still write the preceding row bands.
    if(master+slave<64) return;
    Balance &b=job_kind==CONTACT?contact_balance:ordinary_balance;
    int direction=slave>master+master/4?1:master>slave+slave/4?-1:0;
    if(!direction) { b.votes=0;return; }
    if((b.votes<0 && direction>0) || (b.votes>0 && direction<0)) b.votes=0;
    b.votes+=direction;
    if(b.votes>=3 || b.votes<=-3) { b.split=Clamp(b.split+direction*4,20,180);b.votes=0; }
}
static volatile Shared &SharedState() {
    return *(volatile Shared *)((uintptr_t)&storage|0x20000000u);
}
static inline void Barrier() { asm volatile("":::"memory"); }
static volatile Command &Acquire() {
    volatile Shared &s=SharedState();
    if(s.written-s.read>=capacity) {
        uint16_t waited=Timer();
#ifdef PROFILE
        uint16_t begin=Profile_ReadTimer();
#endif
        SH2WaitQueue(&s.read,s.written,capacity);
        queue_ticks+=(uint16_t)(Timer()-waited);
#ifdef PROFILE
        worker_profile_state[0]+=(uint16_t)(Profile_ReadTimer()-begin);
#endif
    }
    return s.commands[s.written&(capacity-1)];
}
static void Publish() {
    Barrier();volatile Shared &s=SharedState();s.written=s.written+1;
}
static A32X_COLD void RestoreRows(volatile Command &c,unsigned read) {
    volatile uint16_t *target=(volatile uint16_t *)(uintptr_t)c.argument;
    const uint16_t *source=(const uint16_t *)(uintptr_t)c.points[0].x;
    int first=c.points[0].y,last=c.points[1].x,y=c.points[1].y,end=c.points[2].x;
    unsigned token=c.points[2].y;
    volatile Shared &s=SharedState();Barrier();s.read=read+1;
    for(;y<end;++y) {
        unsigned i=y*(GAME_WIDTH/2)+first,limit=y*(GAME_WIDTH/2)+last;
        PixelCopyWords(target+i,source+i,limit-i+1);
    }
    Barrier();s.completed=token;
}
}
A32X_COLD void RendererWorker_Init() {
#ifndef PROFILE
    // PROFILE initializes the same CPU-local timer before worker startup.
    volatile uint8_t *const frt=(volatile uint8_t *)0xFFFFFE10;
    frt[0]=1;frt[1]=0;frt[6]=2;frt[2]=0;frt[3]=0;
#endif
}
A32X_COLD void RendererWorker_WaitRestore() {
    if(!restore_token) return;
    SH2WaitEqual32(&SharedState().completed,restore_token);
    Barrier();restore_token=0;
}
A32X_COLD int RendererWorker_Restore(volatile uint16_t *target,const uint16_t *source,Rect area) {
    RendererWorker_WaitRestore();
    int end=area.y2+1;
    // RAM compositions and small repairs benefit from the serial path. Do
    // not dispatch when the remaining copy cannot repay a queue exchange.
    if(((uintptr_t)target&0xff000000u)!=0x24000000u || area.x1>area.x2 ||
       area.y1>area.y2 || area.y2-area.y1<7 ||
       (area.x2/2-area.x1/2+1)*(area.y2-area.y1+1)<512) return end;
    int split=area.y1+(area.y2-area.y1+2)/2;
    volatile Command &c=Acquire();
    // BEGIN's unused low bit identifies a restore, preserving all six
    // material bits in the existing primitive command encoding.
    c.header=(uint32_t(BEGIN)<<30)|1;c.argument=(uintptr_t)target;
    c.points[0].x=(uintptr_t)source|0x20000000u;c.points[0].y=area.x1/2;
    c.points[1].x=area.x2/2;c.points[1].y=split;c.points[2].x=end;
    c.points[2].y=restore_token=++frame_token;Publish();return split;
}
A32X_COLD int RendererWorker_ContactSplit(int first,int last) {
    return first+Clamp((last-first)*contact_balance.split/200,1,last-first-1);
}
A32X_COLD void RendererWorker_Begin(RasterSurface &surface) {
    RendererWorker_WaitRestore();
    job_kind=PRIMITIVE;job_split=ordinary_balance.split;
    job_first=surface.first;job_last=surface.last;queue_ticks=0;job_begin=Timer();
    // Both CPUs own disjoint whole rows. Every primitive reaches
    // both owners in painter order. Whole-row ownership also protects the read /
    // modify / write needed for transparent framebuffer byte stores of zero.
    volatile Command &c=Acquire();c.header=uint32_t(BEGIN)<<30;c.argument=(uintptr_t)surface.target;
    c.points[0].x=(uintptr_t)surface.coverage;
    c.points[0].y=job_split;c.points[1].x=surface.last;c.points[1].y=surface.first;
    c.points[2].x=surface.deferred.x1;c.points[2].y=surface.deferred.y1;
    c.points[3].x=surface.deferred.x2;c.points[3].y=surface.deferred.y2;
    Publish();surface.last=Min(surface.last,job_split);
}
bool RendererWorker_Submit(unsigned type,const Point *points,unsigned count,uint8_t color,int size,uint8_t material) {
    int first=points[0].y,last=first;
    if(type==1 || (type==0 && count==2)) for(unsigned i=1;i<count;++i) {
        first=Min(first,points[i].y);last=Max(last,points[i].y);
    } else if(type!=2) { first-=size;last+=size; }
    bool master=first<job_split && first<job_last && last>=job_first;
    if(last<job_split || first>=job_last) return master;
    volatile Command &c=Acquire();c.header=(uint32_t(PRIMITIVE)<<30)|(type<<16)|(unsigned(material)<<24)|(count<<8)|color;c.argument=(unsigned)size;
    for(unsigned i=0;i<count;++i) { c.points[i].x=points[i].x;c.points[i].y=points[i].y; }
    Publish();return master;
}
A32X_COLD void RendererWorker_Contact(RasterSurface &surface,void (*draw)(void *,RasterSurface &),void *context,int split) {
    RendererWorker_WaitRestore();job_kind=CONTACT;queue_ticks=0;job_begin=Timer();
    volatile Command &c=Acquire();c.header=uint32_t(CONTACT)<<30;c.argument=(uintptr_t)draw;
    c.points[0].x=(uintptr_t)context;c.points[0].y=(uintptr_t)surface.target;
    c.points[1].x=split;c.points[1].y=surface.last;
    Publish();surface.last=split;
}
A32X_COLD void RendererWorker_Finish(RasterSurface &surface) {
    uint32_t elapsed=(uint16_t)(Timer()-job_begin);
    uint32_t master=elapsed>queue_ticks?elapsed-queue_ticks:0;
    volatile Shared &s=SharedState();volatile Command &c=Acquire();
    unsigned token=++frame_token;c.header=uint32_t(END)<<30;c.argument=token;Publish();
#ifdef PROFILE
    uint16_t begin=Profile_ReadTimer();
#endif
    SH2WaitEqual32(&s.completed,token);
#ifdef PROFILE
    worker_profile_state[1]+=(uint16_t)(Profile_ReadTimer()-begin);++worker_profile_state[2];
#endif
    Barrier();Rect &d=surface.damage;
    d.x1=Min(d.x1,s.damage.x1);d.x2=Max(d.x2,s.damage.x2);
    d.y1=Min(d.y1,s.damage.y1);d.y2=Max(d.y2,s.damage.y2);
    Adapt(master,s.raster_ticks);
}
void RendererWorker_Poll() {
    volatile Shared &s=SharedState();unsigned read=s.read;
    if(read==s.written) return;
    Barrier();volatile Command &c=s.commands[read&(capacity-1)];
    unsigned header=c.header,argument=c.argument;
    unsigned kind=header>>30,type=(header>>16)&255,count=(header>>8)&255;
    if(kind==BEGIN && (header&1)) {
        RestoreRows(c,read);return;
    }
    uintptr_t coverage=kind==BEGIN?(uintptr_t)c.points[0].x:0;
    int split=kind==BEGIN?c.points[0].y:0;
    int end=kind==BEGIN?c.points[1].x:0,start=kind==BEGIN?c.points[1].y:0;
    Rect deferred={320,200,-1,-1};
    if(kind==BEGIN) deferred={c.points[2].x,c.points[2].y,c.points[3].x,c.points[3].y};
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
        uint16_t begin=Timer();
        slave_surface={(volatile uint16_t *)target,first,last,{320,200,-1,-1}};
        ((void (*)(void *,RasterSurface &))argument)((void *)context,slave_surface);
        slave_ticks=(uint16_t)(Timer()-begin);
#ifdef PROFILE
        ++worker_profile_state[5];
#endif
    }
    else if(kind==BEGIN) {
        slave_ticks=0;
        slave_surface={(volatile uint16_t *)argument,Max(start,split),end,{320,200,-1,-1},0,(volatile uint8_t *)coverage};
        slave_surface.deferred=deferred;
    }
    else if(kind==PRIMITIVE) {
        uint16_t timed=Timer();
#ifdef PROFILE
        uint16_t begin=Profile_ReadTimer();
#endif
        RasterPrimitive(slave_surface,type,slave_points,count,color,(int)argument,(header>>24)&63);
        slave_ticks+=(uint16_t)(Timer()-timed);
#ifdef PROFILE
        worker_profile_state[3]+=(uint16_t)(Profile_ReadTimer()-begin);++worker_profile_state[4];
#endif
    }
    else if(kind==END) {
        s.raster_ticks=slave_ticks;
        s.damage.x1=slave_surface.damage.x1;s.damage.y1=slave_surface.damage.y1;
        s.damage.x2=slave_surface.damage.x2;s.damage.y2=slave_surface.damage.y2;
        Barrier();s.completed=argument;
    }
}
#else
void RendererWorker_Init() {}
int RendererWorker_Restore(volatile uint16_t *,const uint16_t *,Rect area) { return area.y2+1; }
void RendererWorker_WaitRestore() {}
int RendererWorker_ContactSplit(int first,int last) { return first+(last-first+1)/2; }
void RendererWorker_Begin(RasterSurface &) {}
bool RendererWorker_Submit(unsigned,const Point *,unsigned,uint8_t,int,uint8_t) { return true; }
void RendererWorker_Finish(RasterSurface &) {}
void RendererWorker_Contact(RasterSurface &,void (*)(void *,RasterSurface &),void *,int) {}
void RendererWorker_Poll() {}
#endif
