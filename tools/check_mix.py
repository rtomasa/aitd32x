#!/usr/bin/env python3
"""Compare native v14/v15 music and isolated PWM levels with identical fixtures."""
import argparse,ctypes as C,json,math,struct,subprocess,re
from pathlib import Path
import emulator_check as ec
p=argparse.ArgumentParser();p.add_argument('core',type=Path);p.add_argument('--reference',type=Path,required=True);p.add_argument('--mars',type=Path,required=True);a=p.parse_args();current=ec.ROOT

def measure(root):
 ec.ROOT=root.resolve();root=ec.ROOT;e=ec.Emulator(a.core,'NTSC');e.run(180)
 def press(pad):e.run(12);e.run(12,pad);e.run(24)
 press(128);assert e.state()['mode']==1
 f=current/'build/mix-layout.cpp';f.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned layout[]={offsetof(Game,world)+offsetof(World,music)};\n')
 out=f.with_suffix('.s');subprocess.run([str(a.mars/'sh-elf/bin/sh-elf-g++'),'-m2','-mb','-Wno-invalid- offsetof'.replace(' ',''),'-I'+str(root),'-S',str(f),'-o',str(out)],check=True)
 music_offset=int(re.findall(r'\.long\s+([-0-9xa-fA-F]+)',out.read_text().split('_layout:',1)[1].split('.ident',1)[0])[0],0)
 mem=C.c_void_p.in_dll(e.lib,'Pico32xMem').value;g=ec.symbol_address('__ZL4game')&0x3ffff
 q=(C.c_uint16*2).from_address(mem+g+music_offset);q[0]=0;q[1]=0 if root==a.reference.resolve() else 4
 e.run(12);press(128);assert e.state()['paused']
 def levels(data):
  v=[x[0] for x in struct.iter_unpack('<h',data)];return dict(rms=math.sqrt(sum(x*x for x in v)/len(v)),peak=max(abs(x) for x in v),clipped=sum(abs(x)>=32767 for x in v))
 e.capture_audio=True;e.audio.clear();e.run(180);music=levels(e.audio)
 e.close();e=ec.Emulator(a.core,'NTSC');e.run(180);e.capture_audio=True
 text=subprocess.check_output([str(a.mars/'sh-elf/bin/sh-elf-nm'),str(root/'build/AITD32X.elf')],text=True)
 queue=min(int(line.split()[0],16)&0x3ffff for line in text.splitlines() if line.endswith('__ZN12_GLOBAL__N_1L7storageE'))
 mem=C.c_void_p.in_dll(e.lib,'Pico32xMem').value
 def read(off):
  q=(C.c_uint16*2).from_address(mem+off);return q[0]<<16|q[1]
 def write(off,v):
  q=(C.c_uint16*2).from_address(mem+off);q[0]=(v>>16)&65535;q[1]=v&65535
 n=read(queue);entry=queue+8+(n&7)*8
 for i,v in enumerate((0,-1,0,0)):C.c_uint16.from_address(mem+entry+i*2).value=v&65535
 write(queue,n+1);e.audio.clear();e.run(120);effect=levels(e.audio);e.close();return dict(music=music,effect=effect)
old=measure(a.reference);new=measure(current);ec.ROOT=current
report=dict(reference=old,current=new,music_rms_ratio=new['music']['rms']/old['music']['rms'],effect_rms_ratio=new['effect']['rms']/old['effect']['rms'])
assert .4<report['music_rms_ratio']<.65 and 1.4<report['effect_rms_ratio']<1.6,report
assert new['music']['clipped']==new['effect']['clipped']==0
(current/'validation/mix-v15.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
