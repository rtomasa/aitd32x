#!/usr/bin/env python3
"""Check original ENDSEQ pixels, retained delta rendering and ending lifecycle.

The source movie is decoded independently from its DOS byte stream. Controller
ticks exercise the actual 25 Hz update path while the movie uses its separate
presentation clock. Fixtures use private host SRAM, never emulator save files.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from aitdpack.aitdpack import Pak

GAMEPLAY, MENU, ENDING, END = 10, 5, 14, 15
FRAME_TIME = 125                 # Five 60 Hz presentation ticks: 1/12 second.
WORLD_STEP = 60                 # One 25 Hz world tick, in 1/1500-second units.
SCENE = slice(12 * 320, 212 * 320)


def original_frames(game):
    decoder = C.CDLL(str(ROOT / 'tools/aitdpack/fitd_unpack.so'))
    decoder.PAK_explode.argtypes = [C.c_void_p, C.c_void_p, C.c_uint,
                                   C.c_uint, C.c_ushort]
    movie = Pak(game / 'ENDSEQ.PAK', decoder)
    first = movie.get(0)
    assert first[:2] == b'VP' and len(first) == 64770
    pixels = bytearray(first[770:])
    frames = [bytes(pixels)]
    # Match FITD unapckSequenceFrame's byte grammar directly. The AITD1 PAK
    # entries start at their first command, without an AITD2 size prefix.
    for frame in range(1, len(movie)):
        source = movie.get(frame)
        src = dst = 0
        while True:
            opcode = source[src]
            src += 1
            if not opcode:
                break
            if opcode < 3:
                count = opcode
            elif opcode == 3:
                count = source[src]
                src += 1
            else:
                count = int.from_bytes(source[src:src + 2], 'little')
                src += 2
            color = source[src]
            src += 1
            assert count and dst + count <= 64000, (frame, src, dst, count)
            if color:
                for pixel in range(dst, dst + count):
                    pixels[pixel] = color
            dst += count
        assert src == len(source) and dst == 64000, (frame, src, dst)
        frames.append(bytes(pixels))
    palette = [(r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)
               for r, g, b in zip(first[2:770:3], first[3:770:3], first[4:770:3])]
    return frames, palette, hashlib.sha256(movie.b).hexdigest()


def check(args):
    frames, palette, source_hash = original_frames(args.game)
    assert len(frames) == 32, 'unexpected original ending frame count'
    bank = (args.assets / 'bank.bin').read_bytes()
    manifest = json.loads((args.assets / 'manifest.json').read_text())
    initial = C.create_string_buffer(bank)
    lib = C.CDLL(str(args.host.resolve()))
    lib.host_init.argtypes = [C.c_void_p, C.c_uint]
    lib.host_start_ending.argtypes = [C.c_int]
    lib.host_advance_presentation.argtypes = [C.c_uint]
    for name in ('host_pixels', 'host_palette', 'host_background', 'host_sram'):
        getattr(lib, name).restype = C.c_void_p
    defines = (args.assets / 'resource_ids.h').read_text()
    def count(name):
        return int(next(line.split()[-1] for line in defines.splitlines()
                        if line.startswith('#define ' + name + ' ')))
    objects, variables = count('A32X_OBJECT_COUNT'), count('A32X_VAR_COUNT')

    def scene():
        return C.string_at(lib.host_pixels(), 320 * 224)[SCENE]

    def state():
        # Exclude the presentation and Game tick counters; the complete world,
        # player identity, variables, inventory and original object state freeze.
        return ([lib.host_state(i) for i in (1, 2, 3, 4, 5, 7, 8)],
                [lib.host_world(i) for i in (0, 1, 2, 6, 7, 9, 10, 11, 14, 15, 16)],
                [lib.host_variable(i) for i in range(variables)],
                [lib.host_inventory(i) for i in range(lib.host_world(6))],
                [[lib.host_object(i, j) for j in range(26)] for i in range(objects)])

    def sram_hash():
        return hashlib.sha256(C.string_at(lib.host_sram(), 131072)).hexdigest()

    def fault():
        assert not lib.host_world(3), [lib.host_world(i) for i in (3, 4, 5)]

    def assert_frame(frame, character, physical_bank):
        assert lib.host_startup(0) == ENDING and lib.host_startup(3) == frame
        actual = C.string_at(lib.host_background(), 64000)
        expected = frames[frame]
        assert actual == expected, ('retained original image', character, frame)
        actual = scene()
        assert actual == expected, ('framebuffer history', character, frame, physical_bank,
                                    sum(a != b for a, b in zip(actual, expected)))
        actual_palette = list((C.c_uint16 * 256).from_address(lib.host_palette()))
        assert actual_palette == palette, ('original ending palette', character, frame)
        fault()

    rows = []
    for character in (0, 1):
        lib.host_init(initial, len(bank))
        lib.host_startgame(character)
        lib.host_tick(0)
        for item in (13, 3, 5):
            lib.host_take(item)
        lib.host_clear_message()
        lib.host_set_variable(variables - 1, 302)
        C.memset(lib.host_sram(), 0x5A, 131072)
        saved = sram_hash()
        before = state()
        lib.host_buffer(0)
        lib.host_start_ending(0)
        framebuffer_checks = 0
        for physical_bank in (0, 1):
            lib.host_buffer(physical_bank)
            lib.host_draw_cached()
            assert_frame(0, character, physical_bank)
            framebuffer_checks += 1
        assert state() == before, 'starting the movie changed world state'

        # Draw three successive frames into one bank before switching. The
        # other bank must retain all missed delta regions until it is restored.
        for frame in range(32):
            physical_bank = (frame // 3) & 1
            lib.host_buffer(physical_bank)
            if frame:
                lib.host_advance_presentation(FRAME_TIME - WORLD_STEP)
            assert_frame(frame, character, physical_bank)
            framebuffer_checks += 1
            lib.host_tick(0)
            assert_frame(frame, character, physical_bank)
            assert state() == before, ('25 Hz tick advanced the movie world', character, frame)
            framebuffer_checks += 1
            if frame % 7 == 6 or frame == 31:
                lib.host_buffer(physical_bank ^ 1)
                lib.host_draw_cached()
                assert_frame(frame, character, physical_bank ^ 1)
                framebuffer_checks += 1
                lib.host_buffer(physical_bank)
        lib.host_advance_presentation(FRAME_TIME - WORLD_STEP)
        assert lib.host_state(6) == 1 and lib.host_startup(0) == GAMEPLAY
        assert state() == before, 'normal movie completion reset the escape world'
        assert sram_hash() == saved, 'movie completion changed private SRAM'

        # Every advertised skip button resumes the same escape state. A release
        # tick occurs inside the paused movie so no gameplay update is injected.
        for button in (16, 32, 64, 128):
            lib.host_start_ending(0)
            lib.host_tick(0)
            lib.host_tick(button)
            assert lib.host_state(6) == 1 and lib.host_startup(0) == GAMEPLAY
            assert state() == before, ('movie skip reset the escape world', character, button)
            assert sram_hash() == saved

        # Pregzt's death prevents later LIGHT commands from changing darkness.
        # Both movie exits must brighten the escape while retaining that flag.
        lib.host_set_cvar(12, 1)
        for skip in (False, True):
            lib.host_set_dark(1)
            lib.host_start_ending(0)
            if skip:
                lib.host_tick(0)
                lib.host_tick(128)
            else:
                lib.host_advance_presentation(32 * FRAME_TIME)
            assert lib.host_startup(0) == GAMEPLAY and not lib.host_dark()
            assert lib.host_cvar(12) == 1 and state() == before
            assert sram_hash() == saved

        # Exercise GAME_OVER's production dispatch, then its timed title return.
        lib.host_game_over()
        world_ticks = lib.host_world(11)
        lib.host_tick(0)
        assert lib.host_startup(0) == END and lib.host_state(6) == 0
        lib.host_advance_presentation(120 * 25 - 1)
        assert lib.host_startup(0) == END and lib.host_world(11) == world_ticks
        lib.host_advance_presentation(1)
        assert lib.host_startup(0) == MENU and lib.host_state(6) == 0
        assert sram_hash() == saved, 'final title return changed private SRAM'
        # The final hold is skippable too, independently of movie skipping.
        lib.host_startgame(character)
        lib.host_game_over()
        lib.host_tick(0)
        lib.host_tick(128)
        assert lib.host_startup(0) == MENU and sram_hash() == saved
        rows.append(dict(character=character, original_frames_checked=len(frames),
                         framebuffer_checks=framebuffer_checks, two_bank_damage_history=True,
                         original_palette=True, world_frozen=True,
                         completion_preserves_escape=True, skip_buttons=[16, 32, 64, 128],
                         killed_pregzt_escape_bright_on_completion_and_skip=True,
                         game_over_timed_title_return=True, game_over_skip=True,
                         private_sram_unchanged=True))
    report = dict(passed=True, host_sha256=hashlib.sha256(args.host.read_bytes()).hexdigest(),
                  bank_sha256=hashlib.sha256(bank).hexdigest(),
                  source_endseq_sha256=source_hash,
                  original_frame_sha256=[hashlib.sha256(frame).hexdigest() for frame in frames],
                  characters=rows,
                  scope='Host ending pixels and lifecycle; emulator/hardware timing are separate checks',
                  timing='Five 60 Hz presentation ticks per frame; console adaptation, not DOS timing validation')
    assert manifest['bank_sha256'] == report['bank_sha256']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=ROOT / 'msdos-game/AITD_CD/INDARK')
    parser.add_argument('--assets', type=Path, default=ROOT / 'assets')
    parser.add_argument('--host', type=Path, default=ROOT / 'build/libaitd32x.so')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/ending-check/report.json')
    args = parser.parse_args()
    print(json.dumps(check(args), indent=2))


if __name__ == '__main__':
    main()
