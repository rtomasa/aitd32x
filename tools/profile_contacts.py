#!/usr/bin/env python3
"""Measure contact and interaction scenes on the SH2 cartridge. Placement/offer setup is diagnostic; controller input executes gameplay."""
import argparse,ctypes as C,json,re,subprocess,hashlib
from pathlib import Path
import emulator_check as ec
p=argparse.ArgumentParser();p.add_argument('core',type=Path);p.add_argument('--mars',type=Path,required=True);p.add_argument('--character',choices=['edward','emily'],default='edward');p.add_argument('--region',choices=['NTSC','PAL'],default='NTSC');p.add_argument('--project',type=Path,default=ec.ROOT);p.add_argument('--scene',choices=['chest','hall2','hall3','bowopen','chair','window','chestopen'],default='chest');p.add_argument('--label',default='v8');p.add_argument('--music',type=int,default=-1);a=p.parse_args();ec.ROOT=a.project.resolve();root=ec.ROOT
fields={n:'offsetof('+t+','+f+')' for n,t,f in [('player','Game','player'),('world','Game','world'),('pos','Actor','pos'),('beta','Actor','beta'),('pending','ActiveObject','pending_anim'),('pt','ActiveObject','pending_type'),('pn','ActiveObject','pending_next'),('floor','Actor','floor'),('room','Actor','room'),('dirty','Game','dirty'),('camera','Game','camera'),('sig','Game','static_signature'),('objects','World','objects'),('active','World','active'),('value','ActiveObject','value'),('poses','World','poses'),('vars','World','vars'),('inventory','World','inventory'),('invcnt','World','inventory_count'),('prompt','World','prompt'),('held','Game','held'),('edges','Game','pending_edges'),('effects','World','effects'),('serial','World','effect_serial'),('ecount','Effect','count')]};fields['music']='offsetof(World,music)';fields.update(dynamic=('offsetof(Game,dynamic_slots)' if 'dynamic_slots' in (root/'src/engine/game.hpp').read_text() else '0'),bounds='offsetof(Game,static_bounds)',spancount='offsetof(Game,static_span_count)',view='offsetof(World,view_changed)',wcam='offsetof(World,camera)',static_size='sizeof(Game)',active_size='sizeof(ActiveObject)',actor_size='sizeof(Actor)',effect_size='sizeof(Effect)')
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

if a.character=='emily':press(32)
press(128);run(hz*2);pause()
scenes={'chest':(0,0,-4000,0,1200,0,3),'hall2':(1,1,2700,0,400,0,2),'hall3':(1,1,-800,0,-1000,0,3),'chair':(1,5,-1800,0,-200,256,5),'window':(1,4,-1250,0,1700,512,7),'bowopen':(1,1,-800,0,-1000,0,3),'chestopen':(1,2,1800,0,1400,256,9)}
floor,room,x,y,z,beta,cam=scenes[a.scene];pose(1,floor,room,x,y,z,beta)
variable(33,1)
if a.music>=0:write32(wbase+o['music'],a.music)
if a.scene=='chest':pose(0,0,0,-4000,0,300,768)
write32(wbase+o['wcam'],cam);byte(wbase+o['view'],1)
resume();run(hz)
# Stage's first update establishes its room before choosing this camera.
pause();write32(wbase+o['wcam'],cam);byte(wbase+o['view'],1)
if a.scene=='bowopen':
 s=slot(22);assert s>=0;write32(wbase+o['poses']+s*o['actor_size']+o['beta'],512);setobject(22,12,512)
if a.scene=='chair':pose(59,1,5,-2690,0,-2080,256)
if a.scene=='chestopen':
 variable(32,1) # Already unlocked, so Search can exercise repeated lid cycles.
 setobject(38,6,object(38,6)|0x8000) # Suppress the saber pickup pause in this fixture.
resume();run(hz)
# Select Push using the real controller UI.
if a.scene in ('chest','chair'):
 press(32);press(64);press(2);press(2);press(2);press(64)
if a.scene=='chestopen':press(32);press(64);press(2);press(64)
pad=65 if a.scene in ('chest','chair') else 64 if a.scene=='chestopen' else 0
try:profile_address=ec.symbol_address('_profile_state')&0x3ffff
except RuntimeError:profile_address=None
def profile():
 if profile_address is None:return None
 w=(C.c_uint16*50).from_address(mem+profile_address)
 return [w[2*i]<<16|w[2*i+1] for i in range(25)]
run(hz);e.capture(a.label+'-'+a.scene+'-before.png')
before=state();pb=profile();signature=read32(o['sig']);rebuilds=0;batches=[];last=pb;timer=0
for _ in range(hz*5):
 run(1,pad);next_sig=read32(o['sig']);rebuilds+=next_sig!=signature;signature=next_sig
 current=profile()
 if current and current[0]!=last[0]:timer+=(current[23]-last[23])&65535;last=current
end=state();pe=profile();e.capture(a.label+'-'+a.scene+'-after.png')
# Low-FPS samples end between completed frames; retain the observed clock
# progress rather than rejecting a slow baseline before writing its report.
report=dict(label=a.label,scene=a.scene,region=a.region,character=a.character,seconds=5,fps=(end[10]-before[10])/5,ticks=end[26]-before[26],static_rebuilds=rebuilds,start=before,end=end,rom_sha256=hashlib.sha256((root/'build/AITD32X.32x').read_bytes()).hexdigest())
report['completed_frame_seconds']=(end[9]-before[9])/2/hz
report['simulation_hz']=report['ticks']/report['completed_frame_seconds']
assert abs(report['ticks']-25*report['completed_frame_seconds'])<=1.5,('simulation clock',report)
report['cache']=[dict(id=read32(wbase+o['active']+i*o['active_size']),flags=read16(wbase+o['active']+i*o['active_size']+o['value']+4),dynamic=bool(o['dynamic'] and read32(o['dynamic'])&(1<<i)),spans=read16(o['spancount']+2*i)&65535,bounds=[read32(o['bounds']+16*i+4*k) for k in range(4)]) for i in range(24) if read32(wbase+o['active']+i*o['active_size'])>=0]
if pe:
 stages=['update','restore','transform','sort','primitives','fill','mask','contact_and_fps','rebuild_and_palette','flip','frame'];n=pe[0]-pb[0];cpu=(53203424 if a.region=='PAL' else 53693175)*(int(2.4*1024)/1024)/7
 report['timer_calibration']=(timer*128/cpu)/(((pe[24]-pb[24])&65535)/2/hz)
 report['profile_frames']=n;report['timings']={stage:dict(ms=((pe[1+2*i]-pb[1+2*i])&0xffffffff)*128000/cpu/n,calls=pe[2+2*i]-pb[2+2*i]) for i,stage in enumerate(stages)}
(root/'build'/(a.label+'-'+a.scene+'.json')).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True);e.close()
