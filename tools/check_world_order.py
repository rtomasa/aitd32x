#!/usr/bin/env python3
"""Check whole-house ordering of geometrically disjoint camera-depth ranges.

Uses original camera metadata and private host state, with no gameplay clock
advancement, emulator save files or original-resource writes. A preserved host
library can demonstrate the preceding comparator's ordering failures.
"""
import argparse
import ctypes as C
import hashlib
import itertools
import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path,
                        help='Pre-fix host library directory; optional assets/bank.bin, otherwise current bank')
    args = parser.parse_args()
    data = (ROOT / 'assets/bank.bin').read_bytes()
    manifest = json.loads((ROOT / 'assets/manifest.json').read_text())
    entries = {entry['name']: entry for entry in manifest['assets']}
    table = re.search(r'sine_table\[1024\]=\{([^}]+)',
                      (ROOT / 'src/engine/trig.cpp').read_text()).group(1)
    sine = [int(value) for value in table.split(',')]

    def asset(name):
        entry = entries[name]
        return data[entry['offset']:entry['offset'] + entry['packed_size']]

    def rotate(point, angles):
        # Original Y/X/Z Q15 camera transform, including signed truncation.
        def q15(value):
            return value // 32768 if value >= 0 else -((-value) // 32768)

        x, y, z = point
        for axis, angle in ((1, angles[1]), (0, angles[0]), (2, angles[2])):
            if not angle & 1023:
                continue
            sn, cs = sine[angle & 1023], sine[(angle + 256) & 1023]
            if axis == 1:
                x, z = q15(x * cs - z * sn), q15(x * sn + z * cs)
            elif axis == 0:
                y, z = q15(y * cs - z * sn), q15(y * sn + z * cs)
            else:
                x, y = q15(x * cs - y * sn), q15(x * sn + y * cs)
        return x, y, z

    libraries, banks = [], []
    paths = [ROOT / 'build'] + ([args.reference] if args.reference else [])
    for path in paths:
        library = C.CDLL(str((path / 'libaitd32x.so').resolve()))
        reference_bank = path / 'assets/bank.bin'
        bank = C.create_string_buffer(reference_bank.read_bytes() if reference_bank.exists() else data)
        library.host_init.argtypes = [C.c_void_p, C.c_uint]
        library.host_init(bank, len(bank) - 1)
        libraries.append(library)
        banks.append(bank)

    def order(library):
        ids = []
        for index in range(50):
            identifier = library.host_draw_order(index)
            if identifier < 0:
                break
            ids.append(identifier)
        assert len(ids) == len(set(ids)), ('duplicate draw slot', ids)
        return ids

    def inspect(library, floor, room, camera, position):
        library.host_begin_world(character, floor, room, camera)
        library.host_place(1, floor, room, *position, 0)
        ids = order(library)
        camera_data, room_data = asset(f'CAMERA_{floor}_{camera}'), asset(f'ROOM_{floor}_{room}')
        angles = struct.unpack_from('>3h', camera_data)
        cx, cy, cz = struct.unpack_from('>3h', camera_data, 6)
        rx, ry, rz = struct.unpack_from('>3h', room_data)
        origin = ((cx - rx) * 10, (ry - cy) * 10, (rz - cz) * 10)
        intervals = {}
        for identifier in ids:
            box = [library.host_box(identifier, field) for field in range(6)]
            corners = itertools.product(box[:2], box[2:4], box[4:6])
            depths = [rotate(tuple(value - offset for value, offset in zip(point, origin)), angles)[2]
                      for point in corners]
            intervals[identifier] = min(depths), max(depths)
        failures, constraints = [], 0
        for index, earlier in enumerate(ids):
            near_a, far_a = intervals[earlier]
            for later in ids[index + 1:]:
                near_b, far_b = intervals[later]
                if near_b >= far_a and near_a < far_b:
                    failures.append([earlier, later])
                if (near_a >= far_b and near_b < far_a) or (near_b >= far_a and near_a < far_b):
                    constraints += 1
        assert ids == order(library), ('unstable unchanged draw order', floor, room, camera)
        return failures, constraints

    cases, camera_views, previous_failures, constraints = 0, set(), [], 0
    # Sample several player positions without assuming that every original
    # room/view pair permits a playable camera-zone center.
    for character in range(2):
        for floor, (room_count, _) in enumerate(manifest['levels']):
            for room in range(room_count):
                room_data = asset(f'ROOM_{floor}_{room}')
                count = struct.unpack_from('>H', room_data, 6)[0]
                offset = struct.unpack_from('>I', room_data, 12)[0]
                for camera in struct.unpack_from('>' + str(count) + 'H', room_data, offset):
                    camera_views.add((floor, camera))
                    for position in ((0, 0, 0), (-300, 0, 0), (300, 0, 0), (0, 0, -300), (0, 0, 300)):
                        failures, checked = inspect(libraries[0], floor, room, camera, position)
                        assert not failures, ('separated depth drawn out of order', character,
                                              floor, room, camera, position, failures)
                        constraints += checked
                        if len(libraries) > 1:
                            failures, _ = inspect(libraries[1], floor, room, camera, position)
                            if failures:
                                previous_failures.append(dict(character=character, floor=floor,
                                    room=room, camera=camera, position=position, pairs=failures))
                        cases += 1

    fixtures = []
    for character in range(2):
        for floor, room, camera, position, behind, foreground in (
                (1, 4, 3, (0, 0, 0), 32, 29),
                (3, 3, 19, (1260, 0, 0), 145, 139),
                (3, 3, 19, (1260, 0, 0), 145, 140),
                (3, 3, 19, (1260, 0, 0), 1, 139),
                (3, 3, 19, (1260, 0, 0), 1, 140)):
            failures, _ = inspect(libraries[0], floor, room, camera, position)
            ids = order(libraries[0])
            assert not failures and ids.index(behind) < ids.index(foreground), (
                'known door ordering', character, floor, room, camera, behind, foreground, ids)
            fixtures.append([character, floor, room, camera, behind, foreground])
    assert len(camera_views) == sum(level[1] for level in manifest['levels'])
    if args.reference:
        assert previous_failures, 'Reference did not reproduce the ordering defect'
    report = dict(passed=True, sampled_cases=cases, views=len(camera_views),
                  disjoint_depth_constraints=constraints, known_door_fixtures=fixtures,
                  previous_failure_cases=previous_failures,
                  bank_sha256=hashlib.sha256(data).hexdigest(), hardware_validation=False)
    (ROOT / 'build/world-order.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'{cases} sampled room/view/position cases, {len(camera_views)} views, '
          f'{constraints} disjoint-depth constraints; known foreground doors pass.')


if __name__ == '__main__':
    main()
