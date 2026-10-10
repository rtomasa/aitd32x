// SPDX-License-Identifier: GPL-2.0-or-later
#include "audio.hpp"
#include "platform_api.hpp"
#ifndef AITD_RESOURCE_IDS
#define AITD_RESOURCE_IDS "../../assets/resource_ids.h"
#endif
#include AITD_RESOURCE_IDS
#if defined(__sh__)
#include "32x/hardware.hpp"
static int played_music=-99;static uint32_t music_probe;
extern "C" const uint8_t asset_bank[];
namespace {
struct Request { int16_t sample,next,repeat,pad; };
struct Queue { uint32_t written,read;Request requests[8]; };
static Queue storage;
static volatile Queue &Shared() { return *(volatile Queue *)((uintptr_t)&storage|0x20000000u); }
struct Voice { const uint8_t *data;uint32_t count,pos;int predictor,index,next,repeat; };
static Voice voices[2];static unsigned replacement;
static uint16_t cycle;static bool running;
static const int16_t steps[]={7,8,9,10,11,12,13,14,16,17,19,21,23,25,28,31,34,37,41,45,50,55,60,66,73,80,88,97,107,118,130,143,157,173,190,209,230,253,279,307,337,371,408,449,494,544,598,658,724,796,876,963,1060,1166,1282,1411,1552,1707,1878,2066,2272,2499,2749,3024,3327,3660,4026,4428,4871,5358,5894,6484,7132,7845,8630,9493,10442,11487,12635,13899,15289,16818,18500,20350,22385,24623,27086,29794,32767};
static const int8_t indices[]={-1,-1,-1,-1,2,4,6,8};
static void Start(Voice &v,int id,int next,int repeat) {
    Asset a{};
    if(id>=0 && id<A32X_SOUND_COUNT) {
        const uint8_t *e=asset_bank+16+16*sound_assets[id];
        a={asset_bank+BE32(e),BE32(e+4),BE32(e+8),BE16(e+12),BE16(e+14)};
    }
    v={};if(!a.data || a.type!=15 || a.size<8) return;
    unsigned count=BE32(a.data);if(!count || (count/2)>a.size-8) return;
    v.data=a.data;v.count=count;v.predictor=BS16(a.data+4);v.index=a.data[6];v.next=next;v.repeat=repeat;
}
static int Sample(Voice &v) {
    if(!v.count) return 0;
    if(v.pos>=v.count) {
        if(v.next>=0) { int next=v.next,repeat=v.repeat;Start(v,next,-1,repeat); }
        else if(v.repeat) { const uint8_t *data=v.data;int repeat=v.repeat;v.pos=0;v.predictor=BS16(data+4);v.index=data[6];v.repeat=repeat<0?-1:repeat-1; }
        else { v.count=0;return 0; }
        if(!v.count) return 0;
    }
    if(v.pos) {
        unsigned n=v.pos-1,code=v.data[8+n/2];code=(n&1)?code>>4:code&15;
        int step=steps[v.index],diff=(step>>3)+((code&1)?step>>2:0)+((code&2)?step>>1:0)+((code&4)?step:0);
        v.predictor=Clamp(v.predictor+((code&8)?-diff:diff),-32768,32767);v.index=Clamp(v.index+indices[code&7],0,88);
    }
    ++v.pos;return v.predictor;
}
static uint16_t Command(uint16_t op,uint16_t value=0) {
    COMM(1)=value;COMM(0)=op;while(COMM(0)!=0x5FFF) { asm volatile("nop; nop; nop; nop"); }return COMM(1);
}
}
void Audio_Sample(int id,int next,int repeat) {
    if(id<-2 || id>=A32X_SOUND_COUNT) return;
    volatile Queue &q=Shared();unsigned write=q.written;
    // A burst of simulation catch-up must not block either rendering CPU.
    if(write-q.read>=8) return;
    volatile Request &r=q.requests[write&7];r.sample=id;r.next=next;r.repeat=repeat;
    asm volatile("":::"memory");q.written=write+1;
}
void Audio_StopSamples() { Audio_Sample(-2); }
A32X_COLD void Audio_Reset() { played_music=-99;Audio_StopSamples();Command(0x5013); }
A32X_COLD void Audio_Music(int id) {
    if(id<0 || id>=A32X_MUSIC_COUNT) { Command(0x5013);return; }
    Asset a=Platform_ReadAsset(music_assets[id]);if(!a.data || a.type!=16) return;
    uintptr_t offset=(uintptr_t)a.data-0x02000000;Command(0x5010,offset>>16);Command(0x5011,offset);
}
bool Audio_MusicPlaying() { return Command(0x5014)!=0; }
void Audio_SlavePoll() {
    // Protect voice state while the PWM ISR consumes it.
    uint32_t saved;asm volatile("stc sr,%0" : "=r"(saved));uint32_t masked=saved|0xF0;asm volatile("ldc %0,sr"::"r"(masked):"memory");
    volatile Queue &q=Shared();
    if(q.read!=q.written) {
        volatile Request &r=q.requests[q.read&7];int id=r.sample,next=r.next,repeat=r.repeat;q.read=q.read+1;
        if(id==-2) { voices[0].count=voices[1].count=0; }
        else if(id>=0) {
            // The chest's key-selected LIFE repeats SAMPLE 3 each tick until
            // Search completes. Keep its unlock effect and the door creak (4)
            // playing through instead of replacing them with their beginnings.
            // Leave other effects and explicit repeat/chaining commands alone.
            bool playing=false;
            if((id==3 || id==4) && next<0 && !repeat) {
                const uint8_t *data=asset_bank+BE32(asset_bank+16+16*sound_assets[id]);
                for(const Voice &v:voices) if(v.count && v.data==data) playing=true;
            }
            if(!playing) { unsigned v=!voices[0].count?0:!voices[1].count?1:replacement++&1;Start(voices[v],id,next,repeat); }
        }
    }
    if(!running && (voices[0].count || voices[1].count)) {
        cycle=COMM(7)==50?2851:2877;REG16(0x20004032)=cycle;REG16(0x20004030)=0x0305;
        running=true;Audio_PWMInterrupt();*(volatile uint8_t *)0x20004001=1;
    }
    asm volatile("ldc %0,sr"::"r"(saved):"memory");
}
extern "C" void Audio_PWMInterrupt() {
    for(int i=0;i<3;++i) {
        int mix=Clamp((Sample(voices[0])+Sample(voices[1]))*3/4,-32768,32767);
        unsigned value=(cycle/2)+((mix*(int)(cycle/2-1))>>15);REG16(0x20004038)=(uint16_t)value;
    }
    if(!voices[0].count && !voices[1].count) {
        // Keep centered output after the last sample; no DC click / IRQ overhead.
        REG16(0x20004038)=cycle/2;*(volatile uint8_t *)0x20004001=0;REG16(0x20004030)=5;running=false;
    }
}
#else
static int current_music=-1;static int played_music=-99;static uint32_t music_probe;
static int sample_log[8192][3];static unsigned sample_count;
extern "C" unsigned host_sample_count() { return sample_count; }
extern "C" int host_sample_event(unsigned index,unsigned field) { return index<sample_count && field<3?sample_log[index&8191][field]:-999; }
extern "C" int host_music_track() { return current_music; }
extern "C" void host_music_end() { current_music=-1; }
void Audio_Sample(int id,int next,int repeat) { sample_log[sample_count++&8191][0]=id;sample_log[(sample_count-1)&8191][1]=next;sample_log[(sample_count-1)&8191][2]=repeat; }
void Audio_StopSamples() {}
void Audio_Reset() { current_music=-1;played_music=-99;sample_count=0; }
void Audio_Music(int id) { current_music=id; }
bool Audio_MusicPlaying() { return current_music>=0; }
void Audio_SlavePoll() {}
extern "C" void Audio_PWMInterrupt() {}
#endif

// CD LIFE IDs remain in World/save files. Playback maps them to AdLib cues.
static A32X_COLD int Audio_AdLibTrack(int cd) {
    switch(cd) {
    case 2:return 7; case 4:return 0; case 5:return 2;
    case 7:case 11:case 12:case 13:case 14:return 1;
    case 8:case 16:return 5; case 15:return 3; case 17:return 4;
    default:return -1;
    }
}
// Game-facing state tracks original LIFE music/end/queued transitions.
A32X_COLD void Audio_UpdateMusic(int &music,int &next,uint32_t tick) {
    if(music!=played_music) {
#if defined(__sh__)
        if(music==-2) Command(0x5012,COMM(7)*3);else
#endif
        // Several CD stingers share one floppy theme. Preserve its playhead
        // when a CD cue changes but the corresponding AdLib theme does not.
        if(music<0 || played_music<0 || Audio_AdLibTrack(music)!=Audio_AdLibTrack(played_music) || !Audio_MusicPlaying())
            Audio_Music(Audio_AdLibTrack(music));
        played_music=music;music_probe=tick;
    }
    if(music!=-1 && tick-music_probe>=10) {
        music_probe=tick;
        if(!Audio_MusicPlaying()) { music=next;next=-1;played_music=-99;Audio_UpdateMusic(music,next,tick); }
    }
}
