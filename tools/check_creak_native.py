#!/usr/bin/env python3
"""Exercise duplicate unlock/creak requests in the ROM's slave/PWM mixer.

Requests are injected only into transient emulator RAM, without battery files.
The key-selected chest LIFE issues SAMPLE 3 every tick; check_key_chest.py
exercises that original-script path. This fixture checks actual voice playback.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import emulator_check as ec

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('core',type=Path)
p.add_argument('--region',choices=['NTSC','PAL'],default='NTSC')
a=p.parse_args()
hz=50 if a.region=='PAL' else 60
e=ec.Emulator(a.core,a.region)
e.run(hz*3)
mem=C.c_void_p.in_dll(e.lib,'Pico32xMem').value
# Both renderer and audio have a local symbol named storage; audio comes first.
queue=ec.symbol_address('__ZN12_GLOBAL__N_1L7storageE')&0x3ffff
voices=ec.symbol_address('__ZN12_GLOBAL__N_1L6voicesE')&0x3ffff

def read32(off):
    w=(C.c_uint16*2).from_address(mem+off)
    return w[0]<<16|w[1]

def write32(off,n):
    w=(C.c_uint16*2).from_address(mem+off)
    w[0]=(n>>16)&65535;w[1]=n&65535

def request(sample,next=-1,repeat=0):
    written=read32(queue)
    assert written-read32(queue+4)<8,'audio queue full'
    entry=queue+8+(written&7)*8
    for k,v in enumerate((sample,next,repeat,0)):
        C.c_uint16.from_address(mem+entry+2*k).value=v&65535
    write32(queue,written+1)

def state():
    return [(read32(voices+28*k+4),read32(voices+28*k+8)) for k in range(2)]

def stop():
    request(-2);e.run(2)
    assert all(count==0 for count,pos in state()),state()

try:
    effects=[]
    for sample,count,seconds in ((3,15241,1),(4,21803,2)):
        request(sample);e.run(2)
        positions=[state()[0][1]]
        assert state()[0][0]==count and state()[1][0]==0,state()
        # An interaction burst previously filled both voices, then reset them.
        for _ in range(hz*seconds):
            request(sample);e.run(1)
            current=state()
            assert current[0][0]==count and current[1][0]==0,current
            positions.append(current[0][1])
        assert all(x<y for x,y in zip(positions,positions[1:])),positions
        e.run(hz)
        assert state()[0]==(0,count) and state()[1][0]==0,state()
        assert read32(queue)==read32(queue+4),'requests not drained'
        request(sample);e.run(2)
        assert state()[0][0]==count and 0<state()[0][1]<1000,state()
        request(37);e.run(1)
        assert all(n>0 for n,pos in state()),state()
        stop()
        effects.append(dict(sample=sample,duplicate_requests=hz*seconds,
                            position_monotonic=True,completed_samples=count,
                            replay_after_completion=True))
    # Other one-shots still overlap; explicit chains/repeats are accepted.
    for first,second in ((37,(37,-1,0)),(3,(3,37,0)),(3,(3,-1,1)),
                         (4,(4,37,0)),(4,(4,-1,1))):
        request(first);e.run(2);request(*second);e.run(1)
        assert all(count>0 for count,pos in state()),(first,second,state())
        stop()
    report=dict(region=a.region,effects=effects,stop=True,other_effect_overlap=True,
                explicit_chain_and_repeat=True,
                rom_sha256=hashlib.sha256((ec.ROOT/'build/AITD32X.32x').read_bytes()).hexdigest())
    (ec.ROOT/'build'/('creak-native-'+a.region.lower()+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
finally:
    e.close()
