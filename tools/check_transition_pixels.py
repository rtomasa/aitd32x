#!/usr/bin/env python3
import ctypes as C,json
from pathlib import Path
parser=__import__('argparse').ArgumentParser(description='Compare both characters on the reported room/hall route.');parser.add_argument('--reference',type=Path,required=True);parser.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args();root=args.project.resolve();b=C.create_string_buffer((root/'assets/bank.bin').read_bytes());libs=[C.CDLL(str((r/'build/libaitd32x.so').resolve())) for r in [args.reference.resolve(),root]]
for l in libs:l.host_pixels.restype=C.c_void_p
rows=[]
for ch in (0,1):
 for l in libs:
  l.host_init(b,len(b)-1)
  if ch:l.host_tick(32);l.host_tick(0)
  l.host_tick(128);l.host_tick(0);l.host_place(1,1,2,700,0,1700,512);l.host_set_variable(33,1)
 comparisons=0;hall=False
 def compare(label):
  global comparisons
  images=[C.string_at(l.host_pixels(),320*224) for l in libs]
  assert images[0]==images[1],(ch,label,sum(a!=b for a,b in zip(*images)))
  assert [libs[0].host_world(k) for k in [0,1,2,3,11]]==[libs[1].host_world(k) for k in [0,1,2,3,11]]
  comparisons+=1
 for i in range(50):
  for l in libs:l.host_tick(0)
  compare(('setup',i))
 for l in libs:l.host_set_object(33,12,256);l.host_bounds(33,3);l.host_camera(1,2,9)
 for i in range(75):
  for l in libs:l.host_tick(0)
  compare(('settle',i))
 for i in range(20):
  for l in libs:l.host_tick(1)
  compare(('crossing',i));hall|=libs[0].host_world(1)==1
 assert hall
 for i in range(200):
  for l in libs:l.host_tick(0)
  compare(('hall',i))
 rows.append({'character':ch,'exact_frames':comparisons,'world_state_equal':True})
print(json.dumps(rows));(root/'build/room-pixel-parity-v13.json').write_text(json.dumps(rows,indent=2)+'\n')
