#!/usr/bin/env python3
"""Compare cached contact preparation with a preserved renderer, in private RAM.

Exercise both framebuffers, moving characters, changed prop poses, cache hits,
and storage too small to hold a program. No frontend saves or assets change.
"""
import argparse
import ctypes as C
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/prepared-contact-cache.json')
    args = parser.parse_args()
    libraries = [C.CDLL(str(path.resolve())) for path in
                 (ROOT / 'build/libaitd32x.so', args.reference)]
    actual, oracle = libraries
    data = (ROOT / 'assets/bank.bin').read_bytes()
    bank = C.create_string_buffer(data)
    for lib in libraries:
        lib.host_init.argtypes = [C.c_void_p, C.c_uint]
        lib.host_pixels.restype = C.c_void_p
    results = []
    for character in (0, 1):
        for capacity in (8192, 148, 0):
            for lib in libraries:
                lib.host_init(bank, len(data))
                lib.host_begin_world(character, 0, 0, 3)
                for slot in range(50):
                    identifier = lib.host_active(slot, 0)
                    if identifier >= 0 and identifier not in (0, 1):
                        lib.host_delete(identifier)
            before = [actual.renderer_contact_stats(i) for i in range(4, 8)]
            near_before = actual.renderer_contact_stats(1)
            for step in range(5):
                key = 1000 + min(step // 2, 1)
                position = [-4000 + (30 if step & 1 else 0), 0, 1200]
                if step == 4:
                    # Keep the static program warm while taking the dynamic
                    # actor through the near plane. Fallback must reconstruct
                    # the static vertices omitted on a cache hit.
                    points = (C.c_int32 * (384 * 3))()
                    def minimum(where):
                        actual.host_place(1, 0, 0, *where, 0)
                        count = actual.host_camera_vertices(1, points)
                        return min(points[3 * i + 2] for i in range(count))
                    depth = minimum(position)
                    slopes = []
                    for axis in (0, 2):
                        probe = position.copy()
                        probe[axis] += 1000
                        slopes.append((minimum(probe) - depth, axis))
                    slope, axis = max(slopes, key=lambda item: abs(item[0]))
                    position[axis] -= round((depth - 50) * 1000 / slope)
                    assert minimum(position) <= 100, 'near fixture did not cross the plane'
                for lib in libraries:
                    lib.host_place(1, 0, 0, *position, 0)
                    lib.host_place(0, 0, 0, -4000 + (90 if step >= 2 else 0),
                                   0, 300, 768 + (64 if step >= 2 else 0))
                    lib.host_bounds(1, 2)
                    lib.host_bounds(0, 3)
                    lib.host_buffer(step & 1)
                    lib.host_draw_painter()
                assert actual.host_resolve_cached_pair(1, 0, capacity, key, step == 0)
                assert oracle.host_resolve_pair(1, 0)
                images = [C.string_at(lib.host_pixels(), 320 * 224)[12 * 320:212 * 320]
                          for lib in libraries]
                assert images[0] == images[1], (character, capacity, step,
                        sum(a != b for a, b in zip(*images)))
            delta = [actual.renderer_contact_stats(i) - before[i - 4] for i in range(4, 8)]
            if capacity == 8192:
                assert delta[0] == 3 and delta[1] == 2, ('cache not exercised', delta)
            elif capacity == 148:
                assert delta[2] == 2 and delta[3] == 3, ('failed program rebuilt', delta)
            assert actual.renderer_contact_stats(1) > near_before, 'near fallback not exercised'
            results.append(dict(character=character, capacity=capacity,
                                comparisons=5, hits=delta[0], builds=delta[1],
                                capacity_failures=delta[2], negative_hits=delta[3]))
    report = dict(passed=True, private_memory_only=True, comparisons=30, cases=results)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
