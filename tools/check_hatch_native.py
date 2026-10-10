#!/usr/bin/env python3
"""Reported attic hatch ordering: frozen SH2 output must agree across both physical framebuffer banks."""
import argparse,ctypes as C,json,re,subprocess,hashlib
from pathlib import Path
import emulator_check as ec
p=argparse.ArgumentParser();p.add_argument('core',type=Path);p.add_argument('--mars',type=Path,required=True);p.add_argument('--character',choices=['edward','emily'],default='edward');p.add_argument('--region',choices=['NTSC','PAL'],default='NTSC');p.add_argument('--project',type=Path,default=ec.ROOT);p.add_argument('--label',default='v10');a=p.parse_args();ec.ROOT=a.project.resolve();root=ec.ROOT
fields={n:'offsetof('+t+','+f+')' for n,t,f in [('player','Game','player'),('world','Game','world'),('pos','Actor','pos'),('beta','Actor','beta'),('pending','ActiveObject','pending_anim'),('pt','ActiveObject','pending_type'),('pn','ActiveObject','pending_next'),('floor','Actor','floor'),('room','Actor','room'),('dirty','Game','dirty'),('camera','Game','camera'),('sig','Game','static_signature'),('objects','World','objects'),('active','World','active'),('value','ActiveObject','value'),('poses','World','poses'),('vars','World','vars'),('inventory','World','inventory'),('invcnt','World','inventory_count'),('prompt','World','prompt'),('held','Game','held'),('edges','Game','pending_edges'),('effects','World','effects'),('serial','World','effect_serial'),('ecount','Effect','count')]};fields.update(dynamic=('offsetof(Game,dynamic_slots)' if 'dynamic_slots' in (root/'src/engine/game.hpp').read_text() else '0'),bounds='offsetof(Game,static_bounds)',spancount='offsetof(Game,static_span_count)',view='offsetof(World,view_changed)',wcam='offsetof(World,camera)',static_size='sizeof(Game)',active_size='sizeof(ActiveObject)',actor_size='sizeof(Actor)',effect_size='sizeof(Effect)')
f=root/'build'/('contact-layout-'+a.label+'-hatch-'+a.region+'-'+a.character+'.cpp');f.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned bug_layout[]={'+','.join(fields.values())+'};\n');assembly=f.with_suffix('.s')
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
press(128);run(hz*2);pause()
rows=[]
for camera in (3,2):
 pose(0,0,0,-5500,0,1700,768);pose(1,0,0,-5200,0,2500,0)
 write32(wbase+o['wcam'],camera);write32(o['camera'],camera)
 write32(o['sig'],0);byte(wbase+o['view'],0);byte(o['dirty'],1)
 shown={};last=e.vdp[5]&1;swaps=0
 for _ in range(hz*4):
  byte(o['dirty'],1);run(1);bank=e.vdp[5]&1
  if bank!=last:
   last=bank;swaps+=1
   if swaps>=2:shown[bank]=e.framebuffer()[1][12*320:212*320]
  if len(shown)==2:break
 assert len(shown)==2 and shown[0]==shown[1],('hatch bank mismatch',camera,state())
 assert state()[1]==camera and state()[16:18]==[0,0],state()
 ec.check_borders(e.framebuffer()[1])
 e.capture(a.label+'-hatch-'+a.region.lower()+'-'+a.character+'-'+str(camera)+'.png')
 rows.append(dict(camera=camera,framebuffer_banks_equal=True,game_fault=state()[19]))
report=dict(passed=True,character=a.character,region=a.region,scenes=rows,rom_sha256=hashlib.sha256((root/'build/AITD32X.32x').read_bytes()).hexdigest())
(root/'build'/('hatch-native-'+a.label+'-'+a.region.lower()+'-'+a.character+'.json')).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));e.close()
