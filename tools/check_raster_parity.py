#!/usr/bin/env python3
import ctypes as C,json,struct
from pathlib import Path
parser=__import__('argparse').ArgumentParser(description='Compare every compiled prop against a reference renderer.');parser.add_argument('--reference',type=Path,required=True);parser.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args();new=args.project.resolve();old=args.reference.resolve();bank=(new/'assets/bank.bin').read_bytes();buf=C.create_string_buffer(bank);m=json.loads((new/'assets/manifest.json').read_text());assets={a['name']:(a,bank[a['offset']:a['offset']+a['packed_size']]) for a in m['assets']};program=assets['STATIC_RASTERS'][1];expected=struct.unpack_from('>I',program)[0];keys={struct.unpack_from('>2I',program,4+12*i) for i in range(expected)}
libs=[C.CDLL(str((r/'build/libaitd32x.so').resolve())) for r in [old,new]]
for lib in libs:
 lib.host_pixels.restype=lib.host_prop_spans.restype=C.c_void_p;lib.host_init(buf,len(bank))
objects=[struct.unpack_from('>26h',assets['OBJECTS'][1],i*52) for i in range(m['player_object']+291)]
# This key duplicates no rendering algorithm: it selects asset records, while
# the two independent drawing paths compare pixels, masks and coverage spans.
base=assets['GAME_PALETTE'][0]['offset']
def key(character,obj,beta):
 h=2166136261;values=[assets[f'MODEL_{character}_{obj[1]}'][0]['offset']-base,obj[14],obj[15],*obj[8:12],beta,obj[13]]
 for v in values:h=((h^(v&0xffffffff))*16777619)&0xffffffff
 return h
seen=set();comparisons=0;checks=[]
for floor,(_,cameras) in enumerate(m['levels']):
 for camera in range(cameras):
  for obj in objects:
   body=obj[1];room=obj[15]
   if body<0 or obj[14]!=floor:continue
   for ch in (0,1):
    for beta in sorted({obj[12],0,256,512,768}) if body in (25,34) else [obj[12]]:
     k=(floor*256+camera,key(ch,obj,beta))
     if k not in keys or k in seen:continue
     seen.add(k)
     for bounds in (1,3):
      results=[]
      for lib in libs:
       n=lib.host_prop_draw(ch,body,floor,room,camera,*obj[8:12],beta,obj[13],bounds,5)
       results.append((C.string_at(lib.host_pixels(),320*224),C.string_at(lib.host_prop_spans(),n*4),tuple(lib.host_prop_bound(i) for i in range(4))))
      assert results[0]==results[1],('raster parity',ch,floor,room,camera,body,beta,bounds,sum(x!=y for x,y in zip(results[0][0],results[1][0])))
      comparisons+=1
assert seen==keys,(len(seen),len(keys))
# Exercise fallback for relocated and nonorthogonal door geometry.
obj=next(o for o in objects if o[14]==1 and o[15]==2 and o[1]==34)
for beta,xshift in [(128,0),(384,0),(256,47)]:
 results=[]
 for lib in libs:
  n=lib.host_prop_draw(0,34,1,2,2,obj[8]+xshift,*obj[9:12],beta,obj[13],3,5)
  results.append((C.string_at(lib.host_pixels(),320*224),C.string_at(lib.host_prop_spans(),n*4)))
 assert results[0]==results[1],('fallback',beta,xshift)
report={'compiled_entries':len(keys),'pixel_and_coverage_comparisons':comparisons,'bounds_modes':[1,3],'moved_rotating_fallback_comparisons':3,'exact':True}
(new/'build/raster-parity-v13.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
