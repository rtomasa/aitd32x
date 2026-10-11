#!/usr/bin/env python3
"""Focused native message placement and cached pause cleanup in private host RAM."""
import ctypes as C
import hashlib
import json
from pathlib import Path

import emulator_check as ec

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/menu-message-check'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = (ROOT / 'assets/bank.bin').read_bytes()
    bank = C.create_string_buffer(data)
    lib = C.CDLL(str(ROOT / 'build/libaitd32x.so'))
    lib.host_pixels.restype = lib.host_palette.restype = C.c_void_p

    def scene():
        return C.string_at(lib.host_pixels(), 320 * 224)[12 * 320:212 * 320]

    def capture(name):
        palette = (C.c_uint16 * 256).from_address(lib.host_palette())
        colors = [bytes(((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31,
                         ((v >> 10) & 31) * 255 // 31)) for v in palette]
        ec.png(OUT / (name + '.png'), b''.join(colors[v] for v in scene()), 320, 200)

    rows = []
    for character in (0, 1):
        lib.host_init(bank, len(data));lib.host_startgame(character)
        lib.host_clear_message();lib.host_draw_fresh();baseline = scene()
        for frame in (0, 1):
            lib.host_buffer(frame);lib.host_ui(0, 106)  # Original "You feel weak".
            changed = [i for i, (a, b) in enumerate(zip(baseline, scene())) if a != b]
            assert changed and all(184 <= i // 320 <= 199 for i in changed)
            assert all(scene()[i] == 16 for i in changed), 'message added a box or a second overlay'
        capture(f'character-{character}-weak')
        lib.host_clear_message()
        for frame in (0, 1):
            lib.host_buffer(frame);lib.host_draw_cached()
            assert scene() == baseline, 'message remained in framebuffer history'

        # Option changes must reuse the paused scene and clear on both banks.
        lib.host_ui(5, 0);world_ticks = lib.host_world(11)
        for pad in (2, 0, 2, 0, 1, 0):
            lib.host_buffer((lib.host_state(0) + 1) & 1);lib.host_tick(pad)
            assert lib.host_world(11) == world_ticks
        capture(f'character-{character}-pause')
        lib.host_tick(16)
        assert lib.host_world(12) == 0
        for frame in (0, 1):
            lib.host_buffer(frame);lib.host_draw_cached()
            assert scene() == baseline, 'cached pause menu leaked into gameplay'
        lib.host_ui(4, 2);world_ticks = lib.host_world(11)
        lib.host_tick(8);lib.host_tick(0)
        assert lib.host_world(17) == 1 and lib.host_world(11) == world_ticks
        lib.host_tick(64)
        assert lib.host_world(13) == -1
        for frame in (0, 1):
            lib.host_buffer(frame);lib.host_draw_cached()
            assert scene() == baseline, 'cached reading page leaked into gameplay'
        rows.append(dict(character=character, single_unframed_message=True,
                         original_position_color=True, both_framebuffers_clean=True,
                         pause_world_frozen=True, reading_page_cleanup=True))
    report = dict(rom_sha256=hashlib.sha256((ROOT / 'build/AITD32X.32x').read_bytes()).hexdigest(),
                  host=rows, battery_save_files_accessed=False)
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
