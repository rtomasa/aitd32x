#!/usr/bin/env python3
"""Check scheduled projection against native signed division and time old/new helpers.

The isolated cartridge checks defined projection inputs against native C
division, then compares the preceding serial DIVU helper with the scheduled
helper using the 68000 VBlank clock. Assets are linked read-only; no battery
save files are accessed. Emulator timing does not establish hardware results.
"""
import argparse
import ctypes as C
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import emulator_check as ec


DIAGNOSTIC = r'''
#include "../render/project.hpp"
#include <initializer_list>
#include "../render/divide.hpp"
static __attribute__((noinline)) Point OldProject(const Vec3 &v,int fx,int fy,Point c,bool clamp) {
    Point p={c.x+RenderDivide(v.x*fx,v.z),c.y+RenderDivide(v.y*fy,v.z)};
    if(clamp) { p.x=Clamp(p.x,-4096,4096);p.y=Clamp(p.y,-4096,4096); }
    return p;
}
static A32X_COLD __attribute__((noinline)) Point ReferenceProject(const Vec3 &v,int fx,int fy,Point c,bool clamp) {
    Point p={c.x+v.x*fx/v.z,c.y+v.y*fy/v.z};
    if(clamp) { p.x=Clamp(p.x,-4096,4096);p.y=Clamp(p.y,-4096,4096); }
    return p;
}
static A32X_COLD bool CheckProject(const Vec3 &v,int fx,int fy,Point c,bool clamp) {
    Point p=RenderProject(v,fx,fy,c,clamp),q=ReferenceProject(v,fx,fy,c,clamp);
    ++debug_state[1];
    if(p.x==q.x && p.y==q.y) return true;
    debug_state[3]=v.x;debug_state[4]=v.y;debug_state[5]=v.z;
    debug_state[6]=p.x;debug_state[7]=p.y;debug_state[8]=q.x;debug_state[9]=q.y;
    debug_state[0]=3;return false;
}
static A32X_COLD uint16_t Timer() { return COMM(6); }
static A32X_COLD void CheckProjectNative() {
    debug_state[0]=1;
    const int coords[]={-32768,-4096,-1,0,1,4096,32767};
    for(int x:coords) for(int y:coords) for(int z:{51,101,32767,100000})
        for(int fx:{-400,0,400}) for(bool clamp:{false,true})
            if(!CheckProject({x,y,z},fx,391,{160,100},clamp)) return;
    uint32_t seed=0x6c4b6a38;
    for(unsigned i=0;i<8192;++i) {
        auto random=[&]() { seed=seed*1664525u+1013904223u;return seed; };
        Vec3 v={int(random()%200001)-100000,int(random()%200001)-100000,51+int(random()%200000)};
        int fx=int(random()%1001)-500,fy=int(random()%1001)-500;
        Point c={int(random()%321)-160,int(random()%201)-100};
        if(!CheckProject(v,fx,fy,c,i&1)) return;
    }
    for(bool clamp:{false,true}) {
        uint32_t old=0,fresh=0;Point result;
        uint16_t begin=Timer();
        for(unsigned pass=0;pass<64;++pass) {
            for(int i=0;i<4096;++i) { result=OldProject({i*19-1000,i*31-2000,101+i*23},400,391,{160,100},clamp);debug_state[12]=result.x+result.y; }
        }
        old=uint16_t(Timer()-begin);begin=Timer();
        for(unsigned pass=0;pass<64;++pass) {
            for(int i=0;i<4096;++i) { result=RenderProject({i*19-1000,i*31-2000,101+i*23},400,391,{160,100},clamp);debug_state[12]=result.x+result.y; }
        }
        fresh=uint16_t(Timer()-begin);
        debug_state[clamp?16:14]=old;debug_state[clamp?17:15]=fresh;
    }
    debug_state[0]=2;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('core', type=Path)
    parser.add_argument('--mars', '--marsdev', dest='mars', type=Path, required=True)
    parser.add_argument('--project', type=Path, default=ec.ROOT)
    parser.add_argument('--region', choices=['NTSC', 'PAL'], default='NTSC')
    args = parser.parse_args()
    project = args.project.resolve()
    diagnostic = project / 'build/projection-diagnostic'
    # Never follow an unexpected symlink when deleting the old isolated build.
    if diagnostic.is_symlink():
        raise RuntimeError('diagnostic directory must not be a symlink')
    if diagnostic.exists():
        shutil.rmtree(diagnostic)
    diagnostic.mkdir(parents=True)
    shutil.copytree(project / 'src', diagnostic / 'src')
    shutil.copy2(project / 'Makefile', diagnostic / 'Makefile')
    (diagnostic / 'tools').mkdir()
    shutil.copy2(project / 'tools/finalize_rom.py', diagnostic / 'tools/finalize_rom.py')
    (diagnostic / 'assets').symlink_to(project / 'assets', target_is_directory=True)
    master = diagnostic / 'src/sh2/master.cpp'
    source = master.read_text()
    marker = 'extern "C" int m_main(void) {'
    if source.count(marker) != 1:
        raise RuntimeError('could not locate diagnostic entry point')
    opening=source.index(marker)+len(marker)-1
    level=1;closing=opening+1
    while level:
        level+=(source[closing]=='{')-(source[closing]=='}');closing+=1
    source=source[:opening+1]+'\n    CheckProjectNative();for(;;) { asm volatile("nop"); }\n'+source[closing-1:]
    source=source.replace(marker, DIAGNOSTIC+'\n'+marker)
    master.write_text(source)
    log_path = project / 'build/projection-diagnostic-build.log'
    with log_path.open('w') as log:
        command = ['make', '-j2', 'all', 'BUILD=RELEASE', 'MARSDEV=' + str(args.mars.resolve())]
        build = subprocess.run(command, cwd=diagnostic, stdout=log, stderr=subprocess.STDOUT)
    if build.returncode:
        raise RuntimeError('diagnostic build failed; see ' + str(log_path))

    ec.ROOT = diagnostic
    emulator = ec.Emulator(args.core, args.region)
    try:
        emulator.run(180) # The 68000 bootstrap allocates/activates the 32X.
        memory = C.c_void_p.in_dll(emulator.lib, 'Pico32xMem').value
        address = ec.symbol_address('_debug_state') & 0x3ffff
        words = (C.c_uint16 * 36).from_address(memory + address)

        def state():
            return [(words[2*i] << 16) | words[2*i+1] for i in range(18)]

        result = state()
        for frames in range(1200):
            emulator.run(1)
            result = state()
            if result[0] in (2, 3):
                break
        report = dict(region=args.region,comparisons=result[1],status=result[0],
                      expected_comparisons=7*7*4*3*2+8192,hardware_validation=False,
                      benchmark_points_per_mode=262144,timer="68000 VBlank sequence (two units/frame)",
                      unclamped_vblanks=dict(before=result[14]/2,after=result[15]/2),
                      clamped_vblanks=dict(before=result[16]/2,after=result[17]/2),
                      source_sha256=hashlib.sha256((project/'src/render/project.cpp').read_bytes()).hexdigest())
        if result[0]==3:report['mismatch']=result[3:10]
        output = project / ('build/projection-native-' + args.region.lower() + '.json')
        output.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        if result[0] != 2 or result[1] != report['expected_comparisons']:
            raise RuntimeError('native projection failed; see ' + str(output))
    finally:
        emulator.close()


if __name__ == '__main__':
    main()
