#!/usr/bin/env python3
"""Build an isolated, automatic MiSTer/PicoDrive diagnostic; never touch saves.

Reports appear for eight seconds after each three-second measurement. Stage
totals are inclusive and overlap; RESTORE measures submission/master copy,
not all asynchronous slave work. Frozen cases measure renderer capacity, not
gameplay FPS. All code instrumentation/report placement is diagnostic only.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ('baseline', 'fixed100', 'fixed140', 'fixed60', 'serial', 'no-overlap', 'compact', 'compact-sort', 'phases', 'font-bits', 'font-batch')


def batch_glyphs(source):
    source = source.replace('#include "book.hpp"', '#include "book.hpp"\n#include "raster.hpp"')
    source = source.replace('Glyph(Renderer &r,const OriginalFont', 'Glyph(RasterSurface &surface,const OriginalFont')
    source = source.replace('r.Span(y+row,x+first_col,x+col-1,color);',
                            'RasterSpan(surface,y+row,x+first_col,x+col-1,color);')
    source = source.replace('    unsigned total=center || limit>0?', '''    // One fence and damage accumulator cover the complete text range.
    r.FinishRestore();
    RasterSurface surface={r.target,0,GAME_HEIGHT,r.damage[r.buffer_index]};
    unsigned total=center || limit>0?''')
    source = source.replace('Glyph(r,font,', 'Glyph(surface,font,')
    source = source.replace("if(dots) for(unsigned i=0;i<3;++i) x+=Glyph(surface,font,x,y,'.',color);",
        "if(dots) for(unsigned i=0;i<3;++i) x+=Glyph(surface,font,x,y,'.',color);\n    r.damage[r.buffer_index]=surface.damage;")
    source = source.replace('''        for(unsigned j=0;j<length;++j) {
            x+=Glyph(surface,font,x,y,*p++,color);
        }''', '''        r.FinishRestore();
        RasterSurface surface={r.target,0,GAME_HEIGHT,r.damage[r.buffer_index]};
        for(unsigned j=0;j<length;++j) {
            x+=Glyph(surface,font,x,y,*p++,color);
        }
        r.damage[r.buffer_index]=surface.damage;''')
    return source


def register_glyphs(source):
    old = '''        unsigned col=0;
        while(col<width) {
            while(col<width && !(pixels[(bit+col)>>3]&(128>>((bit+col)&7)))) ++col;
            unsigned first_col=col;
            while(col<width && (pixels[(bit+col)>>3]&(128>>((bit+col)&7)))) ++col;
            if(first_col<col) r.Span(y+row,x+first_col,x+col-1,color);
        }'''
    new = '''        // A glyph is at most 15 pixels wide and can begin at any bit.
        // Fetch only the bytes it touches, then scan the row in a register.
        unsigned bits=unsigned(pixels[0])<<24;
        if(bit+width>8) bits|=unsigned(pixels[1])<<16;
        if(bit+width>16) bits|=unsigned(pixels[2])<<8;
        bits<<=bit;
        unsigned col=0;
        while(col<width) {
            while(col<width && !(bits&0x80000000u)) { bits<<=1;++col; }
            unsigned first_col=col;
            while(col<width && (bits&0x80000000u)) { bits<<=1;++col; }
            if(first_col<col) r.Span(y+row,x+first_col,x+col-1,color);
        }'''
    if source.count(old) != 1:
        raise RuntimeError('could not find original glyph scanner')
    return source.replace(old, new)


def compact_commands(source):
    """Ordinary queued projections are clamped to +/-4096 by DrawActor."""
    source = source.replace('Point points[MAX_POLY];',
        'union { uint32_t control[8]; uint32_t packed[MAX_POLY]; };')
    for point in range(4):
        for coordinate, axis in enumerate(('x', 'y')):
            source = source.replace(f'c.points[{point}].{axis}', f'c.control[{point*2+coordinate}]')
    source = source.replace('c.points[i].x=points[i].x;c.points[i].y=points[i].y;',
        'c.packed[i]=(uint32_t(uint16_t(points[i].x))<<16)|uint16_t(points[i].y);')
    source = source.replace('slave_points[i].x=c.points[i].x;slave_points[i].y=c.points[i].y;',
        'uint32_t packed=c.packed[i];\n        slave_points[i].x=int16_t(packed>>16);slave_points[i].y=int16_t(packed);')
    if 'c.points' in source:
        raise RuntimeError('unconverted queue payload')
    return source


def low_overhead(output, variant):
    master = output / 'src/sh2/master.cpp'
    source = master.read_text().replace('extern "C" volatile uint32_t profile_state[],worker_profile_state[];', '''
static unsigned diagnostic_draw_ticks,diagnostic_flip_ticks;
static inline uint16_t Profile_ReadTimer() {
    volatile uint8_t *const frt=(volatile uint8_t *)0xFFFFFE10;
    unsigned high,low,check;
    do { high=frt[2];low=frt[3];check=frt[2]; } while(high!=check);
    return (high<<8)|low;
}''')
    source = source.replace('{ ProfileScope timing(PROFILE_FRAME);game.Draw();game.renderer.FinishRestore(); }',
        '{ uint16_t begin=Profile_ReadTimer();game.Draw();game.renderer.FinishRestore();diagnostic_draw_ticks+=uint16_t(Profile_ReadTimer()-begin); }')
    source = source.replace('{ ProfileScope timing(PROFILE_FLIP);Flip(); }',
        '{ uint16_t begin=Profile_ReadTimer();Flip();diagnostic_flip_ticks+=uint16_t(Profile_ReadTimer()-begin); }')
    source = source.replace('Profile_Reset();for(unsigned i=0;i<6;++i) worker_profile_state[i]=0;',
        'diagnostic_draw_ticks=diagnostic_flip_ticks=0;')
    source = source.replace('debug_state[8+i]=profile_state[1+i*2];', 'debug_state[8+i]=0;')
    source = source.replace('debug_state[19]=worker_profile_state[0];', '''
        unsigned hash=2166136261u;
        for(unsigned i=0;i<320*200/2;++i) hash=(hash^FRAMEBUFFER[256+12*160+i])*16777619u;
        debug_state[8]=hash;
        debug_state[19]=worker_profile_state[0];''')
    source = source.replace('debug_state[19]=worker_profile_state[0];debug_state[20]=worker_profile_state[1];',
        'debug_state[17]=diagnostic_flip_ticks;debug_state[18]=diagnostic_draw_ticks;debug_state[19]=debug_state[20]=0;')
    source = source.replace('debug_state[30]=0;', f'debug_state[30]={VARIANTS.index(variant)+1};')
    source = source.replace('PROFILE V1 - TICKS TOTAL', 'LOW OVERHEAD - '+variant.upper())
    source = source.replace('"UPDATE","RESTORE SUBMIT"', '"PIXEL HASH","RESTORE SUBMIT"')
    source = source.replace('Wait(hz*8)', 'Wait(hz*4)')
    master.write_text(source)
    worker = output / 'src/render/worker.cpp'
    source = worker.read_text()
    if variant.startswith('fixed'):
        source = source.replace('int split=100,votes=0;', f'int split={variant[5:]},votes=0;')
        source = source.replace('if(master+slave<64) return;', '(void)master;(void)slave;return;')
    if variant in ('serial', 'no-overlap'):
        source = source.replace('int end=area.y2+1;', 'int end=area.y2+1;return end;')
    if variant == 'serial':
        source = source.replace('void RendererWorker_Begin(RasterSurface &surface) {',
            'void RendererWorker_Begin(RasterSurface &surface) { RendererWorker_WaitRestore();return;')
        source = source.replace('uint8_t material) {', 'uint8_t material) { return true;')
        source = source.replace('void *context,int split) {', 'void *context,int split) { RendererWorker_WaitRestore();return;')
        source = source.replace('void RendererWorker_Finish(RasterSurface &surface) {',
            'void RendererWorker_Finish(RasterSurface &surface) { return;')
    if variant in ('compact', 'compact-sort'):
        source = compact_commands(source)
    worker.write_text(source)
    if variant == 'compact-sort':
        header = output / 'src/render/render_api.hpp'
        header.write_text(header.read_text().replace('A32X_COLD unsigned SortFaces(', 'unsigned SortFaces('))
    if variant in ('font-bits', 'font-batch'):
        book = output / 'src/render/book.cpp'
        source = register_glyphs(book.read_text())
        if variant == 'font-batch':
            source = batch_glyphs(source)
        book.write_text(source)
    if variant == 'phases':
        source = master.read_text()
        marker = 'static A32X_COLD uint16_t Sequence()'
        helper = '''static unsigned phase_ticks[5],phase_number;
static uint16_t phase_begin;
extern "C" A32X_COLD void DiagnosticPhase(unsigned next) {
    uint16_t now=Profile_ReadTimer();
    if(phase_number) phase_ticks[phase_number-1]+=uint16_t(now-phase_begin);
    phase_number=next;phase_begin=now;
}
'''
        source = source.replace(marker, helper+marker)
        source = source.replace('diagnostic_draw_ticks=diagnostic_flip_ticks=0;',
            'diagnostic_draw_ticks=diagnostic_flip_ticks=0;for(auto &value:phase_ticks) value=0;phase_number=0;')
        source = source.replace('debug_state[8]=hash;',
            'debug_state[8]=hash;for(unsigned i=0;i<5;++i) debug_state[9+i]=phase_ticks[i];')
        source = source.replace('"RESTORE SUBMIT","TRANSFORM","SORT",\n        "PRIMITIVES INCL FILL","FILL"',
            '"DRAW LIST","STATIC PREP","ACTOR DRAW",\n        "CONTACT","EFFECTS"')
        master.write_text(source)
        game = output / 'src/engine/game.cpp'
        source = game.read_text()
        source = 'extern "C" void DiagnosticPhase(unsigned);\n'+source
        source = source.replace('void Game::DrawScene() {', 'void Game::DrawScene() {\n    DiagnosticPhase(1);')
        source = source.replace('int order[MAX_ACTIVE],count=world.DrawList(order);',
            'int order[MAX_ACTIVE],count=world.DrawList(order);DiagnosticPhase(2);')
        source = source.replace('static_slots=next_static_slots;', 'static_slots=next_static_slots;DiagnosticPhase(3);')
        source = source.replace('    // A rotating hatch or door', '    DiagnosticPhase(4);\n    // A rotating hatch or door')
        source = source.replace('    renderer.DrawEffects(world);', '    DiagnosticPhase(5);\n    renderer.DrawEffects(world);')
        source = source.replace('    if(world.dark) DrawLighting(lighting_restore,light,light_center);',
            '    if(world.dark) DrawLighting(lighting_restore,light,light_center);DiagnosticPhase(0);')
        game.write_text(source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mars', type=Path, default=ROOT / '.local/toolchain/mars')
    parser.add_argument('--source', type=Path, default=ROOT,
                        help='Source tree to benchmark, including src/, Makefile and assets/')
    parser.add_argument('--variant', choices=VARIANTS, help='Release renderer with only per-frame timing')
    args = parser.parse_args()
    source_root = args.source.resolve()
    output = ROOT / ('build/mister-experiment/'+args.variant if args.variant else 'build/mister-profile')
    if output.is_symlink():
        raise RuntimeError('diagnostic directory must not be a symlink')
    output.mkdir(parents=True, exist_ok=True)
    if source_root == output.resolve():
        raise RuntimeError('source and diagnostic output must differ')
    shutil.copytree(source_root / 'src', output / 'src', dirs_exist_ok=True)
    shutil.copy2(source_root / 'Makefile', output / 'Makefile')
    (output / 'tools').mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'tools/finalize_rom.py', output / 'tools/finalize_rom.py')
    if not (output / 'assets').exists():
        (output / 'assets').symlink_to(source_root / 'assets', target_is_directory=True)
    shutil.copy2(ROOT / 'tools/mister_profile.cpp', output / 'src/sh2/master.cpp')
    profile = output / 'src/sh2/profile.cpp'
    source = profile.read_text().replace('void Profile_', 'A32X_COLD void Profile_')
    source = source.replace('uint16_t Profile_ReadTimer()', 'A32X_COLD uint16_t Profile_ReadTimer()')
    source = source.replace('#include "../platform/profile.hpp"', '#include "../platform/profile.hpp"\n#include "../engine/types.hpp"')
    source = source.replace('void Profile_Init() {', 'void Profile_Reset() {\n    for(unsigned i=0;i<PROFILE_STAGE_COUNT;++i) elapsed[i]=calls[i]=0;\n}\nA32X_COLD void Profile_Init() {')
    profile.write_text(source)
    header = output / 'src/platform/profile.hpp'
    header.write_text(header.read_text().replace('void Profile_Init();', 'void Profile_Init();\nvoid Profile_Reset();'))
    if args.variant:
        low_overhead(output, args.variant)
    log_path = output / 'build.log'
    with log_path.open('w') as log:
        subprocess.run(['make', '-j2', 'BUILD='+('RELEASE' if args.variant else 'PROFILE'), 'MARSDEV='+str(args.mars.resolve())],
                       cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True)
    report = output / 'layout.json'
    subprocess.run(['python3', str(ROOT / 'tools/check_bank_layout.py'), '--rom',
                    str(output / 'build/AITD32X.32x'), '--elf', str(output / 'build/AITD32X.elf'),
                    '--output', str(report)], check=True, stdout=subprocess.DEVNULL)
    rom = ROOT / ('build/AITD32X-experiment-'+args.variant+'.32x' if args.variant else 'build/AITD32X-mister-profile-v1.32x')
    shutil.copy2(output / 'build/AITD32X.32x', rom)
    print(json.dumps(dict(rom=str(rom), sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),
                          build_log=str(log_path), layout=str(report)), indent=2))


if __name__ == '__main__':
    main()
