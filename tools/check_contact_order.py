#!/usr/bin/env python3
"""Check contact repair against a three-model per-pixel depth oracle.

Actual attic character, chest and item/furniture geometry is placed in private
host memory. One middle model is deliberately marked foundable, which excludes
it from the initial character/prop contact selection. The fixture checks that
it cannot then be promoted above the nearer chest by a foreground replay.
Neither the original resource files nor user saves are changed.
"""
import argparse
import ctypes as C
import hashlib
import json
import struct
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument('--library', type=Path, default=root / 'build/libaitd32x.so')
    parser.add_argument('--record-before', action='store_true',
                        help='Record the known defect instead of requiring corrected pixels.')
    parser.add_argument('--report', type=Path, default=root / 'build/contact-order.json')
    args = parser.parse_args()
    lib = C.CDLL(str(args.library.resolve()))
    lib.host_init.argtypes = [C.c_void_p, C.c_uint]
    lib.host_pixels.restype = C.c_void_p
    original = (root / 'assets/bank.bin').read_bytes()
    assets = {a['name']: a for a in json.loads((root / 'assets/manifest.json').read_text())['assets']}
    rows = []

    def pixels():
        return C.string_at(lib.host_pixels(), 320 * 224)[12 * 320:212 * 320]

    for character in (0, 1):
        for fixture, middle, body, middle_dx, front_dx in (
                ('foundable item', 13, 9, -350 if character else -250, -50),
                ('foundable furniture', 4, 2, -50, -250)):
            for ownership in (False, True):
                data = bytearray(original)
                if ownership:
                    # Preserve vertices, primitives and materials; distinguish
                    # surface ownership without relying on their normal colors.
                    for model, color in ((0, 210), (body, 211), (12, 212)):
                        base = assets[f'MODEL_{character}_{model}']['offset']
                        count = struct.unpack_from('>H', data, base + 6)[0]
                        directory = struct.unpack_from('>I', data, base + 32)[0]
                        for index in range(count):
                            primitive = base + struct.unpack_from('>I', data, base + directory + 4 * index)[0]
                            data[primitive + 2] = color
                    # Prepared draws contain original colors, so only the
                    # copied diagnostic bank disables their lookup.
                    base = assets['STATIC_RASTERS']['offset']
                    data[base:base + 4] = bytes(4)
                bank = C.create_string_buffer(bytes(data))
                for pipeline in ('cached', 'uncached'):
                    lib.host_init(bank, len(data))
                    lib.host_begin_world(character, 0, 0, 3)
                    for slot in range(50):
                        object_id = lib.host_active(slot, 0)
                        if object_id >= 0 and object_id not in (0, 1, middle):
                            lib.host_delete(object_id)
                    for object_id in (0, middle):
                        lib.host_set_object(object_id, 17, -1)
                    lib.host_set_object(middle, 2, 128)
                    lib.host_place(1, 0, 0, -4000, 0, 1200, 0)
                    lib.host_bounds(1, 2)
                    lib.host_place(middle, 0, 0, -4000 + middle_dx, 0, 1200 - middle_dx // 2, 0)
                    lib.host_bounds(middle, 3)
                    lib.host_place(0, 0, 0, -4000 + front_dx, 0, 1200 - front_dx // 2, 768)
                    lib.host_bounds(0, 3)
                    order = [lib.host_draw_order(index) for index in range(4)]
                    assert order == [1, middle, 0, -1], ('fixture lost middle layer', fixture, character, order)
                    draw = lib.host_draw_cached if pipeline == 'cached' else lib.host_draw_uncached_scene
                    for physical_bank in (0, 1, 0, 1):
                        lib.host_buffer(physical_bank)
                        draw()
                        actual = pixels()
                        boxes = {object_id: [lib.host_render_bound(object_id, field) for field in range(4)]
                                 for object_id in (0, 1, middle)}
                        a, b = boxes[1], boxes[0]
                        area = [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]
                        assert area[0] <= area[2] and area[1] <= area[3], ('no contact', boxes)
                        assert lib.host_resolve_group3(*order[:3], *area), ('oracle exceeded capacity', fixture)
                        expected = pixels()
                        differences = sum(a != b for a, b in zip(actual, expected))
                        promoted = sum(a == 211 and b == 210 for a, b in zip(actual, expected)) if ownership else None
                        if not args.record_before:
                            assert differences == 0, (fixture, character, pipeline, physical_bank, differences, promoted)
                        assert not lib.host_world(3), ('script fault', fixture, character)
                        rows.append(dict(fixture=fixture, character=character, ownership_colors=ownership,
                                         pipeline=pipeline, bank=physical_bank, area=area,
                                         changed_pixels=differences, incorrectly_promoted_pixels=promoted,
                                         sha256=hashlib.sha256(actual).hexdigest()))
    if args.record_before:
        assert any(row['incorrectly_promoted_pixels'] for row in rows), 'Baseline no longer reproduces defect.'
    report = dict(passed=not args.record_before, recorded_before=args.record_before,
                  library_sha256=hashlib.sha256(args.library.read_bytes()).hexdigest(),
                  oracle='stable three-model reciprocal-depth group in the original character/chest contact area',
                  fixtures_in_memory_only=True, comparisons=len(rows), scenes=rows)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=report['passed'], comparisons=len(rows),
                          changed_pixels=sum(row['changed_pixels'] for row in rows),
                          report=str(args.report)), indent=2))


if __name__ == '__main__':
    main()
