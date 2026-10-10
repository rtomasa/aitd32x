#!/usr/bin/env python3
"""Standing actors/moved chest must occlude the hatch in both reported cameras."""
import ctypes as C,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];L=C.CDLL(str(root/'build/libaitd32x.so'));data=C.create_string_buffer((root/'assets/bank.bin').read_bytes());L.host_init.argtypes=[C.c_void_p,C.c_uint];L.host_pixels.restype=C.c_void_p
rows=[]
for ch in (0,1):
 for cam in (3,2):
  L.host_init(data,len(data)-1)
  if ch:L.host_tick(32);L.host_tick(0)
  L.host_tick(128);L.host_tick(0)
  L.host_place(0,0,0,-5500,0,1700,768);L.host_place(1,0,0,-5200,0,2500,0)
  L.host_tick(0);L.host_clear_message();L.host_camera(0,0,cam)
  # y increases downwards. Verify this fixture places both objects above
  # the actual hatch, then require its pixels to be painted first.
  order=[L.host_draw_order(i) for i in range(24) if L.host_draw_order(i)>=0]
  for id in (0,1):
   assert L.host_box(id,3)<=L.host_box(8,2),(id,'fixture')
   assert order.index(8)<order.index(id),(ch,cam,'hatch hides raised object',order)
  L.host_draw_fresh();fresh=C.string_at(L.host_pixels(),320*224)
  L.host_draw_cached();cached=C.string_at(L.host_pixels(),320*224);assert fresh==cached,(ch,cam,'cache')
  L.host_draw_painter();painter=C.string_at(L.host_pixels(),320*224);assert fresh==painter,(ch,cam,'original painter')
  rows.append(dict(character=ch,camera=cam,hatch_behind_chest_and_player=True,cached_equal_fresh=True,cached_equal_original_painter=True,order=order))
print(json.dumps(rows,indent=2));(root/'build/cache-v10-hatch.json').write_text(json.dumps(rows,indent=2)+'\n')
