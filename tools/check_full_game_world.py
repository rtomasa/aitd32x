#!/usr/bin/env python3
"""Focused full-house activation, original stairs and compact-pose checks.

Uses private host state only. No emulator or user's battery saves are opened.
Build the host library and import the complete original assets before running.
"""
import argparse
import ctypes as C
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path,
                        help='Preserved preceding host library and assets for early-world state parity')
    args = parser.parse_args()
    bank = (ROOT / 'assets/bank.bin').read_bytes()
    manifest = json.loads((ROOT / 'assets/manifest.json').read_text())
    entries = {entry['name']: entry for entry in manifest['assets']}
    memory = C.create_string_buffer(bank)
    lib = C.CDLL(str(ROOT / 'build/libaitd32x.so'))
    lib.host_init.argtypes = [C.c_void_p, C.c_uint]
    lib.host_pixels.restype = C.c_void_p
    lib.host_init(memory, len(bank))

    def asset(name):
        entry = entries[name]
        return bank[entry['offset']:entry['offset'] + entry['packed_size']]

    def healthy(context):
        assert lib.host_world(3) == 0, (context, 'LIFE fault',
                                       [lib.host_world(i) for i in (3, 4, 5)])
        assert not lib.host_world(14), (context, 'world finished')

    cases, views, auxiliary, peak = [], set(), [], 0
    for character in range(2):
        for floor, (rooms, cameras) in enumerate(manifest['levels']):
            assert rooms and cameras, ('missing floor', floor)
            for room in range(rooms):
                data = asset(f'ROOM_{floor}_{room}')
                count = struct.unpack_from('>H', data, 6)[0]
                offset = struct.unpack_from('>I', data, 12)[0]
                if not count:
                    if not character:
                        auxiliary.append([floor, room])
                    continue
                for camera in struct.unpack_from('>' + str(count) + 'H', data, offset):
                    assert camera < cameras, ('room camera range', floor, room, camera)
                    assert entries[f'CAMERA_{floor}_{camera}']['type'] == 3
                    assert entries[f'BACKGROUND_{floor}_{camera}']['unpacked_size'] == 64000
                    lib.host_begin_world(character, floor, room, camera)
                    healthy((character, floor, room, camera))
                    ids = [lib.host_active(slot, 0) for slot in range(50)]
                    active = [identifier for identifier in ids if identifier >= 0]
                    assert 1 in active and len(active) == len(set(active))
                    assert all(lib.host_object(identifier, 0) == slot
                               for slot, identifier in enumerate(ids) if identifier >= 0)
                    peak = max(peak, len(active))
                    cases.append([character, floor, room, camera, len(active)])
                    views.add((floor, camera))
    assert len(views) == sum(level[1] for level in manifest['levels']), ('unvisited views', views)
    assert peak >= 36 and peak <= 50, ('full-house actor capacity', peak)

    stairs = []
    for character in range(2):
        # Original floor-1 tower staircase, scenario zone 2. Placement avoids
        # travel; the original zone, floor LIFE and track perform the transition.
        lib.host_begin_world(character, 1, 7, 14)
        lib.host_place(1, 1, 7, 300, 0, 3890, 512)
        for tick in range(700):
            lib.host_world_tick(0, 0)
            healthy(('stairs to floor 2', character, tick))
            if lib.host_world(0) == 2 and lib.host_object(1, 23) == 1:
                break
        else:
            raise AssertionError(('stairs timeout', character,
                                  [lib.host_world(i) for i in (0, 1, 2)],
                                  [lib.host_object(1, i) for i in (8, 9, 10, 23, 24, 25)]))
        stairs.append(dict(character=character, ticks=tick + 1,
                           floor=lib.host_world(0), room=lib.host_world(1)))

    lib.host_begin_world(0, 0, 0, 0)
    lib.host_movemode(21, 2, 1)
    lib.host_track(21)
    assert lib.host_speed(21) == 4, 'Original follow mode must begin walking'
    lib.host_startgame(0)
    assert lib.host_check_contact_capacity(), 'Contact scratch must handle all 50 actors and reject larger groups'

    parity = []
    if args.reference:
        previous = C.CDLL(str((args.reference / 'libaitd32x.so').resolve()))
        previous_bank = C.create_string_buffer((args.reference / 'assets/bank.bin').read_bytes())
        previous.host_init.argtypes = [C.c_void_p, C.c_uint]
        previous.host_pixels.restype = C.c_void_p
        previous.host_init(previous_bank, len(previous_bank) - 1)
        bones = [struct.unpack_from('>H', asset(f'MODEL_0_{model}'), 4)[0]
                 for model in range(272)]

        def snapshot(engine):
            return ([engine.host_world(i) for i in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14)],
                    [[engine.host_object(i, field) for field in range(26)] for i in range(292)],
                    [engine.host_variable(i) for i in range(207)],
                    [[engine.host_group(identifier, bone, field) for field in range(4)]
                     for identifier in (1, 9, 21) if engine.host_object(identifier, 0) >= 0
                     for bone in range(bones[engine.host_object(identifier, 1)]
                                       if engine.host_object(identifier, 1) >= 0 else 0)],
                    # Exclude native information rows; all geometry above
                    # them must retain exact pixels through cache changes.
                    C.string_at(engine.host_pixels(), 320 * 224)[320 * 12:320 * 192])

        for character in range(2):
            for scenario in ('idle', 'walk', 'open', 'stairs', 'throw'):
                for engine in (previous, lib):
                    engine.host_startgame(character)
                    if scenario == 'open':
                        engine.host_place(1, 0, 0, -6000, 0, -395, 256)
                        engine.host_found_life(2, 64)
                    elif scenario == 'stairs':
                        engine.host_place(1, 0, 0, 6830, 0, 2900, 0)
                    elif scenario == 'throw':
                        engine.host_take(3)
                        engine.host_found_life(3, 512)
                for tick in range(320 if scenario == 'stairs' else 120):
                    pad = (1 if tick < 60 else 4 if tick < 90 else 2) if scenario == 'walk' else 65 if scenario == 'open' else 0
                    previous.host_tick(pad)
                    lib.host_tick(pad)
                    assert snapshot(previous) == snapshot(lib), ('early-world parity', character, scenario, tick)
                parity.append(dict(character=character, scenario=scenario, ticks=tick + 1,
                                   geometry_pixel_parity=True))

    report = dict(passed=True, rooms=sum(level[0] for level in manifest['levels']),
                  cameras=len(views), activation_cases=len(cases), peak_initial_actors=peak,
                  auxiliary_rooms_without_camera=auxiliary, stairs=stairs,
                  follow_speed=4, contact_actor_capacity=50, cases=cases, early_world_parity=parity,
                  bank_sha256=hashlib.sha256(bank).hexdigest(),
                  hardware_validation=False)
    (ROOT / 'build/full-game-world.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'{report["rooms"]} room resources, {len(views)} views, {len(cases)} activation cases; '
          f'peak {peak}/50 actors; both original floor-2 stair transitions passed.')


if __name__ == '__main__':
    main()
