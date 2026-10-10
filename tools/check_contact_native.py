#!/usr/bin/env python3
"""Compare frozen contact scenes on two actual ROMs and both framebuffer banks.

The host engine creates memory-only scene fixtures. All actor poses, collision
bounds and draw flags are then copied into each cartridge using layouts
from its SH2 compiler. This avoids animation-clock drift between faster/slower
builds. No emulator save or battery data is loaded or written.
"""
import argparse
import ctypes as C
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path

import emulator_check as ec


FIELDS = {}
for prefix, typename, fields in (
        ('g', 'Game', 'player world mode camera character paused dirty held pending_edges menu static_signature dynamic_slots static_hash static_owner static_quiet_since'),
        ('w', 'World', 'objects active poses floor room camera character effects vars prompt message book finished fault_code ticks now view_changed'),
        ('a', 'Actor', 'pos alpha beta gamma character room floor collision_min collision_max model animation frame frame_phase anim_asset previous state'),
        ('o', 'ActiveObject', 'id value'), ('e', 'Effect', 'count')):
    for field in fields.split():
        FIELDS[f'{prefix}_{field}'] = f'offsetof({typename},{field})'
FIELDS.update(actor_size='sizeof(Actor)', active_size='sizeof(ActiveObject)', effect_size='sizeof(Effect)',
              clock_phase='offsetof(Clock,phase)', clock_last='offsetof(Clock,last)')


def layout(root, mars):
    fields = dict(FIELDS)
    if 'static_slots' in (root / 'src/engine/game.hpp').read_text():
        fields['g_static_slots'] = 'offsetof(Game,static_slots)'
    source = root / 'build/contact-native-layout.cpp'
    assembly = source.with_suffix('.s')
    source.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned contact_layout[]={' + ','.join(fields.values()) + '};\n')
    subprocess.run([str(mars / 'sh-elf/bin/sh-elf-g++'), '-m2', '-mb', '-std=c++17', '-Wno-invalid-offsetof', '-I' + str(root),
                    '-S', str(source), '-o', str(assembly)], check=True, stdout=subprocess.DEVNULL)
    text = assembly.read_text().split('_contact_layout:', 1)[1].split('.ident', 1)[0]
    values = [int(value, 0) for value in re.findall(r'\.long\s+([-0-9xa-fA-F]+)', text)]
    assert len(fields) == len(values)
    return dict(zip(fields, values))


def fixtures(root):
    lib = C.CDLL(str(root / 'build/libaitd32x.so'))
    data = (root / 'assets/bank.bin').read_bytes()
    bank = C.create_string_buffer(data)
    lib.host_init.argtypes = [C.c_void_p, C.c_uint]
    scenes = []
    for character in (0, 1):
        for name, floor, room, camera, x, z, beta in (
                ('chest-push', 0, 0, 3, -4000, 1200, 0),
                ('chest-open', 1, 2, 9, 1800, 1400, 256),
                ('hatch-opening', 0, 0, 3, -5200, 2500, 0),
                ('hall-door', 1, 1, 2, 2700, 400, 0)):
            lib.host_init(bank, len(data))
            if character:
                lib.host_tick(32)
                lib.host_tick(0)
            lib.host_tick(128)
            lib.host_tick(0)
            lib.host_place(1, floor, room, x, 0, z, beta)
            lib.host_set_variable(33, 1)
            if name == 'chest-push':
                lib.host_place(0, 0, 0, -4000, 0, 300, 768)
            for _ in range(5):
                lib.host_tick(0)
            if name == 'chest-open':
                lib.host_set_variable(32, 1)
                lib.host_set_object(38, 6, lib.host_object(38, 6) | 0x8000)
                lib.host_found_life(2, 64)
                for _ in range(12):
                    lib.host_tick(64)
            elif name == 'chest-push':
                lib.host_found_life(2, 256)
                for _ in range(12):
                    lib.host_tick(65)
            elif name == 'hatch-opening':
                lib.host_set_object(8, 11, 400)
                lib.host_bounds(8, 3)
            lib.host_clear_message()
            lib.host_camera(floor, room, camera)
            before = [lib.renderer_contact_stats(index) for index in range(4)]
            lib.host_draw_cached()
            after = [lib.renderer_contact_stats(index) for index in range(4)]
            actors = []
            for slot in range(24):
                object_id = lib.host_active(slot, 0)
                if object_id < 0:
                    continue
                actors.append(dict(slot=slot, id=object_id,
                                   words=[lib.host_object(object_id, field) for field in range(26)],
                                   bounds=[lib.host_bounds_value(object_id, field) for field in range(6)],
                                   groups=[[lib.host_group(object_id, group, field) for field in range(4)] for group in range(40)]))
            scenes.append(dict(name=name, character=character, floor=floor, room=room, camera=camera,
                               actors=actors, prepared_groups=after[0] - before[0],
                               variables=[lib.host_variable(index) for index in range(207)]))
    assert all(scene['prepared_groups'] for scene in scenes), ('contact fixture missed fast path',
        [(scene['name'], scene['character'], scene['prepared_groups']) for scene in scenes])
    return scenes


def check_fallbacks(root, reference, assets):
    libraries = [C.CDLL(str(project / 'build/libaitd32x.so')) for project in (reference, root)]
    data = (root / 'assets/bank.bin').read_bytes()
    bank = C.create_string_buffer(data)
    for library in libraries:
        library.host_init.argtypes = [C.c_void_p, C.c_uint]
        library.host_pixels.restype = C.c_void_p

    def both(name, *arguments):
        for library in libraries:
            getattr(library, name)(*arguments)

    def compare(label):
        images = [C.string_at(library.host_pixels(), 320 * 224) for library in libraries]
        assert images[0] == images[1], (label, 'fallback pixel mismatch', sum(a != b for a, b in zip(*images)))

    camera = struct.unpack_from('>9h', data, assets['CAMERA_0_3']['offset'])
    room = struct.unpack_from('>3h', data, assets['ROOM_0_0']['offset'])
    camera_position = ((camera[3] - room[0]) * 10, (room[1] - camera[4]) * 10, (room[2] - camera[5]) * 10)
    rows = []
    for character in (0, 1):
        both('host_init', bank, len(data))
        if character:
            both('host_tick', 32)
            both('host_tick', 0)
        both('host_tick', 128)
        both('host_tick', 0)
        for object_id in (1, 0):
            both('host_place', object_id, 0, 0, -4000, 0, 1200, 0)
        # Two detailed character bodies fit 768 vertices but exceed the
        # prepared command capacity, exercising fallback without corruption.
        both('host_set_object', 0, 1, 12)
        both('host_camera', 0, 0, 3)
        before = libraries[1].renderer_contact_stats(2)
        both('host_resolve_pair', 1, 0)
        assert libraries[1].renderer_contact_stats(2) == before + 1
        compare(('command capacity', character))
        # Centering the model at the camera crosses the native near plane.
        both('host_place', 1, 0, 0, *camera_position, 0)
        both('host_draw_fresh')
        before = libraries[1].renderer_contact_stats(1)
        both('host_draw_depth', 1)
        assert libraries[1].renderer_contact_stats(1) == before + 1
        compare(('near clipping', character))
        rows.append(dict(character=character, command_capacity_pixels_match=True, near_clipping_pixels_match=True))
    return rows


def capture(root, core, mars, region, scenes, assets):
    ec.ROOT = root
    offsets = layout(root, mars)
    emulator = ec.Emulator(core, region)
    emulator.run(180)
    emulator.run(6, 128)
    emulator.run(120)
    emulator.run(6, 128)
    emulator.run(120)
    assert emulator.state()['paused']
    memory = C.c_void_p.in_dll(emulator.lib, 'Pico32xMem').value
    base = ec.symbol_address('__ZL4game') & 0x3ffff
    clock = (ec.symbol_address('__ZL11clock_state') & 0x3ffff) - base
    asset_bank = ec.symbol_address('_asset_bank')
    w = offsets['g_world']
    worker = None
    if 'RendererWorker_Contact' in (root / 'src/render/worker.cpp').read_text():
        symbols = subprocess.check_output([str(mars / 'sh-elf/bin/sh-elf-nm'), str(root / 'build/AITD32X.elf')], text=True)
        stores = [int(line.split()[0], 16) for line in symbols.splitlines() if line.endswith('__ZN12_GLOBAL__N_1L7storageE')]
        # Audio and renderer have separate local `storage` symbols. The
        # renderer ring follows its frame token/slave-surface allocation.
        worker = max(stores) & 0x3ffff
        contact = ec.symbol_address('__ZN8Renderer13ContactWorkerEPvR13RasterSurface')

    def memory_word(address):
        words = (C.c_uint16 * 2).from_address(memory + address)
        return words[0] << 16 | words[1]

    def completed_contacts(start):
        if worker is None:
            return []
        read, completed = memory_word(worker + 4), memory_word(worker + 8)
        found = []
        # SH2 Command is two u32 fields + 66 (i32,i32) points. Shared places
        # eight entries after its three counters and four-word damage Rect.
        for serial in range(max(start, read - 8), read - 1):
            command = worker + 28 + (serial & 7) * 536
            end = worker + 28 + ((serial + 1) & 7) * 536
            if (memory_word(command) == 0 and memory_word(command + 4) == contact and
                    memory_word(end) >> 30 == 3 and memory_word(end + 4) <= completed):
                found.append(serial)
        return found

    def write(offset, data):
        assert offset % 2 == 0 and len(data) % 2 == 0
        target = (C.c_uint16 * (len(data) // 2)).from_address(memory + base + offset)
        for index, (value,) in enumerate(struct.iter_unpack('>H', data)):
            target[index] = value

    def integers(offset, *values):
        write(offset, struct.pack('>' + 'I' * len(values), *(value & 0xffffffff for value in values)))

    def byte(offset, value):
        C.c_uint8.from_address(memory + base + (offset ^ 1)).value = value

    def asset(offset, name):
        value = assets[name]
        write(offset, struct.pack('>3I2H', asset_bank + value['offset'], value['packed_size'], value['unpacked_size'], value['type'], value['flags']))

    results = []
    for scene in scenes:
        worker_start = memory_word(worker) if worker is not None else 0
        character = scene['character']
        for field, value in [('mode', 1), ('camera', scene['camera']), ('character', character), ('menu', 0),
                             ('static_signature', 0), ('dynamic_slots', 0)]:
            integers(offsets['g_' + field], value)
        if 'g_static_slots' in offsets:
            integers(offsets['g_static_slots'], 0)
        write(offsets['g_static_hash'], bytes(24 * 4))
        write(offsets['g_static_owner'], bytes([255]) * (24 * 2))
        write(offsets['g_static_quiet_since'], bytes(24 * 2))
        write(offsets['g_held'], bytes(2))
        write(offsets['g_pending_edges'], bytes(2))
        byte(offsets['g_paused'], 0)
        for field, value in [('floor', scene['floor']), ('room', scene['room']), ('camera', scene['camera']),
                             ('character', character), ('prompt', -1), ('message', -1), ('book', -1), ('fault_code', 0), ('ticks', 100), ('now', 100)]:
            integers(w + offsets['w_' + field], value)
        byte(w + offsets['w_finished'], 0)
        byte(w + offsets['w_view_changed'], 0)
        write(w + offsets['w_vars'], struct.pack('>207h', *scene['variables']))
        for index in range(3):
            byte(w + offsets['w_effects'] + index * offsets['effect_size'] + offsets['e_count'], 0)
        for index in range(292):
            write(w + offsets['w_objects'] + index * 52, b'\xff\xff')
        for slot in range(24):
            integers(w + offsets['w_active'] + slot * offsets['active_size'] + offsets['o_id'], -1)
        for actor in scene['actors']:
            slot, object_id, words = actor['slot'], actor['id'], actor['words']
            record = struct.pack('>26h', *words)
            write(w + offsets['w_objects'] + object_id * 52, record)
            write(w + offsets['w_objects'] + object_id * 52, struct.pack('>h', slot))
            active = w + offsets['w_active'] + slot * offsets['active_size']
            integers(active + offsets['o_id'], object_id)
            write(active + offsets['o_value'], record)
            pose = offsets['g_player'] if object_id == 1 else w + offsets['w_poses'] + slot * offsets['actor_size']
            integers(pose + offsets['a_pos'], *words[8:11])
            for field, value in [('alpha', words[11]), ('beta', words[12]), ('gamma', words[13]),
                                 ('character', character), ('floor', words[14]), ('room', words[15]),
                                 ('frame', words[20]), ('frame_phase', 0)]:
                integers(pose + offsets['a_' + field], value)
            bounds = actor['bounds']
            integers(pose + offsets['a_collision_min'], *bounds[::2])
            integers(pose + offsets['a_collision_max'], *bounds[1::2])
            if words[1] >= 0:
                asset(pose + offsets['a_model'], f'MODEL_{character}_{words[1]}')
            if words[19] >= 0:
                asset(pose + offsets['a_animation'], f'ANIM_{character}_{words[19]}')
                integers(pose + offsets['a_anim_asset'], assets[f'ANIM_{character}_{words[19]}']['id'])
            group_data = b''.join(struct.pack('>4i', *group) for group in actor['groups'])
            write(pose + offsets['a_state'], group_data)
            write(pose + offsets['a_previous'], group_data)
        # Ignore a completion which may have started before memory placement.
        # Each captured bank must be presented again with this frozen state.
        shown = {}
        slave_jobs = set()
        previous = emulator.vdp[5] & 1
        swaps = 0
        for _ in range(600):
            # Rebase the scheduler once per VBlank to freeze the scene without
            # the PAUSED panel hiding the character/contact pixels. At most
            # one new VBlank (25 phase units) can arrive per emulator.run(1),
            # below either region's 50/60-unit threshold. The assertion below
            # proves no gameplay step occurred during this diagnostic draw.
            integers(clock + offsets['clock_phase'], 0)
            write(clock + offsets['clock_last'], struct.pack('>H', emulator.comm()[6] & ~1))
            byte(offsets['g_dirty'], 1)
            emulator.run(1)
            assert memory_word(base + w + offsets['w_ticks']) == 100, ('unfrozen fixture', scene['name'], character)
            bank = emulator.vdp[5] & 1
            if previous != bank:
                previous = bank
                swaps += 1
                if swaps >= 3:
                    shown[bank] = emulator.framebuffer()[1][12 * 320:212 * 320]
                    slave_jobs.update(completed_contacts(worker_start))
            if len(shown) == 2:
                break
        assert len(shown) == 2 and shown[0] == shown[1], ('physical framebuffer mismatch', scene['name'], character, swaps)
        if worker is not None:
            assert slave_jobs, ('no completed slave contact job', scene['name'], character)
        results.append(dict(name=scene['name'], character=character, pixels=shown[0], prepared_groups=scene['prepared_groups'],
                            completed_slave_jobs=len(slave_jobs)))
    emulator.close()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('core', type=Path)
    parser.add_argument('--mars', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--project', type=Path, default=ec.ROOT)
    parser.add_argument('--region', choices=['NTSC', 'PAL'], default='NTSC')
    args = parser.parse_args()
    root, reference = args.project.resolve(), args.reference.resolve()
    manifest = json.loads((root / 'assets/manifest.json').read_text())
    assets = {asset['name']: asset for asset in manifest['assets']}
    fallbacks = check_fallbacks(root, reference, assets)
    scenes = fixtures(root)
    outputs = [capture(project, args.core, args.mars.resolve(), args.region, scenes, assets) for project in (reference, root)]
    for output in outputs:
        for name in {scene['name'] for scene in scenes}:
            characters = [scene['pixels'] for scene in output if scene['name'] == name]
            assert len(characters) == 2 and characters[0] != characters[1], ('character is not visibly distinct', name)
    rows = []
    for before, after in zip(*outputs):
        assert before['pixels'] == after['pixels'], (after['name'], after['character'], 'baseline mismatch', sum(a != b for a, b in zip(before['pixels'], after['pixels'])))
        rows.append(dict(name=after['name'], character=after['character'], both_banks_match_reference=True,
                         prepared_groups=after['prepared_groups'], completed_slave_jobs=after['completed_slave_jobs'],
                         sha256=hashlib.sha256(after['pixels']).hexdigest()))
    report = dict(passed=True, region=args.region, visible_characters_distinct=True, gameplay_ticks_frozen=True,
                  pause_overlay=False, scenes=rows, host_fallbacks=fallbacks,
                  roms=[dict(path=str(project), sha256=hashlib.sha256((project / 'build/AITD32X.32x').read_bytes()).hexdigest()) for project in (reference, root)])
    (root / 'build' / f'contact-native-parity-{args.region.lower()}.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
