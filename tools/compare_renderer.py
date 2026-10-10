#!/usr/bin/env python3
"""Compare optimized raster output with a reference host build using real assets.

Both builds must use the corrected one-pixel type-2 point. This checks that
edge stepping, shared projection and bulk masks preserve the previous pixels.
"""
import argparse,ctypes as C,json
from pathlib import Path
from emulator_check import ROOT,png

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('reference',type=Path);ap.add_argument('optimized',type=Path)
    args=ap.parse_args();libs=[C.CDLL(str(p.resolve())) for p in [args.reference,args.optimized]]
    bank=C.create_string_buffer((ROOT/'assets/bank.bin').read_bytes())
    for lib in libs:
        lib.host_pixels.restype=C.c_void_p;lib.host_palette.restype=C.c_void_p
        lib.host_init(bank,len(bank)-1)
    comparisons=0
    def compare():
        nonlocal comparisons
        pixels=[C.string_at(lib.host_pixels(),320*224) for lib in libs]
        if pixels[0]!=pixels[1]:
            changed=sum(a!=b for a,b in zip(*pixels))
            raise RuntimeError(f'{changed} changed pixels at comparison {comparisons}')
        if C.string_at(libs[0].host_palette(),512)!=C.string_at(libs[1].host_palette(),512):
            raise RuntimeError('palette changed')
        comparisons+=1
    for pad,ticks in [(128,1),(0,10),(8,13),(17,250),(8,13),(17,140),(8,13),(17,300),(32,1),(0,10),(4,25),(1,100)]:
        for _ in range(ticks):
            for lib in libs:lib.host_tick(pad)
            compare()
    # Reinitialize so diagnostic placement uses camera 0, including clipping
    # outside the normal walkable area and both sides of camera near z=51.
    for character in range(2):
        for lib in libs:
            lib.host_init(bank,len(bank)-1)
            if character:lib.host_tick(32)
            lib.host_tick(128)
        for x,z in [(3231,500),(3231,-1548),(3231,-3734),(4500,500),(4500,-1548),(4500,-3500),(5000,-4000),(4500,-6000),(6000,-5000)]:
            for beta in [0,140,260,520,780]:
                for lib in libs:lib.host_pose(x,z,beta)
                compare()
                if x==4500 and z==-3500 and beta==0:
                    lib=libs[1];p=C.string_at(lib.host_pixels(),320*224)
                    pal=(C.c_uint16*256).from_address(lib.host_palette())
                    rgb=b''.join(bytes(((pal[i]&31)*255//31,((pal[i]>>5)&31)*255//31,((pal[i]>>10)&31)*255//31)) for i in p)
                    png(ROOT/'build'/('eye-close-'+['edward','emily'][character]+'.png'),rgb,320,224)
    report=dict(exact_pixel_comparisons=comparisons,characters=['edward','emily'],camera_route=True,near_plane_cases=True,reference_eyes='corrected type-2 one pixel')
    (ROOT/'build/renderer-comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
