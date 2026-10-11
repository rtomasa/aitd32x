#!/usr/bin/env python3
"""Check pushed attic furniture against the window's separating plane.

Original models in their fixture poses lie on opposite sides of world Z=4972:
the cupboard ends there, whereas the window starts at 5000. The camera is at
Z=1160, so every shared ray reaches the cupboard first. This expectation is
independent of the engine's pair sorting or its overlapping camera-Z ranges.
Fixtures use private host memory and do not modify resources or user saves.
"""
import argparse
import ctypes as C
import hashlib
import json
import struct
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, default=root / 'build/libaitd32x.so')
    parser.add_argument('--record-before', action='store_true')
    parser.add_argument('--report', type=Path, default=root / 'build/window-furniture.json')
    args = parser.parse_args()
    data = (root / 'assets/bank.bin').read_bytes()
    entries = {entry['name']: entry for entry in
               json.loads((root / 'assets/manifest.json').read_text())['assets']}
    lib = C.CDLL(str(args.library.resolve()))
    lib.host_init.argtypes = [C.c_void_p, C.c_uint]
    lib.host_pixels.restype = C.c_void_p
    bank = C.create_string_buffer(data)

    def asset(name):
        entry = entries[name]
        return data[entry['offset']:entry['offset'] + entry['packed_size']]

    def vertices(name):
        model = asset(name)
        count = struct.unpack_from('>H', model, 2)[0]
        offset = struct.unpack_from('>I', model, 20)[0]
        points = [list(struct.unpack_from('>3h', model, offset + index * 6)) for index in range(count)]
        # The opened cupboard has two hinged groups. This fixture keeps the
        # original zero-angle bind state, requiring only its anchor offsets.
        groups = struct.unpack_from('>H', model, 4)[0]
        group_offset = struct.unpack_from('>I', model, 24)[0]
        for index in range(groups):
            group = struct.unpack_from('>3H2b4h', model, group_offset + index * 16)
            assert group[5:] == (0, 0, 0, 0), ('Fixture bind state is not identity', name, group)
            start, size, anchor = group[:3]
            delta = points[anchor].copy()
            for point in points[start:start + size]:
                for axis in range(3):
                    point[axis] += delta[axis]
        return points

    camera, room = asset('CAMERA_0_2'), asset('ROOM_0_0')
    camera_z = (struct.unpack_from('>h', room, 4)[0] -
                struct.unpack_from('>h', camera, 10)[0]) * 10
    rows = []
    for character in range(2):
        for body in (2, 3):
            for window in (5, 6):
                cupboard_z = [point[2] + 4540 for point in vertices(f'MODEL_{character}_{body}')]
                window_z = [point[2] + 5000 for point in vertices(f'MODEL_{character}_{window}')]
                assert camera_z < min(cupboard_z) <= max(cupboard_z) < min(window_z)
                for x in (-1800, -1200, -600, 0, 600, 1200):
                    for pipeline in ('cached', 'uncached'):
                        lib.host_init(bank, len(data))
                        lib.host_begin_world(character, 0, 0, 2)
                        # Hide the player from this two-surface proof; the
                        # ordinary contact checks cover player/prop depth.
                        lib.host_set_object(1, 1, -1)
                        lib.host_set_object(4, 1, body)
                        lib.host_set_object(7, 1, window)
                        lib.host_place(4, 0, 0, x, 0, 4540, 0)
                        lib.host_clear_message()
                        lib.host_camera(0, 0, 2)
                        order = [lib.host_draw_order(index) for index in range(50)]
                        order = order[:order.index(-1)]
                        correctly_ordered = order.index(7) < order.index(4)
                        draw = (lib.host_draw_cached if pipeline == 'cached' else
                                lib.host_draw_uncached_scene)
                        for physical_bank in (0, 1, 0, 1):
                            lib.host_buffer(physical_bank)
                            draw()
                            actual = C.string_at(lib.host_pixels(), 320 * 224)
                            # Repaint the independently nearer cupboard last.
                            # Its masks and normal primitive order stay intact;
                            # only a misplaced window can change these pixels.
                            lib.host_draw_actor(4)
                            expected = C.string_at(lib.host_pixels(), 320 * 224)
                            changed = sum(a != b for a, b in zip(actual, expected))
                            if not args.record_before:
                                assert correctly_ordered and not changed, (
                                    character, body, window, x, pipeline, physical_bank, order, changed)
                            assert not lib.host_world(3), ('script fault', character, x)
                            rows.append(dict(character=character, furniture_body=body,
                                window_body=window, furniture_x=x, pipeline=pipeline,
                                bank=physical_bank, order=order, window_before_furniture=correctly_ordered,
                                incorrectly_overdrawn_pixels=changed,
                                furniture_z=[min(cupboard_z), max(cupboard_z)],
                                window_z=[min(window_z), max(window_z)]))
    regressions = [row for row in rows if row['incorrectly_overdrawn_pixels']]
    if args.record_before:
        assert regressions, 'Reference does not reproduce the window-over-cupboard defect'
    report = dict(passed=not args.record_before, recorded_before=args.record_before,
                  comparisons=len(rows), camera_z=camera_z,
                  oracle='Disjoint original mesh Z ranges and an independent nearer-cupboard repaint',
                  host_sha256=hashlib.sha256(args.library.read_bytes()).hexdigest(),
                  fixtures_in_memory_only=True, hardware_validation=False, scenes=rows)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=report['passed'], comparisons=len(rows),
                         incorrect_frames=len(regressions),
                         incorrect_pixels=sum(row['incorrectly_overdrawn_pixels'] for row in rows),
                         report=str(args.report)), indent=2))


if __name__ == '__main__':
    main()
