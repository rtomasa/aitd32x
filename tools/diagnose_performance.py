#!/usr/bin/env python3
"""Measure a five-second walking interval in the actual 32X cartridge.

Run each character/region in a fresh process; some PicoDrive cores retain state
across retro_deinit/retro_init. Uses emulated time, not host execution speed.
"""
import argparse,hashlib,json
from pathlib import Path
from emulator_check import Emulator,ROOT

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('core',type=Path)
    ap.add_argument('--region',choices=['PAL','NTSC'],default='NTSC')
    ap.add_argument('--character',choices=['edward','emily'],default='edward')
    args=ap.parse_args();e=Emulator(args.core,args.region)
    refresh=50 if args.region=='PAL' else 60
    e.run(180)
    if args.character=='emily':e.run(6,32);e.run(12)
    e.run(6,128);e.run(60)
    start=e.state();previous=e.vdp[5]&1;swaps=0
    for _ in range(refresh*5):
        e.run(1,1)
        bank=e.vdp[5]&1;swaps+=bank!=previous;previous=bank
    end=e.state();frames=end['render_frames']-start['render_frames']
    ticks=end['tick']-start['tick']
    if abs(ticks-125)>3:raise RuntimeError('logical clock fell behind during walking')
    if abs(frames-swaps)>2:raise RuntimeError('game frame count differs from observed framebuffer swaps')
    name='performance-'+args.region.lower()+'-'+args.character
    report=dict(region=args.region,character=args.character,seconds=5,
                game_frames=frames,observed_swaps=swaps,render_fps=frames/5,
                simulation_ticks=ticks,simulation_hz=ticks/5,
                counter_fps=end['fps_tenths']/10,start=start,end=end,
                rom_sha256=hashlib.sha256((ROOT/'build/AITD32X.32x').read_bytes()).hexdigest())
    (ROOT/'build'/(name+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    e.capture(name+'.png');e.close()
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
