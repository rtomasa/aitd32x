#!/usr/bin/env python3
"""Profile the actual SH-2 cartridge in three reproducible camera-0 positions.

Use a fresh process per case. PROFILE builds need a core with FRC support;
tools/picodrive-frt.patch supplies the counter-only shim for PicoDrive.
RELEASE builds report FPS and swap counts on the unmodified core.
"""
import argparse,ctypes as C,hashlib,json
from pathlib import Path
import emulator_check as ec
STAGES=['update','restore','transform','sort','primitives','fill','mask','fps_ui','palette','flip','frame']

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('core',type=Path)
    ap.add_argument('--project',type=Path,default=ec.ROOT)
    ap.add_argument('--region',choices=['NTSC','PAL'],default='NTSC')
    ap.add_argument('--character',choices=['edward','emily'],default='edward')
    ap.add_argument('--distance',choices=['far','middle','near'],default='near')
    ap.add_argument('--label',default='profile')
    args=ap.parse_args();ec.ROOT=args.project.resolve()
    e=ec.Emulator(args.core,args.region);refresh=50 if args.region=='PAL' else 60
    try:address=ec.symbol_address('_profile_state')&0x3ffff
    except RuntimeError:address=None
    def profile():
        if address is None:return None
        memory=C.c_void_p.in_dll(e.lib,'Pico32xMem').value
        w=(C.c_uint16*50).from_address(memory+address)
        return [(w[i*2]<<16)|w[i*2+1] for i in range(25)]
    e.run(180)
    if args.character=='emily':e.run(6,32);e.run(12)
    e.run(6,128);e.run(refresh*2)
    if args.distance=='near':e.run(refresh*12,1)
    elif args.distance=='far':
        for _ in range(refresh*25):
            if e.state()['z']>=500:break
            e.run(1,2)
        else:raise RuntimeError('far position was not reached')
    e.run(refresh*2)
    start=e.state();before=profile();last=before;timer_elapsed=0
    bank=e.vdp[5]&1;swaps=0
    for _ in range(refresh*5):
        e.run(1)
        next_bank=e.vdp[5]&1;swaps+=next_bank!=bank;bank=next_bank
        current=profile()
        if current and current[0]!=last[0]:
            if current[0]-last[0]!=1:raise RuntimeError('missed a completed profile frame')
            timer_elapsed+=(current[23]-last[23])&0xffff;last=current
    end=e.state();after=profile();frames=end['render_frames']-start['render_frames']
    ticks=end['tick']-start['tick']
    if abs(ticks-125)>3:raise RuntimeError('25 Hz simulation fell behind')
    if not -2<=swaps-frames<=7:raise RuntimeError('FPS count disagrees with physical swaps: '+str((frames,swaps,start,end)))
    # FPS sampling can request a redraw without a new game tick. Such swaps
    # are deliberately excluded from rendered_total (master.cpp game_frame).
    overlay_swaps=max(0,swaps-frames)
    if end['camera']!=0:raise RuntimeError('benchmark left camera 0')
    report=dict(label=args.label,region=args.region,character=args.character,distance=args.distance,
                seconds=5,game_frames=frames,observed_swaps=swaps,overlay_only_swaps=overlay_swaps,render_fps=frames/5,
                simulation_ticks=ticks,counter_fps=end['fps_tenths']/10,start=start,end=end,
                rom_sha256=hashlib.sha256((ec.ROOT/'build/AITD32X.32x').read_bytes()).hexdigest())
    if after:
        n=after[0]-before[0]
        # PicoDrive defaults to 2.4x 68K to approximate bus latencies (pico.h),
        # quantized to a 10-bit fixed-point multiplier. This is an emulator
        # timing model; physical 32X SH-2 clocks are not used to convert it.
        cpu_hz=(53203424 if args.region=='PAL' else 53693175)*(int(2.4*1024)/1024)/7
        report['profile_frames']=n;report['timer_clock_hz']=cpu_hz/128
        seq_frames=((after[24]-before[24])&0xffff)/2
        report['timer_calibration_ratio']=(timer_elapsed*128/cpu_hz)/(seq_frames/refresh)
        if not 0.98<report['timer_calibration_ratio']<1.02:
            raise RuntimeError('FRC timer does not agree with VBlank time: '+str(report['timer_calibration_ratio']))
        timings={}
        for i,stage in enumerate(STAGES):
            delta=(after[1+i*2]-before[1+i*2])&0xffffffff
            timings[stage]=dict(timer_ticks=delta,calls=after[2+i*2]-before[2+i*2],ms_per_frame=delta*128000/cpu_hz/n)
        timings['clip_project_dispatch']=dict(ms_per_frame=timings['primitives']['ms_per_frame']-timings['fill']['ms_per_frame'])
        report['timings']=timings
    name='-'.join([args.label,args.region.lower(),args.character,args.distance])
    (ec.ROOT/'build'/(name+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    e.capture(name+'.png');e.close()
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
