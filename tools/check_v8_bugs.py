#!/usr/bin/env python3
"""Focused regressions for the reported v7 bugs; uses the cartridge engine/assets."""
import ctypes as C,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
L=C.CDLL(str(ROOT/'build/libaitd32x.so'));data=C.create_string_buffer((ROOT/'assets/bank.bin').read_bytes());L.host_init.argtypes=[C.c_void_p,C.c_uint]
def tick(pad=0):
 L.host_tick(pad);assert not L.host_world(3),('script',*[L.host_world(i) for i in (3,4,5)])
def run(n,pad=0):
 for _ in range(n):tick(pad)
def init(ch):
 L.host_init(data,len(data)-1)
 if ch:tick(32);tick()
 tick(128);tick()
def until(test,n,pad=0):
 for _ in range(n):
  if test():return
  tick(pad)
 raise AssertionError(('timeout',L.host_world(11),L.host_world(14),L.host_object(57,17),L.host_variable(54),L.host_variable(21)))
def position(id):return [L.host_object(id,f) for f in (8,9,10)]
results=[]
for ch in (0,1):
 init(ch);L.host_place(1,1,4,0,0,0,0);run(3);L.host_set_variable(33,1)
 L.host_take(56);L.host_found_life(56,512)
 until(lambda:L.host_variable(46)==1,200)
 assert L.host_object(56,1)==59 and L.host_object(53,15)==4 and not L.host_object(56,6)&0x8000
 assert position(53)==position(56)
 L.host_take(53);assert L.host_object(53,6)&0x8000
 vase=dict(broken=True,key_taken=True,position=position(56))
 init(ch);L.host_place(1,1,4,0,0,-1000,0);run(3)
 until(lambda:L.host_object(57,17)==74,1900)
 assert L.host_object(57,10)<1800,('window exit',position(57))
 arrival=position(57)
 # Original scripts and normal fight input perform the damage/death sequence;
 # diagnostic placement shortens pursuit and keeps this check repeatable.
 L.host_place(1,1,4,0,0,-1000,0);L.host_place(57,1,4,0,0,-1650,512)
 for attempt in range(10):
  if L.host_variable(54)<=0:break
  L.host_place(1,1,4,0,0,-1000,0);L.host_place(57,1,4,0,0,-1650,512);run(100,65)
 assert L.host_variable(54)<=0,('dog damage',L.host_variable(54))
 killed=dict(health=L.host_variable(54),arrival=arrival)
 until(lambda:L.host_object(57,14)==-1,500)
 assert L.host_effects(0)>0 and L.host_effects(1)>0
 killed['particles']=L.host_effects(1);killed['deleted']=True
 run(70);assert L.host_effects(1)==0
 # Attic zombie death reaches SPECIAL 0 through its actual LIFE, using rifle.
 init(ch);run(2400);L.host_place(1,0,0,2000,0,3500,0);L.host_place(21,0,0,2000,0,2850,512);run(700,65)
 assert L.host_variable(22)<=0;run(1800);assert L.host_object(9,17)==18
 L.host_take(3);L.host_found_life(3,1);L.host_place(1,0,0,2000,0,3500,0);L.host_place(9,0,0,2000,0,2000,512)
 until(lambda:L.host_variable(18)<=0,350,65)
 until(lambda:L.host_object(9,14)==-1,500)
 assert L.host_effects(1)>0
 zombie=dict(health=L.host_variable(18),particles=L.host_effects(1))
 # Original hallway camera 2 contains a coverage gap at its far end. Keeping
 # a valid view there is required; camera 1 belongs to the stair/bow room.
 init(ch);L.host_place(1,1,1,0,0,0,0);run(3);L.host_camera(1,1,2)
 # Cover all nearby room-1 gap points without crossing room scenario links.
 cameras=[]
 for x,z in [(0,0),(400,0),(800,0),(1200,0),(1550,0),(1600,0)]:
  L.host_place(1,1,1,x,0,z,0);L.host_camera(1,1,2);tick();cameras.append(L.host_world(2))
  assert L.host_world(2)!=1,('hallway fallback',x,z)
 assert cameras[4]==2,('uncovered hallway gap',cameras)
 results.append(dict(character=ch,vase=vase,dog=killed,zombie=zombie,hallway=cameras))
(ROOT/'build/bugs-v8-host.json').write_text(json.dumps(dict(passed=True,results=results),indent=2)+'\n')
print(json.dumps(results))
