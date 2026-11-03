#!/usr/bin/env python3
"""Build/measure six frozen moving-contact poses; never open battery files.

The explicit movable flag retains a dynamic prop without advancing simulation.
Both source versions use the same poses, flags and low-overhead timing entry.
Diagnostic-only pair counters do not enter the playable cartridge.
"""
import argparse
import ctypes as C
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import build_mister_profile as profile
import check_mister_profile as reader
import emulator_check as ec

ROOT=Path(__file__).resolve().parents[1]
NAMES=reader.CONTACT_NAMES
SETUP=r'''static A32X_COLD void Setup(unsigned which) {
    unsigned scene=which%3,character=which/3;
    game.Init(false);game.character=character;game.StartGameplay();
    World &w=game.world;int f=scene==2?0:1,r=scene==1?3:scene==2?0:1,c=scene==1?12:3;
    w.Init(game.player,character,f,r);
    Vec3 pos=scene==1?Vec3{1100,0,1200}:scene==2?Vec3{-4000,0,1200}:Vec3{-710,0,-1040};
    int slot=w.Slot(1);
    if(slot>=0) w.Stage(slot,f,r,pos);
    else { w.Set(1,O_FLOOR,f);w.Set(1,O_ROOM,r);w.Set(1,O_X,pos.x);w.Set(1,O_Y,pos.y);w.Set(1,O_Z,pos.z); }
    w.floor=f;w.room=r;w.camera=c;w.RefreshActors();game.player.beta=scene==1?512:0;
    int prop=scene==2?0:29;
    if(scene==2) w.Stage(w.Slot(prop),0,0,{-3900,0,300});
    w.Set(prop,O_BETA,scene==2?800:scene==1?160:96);
    w.SetBounds(w.Slot(prop),3);w.Set(prop,O_FLAGS,w.Get(prop,O_FLAGS)|F_MOVABLE);
    w.message=w.prompt=w.book=-1;w.view_changed=true;game.camera=c;
    game.ResetCache();Audio_Reset();game.dirty=true;Draw();
}
'''


def build(source,output,mars):
    if output.is_symlink() or output.resolve()==source.resolve():
        raise RuntimeError('unsafe diagnostic output directory')
    output.mkdir(parents=True,exist_ok=True)
    shutil.copytree(source/'src',output/'src',dirs_exist_ok=True)
    shutil.copy2(source/'Makefile',output/'Makefile')
    (output/'tools').mkdir(exist_ok=True)
    shutil.copy2(ROOT/'tools/finalize_rom.py',output/'tools/finalize_rom.py')
    assets=output/'assets'
    if not assets.exists():assets.symlink_to(source/'assets',target_is_directory=True)
    if assets.resolve()!=(source/'assets').resolve():raise RuntimeError('diagnostic asset source changed')
    shutil.copy2(ROOT/'tools/mister_profile.cpp',output/'src/sh2/master.cpp')
    profile.low_overhead(output,'baseline')
    master=output/'src/sh2/master.cpp';s=master.read_text()
    begin=s.index('static A32X_COLD void Setup(')
    end=s.index('extern "C" A32X_COLD int m_main',begin)
    s=s[:begin]+SETUP+s[end:]
    begin=s.index('static A32X_COLD const char *Name(')
    end=s.index('static A32X_COLD void Report()',begin)
    names=','.join(json.dumps(name) for name in NAMES)
    s=s[:begin]+'static A32X_COLD const char *Name(unsigned which) { static const char *const names[]={'+names+'};return names[which]; }\n'+s[end:]
    s=s.replace('if(which==0) {','if(false) {')
    s=s.replace('diagnostic_draw_ticks=diagnostic_flip_ticks=0;',
                'diagnostic_draw_ticks=diagnostic_flip_ticks=0;debug_state[29]=0;')
    s=s.replace('debug_state[6]=updates;','debug_state[6]=debug_state[29];')
    s=s.replace('debug_state[30]=1;','debug_state[30]=64;')
    s=s.replace('WORLD UPDATES','PLANNED DRAWS').replace('LOW OVERHEAD - BASELINE','CONTACT PAIR - FROZEN')
    master.write_text(s)
    pair=output/'src/render/contact_pair.cpp'
    if pair.exists():
        s=pair.read_text()
        marker='PAIR_STAT(1);return true;'
        if s.count(marker)!=1:raise RuntimeError('pair counter insertion point changed')
        pair.write_text('extern "C" volatile unsigned debug_state[32];\n'+s.replace(marker,'++debug_state[29];'+marker))
    with (output/'build.log').open('w') as log:
        subprocess.run(['make','-j2','BUILD=RELEASE','MARSDEV='+str(mars)],cwd=output,
                       stdout=log,stderr=subprocess.STDOUT,check=True)
    subprocess.run(['python3',str(ROOT/'tools/check_bank_layout.py'),'--rom',
                    str(output/'build/AITD32X.32x'),'--elf',str(output/'build/AITD32X.elf'),
                    '--output',str(output/'layout.json')],check=True,stdout=subprocess.DEVNULL)


def measure(core,output,region):
    original=ec.ROOT;ec.ROOT=output
    emulator=ec.Emulator(core,region);address=ec.symbol_address('_debug_state')&0x3ffff
    hz=50 if region=='PAL' else 60;rows={}
    try:
        for _ in range(hz*70):
            emulator.run(1);memory=C.c_void_p.in_dll(emulator.lib,'Pico32xMem').value
            if not memory:continue
            words=(C.c_uint16*64).from_address(memory+address)
            values=[(words[2*i]<<16)|words[2*i+1] for i in range(32)]
            if reader.valid(values) and values[1] not in rows:
                row=reader.result(values);row['name']=NAMES[row['case']]
                row.pop('updates')
                expected=(53203424 if hz==50 else 53693175)*(int(2.4*1024)/1024)/7/128
                ratio=row['frc_ticks']/(row['vblanks']/hz)/expected
                assert 0.97<ratio<1.03,('use a calibrated FRC-enabled core',ratio)
                row['timer_calibration_ratio']=ratio;rows[row['case']]=row
                if len(rows)==6:break
        assert len(rows)==6,('diagnostic did not finish',sorted(rows))
        report=dict(platform='PicoDrive '+region,emulator_only=True,private_memory_only=True,
                    rom_sha256=hashlib.sha256((output/'build/AITD32X.32x').read_bytes()).hexdigest(),
                    core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),cases=list(rows.values()))
        (output/('picodrive-'+region+'.json')).write_text(json.dumps(report,indent=2)+'\n')
        for row in rows.values():
            print(json.dumps(dict(name=row['name'],draw_ms=row['stage_ms_per_draw']['draw_inclusive'],
                  fps=row['fps'],pixel_hash=row['pixel_hash'],planned_draws=row['planned_draws'],draws=row['draws'])),flush=True)
    finally:
        emulator.close();ec.ROOT=original


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT)
    parser.add_argument('--label',required=True)
    parser.add_argument('--mars',type=Path,default=ROOT/'.local/toolchain/mars')
    parser.add_argument('--core',type=Path,help='Optional calibrated FRC-enabled PicoDrive core')
    parser.add_argument('--region',choices=('NTSC','PAL'),default='NTSC')
    args=parser.parse_args()
    if not re.fullmatch('[a-z0-9-]+',args.label):parser.error('use a simple lowercase label')
    output=ROOT/'build/contact-pair-profile'/args.label
    build(args.source.resolve(),output,args.mars.resolve())
    print('Diagnostic ROM: '+str(output/'build/AITD32X.32x'),flush=True)
    if args.core:measure(args.core.resolve(),output,args.region)


if __name__=='__main__':main()
