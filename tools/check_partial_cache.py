#!/usr/bin/env python3
"""Compare partial scenery repairs to forced rebuilds, using two host banks.

All placements and optional material changes are in-memory fixtures. No saves
or asset files are read back or overwritten. The second library is an isolated
copy of the same host build, so renderer/cache state cannot alias the oracle.
"""
import argparse
import ctypes as C
import hashlib
import json
import shutil
import struct
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.project.resolve()
    library = root / 'build/libaitd32x.so'
    original_bank = (root / 'assets/bank.bin').read_bytes()
    manifest = json.loads((root / 'assets/manifest.json').read_text())
    assets = {asset['name']: asset for asset in manifest['assets']}
    rows = []
    with tempfile.TemporaryDirectory(prefix='partial-cache-', dir=root / 'build') as temporary:
        duplicate = Path(temporary) / library.name
        shutil.copy2(library, duplicate)
        libs = [C.CDLL(str(path)) for path in (library, duplicate)]
        for lib in libs:
            lib.host_init.argtypes = [C.c_void_p, C.c_uint]
            lib.host_pixels.restype = lib.host_background.restype = C.c_void_p
            lib.host_cache.restype = C.c_uint

        def both(name, *values):
            for lib in libs:
                getattr(lib, name)(*values)

        def cache():
            lib = libs[0]
            return dict(signature=lib.host_cache(0, 0), slots=lib.host_cache(1, 0),
                        hashes=[lib.host_cache(4, slot) for slot in range(24)],
                        owners=[lib.host_cache(5, slot) for slot in range(24)])

        def order_only(before, after):
            slots = before['slots']
            return (before['signature'] != after['signature'] and
                    bool(before['signature']) and slots == after['slots'] and
                    all(before['hashes'][slot] == after['hashes'][slot] and
                        before['owners'][slot] == after['owners'][slot]
                        for slot in range(24) if slots & (1 << slot)))

        def compare(label):
            for api, size in [('host_pixels', 320 * 224), ('host_background', 64000)]:
                images = [C.string_at(getattr(lib, api)(), size) for lib in libs]
                assert images[0] == images[1], (label, api, sum(a != b for a, b in zip(*images)))
            state = [[lib.host_world(field) for field in range(18)] for lib in libs]
            assert state[0] == state[1], (label, 'world state', state)
            assert not state[0][3], (label, 'script fault', state[0])

        def draw(bank, label):
            both('host_buffer', bank)
            before = cache()
            libs[0].host_draw_cached()
            after = cache()
            libs[1].host_draw_fresh()
            compare(label)
            return order_only(before, after)

        def tick(pad, bank, label):
            both('host_buffer', bank)
            before = cache()
            both('host_tick', pad)
            after = cache()
            libs[1].host_draw_fresh()
            compare(label)
            return order_only(before, after)

        def initialize(data, character, room=2, camera=9):
            nonlocal bank
            bank = C.create_string_buffer(data)
            both('host_init', bank, len(data))
            if character:
                both('host_tick', 32)
                both('host_tick', 0)
            both('host_tick', 128)
            both('host_tick', 0)
            both('host_place', 1, 1, room, 700, 0, 1700, 512)
            both('host_set_variable', 33, 1)
            for index in range(50):
                tick(0, index & 1, ('settle', character, index))
            both('host_camera', 1, room, camera)
            for physical_bank in (0, 1):
                draw(physical_bank, ('warm bank', physical_bank))

        bank = None
        for character in (0, 1):
            initialize(original_bank, character)
            both('host_set_object', 33, 12, 256)
            both('host_bounds', 33, 3)
            both('host_camera', 1, 2, 9)
            partial = 0
            frames = 0
            entered_hall = False
            for phase, count, pad in [('settle', 75, 0), ('crossing', 20, 1), ('hall', 200, 0)]:
                for index in range(count):
                    partial += tick(pad, frames & 1, (character, phase, index))
                    frames += 1
                    entered_hall |= libs[0].host_world(1) == 1
            assert entered_hall, ('did not enter hallway', character)
            rows.append(dict(character=character, scenario='bedroom/hall route',
                             compared_frames=frames + 52, partial_order_repairs=partial,
                             pixels_background_and_world_equal=True))

            # Place an earlier valid cache ordering in the framebuffer, then
            # let Game::Draw repair it from unchanged hashes/owners/geometry.
            # Overlapping door models supply a definite order-dependent image.
            # The material fixture combines opaque black and glass polygons,
            # including the real camera masks of the bedroom scene.
            for material_fixture in (False, True):
                data = bytearray(original_bank)
                if material_fixture:
                    for body, color, material in ((25, 0, 0), (34, 23, 2)):
                        asset = assets[f'MODEL_{character}_{body}']
                        base = asset['offset']
                        primitive_count = struct.unpack_from('>H', data, base + 6)[0]
                        primitive_table = struct.unpack_from('>I', data, base + 32)[0]
                        changed = 0
                        for index in range(primitive_count):
                            offset = struct.unpack_from('>I', data, base + primitive_table + 4 * index)[0]
                            primitive = base + offset
                            if data[primitive] == 1:
                                data[primitive + 2:primitive + 4] = bytes((color, material))
                                changed += 1
                        assert changed, ('no fixture polygons', body)
                    # Prepared programs contain the original colors. Disable
                    # their lookup in this copied bank to shade mutated models.
                    data[assets['STATIC_RASTERS']['offset']:assets['STATIC_RASTERS']['offset'] + 4] = bytes(4)
                initialize(bytes(data), character)
                for object_id in (29, 33):
                    both('host_set_object', object_id, 17, -1)
                pose = [libs[0].host_object(33, field) for field in (8, 9, 10, 12)]
                both('host_place', 29, 1, 2, *pose)
                for index in range(30):
                    tick(0, index & 1, ('overlapping props', character, material_fixture, index))
                expected = C.string_at(libs[1].host_background(), 64000)
                repairs = 0
                changed_pixels = 0
                for physical_bank in (0, 1):
                    both('host_buffer', physical_bank)
                    libs[0].host_reverse_static_cache()
                    altered = C.string_at(libs[0].host_background(), 64000)
                    changed_pixels += sum(a != b for a, b in zip(altered, expected))
                    repairs += draw(physical_bank, ('reversed bake', character, material_fixture, physical_bank))
                    for next_bank in (physical_bank ^ 1, physical_bank):
                        draw(next_bank, ('after repaired bank', character, material_fixture, next_bank))
                assert repairs == 2, ('partial path not exercised on both banks', character, material_fixture, repairs)
                assert changed_pixels, ('reverse fixture did not change bake pixels', character, material_fixture)
                rows.append(dict(character=character, scenario='black/glass/masks' if material_fixture else 'reversed static order',
                                 repaired_banks=[0, 1], partial_order_repairs=repairs,
                                 repaired_pixel_changes=changed_pixels,
                                 pixels_background_and_world_equal=True))

            # Actual geometry invalidation changes cache membership and must
            # take the full path rather than trusting old coverage/footprints.
            before = cache()
            both('host_set_object', 33, 12, (libs[0].host_object(33, 12) + 128) & 1023)
            assert not draw(0, ('geometry invalidation', character))
            assert before['slots'] != cache()['slots'], ('geometry did not leave static cache', character)
            assert libs[0].host_cache(3, 1), ('full geometry rebuild did not invalidate opposite bank', character)
            draw(1, ('geometry opposite bank', character))
            both('host_camera', 1, 2, 8)
            for physical_bank in (0, 1):
                draw(physical_bank, ('camera fallback', character, physical_bank))
            rows.append(dict(character=character, scenario='geometry/camera full fallback',
                             checked_banks=[0, 1], pixels_background_and_world_equal=True))

    report = dict(passed=True, library_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),
                  oracle='independent instance forced to rebuild its complete scenery cache',
                  fixtures_in_memory_only=True, scenes=rows)
    path = root / 'build/partial-cache-parity.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
