#!/usr/bin/env python3
"""Time original stair/room transitions on the release SH2 ROM, in VBlanks."""
import argparse,ctypes as C,json,re,subprocess,hashlib
from pathlib import Path
import emulator_check as ec
p=argparse.ArgumentParser();p.add_argument('core',type=Path);p.add_argument('--mars',type=Path,required=True);p.add_argument('--project',type=Path,default=ec.ROOT);p.add_argument('--label',default='v10');p.add_argument('--region',choices=['NTSC','PAL'],default='NTSC');p.add_argument('--character',choices=['edward','emily'],default='edward');a=p.parse_args();root=ec.ROOT=a.project.resolve();hz=50 if a.region=='PAL' else 60
fields={'player':'offsetof(Game,player)','pos':'offsetof(Actor,pos)','beta':'offsetof(Actor,beta)','dirty':'offsetof(Game,dirty)','world':'offsetof(Game,world)','objects':'offsetof(World,objects)','active':'offsetof(World,active)','value':'offsetof(ActiveObject,value)','active_size':'sizeof(ActiveObject)','held':'offsetof(Game,held)','edges':'offsetof(Game,pending_edges)'}
src=root/'build'/('transition-layout-'+a.label+'-'+a.region+'-'+a.character+'.cpp');src.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned layout[]={'+','.join(fields.values())+'};\n');asm=src.with_suffix('.s');subprocess.run([str(a.mars/'sh-elf/bin/sh-elf-g++'),'-m2','-mb','-std=c++17','-w','-I'+str(root),'-S',str(src),'-o',str(asm)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
values=[int(v,0) for v in re.findall(r'\.long\s+([-0-9xa-fA-F]+)',asm.read_text().split('_layout:',1)[1].split('.ident',1)[0])];o=dict(zip(fields,values));assert len(o)==len(fields)
e=ec.Emulator(a.core,a.region);e.run(180);mem=C.c_void_p.in_dll(e.lib,'Pico32xMem').value;game=ec.symbol_address('__ZL4game')&0x3ffff;debug=ec.symbol_address('_debug_state')&0x3ffff
trace=[];capture=False;last_frame=-1;last_view=None

def read16(off):return C.c_int16.from_address(mem+game+off).value
def write(off,v):
 w=(C.c_uint16*2).from_address(mem+game+off);w[0]=(v>>16)&65535;w[1]=v&65535
def byte(off,v=None):
 b=C.c_uint8.from_address(mem+game+(off^1))
 if v is not None:b.value=v
 return b.value
def state():
 w=(C.c_uint16*64).from_address(mem+debug);return [C.c_int32(w[2*i]<<16|w[2*i+1]).value for i in range(32)]
def run(n,pad=0):
 global last_frame,last_view
 for _ in range(n):
  e.run(1,pad);s=state();assert s[19]==0 and e.comm()[0]!=0xe001,('fault',s)
  if capture and s[10]!=last_frame:
   view=[s[16],s[17],s[1]];elapsed=((e.comm()[6]-s[9])&65535)/2
   trace.append(dict(frame=s[10],view=view,transition=(last_view is not None and view!=last_view),vblanks=elapsed,ms=elapsed*1000/hz,tick=s[26],position=s[2:5],sequence=s[9]))
   if view!=last_view:e.capture(a.label+'-'+a.region.lower()+'-'+a.character+'-transition-'+str(len(trace))+'.png')
   last_frame=s[10];last_view=view
 return state()
def until(test,seconds=20,pad=0):
 for _ in range(seconds*hz):
  s=state()
  if test(s):return s
  run(1,pad)
 raise AssertionError(('timeout',state()))
def press(pad):
 run(6);until(lambda s:read16(o['held'])==0 and read16(o['edges'])==0,10)
 run(6,pad);until(lambda s:read16(o['held'])==pad and read16(o['edges'])==0,10,pad)
 run(12);until(lambda s:read16(o['held'])==0 and read16(o['edges'])==0,10)
 tick=state()[0];until(lambda s:s[0]!=tick,10)
def pose(x,y,z,beta):
 if not state()[7]:press(128)
 assert state()[7]
 for d,v in enumerate((x,y,z)):write(o['player']+o['pos']+d*4,v)
 write(o['player']+o['beta'],beta);byte(o['dirty'],1)
 press(128)
if a.character=='emily':press(32)
press(128);run(hz*2);capture=True
# Original stair trigger/track establishes floor 1; controller walks room links.
pose(6830,0,2900,0)
until(lambda s:s[16]==1 and s[17]==6 and s[3]==0 and s[4]<-1800,20);run(hz*2)
run(hz*7,1);assert state()[16:18]==[1,0],state()
until(lambda s:s[16:18]==[1,6],20,2)
until(lambda s:s[16]==0,25,2);run(hz*3)
assert state()[16]==0
transitions=[dict(first=f,next_frames=trace[i+1:i+6]) for i,f in enumerate(trace) if f['transition']]
report=dict(passed=True,label=a.label,region=a.region,character=a.character,rom_sha256=hashlib.sha256((root/'build/AITD32X.32x').read_bytes()).hexdigest(),transitions=transitions,frames=trace)
(root/'build'/('transitions-'+a.label+'-'+a.region.lower()+'-'+a.character+'.json')).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(passed=True,label=a.label,transitions=[t['first'] for t in transitions])),flush=True);e.close()
