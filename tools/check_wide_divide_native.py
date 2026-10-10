#!/usr/bin/env python3
"""Compare signed 64/32 DIVU rendering arithmetic with native libgcc in PicoDrive.

Only src/, Makefile and the ROM finalizer are copied to an isolated diagnostic
under build/. Assets are linked read-only; user battery saves are never loaded.
The diagnostic runs before game initialization and reuses debug_state.
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
#include "../render/divide.hpp"
// Keep diagnostic vectors and code outside the production SDRAM budget.
static const int64_t wide_numerators[] __attribute__((section(".romcode.testdata")))={
    INT64_MIN,INT64_MIN+1,-(INT64_C(1)<<60),-(INT64_C(1)<<40),
    -INT64_C(4294967297),-INT64_C(4294967296),-INT64_C(2147483649),
    INT32_MIN,-INT64_C(2147483647),-1,0,1,INT32_MAX,INT64_C(2147483648),
    INT64_C(2147483649),INT64_C(4294967295),INT64_C(4294967296),
    INT64_C(4294967297),(INT64_C(1)<<40),(INT64_C(1)<<60),INT64_MAX
};
static const int32_t wide_denominators[] __attribute__((section(".romcode.testdata")))={
    INT32_MIN,-INT32_MAX,-65537,-65536,-257,-256,-3,-2,-1,
    1,2,3,51,255,256,257,4095,4096,65535,65536,65537,1000003,134217728,INT32_MAX
};
static const int64_t wide_quotients[] __attribute__((section(".romcode.testdata")))={
    -INT64_C(2147483649),INT32_MIN,-INT64_C(2147483647),-1,0,1,
    INT64_C(2147483646),INT32_MAX,INT64_C(2147483648)
};
static A32X_COLD __attribute__((noinline)) int64_t ReferenceWideDivide(int64_t n,int32_t d) {
    return n/d;
}
static A32X_COLD bool CheckWideValue(int64_t n,int32_t d) {
    // The sole signed 64-bit division overflow is undefined in C.
    if(n==INT64_MIN && d==-1) return true;
    int32_t actual=RenderDivideWide(n,d);
    int64_t reference=ReferenceWideDivide(n,d);
    int32_t expected=(int32_t)reference;
    ++debug_state[1];
    ++debug_state[reference<INT32_MIN || reference>INT32_MAX?8:9];
    if(actual==expected) return true;
    debug_state[3]=(int32_t)((uint64_t)n>>32);debug_state[4]=(int32_t)n;
    debug_state[5]=d;debug_state[6]=actual;debug_state[7]=expected;
    debug_state[0]=3;return false;
}
static A32X_COLD uint32_t WideRandom(uint32_t &state) {
    state=state*1664525u+1013904223u;return state;
}
static A32X_COLD void CheckWideNative() {
    debug_state[0]=1;debug_state[2]=1;
    for(int64_t n:wide_numerators) for(int32_t d:wide_denominators)
        if(!CheckWideValue(n,d)) return;
    debug_state[2]=2;
    for(int64_t q:wide_quotients) for(int32_t d:wide_denominators) {
        int64_t magnitude=d<0?-(int64_t)d:d;
        int64_t adjacent[]={-magnitude+1,-1,0,1,magnitude-1};
        for(int64_t delta:adjacent) if(!CheckWideValue(q*d+delta,d)) return;
    }
    debug_state[2]=3;uint32_t random=0x6c4b6a38;
    for(unsigned i=0;i<4096;++i) {
        uint64_t hi=WideRandom(random),lo=WideRandom(random);
        int64_t n=(int64_t)((hi<<32)|lo);
        int32_t d=(int32_t)WideRandom(random);if(!d) d=1;
        if(!CheckWideValue(n,d)) return;
    }
    debug_state[2]=4;
    for(unsigned i=0;i<8192;++i) {
        // Depth gradients use reciprocal z up to floor(2^20/51), screen
        // differences up to 8192, a factor of 256 and positive triangle area.
        int a=(int)(WideRandom(random)%41121)-20560;
        int b=(int)(WideRandom(random)%16385)-8192;
        int c=(int)(WideRandom(random)%41121)-20560;
        int d=(int)(WideRandom(random)%16385)-8192;
        int32_t area=1+(int32_t)(WideRandom(random)%134217728);
        if(!(i&7)) area=1+(area&255); // Stress thin triangles and overflow.
        if(!CheckWideValue(((int64_t)a*b-(int64_t)c*d)*256,area)) return;
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
    diagnostic = project / 'build/wide-divide-diagnostic'
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
    source = source.replace(marker, DIAGNOSTIC + '\n' + marker + '\n'
                            '    CheckWideNative();for(;;) { asm volatile("nop"); }\n')
    master.write_text(source)
    log_path = project / 'build/wide-divide-diagnostic-build.log'
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
        words = (C.c_uint16 * 20).from_address(memory + address)

        def state():
            return [(words[2*i] << 16) | words[2*i+1] for i in range(10)]

        result = state()
        for frames in range(1200):
            emulator.run(1)
            result = state()
            if result[0] in (2, 3):
                break
        report = dict(
            region=args.region, comparisons=result[1], status=result[0], category=result[2],
            signed32_overflow_cases=result[8], signed32_in_range_cases=result[9],
            expected_comparisons=21*24-1 + 9*24*5 + 4096 + 8192,
            emulator_frames=180+frames+1,
            diagnostic_rom_sha256=hashlib.sha256((diagnostic / 'build/AITD32X.32x').read_bytes()).hexdigest(),
            divide_header_sha256=hashlib.sha256((diagnostic / 'src/render/divide.hpp').read_bytes()).hexdigest(),
            native_reference='libgcc signed int64 division narrowed to int32',
            hardware_validation=False,
        )
        if result[0] == 3:
            report['mismatch'] = dict(
                numerator=C.c_int64((result[3] << 32) | result[4]).value,
                denominator=C.c_int32(result[5]).value,
                actual=C.c_int32(result[6]).value, expected=C.c_int32(result[7]).value,
            )
        output = project / ('build/wide-divide-native-' + args.region.lower() + '.json')
        output.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        if result[0] != 2 or result[1] != report['expected_comparisons']:
            raise RuntimeError('native wide division failed; see ' + str(output))
        if not result[8] or not result[9]:
            raise RuntimeError('native wide division missed a result range')
    finally:
        emulator.close()


if __name__ == '__main__':
    main()
