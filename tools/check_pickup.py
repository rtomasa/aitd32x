#!/usr/bin/env python3
"""Focused original found-object window check; uses only private host memory."""
import ctypes as C
import hashlib
import json
from pathlib import Path

import emulator_check as ec

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/pickup-check'
A, B, C_BUTTON, LEFT, RIGHT = 64, 16, 32, 4, 8


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bank = (ROOT / 'assets/bank.bin').read_bytes()
    buffer = C.create_string_buffer(bank)
    lib = C.CDLL(str(ROOT / 'build/libaitd32x.so'))
    lib.host_pixels.restype = lib.host_palette.restype = C.c_void_p

    def scene():
        return C.string_at(lib.host_pixels(), 320 * 224)[12 * 320:212 * 320]

    def snapshot():
        return ([lib.host_state(i) for i in range(1, 9)],
                [lib.host_world(i) for i in (0, 1, 2, 6, 7, 8, 9, 10, 11, 14, 15, 16)],
                [lib.host_variable(i) for i in range(207)],
                [[lib.host_object(i, j) for j in range(26)] for i in range(292)])

    def capture(name):
        pixels = C.string_at(lib.host_pixels(), 320 * 224)
        palette = (C.c_uint16 * 256).from_address(lib.host_palette())
        colors = [bytes(((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31,
                         ((v >> 10) & 31) * 255 // 31)) for v in palette]
        ec.png(OUT / (name + '.png'), b''.join(colors[v] for v in pixels), 320, 224)

    rows = []
    for character in (0, 1):
        lib.host_init(buffer, len(bank));lib.host_startgame(character)
        lib.host_clear_message();lib.host_draw_fresh();baseline = scene()
        count = lib.host_world(6)
        lib.host_ui(1, 13)
        assert lib.host_world(8) == 13
        before = snapshot();fixed = None;poses = set()
        for tick in range(60):
            lib.host_buffer(tick & 1);lib.host_tick(0)
            pixels = scene()
            static = bytes(v for i, v in enumerate(pixels)
                           if not (48 <= i % 320 <= 271 and 48 <= i // 320 <= 151))
            if fixed is None:
                fixed = static
            assert static == fixed, 'pickup preview wrote outside the original window interior'
            assert all(pixels[y * 320 + x] == 0 for y in range(200) for x in range(320)
                       if not (40 <= x < 280 and 40 <= y < 160)), 'room remains behind found-object window'
            poses.add(hashlib.sha256(pixels[80 * 320:135 * 320]).hexdigest())
        assert len(poses) > 10, 'found-object 3D preview did not rotate'
        assert snapshot() == before, 'pickup animation advanced paused gameplay state'
        capture(f'character-{character}-take')
        # Native Leave/Take selection, with Take selected initially.
        lib.host_tick(LEFT);capture(f'character-{character}-leave')
        lib.host_tick(A)
        assert lib.host_world(8) == -1 and lib.host_world(6) == count
        for frame in (0, 1):
            lib.host_buffer(frame);lib.host_draw_cached()
            assert scene() == baseline, f'pickup pixels leaked into room framebuffer {frame}'
        # Both shortcut buttons leave, independently of the selected choice.
        for button in (B, C_BUTTON):
            lib.host_ui(1, 13);lib.host_tick(button)
            assert lib.host_world(8) == -1 and lib.host_world(6) == count
        lib.host_ui(1, 13);lib.host_tick(LEFT);lib.host_tick(RIGHT)
        # A saved pending pickup reappears after the load pause menu closes.
        # These calls use the host library's private SRAM array only.
        assert lib.host_save() and lib.host_load()
        assert lib.host_world(12) == 3 and lib.host_world(8) == 13
        lib.host_tick(B)
        assert lib.host_world(12) == 0 and lib.host_world(8) == 13
        lib.host_tick(A)
        assert lib.host_world(8) == -1 and lib.host_world(6) == count + 1
        assert 13 in [lib.host_inventory(i) for i in range(lib.host_world(6))]
        assert not lib.host_world(3), 'taking an item caused a script fault'
        rows.append(dict(character=character, preview_frames=len(poses), paused_world=True,
                         native_leave_take=True, leave_shortcuts=True,
                         take_dispatch=True, loaded_prompt_resumed=True,
                         both_framebuffers_restored=True))
    report = dict(rom_sha256=hashlib.sha256((ROOT / 'build/AITD32X.32x').read_bytes()).hexdigest(),
                  host=rows, battery_save_files_accessed=False)
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
