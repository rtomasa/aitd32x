#!/usr/bin/env python3
"""Check the actual cartridge's movement against original animation data.

Run each region/character in a fresh process. Two seconds of walking from the
original spawn remains unobstructed, making elapsed animation phase and root
position directly comparable even when rendering falls below the logic rate.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from emulator_check import Emulator,ROOT

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('core',type=Path)
    ap.add_argument('--region',choices=['NTSC','PAL'],default='NTSC')
    ap.add_argument('--character',choices=['edward','emily'],default='edward')
    args=ap.parse_args();hz=50 if args.region=='PAL' else 60
    character=int(args.character=='emily')
    manifest=json.loads((ROOT/'assets/manifest.json').read_text())
    asset=next(a for a in manifest['assets'] if a['name']==f'ANIM_{character}_254')
    bank=(ROOT/'assets/bank.bin').read_bytes()
    data=bank[asset['offset']:asset['offset']+asset['packed_size']]
    frames,groups=struct.unpack_from('>2H',data)
    keys=[struct.unpack_from('>H3h',data,4+i*(8+groups*8)) for i in range(frames)]
    cycle_phase=sum(k[0] for k in keys)*25
    e=Emulator(args.core,args.region);e.run(180)
    if character:e.run(6,32);e.run(12)
    e.run(6,128);e.run(hz*2)
    start=e.state();previous=None;total_phase=0;swaps=0;lastbank=e.vdp[5]&1
    for _ in range(hz*2):
        e.run(1,1);state=e.state();nextbank=e.vdp[5]&1
        swaps+=nextbank!=lastbank;lastbank=nextbank
        if state['animation_asset']!=asset['id']:continue
        phase=sum(k[0] for k in keys[:state['animation_frame']])*25+state['animation_phase']
        total_phase+=phase if previous is None else (phase-previous)%cycle_phase
        previous=phase
    end=e.state();walking_ticks=total_phase//60
    if total_phase%60 or abs(walking_ticks-50)>3:raise RuntimeError('animation clock did not advance at 60 Hz during the two-second walk')
    loops,phase=divmod(total_phase,cycle_phase)
    expected=loops*sum(k[3] for k in keys)
    for duration,x,y,z in keys:
        span=duration*25
        if phase>=span:expected+=z;phase-=span
        else:expected+=int(z*phase/span);break
    if end['z']-start['z']!=expected or end['x']!=start['x']:raise RuntimeError('native displacement differs from original animation root motion')
    if end['render_frames']-start['render_frames']!=swaps:raise RuntimeError('FPS frame count differs from framebuffer swaps')
    name=f'movement-v4-{args.region.lower()}-{args.character}'
    e.capture(name+'.png')
    e.run(6,128);e.run(hz);paused=e.state();e.run(hz*2);after=e.state()
    for field in ['x','y','z','beta','animation_frame','animation_phase','animation_asset']:
        if paused[field]!=after[field]:raise RuntimeError('animation or motion advanced while paused')
    if not paused['paused'] or abs(after['tick']-paused['tick']-50)>2:raise RuntimeError('pause or 25 Hz logical clock failed')
    report=dict(region=args.region,character=args.character,seconds=2,walking_ticks=walking_ticks,
                animation_units=total_phase/25,expected_z_delta=expected,actual_z_delta=end['z']-start['z'],
                render_fps=swaps/2,pause_passed=True,start=start,end=end,
                rom_sha256=hashlib.sha256((ROOT/'build/AITD32X.32x').read_bytes()).hexdigest())
    (ROOT/'build'/(name+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    e.close();print(json.dumps(report),flush=True)

if __name__=='__main__':main()
