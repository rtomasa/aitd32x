#!/usr/bin/env python3
"""Actual cartridge gameplay checks in PicoDrive DRC_SH2; placement is diagnostic.

Controller input performs item actions. Debugger placement only shortens travel.
Run each character/region in its own process. No changes to release game code.
"""
import argparse,ctypes as C,json,re,struct,subprocess,hashlib
from pathlib import Path
import emulator_check as ec

def main():
 p=argparse.ArgumentParser();p.add_argument('core',type=Path);p.add_argument('--mars',type=Path,required=True);p.add_argument('--region',choices=['NTSC','PAL'],default='NTSC');p.add_argument('--character',choices=['edward','emily'],default='edward');p.add_argument('--combat',action='store_true');a=p.parse_args()
 root=ec.ROOT;tag=a.region.lower()+'-'+a.character;refresh=50 if a.region=='PAL' else 60
 fields={'player':'offsetof(Game,player)','pos':'offsetof(Actor,pos)','beta':'offsetof(Actor,beta)','dirty':'offsetof(Game,dirty)','world':'offsetof(Game,world)','ticks':'offsetof(World,ticks)','now':'offsetof(World,now)','message':'offsetof(World,message)','static_signature':'offsetof(Game,static_signature)','objects':'offsetof(World,objects)','active':'offsetof(World,active)','active_value':'offsetof(ActiveObject,value)','active_size':'sizeof(ActiveObject)','poses':'offsetof(World,poses)','actor_size':'sizeof(Actor)','vars':'offsetof(World,vars)'}
 source=root/'build'/('gameplay-layout-'+tag+'.cpp');assembly=source.with_suffix('.s')
 source.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned gameplay_layout[]={'+','.join(fields.values())+'};\n')
 subprocess.run([str(a.mars/'sh-elf/bin/sh-elf-g++'),'-m2','-mb','-std=c++17','-Wno-invalid-offsetof','-I'+str(root),'-S',str(source),'-o',str(assembly)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 values=[int(v,0) for v in re.findall(r'\.long\s+([-0-9xa-fA-F]+)',assembly.read_text().split('_gameplay_layout:',1)[1].split('.ident',1)[0])];offsets=dict(zip(fields,values));assert len(offsets)==len(fields)
 e=ec.Emulator(a.core,a.region);e.run(180);mem=C.c_void_p.in_dll(e.lib,'Pico32xMem').value;game=ec.symbol_address('__ZL4game')&0x3ffff;debug=ec.symbol_address('_debug_state')&0x3ffff
 def write(offset,value):
  w=(C.c_uint16*2).from_address(mem+game+offset);w[0]=(value>>16)&65535;w[1]=value&65535
 def byte(offset,value):C.c_uint8.from_address(mem+game+(offset^1)).value=value
 def state():
  w=(C.c_uint16*64).from_address(mem+debug);return [C.c_int32((w[2*i]<<16)|w[2*i+1]).value for i in range(32)]
 def run(frames,pad=0):
  e.run(frames,pad);s=state();assert e.comm()[0]!=0xe001 and s[19]==0,('fault',s);return s
 def press(pad):run(6);run(6,pad);run(12)
 def until(predicate,limit=refresh*20,pad=0):
  for _ in range(limit):
   if predicate(state()):return state()
   run(1,pad)
  raise AssertionError(('timeout',state()))
 def pose(x,y,z,beta):
  if not state()[7]:press(128)
  assert state()[7]
  for d,v in enumerate((x,y,z)):write(offsets['player']+offsets['pos']+d*4,v)
  write(offsets['player']+offsets['beta'],beta);byte(offsets['dirty'],1);run(refresh)
  press(128)
 def capture(name):e.capture('v7-'+tag+'-'+name+'.png')
 def read16(offset):return C.c_int16.from_address(mem+game+offset).value
 def slot(id):return read16(offsets['world']+offsets['objects']+id*52)
 def object(id,field):
  index=slot(id)
  if index<0:return -1
  return read16(offsets['world']+offsets['active']+index*offsets['active_size']+offsets['active_value']+field*2)
 def variable(id):return read16(offsets['world']+offsets['vars']+id*2)
 def enemy_pose(id,x,y,z,beta):
  assert state()[7] and slot(id)>=0
  actor=offsets['world']+offsets['poses']+slot(id)*offsets['actor_size']
  for d,v in enumerate((x,y,z)):write(actor+offsets['pos']+d*4,v)
  write(actor+offsets['beta'],beta)
 bankchecks=[]
 def banks(name):
  if not state()[7]:press(128)
  shown={};last=e.vdp[5]&1;swaps=0
  for _ in range(refresh*4):
   byte(offsets['dirty'],1);run(1);bank=e.vdp[5]&1
   if bank!=last:
    last=bank;swaps+=1
    if swaps>=2:shown[bank]=e.framebuffer()[1][12*320:212*320]
   if len(shown)==2:break
  assert len(shown)==2 and shown[0]==shown[1],('framebuffer banks differ',name)
  bankchecks.append(name);capture(name);press(128)
 if a.character=='emily':press(32)
 press(128);run(refresh*3);assert state()[8]==int(a.character=='emily');banks('attic')
 # Choose Actions > Search, then open the chest and accept the rifle.
 pose(-6000,0,-395,256);press(32);assert state()[18]==1
 press(64);assert state()[18]==2;press(2);press(64);assert state()[27]==64
 until(lambda s:s[24]==3,refresh*8,65);press(64);run(refresh);assert state()[22]==2 and state()[24]==-1
 capture('rifle-taken')
 # Original stair track and inventory retention, without a direct floor write.
 pose(6830,0,2900,0);until(lambda s:s[16]==1 and s[17]==6 and s[3]==0 and s[4]<-1800,refresh*15)
 run(refresh*2);assert state()[22]==2;banks('stairs-landing')
 run(refresh*7,1);assert state()[16]==1 and state()[17]==0;capture('first-floor')
 # Return through the room link, then enter the stair trigger naturally.
 until(lambda s:s[16]==1 and s[17]==6,refresh*15,2);until(lambda s:s[16]==0,refresh*20,2);run(refresh*7)
 assert state()[16]==0 and state()[22]==2;banks('attic-return')
 # A steady five-second sample verifies the clock after scripted transitions.
 run(refresh*2);before=state();run(refresh*5);after=state();ticks=after[26]-before[26]
 assert abs(ticks-125)<=3,(ticks,before,after)
 fps=(after[10]-before[10])/5
 combat=None
 if a.combat:
  # Choose the real Fight action with the controller, then wait for arrival.
  press(32);press(64);press(64);assert state()[27]==16 and state()[23]==2
  pose(2000,0,3500,0);until(lambda s:object(21,17)==21,refresh*110)
  press(128);enemy_pose(21,2000,0,2850,512);press(128)
  until(lambda s:variable(22)<=0 and variable(19)==1,refresh*40,65)
  run(refresh*72);assert object(9,17)==18
  # Select the rifle, equip it, and fire using its original item LIFE.
  press(32);press(2);press(64);press(64);assert state()[23]==3
  pose(2000,0,3500,0);press(128);enemy_pose(9,2000,0,2000,512);press(128)
  until(lambda s:variable(18)<=0,refresh*15,65)
  combat=dict(dog_health=variable(22),zombie_health=variable(18),ammo=variable(13),player_health=variable(21));banks('combat')
 report=dict(combat=combat,region=a.region,character=a.character,passed=True,framebuffer_bank_checks=bankchecks,inventory_count=after[22],simulation_ticks=ticks,render_fps=fps,final_state=after,rom_sha256=hashlib.sha256((root/'build/AITD32X.32x').read_bytes()).hexdigest())
 (root/'build'/('gameplay-native-'+tag+'.json')).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True);e.close()
if __name__=='__main__':main()
