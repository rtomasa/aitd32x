#!/usr/bin/env python3
"""Offline original VOC -> 8kHz IMA ADPCM and ADLM -> YM2612/PSG conversion.
The pinned FITD driver runs only on the host; no OPL emulator in the cartridge.
"""
import ctypes as C, json, math, struct, subprocess
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parent
STEPS=(7,8,9,10,11,12,13,14,16,17,19,21,23,25,28,31,34,37,41,45,50,55,60,66,73,80,88,97,107,118,130,143,157,173,190,209,230,253,279,307,337,371,408,449,494,544,598,658,724,796,876,963,1060,1166,1282,1411,1552,1707,1878,2066,2272,2499,2749,3024,3327,3660,4026,4428,4871,5358,5894,6484,7132,7845,8630,9493,10442,11487,12635,13899,15289,16818,18500,20350,22385,24623,27086,29794,32767)
INDEX=(-1,-1,-1,-1,2,4,6,8)
SLOTS=(0,1,2,8,9,10,16,17,18)
def voc_pcm(data):
    assert data[:19]==b'Creative Voice File', 'not a VOC file'
    pos=struct.unpack_from('<H',data,20)[0];rate=8000;pcm=[]
    while pos<len(data):
        kind=data[pos];pos+=1
        if not kind:break
        n=int.from_bytes(data[pos:pos+3],'little');pos+=3;b=data[pos:pos+n];pos+=n
        if kind==1:
            assert b[1]==0,'unsupported VOC codec';rate=1000000/(256-b[0]);chunk=b[2:]
        elif kind==2:chunk=b
        elif kind==3:
            silence=(struct.unpack_from('<H',b)[0]+1);rate=1000000/(256-b[2]);chunk=bytes([128])*silence
        elif kind in (4,5,6,7):continue
        else:raise ValueError(f'unsupported VOC block {kind}')
        count=round(len(chunk)*8000/rate)
        for i in range(count):
            x=min(len(chunk)-1,i*rate/8000);a=int(x);f=x-a
            v=chunk[a]*(1-f)+chunk[min(a+1,len(chunk)-1)]*f
            pcm.append(round((v-128)*256))
    assert pcm
    return pcm

def ima_encode(pcm):
    predictor=pcm[0];index=0;codes=[];squared=0
    for value in pcm[1:]:
        step=STEPS[index];delta=value-predictor;code=8 if delta<0 else 0;delta=abs(delta);diff=step>>3
        for bit,part in ((4,step),(2,step>>1),(1,step>>2)):
            if delta>=part:code|=bit;delta-=part;diff+=part
        predictor=max(-32768,min(32767,predictor+(-diff if code&8 else diff)))
        index=max(0,min(88,index+INDEX[code&7]));codes.append(code);squared+=(value-predictor)**2
    packed=bytes(codes[i]|((codes[i+1] if i+1<len(codes) else 0)<<4) for i in range(0,len(codes),2))
    return struct.pack('>IhBB',len(pcm),pcm[0],0,0)+packed, math.sqrt(squared/max(1,len(codes)))

def capture(data,lib):
    buffer=C.create_string_buffer(data);lib.capture_clear();lib.capture_begin(buffer);events=[]
    def read(t):
        a=lib.capture_data()
        events.extend((t,a[j]>>8,a[j]&255) for j in range(lib.capture_count()));lib.capture_clear()
    read(0)
    for tick in range(1,18001):
        lib.capture_tick();read(tick)
        if lib.capture_ended():return tick,events
    raise ValueError('ADLM did not finish within five minutes')

def fm_stream(duration,events):
    # Six busiest melodic voices use FM; remaining voices retain their notes
    # through the three quieter PSG tone channels. Rhythm uses PSG percussion.
    usage=[0]*9;state=[0]*256;last=0;rhythm=False
    for t,r,v in events:
        for c in range(9):
            if state[0xb0+c]&32:usage[c]+=t-last
        last=t;state[r]=v;rhythm|=r==0xbd and bool(v&32)
    melodic=range(6 if rhythm else 9)
    ranking=sorted(melodic,key=lambda c:(-usage[c],c));mapping={c:('fm',i) if i<6 else ('psg',i-6) for i,c in enumerate(ranking)}
    regs=[0]*256;cache={};out=[];keys=[False]*9;notes=[None]*9;percussion_off={}
    def emit(t,port,r,v,force=False):
        k=(port,r)
        if force or port==2 or cache.get(k)!=v:out.append((t,port,r,v));cache[k]=v
    def tone(t,c,freq,volume):
        # PSG cannot reach OPL's lowest bass notes. Preserve pitch class by
        # raising those auxiliary voices by octaves instead of clamping pitch.
        freq=max(1,freq)
        while freq<3579545/(32*1023):freq*=2
        period=max(1,min(1023,round(3579545/(32*freq))))
        emit(t,2,0,0x80|(c<<5)|(period&15));emit(t,2,0,period>>4);emit(t,2,0,0x90|(c<<5)|volume)
    for c in range(6):
        port=c//3;local=c%3
        emit(0,0,0x28,c if c<3 else c+1,True)
        # Algorithm 4: operators 1 -> 2; the other two-operator pair is muted.
        for op in (4,12):emit(0,port,0x40+op+local,127)
        emit(0,port,0xb4+local,0xc0)
    emit(0,0,0x22,0);emit(0,0,0x27,0);emit(0,0,0x2b,0)
    for c in range(4):emit(0,2,0,0x9f|(c<<5))
    by_tick=defaultdict(list)
    for t,r,v in events:by_tick[t].append((r,v))
    for t in range(duration+1):
        for c,until in list(percussion_off.items()):
            if t>=until:emit(t,2,0,0x9f|(c<<5));del percussion_off[c]
        for r,v in by_tick[t]:
            old=regs[r];regs[r]=v
            if r==0xbd and v&32:
                fired=(v&~old)&31
                if fired&16:tone(t,0,85,10);percussion_off[0]=t+5
                if fired&4:tone(t,1,180,12);percussion_off[1]=t+5
                if fired&11:
                    emit(t,2,0,0xe7);emit(t,2,0,0xf9 if fired&8 else 0xfc);percussion_off[3]=t+4
                continue
            for source,(kind,c) in mapping.items():
                offset=SLOTS[source]
                if r not in (0xa0+source,0xb0+source,0xc0+source) and r not in [base+offset+op for base in (0x20,0x40,0x60,0x80,0xe0) for op in (0,3)]:continue
                fnum=regs[0xa0+source]|((regs[0xb0+source]&3)<<8);block=(regs[0xb0+source]>>2)&7;key=bool(regs[0xb0+source]&32)
                if kind=='psg':
                    freq=fnum*49716*2**block/2**20
                    volume=min(14,10+(regs[0x43+offset]&63)//5) if key else 15
                    tone(t,c,freq,volume);continue
                port=c//3;local=c%3;channel=c if c<3 else c+1
                if keys[source] and not key:emit(t,0,0x28,channel,True)
                for src_op,dst_op in ((0,0),(3,8)):
                    a=offset+src_op;d=local+dst_op;control=regs[0x20+a];attack=regs[0x60+a];release=regs[0x80+a]
                    emit(t,port,0x30+d,(0,1,2,3,4,5,6,7,8,9,10,10,12,12,15,15)[control&15])
                    emit(t,port,0x40+d,min(127,(regs[0x40+a]&63)+(16 if src_op==3 or regs[0xc0+source]&1 else 0)))
                    emit(t,port,0x50+d,((attack>>4)*2)|(0xC0 if control&16 else 0))
                    emit(t,port,0x60+d,(attack&15)*2)
                    emit(t,port,0x70+d,0 if control&32 else (attack&15)*2)
                    emit(t,port,0x80+d,release)
                emit(t,port,0xb0+local,((regs[0xc0+source]>>1)&7)<<3 | (7 if regs[0xc0+source]&1 else 4))
                # Preserve OPL pitch: OPL clock/72 versus YM clock/144,
                # with the respective 20/21-bit phase counters.
                fn=round(fnum*49716*288/7670454)
                if notes[source]!=(fn,block):
                    emit(t,port,0xa4+local,(block<<3)|(fn>>8),True);emit(t,port,0xa0+local,fn&255,True);notes[source]=(fn,block)
                if key and not keys[source]:emit(t,0,0x28,0x30|channel,True)
                keys[source]=key
    out.append((duration,4,0,0))
    result=bytearray(struct.pack('>II',duration,0));previous=0;count=0
    for t,p,r,v in out:
        delta=t-previous
        assert delta>=0
        while delta>255:result+=bytes((255,3,0,0));delta-=255;count+=1
        result+=bytes((delta,p,r,v));previous=t;count+=1
    struct.pack_into('>I',result,4,count)
    return bytes(result),dict(ticks=duration,seconds=duration*5/294,commands=count,bytes=len(result),channels=mapping,rhythm=rhythm)

def compile_audio(get,paks):
    so=ROOT/'fitd_music_capture.so'
    subprocess.run(['c++','-shared','-fPIC','-O2',str(ROOT/'fitd_music_capture.cpp'),'-o',str(so)],check=True)
    lib=C.CDLL(str(so));lib.capture_data.restype=C.POINTER(C.c_uint16)
    # Load these PAKs through the importer's normal decoder and input hashing.
    get('LISTSAMP',0);get('LISTMUS',0)
    assets=[];report=dict(sample_rate=8000,effects=[],music=[])
    for i in range(len(paks['LISTSAMP'])):
        pcm=voc_pcm(get('LISTSAMP',i));data,error=ima_encode(pcm);assets.append((f'SOUND_{i}',15,data))
        report['effects'].append(dict(id=i,samples=len(pcm),bytes=len(data),rms_error=error))
    for i in range(len(paks['LISTMUS'])):
        ticks,events=capture(get('LISTMUS',i),lib);data,stats=fm_stream(ticks,events);assets.append((f'MUSIC_{i}',16,data));report['music'].append(dict(id=i,**stats))
    return assets,report
