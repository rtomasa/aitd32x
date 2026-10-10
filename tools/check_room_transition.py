#!/usr/bin/env python3
"""Trace sofa-room to hallway. Placement and doorway setup are diagnostic; real walking executes the room link."""
import argparse,ctypes as C,json,re,subprocess,hashlib
from pathlib import Path
import emulator_check as ec
p=argparse.ArgumentParser();p.add_argument('core',type=Path);p.add_argument('--mars',type=Path,required=True);p.add_argument('--character',choices=['edward','emily'],default='edward');p.add_argument('--region',choices=['NTSC','PAL'],default='NTSC');p.add_argument('--project',type=Path,default=ec.ROOT);p.add_argument('--scene',choices=['chest','hall2','hall3','bowopen','chair','window'],default='chest');p.add_argument('--label',default='v13');a=p.parse_args();ec.ROOT=a.project.resolve();root=ec.ROOT
fields={n:'offsetof('+t+','+f+')' for n,t,f in [('player','Game','player'),('world','Game','world'),('pos','Actor','pos'),('beta','Actor','beta'),('pending','ActiveObject','pending_anim'),('pt','ActiveObject','pending_type'),('pn','ActiveObject','pending_next'),('floor','Actor','floor'),('room','Actor','room'),('dirty','Game','dirty'),('camera','Game','camera'),('sig','Game','static_signature'),('objects','World','objects'),('active','World','active'),('value','ActiveObject','value'),('poses','World','poses'),('vars','World','vars'),('inventory','World','inventory'),('invcnt','World','inventory_count'),('prompt','World','prompt'),('held','Game','held'),('edges','Game','pending_edges'),('effects','World','effects'),('serial','World','effect_serial'),('ecount','Effect','count')]};fields.update(lo='offsetof(Actor,collision_min)',hi='offsetof(Actor,collision_max)',hashes='offsetof(Game,static_hash)',quiet='offsetof(Game,static_quiet_since)',dynamic=('offsetof(Game,dynamic_slots)' if 'dynamic_slots' in (root/'src/engine/game.hpp').read_text() else '0'),bounds='offsetof(Game,static_bounds)',spancount='offsetof(Game,static_span_count)',view='offsetof(World,view_changed)',wcam='offsetof(World,camera)',static_size='sizeof(Game)',active_size='sizeof(ActiveObject)',actor_size='sizeof(Actor)',effect_size='sizeof(Effect)')
f=root/'build'/('contact-layout-'+a.label+'-'+a.scene+'-'+a.region+'-'+a.character+'.cpp');f.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned bug_layout[]={'+','.join(fields.values())+'};\n');assembly=f.with_suffix('.s')
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

import struct
record=False;trace=[];last_frame=-1;last_present=None;last_scene=None

def scene():
 items=[]
 for s in range(24):
  off=wbase+o['active']+s*o['active_size'];id=read32(off)
  if id<0:continue
  v=off+o['value'];pa=o['player'] if id==1 else wbase+o['poses']+s*o['actor_size']
  items.append(dict(slot=s,id=id,body=read16(v+2),flags=read16(v+4),life=read16(v+34),room=read32(pa+o['room']),pos=[read32(pa+o['pos']+4*k) for k in range(3)],beta=read32(pa+o['beta']),dynamic=bool(read32(o['dynamic'])&(1<<s)),quiet=read16(o['quiet']+s*2)&65535,hash=read32(o['hashes']+4*s)&0xffffffff,spans=read16(o['spancount']+2*s)&65535))
 return items

def run(n,pad=0):
 global last_frame,last_present,last_scene
 for _ in range(n):
  e.run(1,pad);st=state();assert st[19]==0 and e.comm()[0]!=0xe001,('fault',st)
  if record and st[10]!=last_frame:
   present=e.comm()[6];sc=scene();snapshot=json.dumps(sc,sort_keys=True)
   delta=None if last_present is None else ((present-last_present)&65535)/2
   row=dict(frame=st[10],view=[st[16],st[17],st[1]],position=st[2:5],world_ticks=st[26],hud_fps=st[11]/10,present=present,interval_ms=None if delta is None else delta*1000/hz,render_ms=((present-st[9])&65535)*500/hz,signature=read32(o['sig'])&0xffffffff,dynamic=read32(o['dynamic'])&0xffffffff)
   if snapshot!=last_scene:row['scene']=sc
   trace.append(row);last_scene=snapshot;last_frame=st[10];last_present=present
 return state()
try:
 if a.character=='emily':press(32)
 press(128);run(hz*2);pause();pose(1,1,2,700,0,1700,512)
 variable(33,1);write32(wbase+o['wcam'],9);byte(wbase+o['view'],1)
 resume();run(hz*2);pause();assert slot(33)>=0
 # Open door 33 for the fixture and update its collision bounds to match.
 pa=wbase+o['poses']+slot(33)*o['actor_size'];write32(pa+o['beta'],256);setobject(33,12,256)
 bank=(root/'assets/bank.bin').read_bytes();m=json.loads((root/'assets/manifest.json').read_text());md=next(v for v in m['assets'] if v['name']==f'MODEL_{int(a.character=="emily")}_34');model=bank[md['offset']:md['offset']+md['packed_size']]
 lx,hx,ly,hy,lz,hzbound=struct.unpack_from('>6h',model,8)
 for field,vals in [('lo',(-int(hzbound*32767/32768),ly,int(lx*32767/32768))),('hi',(-int(lz*32767/32768),hy,int(hx*32767/32768)))]:
  for k,v in enumerate(vals):write32(pa+o[field]+k*4,v)
 write32(wbase+o['wcam'],9);byte(wbase+o['view'],1);byte(o['dirty'],1);resume();run(hz*3)
 assert state()[16:18]==[1,2],state()
 record=True;run(hz);e.capture(a.label+'-'+a.region.lower()+'-room-before.png')
 until(lambda:state()[16:18]==[1,1],10,1)
 crossing=len(trace)-1;run(hz*8)
 assert state()[16:18]==[1,1] and state()[1]==2,state()
 e.capture(a.label+'-'+a.region.lower()+'-hall-after.png')
 report=dict(label=a.label,region=a.region,character=a.character,diagnostic=True,rom_sha256=hashlib.sha256((root/'build/AITD32X.32x').read_bytes()).hexdigest(),compression_flags=sorted(set(x['flags'] for x in m['assets'])),crossing_index=crossing,trace=trace)
 path=root/'build'/('room-transition-'+a.label+'-'+a.region.lower()+'.json');path.write_text(json.dumps(report,indent=2)+'\n')
 c=trace[crossing];rows=[]
 for second in range(8):
  fs=[x for x in trace[crossing:] if second*2*hz<=((x['present']-c['present'])&65535)<(second+1)*2*hz]
  rows.append(dict(second=second,draws=len(fs),max_interval_ms=max((x['interval_ms'] or 0 for x in fs),default=0),signatures=len(set(x['signature'] for x in fs)),dynamic_masks=sorted(set(x['dynamic'] for x in fs))))
 print(json.dumps(dict(report=str(path),crossing=c,seconds=rows)),flush=True)
finally:e.close()
