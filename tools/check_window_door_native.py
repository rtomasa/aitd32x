#!/usr/bin/env python3
"""Check reported window/door scenes on the ROM using private SRAM fixtures.

Every scene uses a fresh PicoDrive process. Native pixels in both physical
framebuffers must match the same reloaded host scene. Independent near-face
visibility is checked by check_door_projection.py; this check covers the
linked SH2 renderer, banked camera originals and serialized poses. It neither
reads nor writes battery-save files and does not establish hardware behavior.
While the loaded game is paused, the check replaces World::Update's entry in
private emulator SDRAM with rts/nop and flushes PicoDrive's translated code.
This freezes simulation without the timer-write race at PAL render boundaries;
the renderer and ROM file remain unchanged. No performance is measured here.
"""
import argparse
import ctypes as C
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import emulator_check as ec
from check_full_game_native import FIELDS, Native, load_fixture

ROOT = Path(__file__).resolve().parents[1]


def native_layout(mars):
    # Compile once per region, in private paths: parallel regional checks and
    # their subprocesses must not race on the usual shared layout .s file.
    with tempfile.TemporaryDirectory(prefix='window-door-layout-', dir=ROOT / 'build') as temporary:
        source = Path(temporary) / 'layout.cpp'
        assembly = source.with_suffix('.s')
        source.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned layout[]={' +
                          ','.join(FIELDS.values()) + '};\n')
        subprocess.run([str(mars / 'sh-elf/bin/sh-elf-g++'), '-m2', '-mb', '-std=c++17',
                        '-Wno-invalid-offsetof', '-I' + str(ROOT), '-S', str(source),
                        '-o', str(assembly)], check=True, stdout=subprocess.DEVNULL)
        values = re.findall(r'\.long\s+([-0-9xa-fA-F]+)',
                            assembly.read_text().split('_layout:', 1)[1].split('.ident', 1)[0])
        assert len(values) == len(FIELDS)
        return dict(zip(FIELDS, (int(value, 0) for value in values)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('core', type=Path)
    parser.add_argument('--mars', type=Path, default=ROOT / '.local/toolchain/mars')
    parser.add_argument('--region', choices=('NTSC', 'PAL'), default='NTSC')
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.child:
        meta = json.loads(sys.stdin.buffer.readline())
        offsets = meta.pop('layout')
        sram = sys.stdin.buffer.read(131072)
        expected = sys.stdin.buffer.read()
        assert len(sram) == 131072 and len(expected) == 64000
        check = Native(args.core, args.region, offsets)
        try:
            load_fixture(check, sram)
            # Timer-phase resets cannot cancel an update already chosen in
            # SH2 registers. Freeze only this private simulation function,
            # before presentation input resumes the loaded world.
            update = ec.symbol_address('__ZN5World6UpdateEtb')
            assert 0x06000000 <= update < 0x0603C000, 'Update is outside private SDRAM'
            instructions = (C.c_uint16 * 2).from_address(check.memory + (update & 0x3FFFF))
            instructions[0], instructions[1] = 0x000B, 0x0009  # SH2 rts / nop
            check.e.lib.sh2_drc_flush_all.argtypes = []
            check.e.lib.sh2_drc_flush_all.restype = None
            check.e.lib.sh2_drc_flush_all()
            check.resume_frozen()
            ticks = check.state()['world_ticks']
            shown, previous, swaps = {}, check.e.vdp[5] & 1, 0
            for _ in range(check.hz * 12):
                check.frozen_frame()
                check.healthy()
                assert check.state()['world_ticks'] == ticks, 'fixture advanced simulation'
                physical_bank = check.e.vdp[5] & 1
                if physical_bank != previous:
                    previous, swaps = physical_bank, swaps + 1
                    if swaps >= 3:
                        shown[physical_bank] = check.e.framebuffer()[1][12 * 320:212 * 320]
                if len(shown) == 2:
                    break
            assert shown.keys() == {0, 1}, ('both banks not presented', meta, check.state())
            for physical_bank, actual in shown.items():
                changed = [index for index, (a, b) in enumerate(zip(actual, expected)) if a != b]
                assert not changed, (meta, physical_bank, len(changed), changed[:16])
            row = dict(**meta, both_framebuffers_match_host=True,
                       pixels_sha256=hashlib.sha256(expected).hexdigest())
            print('MEASUREMENT ' + json.dumps(row), flush=True)
        finally:
            check.close()
        return

    library = C.CDLL(str(ROOT / 'build/libaitd32x.so'))
    library.host_init.argtypes = [C.c_void_p, C.c_uint]
    library.host_pixels.restype = library.host_sram.restype = C.c_void_p
    data = (ROOT / 'assets/bank.bin').read_bytes()
    bank = C.create_string_buffer(data)
    offsets = native_layout(args.mars)
    rows = []
    fixtures = [('pink-chair bedroom closed door', 1, 4, 5, (0, 0, 0, 0), 59, 512),
                ('pink-chair bedroom rotating door', 1, 4, 5, (0, 0, 0, 0), 59, 640),
                ('library closed door', 1, 5, 3, (-2500, 0, -1500, 0), 59, 512),
                ('bedroom opposite view', 1, 4, 6, (-700, 0, -2700, 0), 59, 512),
                ('attic pushed cupboard', 0, 0, 2, (0, 0, 4000, 0), 4, None),
                ('ordinary hallway', 1, 1, 2, (100, 0, -650, 0), None, None)]
    for character in (0, 1):
        for name, floor, room, camera, pose, prop, beta in fixtures:
            library.host_init(bank, len(data))
            library.host_begin_world(character, floor, room, camera)
            library.host_place(1, floor, room, *pose)
            if prop is not None:
                assert library.host_object(prop, 0) >= 0, (name, 'prop inactive')
                if name == 'attic pushed cupboard':
                    original_beta = library.host_object(prop, 12)
                    library.host_place(prop, floor, room, -600, 0, 4540, original_beta)
                else:
                    library.host_set_object(prop, 12, beta)
                library.host_bounds(prop, 3)
            library.host_clear_message()
            C.memset(library.host_sram(), 0, 131072)
            assert library.host_save()
            sram = C.string_at(library.host_sram(), 131072)
            # Expected pixels use the same loaded actor state as the cartridge.
            assert library.host_load()
            library.host_clear_message()
            library.host_buffer(0)
            library.host_draw_cached()
            expected = C.string_at(library.host_pixels(), 320 * 224)[12 * 320:212 * 320]
            meta = dict(name=name, character=character, floor=floor, room=room,
                        camera=camera, prop=prop, beta=beta, pose=list(pose), layout=offsets)
            command = [sys.executable, __file__, str(args.core.resolve()), '--mars',
                       str(args.mars.resolve()), '--region', args.region, '--child']
            result = subprocess.run(command, input=json.dumps(meta).encode() + b'\n' + sram + expected,
                                    capture_output=True)
            if result.returncode:
                sys.stderr.buffer.write(result.stdout + result.stderr)
                raise AssertionError(('native fixture failed', meta))
            line = next(line for line in result.stdout.decode().splitlines()
                        if line.startswith('MEASUREMENT '))
            rows.append(json.loads(line[len('MEASUREMENT '):]))
            print(args.region, name, character, 'both banks match', flush=True)
    report = dict(passed=True, region=args.region, emulator_only=True, private_sram_only=True,
                  simulation_freeze='Private SDRAM World::Update rts/nop with DRC flush before Resume; ROM/renderer unchanged',
                  rom_sha256=hashlib.sha256((ROOT / 'build/AITD32X.32x').read_bytes()).hexdigest(),
                  bank_sha256=hashlib.sha256(data).hexdigest(), scenes=rows)
    output = ROOT / 'build' / f'window-door-native-{args.region}.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=True, region=args.region, scenes=len(rows), report=str(output)), indent=2))


if __name__ == '__main__':
    main()
