#!/usr/bin/env python3
"""Compare scenery-cache composition with the same uncached scene pipeline.

The oracle uses ordinary world order, architectural masks, contact depth,
effects and lighting, but never bakes actors. Fixtures live in private host
memory and do not open battery saves. This detects cache/order regressions;
it is not an oracle for the original game's chosen painter order. An optional
preserved library instead checks exact pixels across renderer implementations.
"""
import argparse
import ctypes as C
import hashlib
import json
import shutil
import struct
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENE = slice(12 * 320, 212 * 320)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sweep', action='store_true',
                        help='Also sample original prop-adjacent poses in every camera, for both characters')
    parser.add_argument('--audit', action='store_true',
                        help='Record mismatches without requiring zero differences')
    parser.add_argument('--library', type=Path, default=ROOT / 'build/libaitd32x.so',
                        help='Host library to compare with its uncached oracle')
    parser.add_argument('--reference-library', type=Path,
                        help='Compare cached pixels with a preserved renderer instead of the uncached oracle')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/draw-order-cache.json')
    args = parser.parse_args()
    library = args.library.resolve()
    bank = (ROOT / 'assets/bank.bin').read_bytes()
    memory = C.create_string_buffer(bank)
    manifest = json.loads((ROOT / 'assets/manifest.json').read_text())
    entries = {entry['name']: entry for entry in manifest['assets']}
    checks, failures, views = [], [], set()

    with tempfile.TemporaryDirectory(prefix='draw-order-cache-', dir=ROOT / 'build') as temporary:
        duplicate = Path(temporary) / library.name
        shutil.copyfile(args.reference_library.resolve() if args.reference_library else library, duplicate)
        cached, oracle = [C.CDLL(str(path)) for path in (library, duplicate)]
        libraries = (cached, oracle)
        for lib in libraries:
            lib.host_init.argtypes = [C.c_void_p, C.c_uint]
            lib.host_pixels.restype = C.c_void_p
            lib.host_cache_slots.restype = C.c_uint64
            lib.host_init(memory, len(bank))

        def initialize(character, floor, room, camera, contact=True):
            for lib in libraries:
                lib.host_begin_world(character, floor, room, camera)
                lib.host_clear_message()
                if not contact:
                    # Isolate cached masks: contact depth otherwise repairs
                    # this cabinet independently and conceals the cache error.
                    lib.host_set_object(1, 2, lib.host_object(1, 2) & ~64)
            views.add((floor, camera))

        def compare(label, character, floor, room, camera, pose, physical_bank):
            for lib in libraries:
                lib.host_place(1, floor, room, *pose)
                lib.host_buffer(physical_bank)
            before = [[cached.host_object(identifier, field) for field in range(26)]
                      for identifier in range(292)]
            cached.host_draw_cached()
            if args.reference_library:
                oracle.host_draw_cached()
            else:
                oracle.host_draw_uncached_scene()
            images = [C.string_at(lib.host_pixels(), 320 * 224)[SCENE] for lib in libraries]
            different = [index for index, (a, b) in enumerate(zip(*images)) if a != b]
            after = [[cached.host_object(identifier, field) for field in range(26)]
                     for identifier in range(292)]
            assert before == after, (label, 'render changed object state')
            assert not cached.host_world(3) and not oracle.host_world(3), (label, 'LIFE fault')
            row = dict(case=label, character=character, floor=floor, room=room,
                       camera=camera, pose=list(pose), bank=physical_bank,
                       different_pixels=len(different),
                       static_slots=f'{cached.host_cache_slots(0):013x}')
            # The painter spot-check uses the uncached oracle's framebuffer
            # lifecycle; a preserved cached renderer owns a persistent bake.
            if not args.reference_library and label == 'contact foreground footprint' and pose[0] == -1200:
                # This foreground replay extends outside the repaired contact
                # area. The untouched door pixels must retain painter output,
                # rather than merely agreeing with an overdrawn oracle.
                oracle.host_draw_painter()
                painter = C.string_at(oracle.host_pixels(), 320 * 224)[SCENE]
                for y in range(44, 48):
                    index = y * 320 + 195
                    assert images[0][index] == images[1][index] == painter[index], (
                        label, 'foreground replay changed untouched scenery', character, y)
            checks.append(row)
            if different:
                row['difference_bounds'] = [min(index % 320 for index in different),
                                            min(index // 320 for index in different),
                                            max(index % 320 for index in different),
                                            max(index // 320 for index in different)]
                failures.append(row)

        # Original flags are retained in the public-scene fixtures. The
        # cupboard's mask-only fixture additionally isolates shared replay.
        fixtures = [('bedroom foreground', 1, 2, 3, (3000, 0, 1400, 0), True),
                    ('dining-room foreground', 1, 4, 6, (-700, 0, -2700, 0), True),
                    ('library foreground', 1, 5, 7, (-2690, 0, -2780, 0), True),
                    ('contact foreground footprint', 3, 4, 22, (-1200, 0, -3190, 0), True),
                    ('cabinet mask isolation', 1, 3, 11, (-400, -150, 500, 0), False)]
        for character in (0, 1):
            for label, floor, room, camera, pose, contact in fixtures:
                initialize(character, floor, room, camera, contact)
                # Move across the footprint in both physical framebuffer
                # histories, then return to the original overlapping pose.
                for index, dx in enumerate((0, 80, -80, 0, 0, 0)):
                    moved = (pose[0] + dx, *pose[1:])
                    compare(label, character, floor, room, camera, moved, index & 1)

        if args.sweep:
            for character in (0, 1):
                for floor, (room_count, _) in enumerate(manifest['levels']):
                    for room in range(room_count):
                        entry = entries[f'ROOM_{floor}_{room}']
                        data = bank[entry['offset']:entry['offset'] + entry['packed_size']]
                        count = struct.unpack_from('>H', data, 6)[0]
                        offset = struct.unpack_from('>I', data, 12)[0]
                        cameras = struct.unpack_from('>' + 'H' * count, data, offset)
                        for camera in cameras:
                            # A view shared by several linked rooms is tested
                            # from each room, because mask tests are room based.
                            initialize(character, floor, room, camera)
                            ids = [cached.host_active(slot, 0) for slot in range(50)]
                            props = [identifier for identifier in ids if identifier > 1 and
                                     cached.host_object(identifier, 15) == room and
                                     cached.host_object(identifier, 1) >= 0]
                            poses = [(0, 0, 0, 0)]
                            for prop in props[:3]:
                                x, z = [cached.host_object(prop, field) for field in (8, 10)]
                                poses.extend(((x, 0, z - 700, 0), (x + 700, 0, z, 0)))
                            for index, pose in enumerate(poses):
                                compare('full-house sampled overlap', character, floor, room,
                                        camera, pose, index & 1)
            assert len(views) == sum(level[1] for level in manifest['levels']), 'missing camera coverage'

    report = dict(passed=not failures, comparisons=len(checks),
                  camera_views=len(views), full_house_sweep=args.sweep,
                  oracle=('Preserved renderer with scenery cache' if args.reference_library else
                          'Same engine scene pipeline with all actors dynamic; no scenery bake'),
                  scope='Cache composition and framebuffer histories, not DOS visual or hardware validation',
                  host_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),
                  bank_sha256=hashlib.sha256(bank).hexdigest(), failures=failures,
                  checks=checks)
    if args.reference_library:
        report['reference_sha256'] = hashlib.sha256(args.reference_library.read_bytes()).hexdigest()
    if hasattr(cached, 'renderer_contact_stats'):
        report['contact_cache'] = dict(hits=cached.renderer_contact_stats(4),
                                       builds=cached.renderer_contact_stats(5),
                                       capacity_failures=cached.renderer_contact_stats(6),
                                       negative_hits=cached.renderer_contact_stats(7))
    path = args.output
    path.write_text(json.dumps(report, indent=2) + '\n')
    summary = {key: value for key, value in report.items() if key not in ('checks', 'failures')}
    summary['failed_comparisons'] = len(failures)
    summary['first_failures'] = failures[:3]
    print(json.dumps(summary, indent=2))
    if not args.audit:
        assert not failures, f'{len(failures)} cache composition mismatches; see {path}'


if __name__ == '__main__':
    main()
