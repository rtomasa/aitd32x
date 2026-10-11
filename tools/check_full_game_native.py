#!/usr/bin/env python3
"""Focused full-house ROM, mapper, SRAM and performance checks in PicoDrive.

Fixtures use only host SRAM and the core's private in-memory SRAM. Nothing
reads or writes emulator battery files. This is emulator evidence only.
"""
import argparse
import ctypes as C
import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

import emulator_check as ec
from check_startup_native import Check, A, B, START

ROOT = ec.ROOT
FIELDS = dict(world='offsetof(Game,world)', fault='offsetof(World,fault_code)',
              menu='offsetof(Game,menu)', selection='offsetof(Game,selection)',
              notice='offsetof(Game,action_selection)', book_line='offsetof(Game,book_line)',
              pos='offsetof(Game,player)+offsetof(Actor,pos)', vars='offsetof(World,vars)',
              since='offsetof(Game,startup_since)', time='offsetof(Game,startup_time)',
              dirty='offsetof(Game,dirty)', background='offsetof(Game,renderer)+offsetof(Renderer,background)',
              bounds='offsetof(Game,static_bounds)', phase='offsetof(Clock,phase)', last='offsetof(Clock,last)',
              dark='offsetof(World,dark)')


def layout(mars):
    source = ROOT / 'build/full-game-native-layout.cpp'
    source.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned layout[]={' +
                      ','.join(FIELDS.values()) + '};\n')
    assembly = source.with_suffix('.s')
    subprocess.run([str(mars / 'sh-elf/bin/sh-elf-g++'), '-m2', '-mb', '-std=c++17',
                    '-Wno-invalid-offsetof', '-I' + str(ROOT), '-S', str(source), '-o', str(assembly)], check=True)
    values = re.findall(r'\.long\s+([-0-9xa-fA-F]+)', assembly.read_text().split('_layout:', 1)[1].split('.ident', 1)[0])
    assert len(values) == len(FIELDS)
    return dict(zip(FIELDS, (int(value, 0) for value in values)))


class Native(Check):
    def __init__(self, core, region, offsets):
        # PicoDrive advertises the allocation before its first frame, then hides
        # an entirely blank save from frontends to avoid writing empty .srm files.
        emulator = ec.Emulator
        def allocated_emulator(core, region):
            result = emulator(core, region)
            result.lib.retro_get_memory_size.argtypes = [C.c_uint]
            result.lib.retro_get_memory_size.restype = C.c_size_t
            result.save_capacity = result.lib.retro_get_memory_size(0)
            return result
        ec.Emulator = allocated_emulator
        try:
            super().__init__(core, region, offsets)
        finally:
            ec.Emulator = emulator
        self.clock = ec.symbol_address('__ZL11clock_state') & 0x3ffff
        self.e.capture_audio = False

    def integer_at(self, address, value):
        words = (C.c_uint16 * 2).from_address(address)
        words[0], words[1] = (value >> 16) & 65535, value & 65535

    def frozen_frame(self, pad=0):
        self.integer_at(self.memory + self.clock + self.offsets['phase'], 0)
        C.c_uint16.from_address(self.memory + self.clock + self.offsets['last']).value = self.e.comm()[6] & ~1
        C.c_uint8.from_address(self.memory + self.game + (self.offsets['dirty'] ^ 1)).value = 1
        self.advance(1, pad)

    def bytes_at(self, offset, length):
        assert offset % 2 == length % 2 == 0
        words = (C.c_uint16 * (length // 2)).from_address(self.memory + self.game + offset)
        return struct.pack('>' + str(len(words)) + 'H', *words)

    def healthy(self):
        assert not self.read('fault', world=True), ('native LIFE fault', self.state())
        assert self.mapper_valid(), ('invalid mapped page', list(self.banks))

    def resume_frozen(self):
        assert self.state()['paused'] and self.read('menu') == 3
        for _ in range(self.hz * 2):
            self.frozen_frame(START)
            if not self.state()['paused']:
                break
        for _ in range(self.hz // 3):
            self.frozen_frame()
        assert not self.state()['paused'] and self.read('menu') == 0, self.state()


def load_fixture(check, sram):
    check.advance(check.hz)
    assert check.e.save_capacity == len(sram) == 131072, ('SRAM capacity', check.e.save_capacity)
    memory = check.e.lib.retro_get_memory_data(0)
    assert memory, 'SRAM was not allocated'
    C.memmove(memory, sram, len(sram))
    assert check.e.lib.retro_get_memory_size(0) == len(sram)
    check.press(A)
    check.phase(5)
    check.press(B)
    check.phase(10, 60)
    assert check.state()['paused'], ('save was not loaded', check.state())


def host_fixture(lib, floor, room, camera, position=None, lamp=False):
    C.memset(lib.host_sram(), 0, 131072)
    lib.host_begin_world(0, floor, room, camera)
    if position is not None:
        lib.host_place(1, floor, room, *position, 0)
    if lamp:
        lib.host_set_variable(7, 1)
        lib.host_take(13)
        assert lib.host_run_life(509, 235) == 0 and lib.host_dark()
    assert not lib.host_world(3) and lib.host_save()
    return C.string_at(lib.host_sram(), 131072), [lib.host_object(1, field) for field in (8, 9, 10)]


def source_position(data, room, y):
    views = struct.unpack_from('>I', data, 20)[0]
    for view in range(struct.unpack_from('>H', data, 18)[0]):
        entry = views + view * 16
        if struct.unpack_from('>H', data, entry)[0] != room:
            continue
        polygons = struct.unpack_from('>I', data, entry + 8)[0]
        count = struct.unpack_from('>H', data, polygons)[0]
        points = [struct.unpack_from('>2h', data, polygons + 2 + index * 4) for index in range(count)]
        return [sum(point[0] for point in points) * 10 // count, y,
                sum(point[1] for point in points) * 10 // count]
    raise AssertionError(('camera does not view room', room))


def frozen_scene(check, source, floor, room, camera):
    ticks = check.state()['world_ticks']
    shown, previous, swaps = {}, check.e.vdp[5] & 1, 0
    for _ in range(check.hz * 8):
        check.frozen_frame()
        check.healthy()
        assert check.state()['world_ticks'] == ticks, 'frozen scene advanced simulation'
        bank = check.e.vdp[5] & 1
        if bank != previous:
            previous, swaps = bank, swaps + 1
            if swaps >= 3:
                shown[bank] = check.e.framebuffer()[1][320 * 12:320 * 212]
        if len(shown) == 2:
            break
    assert shown.keys() == {0, 1} and shown[0] == shown[1], 'completed physical framebuffer mismatch'
    background = check.bytes_at(check.offsets['background'], 64000)
    rectangles = struct.iter_unpack('>4i', check.bytes_at(check.offsets['bounds'], 50 * 16))
    covered = bytearray(64000)
    for x1, y1, x2, y2 in rectangles:
        if x1 > x2 or y1 > y2:
            continue
        x1, x2, y1, y2 = max(0, x1), min(319, x2), max(0, y1), min(199, y2)
        if x1 > x2 or y1 > y2:
            continue
        for y in range(y1, y2 + 1):
            covered[y * 320 + x1:y * 320 + x2 + 1] = bytes([1]) * (x2 - x1 + 1)
    positions = [index for index, overlay in enumerate(covered) if not overlay]
    assert len(positions) >= 1000, ('insufficient original background exposure', floor, room, camera, len(positions))
    assert all(background[index] == source[index] for index in positions), ('mapped background differs', floor, room, camera)
    before = check.state()['rendered']
    for _ in range(check.hz):
        check.frozen_frame()
        check.healthy()
        assert check.state()['world_ticks'] == ticks
    draws = check.state()['rendered'] - before
    return dict(floor=floor, room=room, camera=camera, mapped_page=int(check.banks[1]),
                original_background_pixels=len(positions), both_framebuffers_equal=True,
                pixels_sha256=hashlib.sha256(shown[0]).hexdigest(),
                frozen_render_fps=draws, measured_seconds=1, world_ticks=ticks)


def performance(core, region, sram, offsets, root):
    original_root = ec.ROOT
    ec.ROOT = root
    check = Native(core, region, offsets)
    try:
        load_fixture(check, sram)
        check.press(START)
        check.advance(check.hz)
        before = check.state()
        start = check.e.state()
        segments = []
        for seconds, pad in ((3, 0), (2, 1), (1, 4), (1, A), (3, 0)):
            check.advance(check.hz * seconds, pad)
            assert check.e.comm()[4] & 255 == pad, ('emulated controller differs', pad, check.e.comm())
            pose = check.e.state()
            segments.append(dict(seconds=seconds, pad=pad,
                                 pose=[pose[field] for field in ('x', 'y', 'z', 'beta')],
                                 animation=[pose[field] for field in ('animation_asset', 'animation_frame', 'animation_phase')],
                                 world_ticks=check.state()['world_ticks'] - before['world_ticks']))
        end = check.state()
        assert not end['fault'] and not end['paused'], end
        return dict(seconds=10, completed_draws=end['rendered'] - before['rendered'],
                    draw_fps=(end['rendered'] - before['rendered']) / 10,
                    world_ticks=end['world_ticks'] - before['world_ticks'],
                    start_pose=[start[field] for field in ('x', 'y', 'z', 'beta')],
                    final_pose=[check.e.state()[field] for field in ('x', 'y', 'z', 'beta')],
                    fps_tenths=check.e.state()['fps_tenths'], segments=segments)
    finally:
        check.close()
        ec.ROOT = original_root


def selection_latency(check, pad, rectangle):
    """Measure until the changed highlighted option reaches the displayed bank."""
    check.advance(check.hz // 3)
    check.wait(check.settled)
    x1, y1, x2, y2 = rectangle
    def pixels():
        raw = check.e.framebuffer()[1][320 * 12:320 * 212]
        return b''.join(raw[y * 320 + x1:y * 320 + x2] for y in range(y1, y2))
    previous = pixels()
    for frames in range(1, check.hz * 2 + 1):
        check.advance(1, pad)
        assert not check.state()['fault'] and check.mapper_valid()
        if pixels() != previous:
            check.advance(check.hz // 5)
            check.wait(check.settled)
            return dict(frames=frames, milliseconds=round(frames * 1000 / check.hz, 1))
    raise AssertionError(('selection did not become visible', rectangle, check.state()))


def menu_performance(core, region, sram, offsets, root):
    original_root = ec.ROOT
    ec.ROOT = root
    check = Native(core, region, offsets)
    try:
        check.advance(check.hz)
        check.press(A)
        check.phase(5)
        report = dict(start_menu_down=selection_latency(check, 2, (10, 76, 310, 124)),
                      start_menu_up=selection_latency(check, 1, (10, 76, 310, 124)))
        check.press(A)
        check.phase(6)
        report['character_left'] = selection_latency(check, 4, (0, 0, 320, 200))
        report['character_right'] = selection_latency(check, 8, (0, 0, 320, 200))
        check.press(B)
        check.phase(5)
        assert check.e.save_capacity == len(sram) == 131072
        C.memmove(check.e.lib.retro_get_memory_data(0), sram, len(sram))
        check.press(B)
        check.phase(10, 60)
        check.press(START)
        check.advance(check.hz)
        check.press(32)
        assert check.state()['menu'] == 1
        report['inventory_down'] = selection_latency(check, 2, (8, 8, 312, 92))
        report['inventory_up'] = selection_latency(check, 1, (8, 8, 312, 92))
        check.press(A)
        assert check.state()['menu'] == 2
        report['actions_down'] = selection_latency(check, 2, (168, 108, 312, 192))
        report['actions_up'] = selection_latency(check, 1, (168, 108, 312, 192))
        return report
    finally:
        check.close()
        ec.ROOT = original_root


def native_scene(core, region, sram, offsets, scene, expected):
    floor, room, camera = scene
    manifest = json.loads((ROOT / 'assets/manifest.json').read_text())
    entry = next(entry for entry in manifest['assets'] if entry['name'] == f'BACKGROUND_{floor}_{camera}')
    bank = (ROOT / 'assets/bank.bin').read_bytes()
    source = bank[entry['offset']:entry['offset'] + entry['packed_size']]
    check = Native(core, region, offsets)
    try:
        load_fixture(check, sram)
        assert check.position() == expected, ('host/native save pose', expected, check.position())
        assert (check.state()['floor'], check.state()['room'], check.state()['camera']) == tuple(scene)
        check.resume_frozen()
        row = frozen_scene(check, source, floor, room, camera)
        row['host_native_save_compatible'] = True
        before = check.state()
        for _ in range(check.hz):
            check.advance()
            check.healthy()
        after = check.state()
        assert after['world_ticks'] > before['world_ticks'], 'late-floor LIFE did not advance'
        row['live_world_ticks'] = after['world_ticks'] - before['world_ticks']
        row['live_render_fps'] = after['rendered'] - before['rendered']
        row['live_final_location'] = [after[field] for field in ('floor', 'room', 'camera')]
        return row
    finally:
        check.close()


def measured_process(kind, args, sram, root, scene=None, position=None):
    # A fresh core process also resets PicoDrive's controller TH-handshake
    # state, which survives unload/init in this core build and can synthesize
    # held A/B when comparing several ROM instances in one process.
    command = [sys.executable, __file__, str(args.core.resolve()),
               '--region', args.region, '--mars', str(args.mars.resolve()),
               '--measure', kind, '--fixture-root', str(root.resolve())]
    if scene:
        command += ['--scene', *map(str, scene), '--position', *map(str, position)]
    result = subprocess.run(command,
                            input=sram, capture_output=True, check=True)
    line = next(line for line in result.stdout.decode().splitlines() if line.startswith('MEASUREMENT '))
    return json.loads(line[len('MEASUREMENT '):])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('core', type=Path)
    parser.add_argument('--region', choices=('NTSC', 'PAL'), default='NTSC')
    parser.add_argument('--mars', type=Path, default=ROOT / '.local/toolchain/mars')
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--measure', choices=('performance', 'menu', 'scene'), help=argparse.SUPPRESS)
    parser.add_argument('--fixture-root', type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument('--scene', type=int, nargs=3, help=argparse.SUPPRESS)
    parser.add_argument('--position', type=int, nargs=3, help=argparse.SUPPRESS)
    args = parser.parse_args()
    offsets = layout(args.mars)
    if args.measure:
        sram = sys.stdin.buffer.read()
        assert len(sram) == 131072
        if args.measure == 'scene':
            result = native_scene(args.core, args.region, sram, offsets, args.scene, args.position)
        else:
            measure = performance if args.measure == 'performance' else menu_performance
            result = measure(args.core, args.region, sram, offsets, args.fixture_root)
        print('MEASUREMENT ' + json.dumps(result), flush=True)
        return
    bank = (ROOT / 'assets/bank.bin').read_bytes()
    manifest = json.loads((ROOT / 'assets/manifest.json').read_text())
    entries = {entry['name']: entry for entry in manifest['assets']}
    def asset(name):
        entry = entries[name]
        return bank[entry['offset']:entry['offset'] + entry['packed_size']]
    lib = C.CDLL(str(ROOT / 'build/libaitd32x.so'))
    lib.host_sram.restype = C.c_void_p
    lib.host_init.argtypes = [C.c_void_p, C.c_uint]
    memory = C.create_string_buffer(bank)
    lib.host_init(memory, len(bank))
    scenes = [(floor, room, camera) for floor, room, camera in
              ((0, 0, 0), (1, 0, 0), (2, 2, None), (3, 1, 3),
               (4, 0, 0), (5, 10, 18), (6, 0, None), (7, 1, 3))]
    report = dict(region=args.region, emulator_only=True, no_battery_files=True, scenes=[])
    rom = (ROOT / 'build/AITD32X.32x').read_bytes()
    report['rom_sha256'], report['rom_bytes'] = hashlib.sha256(rom).hexdigest(), len(rom)
    for floor, room, camera in scenes:
        if camera is None:
            data = asset(f'ROOM_{floor}_{room}')
            camera = struct.unpack_from('>H', data, struct.unpack_from('>I', data, 12)[0])[0]
        position = source_position(asset(f'CAMERA_{floor}_{camera}'), room,
                                   -4010 if floor in (5, 6) else 0)
        sram, expected = host_fixture(lib, floor, room, camera, position, lamp=floor == 6)
        row = measured_process('scene', args, sram, ROOT, (floor, room, camera), expected)
        report['scenes'].append(row)
        print(args.region, (floor, room, camera), row['frozen_render_fps'], 'FPS', flush=True)
    C.memset(lib.host_sram(), 0, 131072)
    lib.host_startgame(0)
    assert lib.host_save()
    fresh = C.string_at(lib.host_sram(), 131072)
    report['performance'] = dict(after=measured_process('performance', args, fresh, ROOT))
    lib.host_take(13)
    assert lib.host_save()
    menu_sram = C.string_at(lib.host_sram(), 131072)
    report['menu_latency'] = dict(after=measured_process('menu', args, menu_sram, ROOT))
    if args.reference:
        old = C.CDLL(str((args.reference / 'libaitd32x.so').resolve()))
        old.host_sram.restype = C.c_void_p
        old.host_init.argtypes = [C.c_void_p, C.c_uint]
        old_memory = C.create_string_buffer((args.reference / 'assets/bank.bin').read_bytes())
        old.host_init(old_memory, len(old_memory) - 1)
        old.host_startgame(0)
        C.memset(old.host_sram(), 0, 131072)
        assert old.host_save()
        old_sram = C.string_at(old.host_sram(), 131072)
        root = ROOT / 'build/full-game-native-reference'
        (root / 'build').mkdir(parents=True, exist_ok=True)
        for name in ('AITD32X.32x', 'AITD32X.elf'):
            target = root / 'build' / name
            if target.is_symlink():
                target.unlink()
            target.symlink_to((args.reference / name).resolve())
        target = root / 'assets'
        if target.is_symlink():
            target.unlink()
        target.symlink_to((args.reference / 'assets').resolve(), target_is_directory=True)
        report['performance']['before'] = measured_process('performance', args, old_sram, root)
        old.host_take(13)
        assert old.host_save()
        old_menu_sram = C.string_at(old.host_sram(), 131072)
        report['menu_latency']['before'] = measured_process('menu', args, old_menu_sram, root)
        assert report['performance']['after']['segments'] == report['performance']['before']['segments'], 'native simulation/animation trace differs'
    assert hashlib.sha256((ROOT / 'build/AITD32X.32x').read_bytes()).hexdigest() == report['rom_sha256']
    (ROOT / 'build' / ('full-game-native-' + args.region + '.json')).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
