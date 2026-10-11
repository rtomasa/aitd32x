#!/usr/bin/env python3
"""Check original near-face rejection in the reported bedroom/library door views.

The independent oracle physically removes primitives with a camera-space
vertex at Z <= 100, following FITD's processPrim_* rule, from a private asset
bank. It disables prepared drawing programs so those cannot conceal the rule.
Regular painting, scenery baking and contact depth then compare against that
pruned mesh. Original resources and battery-save files are never modified.
"""
import argparse
import ctypes as C
import hashlib
import json
import shutil
import struct
import tempfile
from pathlib import Path

from emulator_check import png

ROOT = Path(__file__).resolve().parents[1]
SCENE = slice(12 * 320, 212 * 320)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, default=ROOT / 'build/libaitd32x.so')
    parser.add_argument('--bank', type=Path, default=ROOT / 'assets/bank.bin')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/door-projection.json')
    parser.add_argument('--audit', action='store_true', help='Record pre-fix differences without failing')
    args = parser.parse_args()
    bank = args.bank.read_bytes()
    manifest = json.loads((ROOT / 'assets/manifest.json').read_text())
    entries = {entry['name']: entry for entry in manifest['assets']}
    checks, failures, proof = [], [], []
    temporary_root = ROOT / 'build'

    with tempfile.TemporaryDirectory(prefix='door-projection-', dir=temporary_root) as temporary:
        duplicate = Path(temporary) / 'oracle.so'
        shutil.copyfile(args.library, duplicate)
        candidate, oracle = [C.CDLL(str(path.resolve())) for path in (args.library, duplicate)]
        banks = [C.create_string_buffer(bank) for _ in range(2)]
        for lib in (candidate, oracle):
            lib.host_init.argtypes = [C.c_void_p, C.c_uint]
            lib.host_pixels.restype = C.c_void_p
            lib.host_palette.restype = C.c_void_p
            lib.host_cache_slots.restype = C.c_uint64
            lib.host_camera_vertices.argtypes = [C.c_int, C.POINTER(C.c_int32)]
            lib.host_camera_vertices.restype = C.c_uint

        def pixels(lib):
            return C.string_at(lib.host_pixels(), 320 * 224)[SCENE]

        def capture(lib, label):
            palette = struct.unpack('<256H', C.string_at(lib.host_palette(), 512))
            colors = [bytes(((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31,
                             ((v >> 10) & 31) * 255 // 31)) for v in palette]
            png(args.output.with_name(f'{args.output.stem}-{label}.png'),
                b''.join(colors[v] for v in C.string_at(lib.host_pixels(), 320 * 224)), 320, 224)

        fixtures = [('pink-chair bedroom', 4, 5, 59),
                    ('library entrance', 5, 3, 59),
                    ('library hallway view', 5, 2, 59),
                    ('bedroom opposite view', 4, 6, 50),
                    ('hallway door', 1, 2, 63)]
        for character in (0, 1):
            for label, room, camera, door in fixtures:
                for beta in range(512, 769, 32):
                    for index, lib in enumerate((candidate, oracle)):
                        C.memmove(banks[index], bank, len(bank))
                        lib.host_init(banks[index], len(bank))
                        lib.host_begin_world(character, 1, room, camera)
                        lib.host_clear_message()
                        # Isolate the same source door in both instances. Mesh
                        # pruning must not affect other instances of body 25.
                        identifiers = [lib.host_active(slot, 0) for slot in range(50)]
                        assert door in identifiers, (label, 'door inactive')
                        for identifier in identifiers:
                            if identifier >= 0 and identifier != door:
                                lib.host_delete(identifier)
                        lib.host_set_object(door, 12, beta)
                        lib.host_bounds(door, 3)

                    vertices = (C.c_int32 * (3 * 384))()
                    count = candidate.host_camera_vertices(door, vertices)
                    body = candidate.host_object(door, 1)
                    model = entries[f'MODEL_{character}_{body}']
                    offset = model['offset']
                    primitive_count = struct.unpack_from('>H', bank, offset + 6)[0]
                    directory = struct.unpack_from('>I', bank, offset + 32)[0]
                    valid, rejected = [], []
                    for face in range(primitive_count):
                        primitive = struct.unpack_from('>I', bank, offset + directory + face * 4)[0]
                        kind, vertex_count = struct.unpack_from('>2B', bank, offset + primitive)
                        indices = struct.unpack_from('>' + str(vertex_count) + 'H', bank,
                                                     offset + primitive + 6)
                        assert indices and all(vertex < count for vertex in indices)
                        depths = [vertices[3 * vertex + 2] for vertex in indices]
                        if min(depths) <= 100:
                            rejected.append(dict(face=face, kind=kind, depths=depths))
                        else:
                            valid.append(primitive)
                    memory = banks[1]
                    C.memmove(C.addressof(memory) + offset + 6, struct.pack('>H', len(valid)), 2)
                    if valid:
                        table = struct.pack('>' + str(len(valid)) + 'I', *valid)
                        C.memmove(C.addressof(memory) + offset + directory, table, len(table))
                    # The original prepared programs have the unpruned mesh.
                    static_programs = entries['STATIC_RASTERS']
                    C.memmove(C.addressof(memory) + static_programs['offset'], b'\0' * 4, 4)
                    if character == 0 and label == 'pink-chair bedroom' and beta == 512:
                        proof = dict(object=door, body=body, floor=1, room=room, camera=camera,
                                     beta=beta, vertex_depth_range=[min(vertices[2:count * 3:3]),
                                                                   max(vertices[2:count * 3:3])],
                                     rejected=rejected, surviving_faces=len(valid))

                    for path in ('painter', 'cache', 'contact'):
                        for lib in (candidate, oracle):
                            if path == 'painter':
                                lib.host_draw_painter()
                            elif path == 'cache':
                                lib.host_draw_fresh()
                                lib.host_draw_cached()
                                slot = lib.host_object(door, 0)
                                assert lib.host_cache_slots(0) & (1 << slot), (label, 'door not baked')
                            else:
                                # Contact depth only writes covered pixels;
                                # start it on the original camera background.
                                lib.host_set_object(door, 1, -1)
                                lib.host_draw_painter()
                                lib.host_set_object(door, 1, body)
                                lib.host_draw_depth(door)
                        images = [pixels(lib) for lib in (candidate, oracle)]
                        difference = sum(a != b for a, b in zip(*images))
                        row = dict(case=label, character=character, room=room, camera=camera,
                                   object=door, beta=beta, path=path, rejected_faces=len(rejected),
                                   surviving_faces=len(valid), different_pixels=difference)
                        checks.append(row)
                        if difference:
                            failures.append(row)
                        assert not candidate.host_world(3) and not oracle.host_world(3), row
                        if character == 0 and label == 'pink-chair bedroom' and beta == 512 and path == 'painter':
                            capture(candidate, 'actual')
                            capture(oracle, 'pruned-original-rule')

    report = dict(passed=not failures, comparisons=len(checks),
                  oracle='Private source mesh with every Z <= 100 primitive removed; prepared programs disabled',
                  scope='Near-face visibility policy, not independent raster math or hardware validation',
                  host_sha256=hashlib.sha256(args.library.read_bytes()).hexdigest(),
                  bank_sha256=hashlib.sha256(bank).hexdigest(), fixture=proof,
                  failed_comparisons=len(failures), failures=failures, checks=checks)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ('checks', 'failures')}, indent=2))
    if not args.audit:
        assert not failures, f'{len(failures)} incorrect near-face draws; see {args.output}'


if __name__ == '__main__':
    main()
