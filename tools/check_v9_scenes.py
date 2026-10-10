#!/usr/bin/env python3
"""Reported window/door poses: cache pixels must match a fresh original-camera painter pass."""
import ctypes as C,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];L=C.CDLL(str(root/'build/libaitd32x.so'));data=C.create_string_buffer((root/'assets/bank.bin').read_bytes());L.host_init.argtypes=[C.c_void_p,C.c_uint];L.host_pixels.restype=C.c_void_p
def pixels():return C.string_at(L.host_pixels(),320*224)
rows=[]
for ch in (0,1):
 for name,room,x,z,cam,broken,angle in [('window-front',4,-1250,1700,7,True,256),('window-back',4,-750,2450,7,True,256),('hall2',1,2700,400,2,False,256),('hall3',1,-800,-1000,3,False,256),('bow-open',1,-800,-1000,3,False,512),('bow-opening',1,4000,100,3,False,384)]:
  L.host_init(data,len(data)-1)
  if ch:L.host_tick(32);L.host_tick(0)
  L.host_tick(128);L.host_tick(0);L.host_place(1,1,room,x,0,z,512)
  for _ in range(3):L.host_tick(0)
  L.host_set_variable(33,1);L.host_clear_message()
  if broken:L.host_set_object(51,1,56);L.host_set_object(51,17,-1)
  if angle!=256:L.host_set_object(22,12,angle);L.host_bounds(22,0)
  L.host_camera(1,room,cam);L.host_draw_fresh();a=pixels();L.host_draw_cached();b=pixels();assert a==b,(name,ch,'cache')
  L.host_draw_painter();c=pixels();diff=sum(x!=y for x,y in zip(a,c));assert diff==0,(name,ch,'original-camera painter',diff);rows.append(dict(scene=name,character=ch,cached_equal_fresh=True,cached_vs_unbaked=diff))
print(json.dumps(rows,indent=2));(root/'build/cache-v9.json').write_text(json.dumps(rows,indent=2)+'\n')
