#!/usr/bin/env python3
"""Check shared ordering fixes on the ROM against frozen host scene pixels.

Each fixture runs in a fresh PicoDrive process with private in-memory SRAM.
No battery file, original resource or hardware is used by this check.
"""
import argparse
import ctypes as C
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import emulator_check as ec
from check_full_game_native import Native, layout, load_fixture

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('core', type=Path)
    parser.add_argument('--mars', type=Path, default=ROOT / '.local/toolchain/mars')
    parser.add_argument('--region', choices=('NTSC', 'PAL'), default='NTSC')
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        meta = json.loads(sys.stdin.buffer.readline())
        sram = sys.stdin.buffer.read(131072)
        expected = sys.stdin.buffer.read()
        assert len(sram) == 131072 and len(expected) == 64000
        check = Native(args.core, args.region, layout(args.mars))
        try:
            load_fixture(check, sram)
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
                changed = [i for i, (a, b) in enumerate(zip(actual, expected)) if a != b]
                assert not changed, (meta, physical_bank, len(changed), changed[:16])
            row = dict(**meta, both_framebuffers_match_host=True,
                       pixels_sha256=hashlib.sha256(expected).hexdigest())
            print('MEASUREMENT ' + json.dumps(row), flush=True)
        finally:
            check.close()
        return

    lib = C.CDLL(str(ROOT / 'build/libaitd32x.so'))
    lib.host_init.argtypes = [C.c_void_p, C.c_uint]
    lib.host_pixels.restype = lib.host_sram.restype = C.c_void_p
    data = (ROOT / 'assets/bank.bin').read_bytes()
    bank = C.create_string_buffer(data)
    rows = []
    for character in (0, 1):
        for name, floor, room, camera, pose in (
                ('dining-room masks', 1, 4, 6, (-700, 0, -2700, 0)),
                ('foreground doors', 3, 3, 19, (1260, 0, 0, 0)),
                ('contact middle item', 0, 0, 3, (-4000, 0, 1200, 0))):
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
            # Reload the same serialized fixture before generating expected
            # pixels so native/host compare precisely the loaded actor poses.
            assert lib.host_load()
            lib.host_clear_message()
            lib.host_buffer(0)
            lib.host_draw_cached()
            expected = C.string_at(lib.host_pixels(), 320 * 224)[12 * 320:212 * 320]
            meta = dict(name=name, character=character, floor=floor, room=room, camera=camera)
            command = [sys.executable, __file__, str(args.core.resolve()), '--mars',
                       str(args.mars.resolve()), '--region', args.region, '--child']
            result = subprocess.run(command, input=json.dumps(meta).encode() + b'\n' + sram + expected,
                                    capture_output=True)
            if result.returncode:
                sys.stderr.buffer.write(result.stdout + result.stderr)
                raise AssertionError(('native fixture failed', meta))
            line = next(line for line in result.stdout.decode().splitlines() if line.startswith('MEASUREMENT '))
            rows.append(json.loads(line[len('MEASUREMENT '):]))
            print(args.region, name, character, 'both banks match', flush=True)
    report = dict(passed=True, region=args.region, emulator_only=True, private_sram_only=True,
                  rom_sha256=hashlib.sha256((ROOT / 'build/AITD32X.32x').read_bytes()).hexdigest(),
                  scenes=rows)
    output = ROOT / 'build' / f'draw-order-native-{args.region}.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=True, region=args.region, scenes=len(rows), report=str(output)), indent=2))


if __name__ == '__main__':
    main()
