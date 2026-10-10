"""Matched stationary ghost/door poses with different cache histories on SH2.
Diagnostic placements and a frozen LIFE/animation state isolate presentation work.
The same final stationary scene is reached with its door settled before entry,
and with the same door marked animated for one draw while already in view.
"""
import argparse,ctypes as C,json,re,subprocess,hashlib
from pathlib import Path
import emulator_check as ec
p=argparse.ArgumentParser();p.add_argument('core',type=Path);p.add_argument('--mars',type=Path,required=True);p.add_argument('--project',type=Path,required=True);p.add_argument('--region',choices=['NTSC','PAL'],default='NTSC');p.add_argument('--character',choices=['edward','emily'],default='edward');p.add_argument('--label',default='v11');p.add_argument('--expect-settled',action='store_true');a=p.parse_args();ec.ROOT=root=a.project.resolve();out=root/'build';hz=50 if a.region=='PAL' else 60
fields={n:'offsetof('+t+','+f+')' for n,t,f in [('player','Game','player'),('world','Game','world'),('pos','Actor','pos'),('beta','Actor','beta'),('pending','ActiveObject','pending_anim'),('floor','Actor','floor'),('room','Actor','room'),('dirty','Game','dirty'),('camera','Game','camera'),('sig','Game','static_signature'),('hashes','Game','static_hash'),('objects','World','objects'),('active','World','active'),('value','ActiveObject','value'),('poses','World','poses'),('vars','World','vars'),('held','Game','held'),('edges','Game','pending_edges'),('speed','ActiveObject','speed'),('vertical','ActiveObject','vertical'),('falling','ActiveObject','falling')]};fields.update(dynamic='offsetof(Game,dynamic_slots)',view='offsetof(World,view_changed)',wcam='offsetof(World,camera)',active_size='sizeof(ActiveObject)',actor_size='sizeof(Actor)')
f=out/('history-layout-'+a.label+'-'+a.region+'-'+a.character+'.cpp');f.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned layout[]={'+','.join(fields.values())+'};\n');asm=f.with_suffix('.s');subprocess.run([str(a.mars/'sh-elf/bin/sh-elf-g++'),'-m2','-mb','-std=c++17','-w','-I'+str(root),'-S',str(f),'-o',str(asm)],check=True)
vals=[int(v,0) for v in re.findall(r'\.long\s+([-0-9xa-fA-F]+)',asm.read_text().split('_layout:',1)[1].split('.ident',1)[0])];o=dict(zip(fields,vals));assert len(o)==len(fields)
e=ec.Emulator(a.core,a.region);e.run(180);mem=C.c_void_p.in_dll(e.lib,'Pico32xMem').value;game=ec.symbol_address('__ZL4game')&0x3ffff;debug=ec.symbol_address('_debug_state')&0x3ffff;wbase=o['world']
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
def until(pred,seconds=20,pad=0):
 for _ in range(hz*seconds):
  if pred():return
  run(1,pad)
 raise AssertionError(('timeout',state()))
def press(pad):
 run(6);until(lambda:read16(o['held'])==0 and read16(o['edges'])==0)
 run(6,pad);until(lambda:read16(o['held'])==pad and read16(o['edges'])==0,pad=pad)
 run(12);until(lambda:read16(o['held'])==0 and read16(o['edges'])==0)
 tick=state()[0];until(lambda:state()[0]!=tick)
def pause():
 if not state()[7]:press(128)
def resume():
 if state()[7]:press(128)
def slot(id):return read16(wbase+o['objects']+52*id)
def objoff(id,f):
 s=slot(id);assert s>=0;return wbase+o['active']+s*o['active_size']+o['value']+2*f
def setobject(id,f,v):
 write16(wbase+o['objects']+52*id+2*f,v)
 s=slot(id)
 if s>=0:write16(objoff(id,f),v)
def actor(id):return o['player'] if id==1 else wbase+o['poses']+slot(id)*o['actor_size']
def pose(id,floor,room,x,y,z,beta):
 assert state()[7];base=actor(id)
 for k,v in enumerate((x,y,z)):write32(base+o['pos']+4*k,v)
 write32(base+o['beta'],beta);write32(base+o['floor'],floor);write32(base+o['room'],room)
 setobject(id,14,floor);setobject(id,15,room);setobject(id,12,beta);byte(o['dirty'],1)
def scene():
 result=[]
 for s in range(24):
  off=wbase+o['active']+s*o['active_size'];id=read32(off)
  if id<0:continue
  b=actor(id);v=off+o['value'];result.append(dict(slot=s,id=id,body=read16(v+2),flags=read16(v+4),room=read32(b+o['room']),pos=[read32(b+o['pos']+4*k) for k in range(3)],beta=read32(b+o['beta']),dynamic=bool(read32(o['dynamic'])&(1<<s))))
 return result
if a.character=='emily':press(32)
press(128);run(hz*2);pause();pose(1,1,7,3300,0,-100,0);variable=lambda n,v:write16(wbase+o['vars']+2*n,v);variable(33,1);write32(wbase+o['wcam'],14);byte(wbase+o['view'],1);resume();run(hz*2);pause()
# Freeze LIFE/pose changes only in this diagnostic. The player keeps its
# animated classification; the stationary ghosts and door retain their final
# original poses. The world tick clock continues at its normal rate.
for s in range(24):
 off=wbase+o['active']+s*o['active_size'];id=read32(off)
 if id<0:continue
 setobject(id,17,-1);setobject(id,19,-1);setobject(id,23,0)
 setobject(id,2,read16(objoff(id,2))&~(64|256))
 write32(off+o['pending'],-1);write32(off+o['speed'],0);write32(off+o['falling'],0);write32(off+o['vertical']+8,0)
pose(63,1,7,3500,0,300,256);setobject(63,2,0)
# Clear only the original v10 cache history, not gameplay/model state.
def resetcache():
 write32(o['sig'],0);write32(o['dynamic'],0)
 for s in range(24):write32(o['hashes']+4*s,0)
 byte(o['dirty'],1)
resetcache();resume();run(hz*2)
assert slot(1)>=0 and slot(63)>=0 and slot(64)>=0
rows=[]
def measure(label):
 run(hz);before=state();run(5*hz);after=state();pixels=e.framebuffer()[1][320*12:320*212]
 row=dict(history=label,fps=(after[10]-before[10])/5,ticks=after[26]-before[26],view=after[16:18]+[after[1]],pixels_sha256=hashlib.sha256(pixels).hexdigest(),scene=scene());rows.append(row);ec.png(out/(a.label+'-'+a.region.lower()+'-'+a.character+'-'+label+'.png'),e.rgb_pixels(),e.width,e.height);print(json.dumps(row),flush=True)
measure('settled-before-entry')
# Same door becomes animated for one draw; it then settles at exactly its
# previous open pose. This emulates the cache change caused by an in-view door.
pause();setobject(64,2,1);setobject(65,2,1);resume();run(hz);pause();setobject(64,2,0);setobject(65,2,0);resume();run(hz);measure('ghosts-settled-in-view')
pause();setobject(63,2,1);resume();run(hz);pause();setobject(63,2,0);resume();run(hz);measure('ghosts-and-door-settled-in-view')
pause();resetcache();resume();run(hz*2);measure('cache-reset')
assert len({r['pixels_sha256'] for r in rows})==1,('pixels differ',rows)
if a.expect_settled:
 for r in rows:
  assert r['fps']>=24.6,(r['history'],'steady FPS',r['fps'])
  assert all(not obj['dynamic'] for obj in r['scene'] if obj['id'] in (63,64,65)),(r['history'],'settled props stayed dynamic')
report=dict(label=a.label,diagnostic=True,region=a.region,character=a.character,rom_sha256=hashlib.sha256((root/'build/AITD32X.32x').read_bytes()).hexdigest(),rows=rows)
(out/(a.label+'-history-'+a.region.lower()+'-'+a.character+'.json')).write_text(json.dumps(report,indent=2)+'\n');e.close()
