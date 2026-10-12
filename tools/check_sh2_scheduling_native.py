#!/usr/bin/env python3
"""Check changing SH2 row ownership against serial host pixels in PicoDrive.

Private SRAM/SDRAM only. Force opposite ownership limits between emulator
slices, freeze simulation, and verify both displayed framebuffer histories.
This checks the compiled queue/fences, including contact depth and glass;
it does not validate physical hardware timing.
"""
import argparse
import ctypes as C
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import emulator_check as ec
from check_full_game_native import Native, load_fixture
from check_window_door_native import native_layout

ROOT = ec.ROOT


def child(args):
    meta = json.loads(sys.stdin.buffer.readline())
    sram = sys.stdin.buffer.read(131072)
    expected = sys.stdin.buffer.read()
    assert len(expected) == 64000 and len(sram) == 131072
    check = Native(args.core, args.region, meta.pop('layout'))
    try:
        load_fixture(check, sram)
        update = ec.symbol_address('__ZN5World6UpdateEtb') & 0x3ffff
        instructions = (C.c_uint16 * 2).from_address(check.memory + update)
        instructions[0], instructions[1] = 0x000b, 0x0009
        check.e.lib.sh2_drc_flush_all()
        check.resume_frozen()
        balances = [ec.symbol_address('__ZN12_GLOBAL__N_1L' + name + 'E') & 0x3ffff
                    for name in ('16ordinary_balance', '15contact_balance')]
        job = ec.symbol_address('__ZN12_GLOBAL__N_1L9job_splitE') & 0x3ffff
        seen, results = set(), []
        ticks = check.state()['world_ticks']
        # Change the boundary between phases, even when a draw is in flight.
        # Published BEGIN/CONTACT commands must retain their original bands.
        for boundary in (20, 180, 100):
            shown, previous, swaps = {}, check.e.vdp[5] & 1, 0
            for frame in range(check.hz * 4):
                for offset in balances:
                    check.integer_at(check.memory + offset, boundary)
                    check.integer_at(check.memory + offset + 4, 0)
                check.frozen_frame()
                check.healthy()
                assert check.state()['world_ticks'] == ticks
                value = check.bytes_at(job - check.game, 4)
                seen.add(int.from_bytes(value, 'big'))
                physical = check.e.vdp[5] & 1
                if physical != previous:
                    previous, swaps = physical, swaps + 1
                    if swaps >= 3:
                        actual = check.e.framebuffer()[1][12 * 320:212 * 320]
                        assert actual == expected, (meta, boundary, physical,
                            sum(a != b for a, b in zip(actual, expected)))
                        shown[physical] = True
                if len(shown) == 2:
                    break
            assert len(shown) == 2, ('renderer stalled', meta, boundary)
            results.append(boundary)
        assert 20 in seen and 180 in seen, ('ownership extremes not exercised', seen)
        print('MEASUREMENT ' + json.dumps(dict(**meta, boundaries=results,
              ordinary_splits_seen=sorted(seen), both_framebuffers_match=True)), flush=True)
    finally:
        check.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('core', type=Path)
    parser.add_argument('--region', choices=('NTSC', 'PAL'), default='NTSC')
    parser.add_argument('--mars', type=Path, default=ROOT / '.local/toolchain/mars')
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        child(args)
        return
    lib = C.CDLL(str(ROOT / 'build/libaitd32x.so'))
    lib.host_init.argtypes = [C.c_void_p, C.c_uint]
    lib.host_sram.restype = lib.host_pixels.restype = C.c_void_p
    data = (ROOT / 'assets/bank.bin').read_bytes()
    bank = C.create_string_buffer(data)
    offsets, rows = native_layout(args.mars), []
    for character in (0, 1):
        for name, floor, room, camera, pose in (
                ('attic glass and cupboard', 0, 0, 0, (3231, 0, -1548, 0)),
                ('contact middle item', 0, 0, 3, (-4000, 0, 1200, 0)),
                ('bedroom door', 1, 4, 5, (0, 0, 0, 0))):
            lib.host_init(bank, len(data))
            lib.host_begin_world(character, floor, room, camera)
            lib.host_place(1, floor, room, *pose)
            if name == 'contact middle item':
                for slot in range(50):
                    object_id = lib.host_active(slot, 0)
                    if object_id >= 0 and object_id not in (0, 1, 13):
                        lib.host_delete(object_id)
                lib.host_set_object(13, 2, 128)
                lib.host_set_object(13, 17, -1)
                lib.host_set_object(0, 17, -1)
                dx = -350 if character else -250
                lib.host_place(13, 0, 0, -4000 + dx, 0, 1200 - dx // 2, 0)
                lib.host_place(0, 0, 0, -4050, 0, 1225, 768)
                lib.host_bounds(1, 2)
                lib.host_bounds(13, 3)
                lib.host_bounds(0, 3)
            lib.host_clear_message()
            C.memset(lib.host_sram(), 0, 131072)
            assert lib.host_save()
            sram = C.string_at(lib.host_sram(), 131072)
            assert lib.host_load()
            lib.host_clear_message()
            lib.host_buffer(0)
            lib.host_draw_cached()
            expected = C.string_at(lib.host_pixels(), 320 * 224)[12 * 320:212 * 320]
            meta = dict(name=name, character=character, layout=offsets)
            command = [sys.executable, __file__, str(args.core.resolve()), '--mars',
                       str(args.mars.resolve()), '--region', args.region, '--child']
            result = subprocess.run(command, input=json.dumps(meta).encode() + b'\n' +
                                    sram + expected, capture_output=True)
            if result.returncode:
                sys.stderr.buffer.write(result.stdout + result.stderr)
                raise AssertionError(('SH2 ownership fixture failed', name, character))
            line = next(s for s in result.stdout.decode().splitlines() if s.startswith('MEASUREMENT '))
            rows.append(json.loads(line[len('MEASUREMENT '):]))
            print(args.region, name, character, 'ownership extremes match', flush=True)
    report = dict(passed=True, emulator_only=True, private_sram_only=True,
                  region=args.region, rom_sha256=hashlib.sha256(
                  (ROOT / 'build/AITD32X.32x').read_bytes()).hexdigest(), scenes=rows)
    output = ROOT / 'build' / f'sh2-scheduling-native-{args.region}.json'
    output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
