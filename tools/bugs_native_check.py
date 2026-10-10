#!/usr/bin/env python3
"""Reported first-floor bugs on the actual SH2 cartridge. Placement/offer setup is diagnostic; controller input executes gameplay."""
import argparse,ctypes as C,json,re,subprocess,hashlib
from pathlib import Path
import emulator_check as ec
p=argparse.ArgumentParser();p.add_argument('core',type=Path);p.add_argument('--mars',type=Path,required=True);p.add_argument('--character',choices=['edward','emily'],default='edward');p.add_argument('--region',choices=['NTSC','PAL'],default='NTSC');a=p.parse_args();root=ec.ROOT
fields={n:'offsetof('+t+','+f+')' for n,t,f in [('player','Game','player'),('world','Game','world'),('pos','Actor','pos'),('beta','Actor','beta'),('pending','ActiveObject','pending_anim'),('pt','ActiveObject','pending_type'),('pn','ActiveObject','pending_next'),('floor','Actor','floor'),('room','Actor','room'),('dirty','Game','dirty'),('camera','Game','camera'),('sig','Game','static_signature'),('objects','World','objects'),('active','World','active'),('value','ActiveObject','value'),('poses','World','poses'),('vars','World','vars'),('inventory','World','inventory'),('invcnt','World','inventory_count'),('prompt','World','prompt'),('held','Game','held'),('edges','Game','pending_edges'),('effects','World','effects'),('serial','World','effect_serial'),('ecount','Effect','count')]};fields.update(active_size='sizeof(ActiveObject)',actor_size='sizeof(Actor)',effect_size='sizeof(Effect)')
f=root/'build'/('bugs-layout-'+a.region+'-'+a.character+'.cpp');f.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned bug_layout[]={'+','.join(fields.values())+'};\n');assembly=f.with_suffix('.s')
subprocess.run([str(a.mars/'sh-elf/bin/sh-elf-g++'),'-m2','-mb','-std=c++17','-Wno-invalid-offsetof','-I'+str(root),'-S',str(f),'-o',str(assembly)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
values=[int(v,0) for v in re.findall(r'\.long\s+([-0-9xa-fA-F]+)',assembly.read_text().split('_bug_layout:',1)[1].split('.ident',1)[0])];o=dict(zip(fields,values));assert len(o)==len(fields)
e=ec.Emulator(a.core,a.region);hz=50 if a.region=='PAL' else 60;e.run(180);mem=C.c_void_p.in_dll(e.lib,'Pico32xMem').value;game=ec.symbol_address('__ZL4game')&0x3ffff;debug=ec.symbol_address('_debug_state')&0x3ffff;wbase=o['world']
def read32(off):
 w=(C.c_uint16*2).from_address(mem+game+off);return C.c_int32(w[0]<<16|w[1]).value
def write32(off,v):
 w=(C.c_uint16*2).from_address(mem+game+off);w[0]=(v>>16)&65535;w[1]=v&65535
def write16(off,v):C.c_uint16.from_address(mem+game+off).value=v&65535
def read16(off):return C.c_int16.from_address(mem+game+off).value
def byte(off,v=None):
 b=C.c_uint8.from_address(mem+game+(off^1))
 if v is not None:b.value=v
 return b.value
def state():
 w=(C.c_uint16*64).from_address(mem+debug);return [C.c_int32(w[2*i]<<16|w[2*i+1]).value for i in range(32)]
def run(n,pad=0):
 e.run(n,pad);assert state()[19]==0 and e.comm()[0]!=0xe001,('fault',state())
def press(pad):
 run(6)
 until(lambda:read16(o['held'])==0 and read16(o['edges'])==0,10)
 run(6,pad)
 until(lambda:read16(o['held'])==pad and read16(o['edges'])==0,10,pad)
 run(12)
 until(lambda:read16(o['held'])==0 and read16(o['edges'])==0,10)
 # Finish a render so debug_state describes the completed input update.
 frames=state()[0];until(lambda:state()[0]!=frames,10)
def pause():
 if not state()[7]:press(128)
def resume():
 if state()[7]:press(128)
def slot(id):return read16(wbase+o['objects']+id*52)
def object(id,f):
 s=slot(id);return read16(wbase+o['objects']+52*id+2*f) if s<0 else read16(wbase+o['active']+s*o['active_size']+o['value']+2*f)
def setobject(id,f,v):
 s=slot(id);write16(wbase+o['objects']+52*id+2*f,v)
 if s>=0:write16(wbase+o['active']+s*o['active_size']+o['value']+2*f,v)
def variable(n,v=None):
 off=wbase+o['vars']+2*n
 if v is not None:write16(off,v)
 return read16(off)
def pose(id,floor,room,x,y,z,beta):
 assert state()[7];s=slot(id);assert s>=0
 actor=o['player'] if id==1 else wbase+o['poses']+s*o['actor_size']
 for k,v in enumerate((x,y,z)):write32(actor+o['pos']+4*k,v)
 write32(actor+o['beta'],beta);write32(actor+o['floor'],floor);write32(actor+o['room'],room)
 setobject(id,14,floor);setobject(id,15,room)
 byte(o['dirty'],1)
def until(pred,seconds=30,pad=0):
 for _ in range(hz*seconds):
  if pred():return
  run(1,pad)
 raise AssertionError(('timeout',state(),variable(54)))
def effects():return sum(byte(wbase+o['effects']+i*o['effect_size']+o['ecount']) for i in range(3))
if a.character=='emily':press(32)
press(128);run(hz*2);pause();pose(1,1,4,0,0,0,0);variable(33,1);resume();run(hz)
# The original SEARCH offer is supplied diagnostically; TAKE, inventory THROW,
# flight, collision, vase LIFE68, PUT_AT key and key TAKE execute unchanged.
write32(wbase+o['prompt'],56);press(64);until(lambda:state()[22]==2,10);assert state()[22]==2,("take",state(),o,read32(wbase+o["prompt"]))
press(32);press(2);press(64);press(64)
until(lambda:variable(46)==1,12);assert object(56,1)==59 and not object(56,6)&0x8000
pause();s=slot(53);assert s>=0;actor=wbase+o['poses']+s*o['actor_size'];point=[read32(actor+o['pos']+4*k) for k in range(3)];pose(1,1,4,*point,0);resume();until(lambda:state()[24] in (53,56),10,1)
if state()[24]==56:press(64);until(lambda:state()[24]==53,10,1)
press(64);assert state()[22]==3
vase=dict(broken=True,key_taken=True,key_position=point)
# Re-enable the original bedroom arrival; no enemy placement until after exit.
pause();variable(33,0);variable(45,1);resume();until(lambda:object(57,17)==74,90)
s=slot(57);actor=wbase+o['poses']+s*o['actor_size'];arrival=[read32(actor+o['pos']+4*k) for k in range(3)];assert arrival[2]<1800,arrival
# Actions > Fight. Align between attempts to shorten pursuit; real controller
# punches apply HIT/HIT_BY, original HP54 and death animation/LIFE deletion.
press(32);press(64);press(64);assert state()[23]==2
for attempt in range(10):
 if variable(54)<=0:break
 pause();pose(1,1,4,0,0,-1000,0);pose(57,1,4,0,0,-1650,512);resume();run(hz*4,65)
assert variable(54)<=0
until(lambda:object(57,14)==-1,15);assert effects()>=30
pause();e.capture('v9-'+a.region.lower()+'-'+a.character+'-dog-death.png');particle_count=effects()
# Frozen depth/material output must agree in both hardware framebuffer banks.
shown={};last=e.vdp[5]&1;swaps=0
for _ in range(hz*4):
 byte(o['dirty'],1);run(1);bank=e.vdp[5]&1
 if bank!=last:
  last=bank;swaps+=1
  if swaps>=2:shown[bank]=e.framebuffer()[1][12*320:212*320]
 if len(shown)==2:break
assert len(shown)==2 and shown[0]==shown[1]
resume();run(hz*3);assert effects()==0
before=state();run(hz*5);after=state();assert abs(after[26]-before[26]-125)<=3
# Reproduce the chair contact in camera 5, including a moving prop.
pause();pose(1,1,5,-1800,0,-200,256);pose(59,1,5,-2690,0,-2080,256);resume();run(hz)
# Choose Actions > Push through the real inventory UI.
press(32);press(64);press(2);press(2);press(2);press(64);run(hz//2,65);pause()
e.capture('v9-'+a.region.lower()+'-'+a.character+'-chair.png')
shown={};last=e.vdp[5]&1;swaps=0
for _ in range(hz*4):
 byte(o['dirty'],1);run(1);bank=e.vdp[5]&1
 if bank!=last:
  last=bank;swaps+=1
  if swaps>=2:shown[bank]=e.framebuffer()[1][12*320:212*320]
 if len(shown)==2:break
assert len(shown)==2 and shown[0]==shown[1],('chair bank mismatch',state())
resume();run(hz*2);contact_before=state();run(hz*5);contact_after=state();contact_fps=(contact_after[10]-contact_before[10])/5
assert abs(contact_after[26]-contact_before[26]-125)<=3
e.capture('v9-'+a.region.lower()+'-'+a.character+'-chair-steady.png')
report=dict(contact_fps=contact_fps,passed=True,character=a.character,region=a.region,vase=vase,dog=dict(arrival=arrival,health=variable(54),deleted=True,death_particles=particle_count),framebuffer_banks_equal=True,simulation_ticks=after[26]-before[26],rom_sha256=hashlib.sha256((root/'build/AITD32X.32x').read_bytes()).hexdigest())
(root/'build'/('bugs-native-'+a.region.lower()+'-'+a.character+'.json')).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));e.close()
