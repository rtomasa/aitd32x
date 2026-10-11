#!/usr/bin/env python3
"""Check lamp masking against a fully rendered scene and both buffer histories.

The lamp is equipped/dropped through original item LIFE and basement LIFE 509.
The ellipse is a console adaptation; these checks establish retained-rendering
correctness, rather than pixel parity with the DOS spotlight artwork.
"""
import ctypes as C
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'build/lighting-check'
SCENE = slice(12 * 320, 212 * 320)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    source_library = ROOT / 'build/libaitd32x.so'
    reference_library = OUTPUT / 'reference.so'
    shutil.copyfile(source_library, reference_library)
    primary = C.CDLL(str(source_library))
    reference = C.CDLL(str(reference_library))
    bank = (ROOT / 'assets/bank.bin').read_bytes()
    memory = C.create_string_buffer(bank)
    for lib in (primary, reference):
        lib.host_init.argtypes = [C.c_void_p, C.c_uint]
        lib.host_pixels.restype = C.c_void_p

    def healthy(lib, context):
        assert not lib.host_world(3), (context, [lib.host_world(i) for i in (3, 4, 5)])

    def frame(lib):
        return C.string_at(lib.host_pixels(), 320 * 224)[SCENE]

    def expected():
        reference.host_set_dark(0)
        reference.host_draw_fresh()
        bright = frame(reference)
        reference.host_set_dark(primary.host_dark())
        # A fresh reference restores the complete camera and rebuilds scenery;
        # its mask cannot inherit the other bank's old lamp footprint.
        reference.host_draw_fresh()
        masked = frame(reference)
        assert all(a == b or a == 0 for a, b in zip(masked, bright)), 'lighting altered visible scene colors'
        source = primary.host_cvar(13)
        if primary.host_dark() and (source < 0 or primary.host_object(source, 0) < 0):
            assert not any(masked), 'a missing lamp still lights the scene'
        else:
            assert sum(value != 0 for value in masked) > 5000, 'fixture does not illuminate meaningful scenery'
        return masked, bright

    rows = []
    for character in (0, 1):
        for lib in (primary, reference):
            lib.host_init(memory, len(bank))
            lib.host_begin_world(character, 6, 0, 2)
            lib.host_place(1, 6, 0, -8025, 0, 2940, 0)
            lib.host_set_variable(7, 1)
            lib.host_take(13)
            assert lib.host_run_life(509, 235) == 0
            assert lib.host_dark() and lib.host_cvar(13) == 1
            lib.host_clear_message()
        checks = []

        def compare(label, bank_number):
            primary.host_buffer(bank_number)
            primary.host_draw_cached()
            masked, _ = expected()
            actual = frame(primary)
            assert actual == masked, (label, character, bank_number,
                                      sum(a != b for a, b in zip(actual, masked)))
            healthy(primary, label)
            checks.append(dict(case=label, bank=bank_number))

        for bank_number in (0, 1, 0, 1):
            compare('held lamp: idle', bank_number)
        # Each moved pose must be correct on the first frame, including the
        # newly illuminated strip beyond that bank's previous lamp footprint.
        for index, (x, z) in enumerate(((-7725, 2840), (-7425, 2640), (-8325, 3140))):
            for lib in (primary, reference):
                lib.host_place(1, 6, 0, x, 0, z, 0)
            compare('held lamp: movement', index & 1)
        for lib in (primary, reference):
            lib.host_drop(13, 1)
            assert lib.host_run_life(509, 235) == 0
            assert lib.host_cvar(13) == 13
            lib.host_clear_message()
        for bank_number in (1, 0):
            compare('dropped lamp: new light source', bank_number)
        for lib in (primary, reference):
            lib.host_delete(13)
            assert lib.host_object(13, 0) < 0 and lib.host_cvar(13) == 13
            lib.host_clear_message()
        for bank_number in (0, 1):
            compare('departed source: no stale light', bank_number)
        for lib in (primary, reference):
            lib.host_take(13)
            assert lib.host_run_life(509, 235) == 0
            assert lib.host_cvar(13) == 1
            lib.host_clear_message()
        for bank_number in (0, 1):
            compare('held lamp: recovered source', bank_number)
        # Source disappearance and reappearance exercise changes with no actor
        # movement, which cannot rely on dynamic geometry damage to repair them.
        for lib in (primary, reference):
            lib.host_set_cvar(13, -1)
        for bank_number in (0, 1):
            compare('no lamp: fully dark', bank_number)
        for lib in (primary, reference):
            lib.host_set_cvar(13, 1)
        for bank_number in (1, 0):
            compare('lamp reappears: immediate restoration', bank_number)
        for lib in (primary, reference):
            lib.host_place(1, 6, 0, -1006, 0, -780, 0)
            lib.host_camera(6, 0, 3)
        for bank_number in (0, 1):
            compare('camera change: retained dark scene', bank_number)
        primary.host_set_dark(0)
        _, bright = expected()
        for bank_number in (0, 1):
            primary.host_buffer(bank_number)
            primary.host_draw_cached()
            assert frame(primary) == bright, ('full illumination recovery', character, bank_number)
        rows.append(dict(character=character, comparisons=checks,
                         full_illumination_restores_both_banks=True))
    report = dict(passed=True, characters=rows,
                  host_sha256=hashlib.sha256(source_library.read_bytes()).hexdigest(),
                  bank_sha256=hashlib.sha256(bank).hexdigest(),
                  scope='Host lamp mask and retained framebuffer checks; DOS spotlight shape and hardware FPS are unvalidated')
    (OUTPUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
