#!/usr/bin/env python3
"""Compare planned contacts with preserved drawing, using private host memory."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCENE=slice(12*320,212*320)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'build/contact-pair.json')
    args=parser.parse_args()
    current,reference=[C.CDLL(str(p.resolve())) for p in (ROOT/'build/libaitd32x.so',args.reference)]
    bank=C.create_string_buffer((ROOT/'assets/bank.bin').read_bytes())
    for lib in (current,reference):
        lib.host_init.argtypes=[C.c_void_p,C.c_uint]
        lib.host_pixels.restype=lib.host_background.restype=C.c_void_p
    def pixels(lib):return C.string_at(lib.host_pixels(),320*224)[SCENE]
    def initialize(lib,character,room,camera,pose):
        lib.host_init(bank,len(bank)-1);lib.host_begin_world(character,1,room,camera)
        lib.host_place(1,1,room,*pose)
        for _ in range(5):lib.host_world_tick(0,0)
        lib.host_clear_message();lib.host_camera(1,room,camera)
    rows=[]
    for character in (0,1):
        for direction,room,camera,pose in (
                ('enter',1,3,(-710,0,-700,0)),('exit',3,12,(1100,0,1700,512))):
            for lib in (current,reference):initialize(lib,character,room,camera,pose)
            before=current.renderer_pair_stats(1)
            for tick in range(225):
                for lib in (current,reference):lib.host_buffer(tick&1);lib.host_tick(1)
                assert pixels(current)==pixels(reference),(direction,character,tick,'pixels')
                assert not current.host_world(3) and not reference.host_world(3)
                assert [current.host_object(1,f) for f in (8,9,10)]==[reference.host_object(1,f) for f in (8,9,10)]
            hits=current.renderer_pair_stats(1)-before
            assert hits>0,('pair not exercised',direction,character)
            rows.append(dict(character=character,direction=direction,comparisons=225,planned_draws=hits))
    direct=0
    for character in (0,1):
        initialize(current,character,1,3,(-710,0,-1040,0))
        current.host_set_object(29,12,96);current.host_bounds(29,3)
        for order in ((29,1),(1,29)):
            for bank_index in (0,1):
                current.host_buffer(bank_index)
                assert current.host_pair_scene(*order,0,0)
                expected=pixels(current)
                assert current.host_pair_scene(*order,1,0),('pair unexpectedly rejected',character,order)
                assert pixels(current)==expected,('isolated pair',character,order,bank_index)
                assert not current.host_pair_scene(*order,1,1), 'intervening geometry guard ignored'
                assert pixels(current)==C.string_at(current.host_background(),64000), 'failed preparation wrote pixels'
                direct+=1
        # Move only the character through the camera near plane. Failed
        # compact preparation must leave a clean background for ordinary draw.
        vertices=(C.c_int32*(384*3))()
        def minimum(position):
            current.host_place(1,1,1,*position,0)
            count=current.host_camera_vertices(1,vertices)
            return min(vertices[3*i+2] for i in range(count))
        position=[-710,0,-1040];z=minimum(position);slopes=[]
        for axis in (0,2):
            probe=position.copy();probe[axis]+=1000
            slopes.append((minimum(probe)-z,axis))
        slope,axis=max(slopes,key=lambda item:abs(item[0]))
        position[axis]-=round((z-50)*1000/slope)
        assert minimum(position)<=100
        before=current.renderer_pair_stats(2)
        assert not current.host_pair_scene(29,1,1,0)
        assert current.renderer_pair_stats(2)>before
        assert pixels(current)==C.string_at(current.host_background(),64000)
    report=dict(passed=True,private_memory_only=True,route_comparisons=900,
                isolated_pair_comparisons=direct,near_fallbacks=2,guard_fallbacks=direct,
                routes=rows,host_sha256=hashlib.sha256((ROOT/'build/libaitd32x.so').read_bytes()).hexdigest())
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
