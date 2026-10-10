#!/usr/bin/env python3
"""Compare the native SH-2 Q15 helper with signed C division in PicoDrive.

Build an isolated diagnostic cartridge. Check every 32768 boundary and its
adjacent inputs across int32_t, plus 65536 deterministic random inputs.
"""
import argparse,ctypes as C,json,shutil,subprocess
from pathlib import Path
import emulator_check as ec

DIAGNOSTIC=r'''
extern "C" { volatile uint32_t q15_diagnostic[5]; }
static bool CheckQ15Value(uint32_t bits) {
    int32_t input=(int32_t)bits;
    int actual=TruncateQ15(input),expected=input/32768;
    ++q15_diagnostic[1];
    if(actual==expected) return true;
    q15_diagnostic[2]=bits;q15_diagnostic[3]=(uint32_t)actual;
    q15_diagnostic[4]=(uint32_t)expected;q15_diagnostic[0]=2;
    return false;
}
extern "C" void CheckQ15Native(void) {
    for(uint32_t i=0;i<131072;++i) {
        uint32_t boundary=i<<15;
        if(!CheckQ15Value(boundary-1) || !CheckQ15Value(boundary) || !CheckQ15Value(boundary+1)) return;
    }
    uint32_t random=0x6c4b6a38;
    for(unsigned i=0;i<65536;++i) {
        random=random*1664525u+1013904223u;
        if(!CheckQ15Value(random)) return;
    }
    q15_diagnostic[0]=1;
}
'''

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('core',type=Path)
    ap.add_argument('--project',type=Path,default=ec.ROOT)
    ap.add_argument('--marsdev',type=Path,required=True)
    args=ap.parse_args();project=args.project.resolve()
    diagnostic=project/'build/q15-diagnostic'
    shutil.rmtree(diagnostic,ignore_errors=True)
    shutil.copytree(project,diagnostic,ignore=shutil.ignore_patterns('build','__pycache__','*.so'))
    math=diagnostic/'src/engine/math.cpp'
    math.write_text(math.read_text()+DIAGNOSTIC)
    master=diagnostic/'src/sh2/master.cpp'
    source=master.read_text().replace('extern "C" int m_main(void) {',
        'extern "C" void CheckQ15Native(void);\nextern "C" int m_main(void) {\n    CheckQ15Native();')
    master.write_text(source)
    with (project/'build/q15-diagnostic-build.log').open('w') as log:
        subprocess.run(['make','all','BUILD=RELEASE','MARSDEV='+str(args.marsdev.resolve()),'-j2'],
                       cwd=diagnostic,stdout=log,stderr=subprocess.STDOUT,check=True)
    ec.ROOT=diagnostic
    e=ec.Emulator(args.core,'NTSC')
    try:
        e.run(180) # Allow the 68000 bootstrap to activate the 32X.
        address=ec.symbol_address('_q15_diagnostic')&0x3ffff
        memory=C.c_void_p.in_dll(e.lib,'Pico32xMem').value
        words=(C.c_uint16*10).from_address(memory+address)
        def state():return [(words[2*i]<<16)|words[2*i+1] for i in range(5)]
        for _ in range(1200):
            e.run(1)
            if state()[0]:break
        else:raise RuntimeError('native Q15 diagnostic did not complete')
        result=state()
        if result[0]!=1:raise RuntimeError('native Q15 mismatch: '+str(result))
        if result[1]!=458752:raise RuntimeError('native Q15 diagnostic skipped inputs')
        report=dict(native_sh2_q15_comparisons=result[1],boundary_and_adjacent_inputs=393216,
                    deterministic_random_inputs=65536,full_int32_range=True,failures=0)
        (project/'build/native-q15.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report))
    finally:e.close()

if __name__=='__main__':main()
