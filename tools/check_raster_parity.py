#!/usr/bin/env python3
"""Compare every prepared prop with a preceding or current ordinary renderer."""
import argparse
import ctypes as C
import json
import shutil
import struct
import tempfile
from contextlib import nullcontext
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--reference', type=Path,
                      help='Reference project containing build/libaitd32x.so')
    mode.add_argument('--ordinary', action='store_true',
                      help='Compare with the current ordinary draw using a private asset bank')
    parser.add_argument('--project', type=Path,
                        default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    new = args.project.resolve()
    bank = (new / 'assets/bank.bin').read_bytes()
    manifest = json.loads((new / 'assets/manifest.json').read_text())
    assets = {entry['name']: (entry, bank[entry['offset']:entry['offset'] + entry['packed_size']])
              for entry in manifest['assets']}
    program = assets['STATIC_RASTERS'][1]
    expected = struct.unpack_from('>I', program)[0]
    keys = {struct.unpack_from('>2I', program, 4 + 12 * i) for i in range(expected)}
    objects_data = assets['OBJECTS'][1]
    assert len(objects_data) % 52 == 0, 'Malformed original object table'
    objects = [struct.unpack_from('>26h', objects_data, i * 52)
               for i in range(len(objects_data) // 52)]

    # A separate library copy owns independent host state. Disable prepared
    # programs only in its private bank; source/generated assets remain intact.
    temporary = tempfile.TemporaryDirectory(prefix='aitd-raster-parity-') if args.ordinary else nullcontext()
    with temporary as directory:
        current_path = new / 'build/libaitd32x.so'
        if args.ordinary:
            ordinary_path = Path(directory) / 'libaitd32x-ordinary.so'
            shutil.copy2(current_path, ordinary_path)
            ordinary_bank = bytearray(bank)
            struct.pack_into('>I', ordinary_bank, assets['STATIC_RASTERS'][0]['offset'], 0)
            buffers = [C.create_string_buffer(bytes(ordinary_bank)), C.create_string_buffer(bank)]
            paths = [ordinary_path, current_path]
        else:
            buffers = [C.create_string_buffer(bank), C.create_string_buffer(bank)]
            paths = [args.reference.resolve() / 'build/libaitd32x.so', current_path]
        libs = [C.CDLL(str(path)) for path in paths]
        for lib, buffer in zip(libs, buffers):
            lib.host_init.argtypes = [C.c_void_p, C.c_uint]
            lib.host_pixels.restype = lib.host_prop_spans.restype = C.c_void_p
            lib.host_init(buffer, len(bank))

        # This key selects resource records, without duplicating rendering.
        # The independent ordinary/prepared paths compare pixels, masks, bounds
        # and coverage spans using the same original pose.
        base = assets['GAME_PALETTE'][0]['offset']

        def key(character, obj, beta):
            value = 2166136261
            fields = [assets[f'MODEL_{character}_{obj[1]}'][0]['offset'] - base,
                      obj[14], obj[15], *obj[8:12], beta, obj[13]]
            for field in fields:
                value = ((value ^ (field & 0xffffffff)) * 16777619) & 0xffffffff
            return value

        def draw(lib, character, body, floor, room, camera, pose, bounds):
            count = lib.host_prop_draw(character, body, floor, room, camera, *pose, bounds, 5)
            assert 0 <= count <= 4096, ('Coverage fixture capacity', count)
            return (C.string_at(lib.host_pixels(), 320 * 224),
                    C.string_at(lib.host_prop_spans(), count * 4),
                    tuple(lib.host_prop_bound(i) for i in range(4)))

        seen = set()
        comparisons = 0
        for floor, (_, cameras) in enumerate(manifest['levels']):
            for camera in range(cameras):
                for obj in objects:
                    body, room = obj[1], obj[15]
                    if body < 0 or obj[14] != floor:
                        continue
                    for character in (0, 1):
                        angles = sorted({obj[12], 0, 256, 512, 768}) if body in (25, 34) else [obj[12]]
                        for beta in angles:
                            pose_key = (floor * 256 + camera, key(character, obj, beta))
                            if pose_key not in keys or pose_key in seen:
                                continue
                            seen.add(pose_key)
                            for bounds in (1, 3):
                                results = [draw(lib, character, body, floor, room, camera,
                                                (*obj[8:12], beta, obj[13]), bounds)
                                           for lib in libs]
                                assert results[0] == results[1], (
                                    'Raster parity', character, floor, room, camera, body, beta, bounds,
                                    sum(a != b for a, b in zip(results[0][0], results[1][0])))
                                comparisons += 1
        assert seen == keys, ('Unvisited prepared poses', len(seen), len(keys), sorted(keys - seen))

        # Exercise fallback for relocated and nonorthogonal door geometry.
        obj = next(obj for obj in objects if obj[14] == 1 and obj[15] == 2 and obj[1] == 34)
        for beta, shift in [(128, 0), (384, 0), (256, 47)]:
            results = [draw(lib, 0, 34, 1, 2, 2,
                            (obj[8] + shift, *obj[9:12], beta, obj[13]), 3)
                       for lib in libs]
            assert results[0] == results[1], ('Fallback', beta, shift)

    report = {'mode': 'ordinary' if args.ordinary else 'reference',
              'compiled_entries': len(keys), 'pixel_and_coverage_comparisons': comparisons,
              'bounds_modes': [1, 3], 'moved_rotating_fallback_comparisons': 3, 'exact': True}
    output = 'raster-parity-ordinary.json' if args.ordinary else 'raster-parity-v13.json'
    (new / 'build' / output).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
