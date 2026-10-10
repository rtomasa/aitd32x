#!/usr/bin/env python3
"""Required v7 gameplay regression on the exact cartridge engine, host platform.

Uses original imported assets. Diagnostic placement shortens travel/time; normal
LIFE/track/update code performs interactions, combat and room transitions.
"""
import ctypes as C,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
L=C.CDLL(str(ROOT/'build/libaitd32x.so'));data=C.create_string_buffer((ROOT/'assets/bank.bin').read_bytes());L.host_init.argtypes=[C.c_void_p,C.c_uint];L.host_pixels.restype=C.c_void_p

def tick(pad=0):
 L.host_tick(pad)
 assert not L.host_world(3),('SCRIPT',L.host_world(3),L.host_world(4),L.host_world(5))
def run(n,pad=0):
 for _ in range(n):tick(pad)
def init(character):
 L.host_init(data,len(data)-1)
 if character:tick(32);tick()
 tick(128);tick()
def state():
 return dict(floor=L.host_world(0),room=L.host_world(1),inventory=[L.host_inventory(i) for i in range(L.host_world(6))],peak_active=L.host_world(9),health=L.host_variable(21),position=[L.host_object(1,f) for f in (8,9,10)])
def until(predicate,n=1000,pad=0):
 for _ in range(n):
  if predicate():return
  tick(pad)
 raise AssertionError(('timeout',state()))
def main():
 results=[]
 for ch in range(2):
  init(ch);L.host_place(1,0,0,-6000,0,-395,256);L.host_found_life(2,64)
  until(lambda:L.host_world(8)==3,100,65);tick();tick(64);tick();assert state()['inventory']==[2,3]
  chest=state()
  L.host_take(15);L.host_found_life(15,4);assert L.host_world(13)==1;tick(64);tick();assert L.host_world(13)==-1
  L.host_drop(15,1);assert L.host_object(15,6)&0x4000;L.host_take(15);assert 15 in state()['inventory']
  L.host_place(1,0,0,6830,0,2900,0);run(300);assert (L.host_world(0),L.host_world(1),L.host_object(1,23))==(1,6,1)
  inventory=state()['inventory'];landing=state();run(150,1);assert L.host_world(1)==0
  # Reverse approach includes moving momentum and the 180-degree track case.
  L.host_place(1,1,6,0,0,-1700,512);run(800);assert (L.host_world(0),L.host_object(1,23))==(0,1) and state()['inventory']==inventory
  roundtrip=state()
  init(ch);L.host_take(3);L.host_found_life(3,512);travel=[]
  for _ in range(160):
   tick();s=L.host_object(3,0)
   if s>=0:travel.append((L.host_object(3,8),L.host_object(3,10),L.host_combat(s,0)))
  assert len({(x,z) for x,z,_ in travel})>2 and travel[-1][2]==0
  L.host_take(3);assert 3 in state()['inventory']
  thrown=travel[-1]
  init(ch);run(2400);assert L.host_object(21,17)==21
  L.host_place(1,0,0,2000,0,3500,0);L.host_place(21,0,0,2000,0,2850,512);run(700,65)
  assert L.host_variable(22)<=0 and L.host_variable(19)==1
  melee=state();run(1800);assert L.host_object(9,17)==18
  L.host_take(3);L.host_found_life(3,1);L.host_place(1,0,0,2000,0,3500,0);L.host_place(9,0,0,2000,0,2000,512);run(250,65)
  assert L.host_variable(18)<=0 and L.host_variable(13)<4
  rifle=state()
  init(ch);cache=[]
  for x,z,beta in [(3231,-1548,0),(-5800,-395,256),(-4500,1500,512),(3000,-4600,0),(5740,1000,768),(0,4200,0)]:
   L.host_place(1,0,0,x,0,z,beta);tick();L.host_clear_message();L.host_draw_fresh();before=C.string_at(L.host_pixels(),320*224)
   L.host_draw_cached();after=C.string_at(L.host_pixels(),320*224);assert before==after,(ch,x,z,'cache ordering')
   cache.append(dict(x=x,z=z,sha256=hashlib.sha256(before).hexdigest()))
  results.append(dict(character=ch,chest=chest,landing=landing,roundtrip=roundtrip,throw_stopped=thrown,melee=melee,rifle=rifle,cache=cache))
 report=dict(passed=True,characters=results,bank_sha256=hashlib.sha256(data.raw[:-1]).hexdigest())
 (ROOT/'build/gameplay-host.json').write_text(json.dumps(report,indent=2)+'\n');print('Both characters: chest, book, drop/retake, throw, enemy arrivals, melee/rifle, stair/room round-trip and 12 fresh/cached comparisons passed.')
if __name__=='__main__':main()
