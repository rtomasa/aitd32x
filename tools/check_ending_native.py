#!/usr/bin/env python3
"""Check the linked ENDSEQ movie in one fresh PicoDrive process per region.

The fixture uses private host/core SRAM. Only the transient picture request is
injected into native RAM; ordinary Game::Update starts the movie. Original DOS
frames are independently decoded, then compared with completed displayed banks.
No emulator battery files are read or written. This is emulator evidence only.
"""
import argparse
import ctypes as C
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path

import emulator_check as ec
from check_ending import original_frames
from check_full_game_native import FIELDS, Native, load_fixture
from check_startup_native import video_image

ROOT = ec.ROOT
ENDING, GAMEPLAY = 14, 10


def layout(mars):
    fields = dict(FIELDS, picture_id='offsetof(World,picture_id)',
                  palette='offsetof(Game,renderer)+offsetof(Renderer,palette)',
                  cvars='offsetof(World,cvars)', world_ticks='offsetof(World,ticks)',
                  objects='offsetof(World,objects)', inventory='offsetof(World,inventory)',
                  inventory_count='offsetof(World,inventory_count)', in_hand='offsetof(World,in_hand)',
                  startup_phase='offsetof(Game,startup_phase)')
    source = ROOT / 'build/ending-native-layout.cpp'
    source.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned layout[]={'+
                      ','.join(fields.values())+'};\n')
    assembly = source.with_suffix('.s')
    subprocess.run([str(mars / 'sh-elf/bin/sh-elf-g++'), '-m2', '-mb', '-std=c++17',
                    '-Wno-invalid-offsetof', '-I'+str(ROOT), '-S', str(source), '-o', str(assembly)], check=True)
    values = re.findall(r'\.long\s+([-0-9xa-fA-F]+)',
                        assembly.read_text().split('_layout:', 1)[1].split('.ident', 1)[0])
    assert len(values) == len(fields)
    return dict(zip(fields, (int(value, 0) for value in values)))


def fixture():
    bank = (ROOT / 'assets/bank.bin').read_bytes()
    lib = C.CDLL(str(ROOT / 'build/libaitd32x.so'))
    lib.host_init.argtypes = [C.c_void_p, C.c_uint]
    lib.host_sram.restype = C.c_void_p
    source = C.create_string_buffer(bank)
    lib.host_init(source, len(bank))
    C.memset(lib.host_sram(), 0, 131072)
    lib.host_begin_world(0, 6, 0, 2)
    lib.host_place(1, 6, 0, -8025, -4010, 2940, 0)
    lib.host_set_variable(7, 1)
    lib.host_take(13)
    lib.host_set_variable(206, 302)
    lib.host_set_cvar(12, 1)
    lib.host_set_dark(1)
    lib.host_clear_message()
    assert lib.host_dark() and not lib.host_world(3) and lib.host_save()
    return C.string_at(lib.host_sram(), 131072)


def check(args):
    frames, palette, source_hash = original_frames(args.game)
    assert len(frames) == 32
    hashes = {}
    for index, frame in enumerate(frames):
        hashes.setdefault(hashlib.sha256(frame).digest(), []).append(index)
    offsets = layout(args.mars)
    sram = fixture()
    native = Native(args.core, args.region, offsets)
    output = ROOT / 'build/ending-native'
    output.mkdir(exist_ok=True)
    try:
        load_fixture(native, sram)
        assert native.position() == [-8025, -4010, 2940]
        assert (native.state()['floor'], native.state()['room'], native.state()['camera']) == (6, 0, 2)
        native.resume_frozen()
        def word(name, index):
            offset = offsets['world'] + offsets[name] + index*2
            return struct.unpack('>h', native.bytes_at(offset, 2))[0]
        def dark():
            offset = offsets['world']+offsets['dark']
            return bool(C.c_uint8.from_address(native.memory+native.game+(offset ^ 1)).value)
        def phase():
            return C.c_uint8.from_address(native.memory+native.game+(offsets['startup_phase'] ^ 1)).value
        def world_state():
            return (native.position(), native.read('world_ticks', world=True),
                    native.bytes_at(offsets['world']+offsets['objects'], 292*52),
                    native.bytes_at(offsets['world']+offsets['vars'], 207*2),
                    native.bytes_at(offsets['world']+offsets['cvars'], 45*2),
                    native.bytes_at(offsets['world']+offsets['inventory'], 30*4),
                    native.read('inventory_count', world=True), native.read('in_hand', world=True))
        assert dark() and word('cvars', 12) == 1 and word('vars', 206) == 302
        before = world_state()
        save_pointer = native.e.lib.retro_get_memory_data(0)
        saved = C.string_at(save_pointer, 131072)
        before_draws, request_frame = native.state()['rendered'], native.frames
        # The only native world mutation: the same request made by END_SEQUENCE.
        native.integer_at(native.memory+native.game+offsets['world']+offsets['picture_id'], -2)
        native.wait(lambda: native.state()['phase'] == ENDING)
        first_frame = native.frames
        seen, video_seen, bank_checks, visible = set(), set(), {0: 0, 1: 0}, []
        previous = None
        pages = set()
        frozen_ticks = native.read('world_ticks', world=True)
        assert world_state() == before, 'movie entry advanced the escape world'

        def displayed(movie):
            nonlocal previous
            table, pixels = native.e.framebuffer()
            assert table == [256+y*160 for y in range(224)]
            bank = native.e.vdp[5] & 1
            digest = hashlib.sha256(pixels[12*320:212*320]).digest()
            if not movie and digest not in hashes:
                return
            key = (bank, digest)
            if key != previous:
                assert digest in hashes, ('native movie framebuffer differs from original',
                                         native.read('book_line'), bank, native.state(), native.e.comm())
                indices = hashes[digest]
                seen.update(indices)
                assert pixels[12*320:212*320] == frames[indices[0]]
                actual_palette = struct.unpack('>256H', native.bytes_at(offsets['palette'], 512))
                # Resume prepares the gameplay palette before its completed
                # framebuffer replaces the last displayed movie frame.
                if movie:
                    assert list(actual_palette) == palette, 'native movie palette differs'
                assert not any(pixels[:12*320]+pixels[212*320:]), 'movie borders changed'
                bank_checks[bank] += 1
                visible.append(dict(indices=indices, bank=bank, video_frame=native.frames,
                                    movie_index=native.read('book_line'), page=int(native.banks[1])))
                previous = key
            # The RGB callback can precede the SH2 flip in this retro_run.
            # Check the important images again while held, without delaying
            # their presentation clock, and capture the actual video output.
            indices = hashes[digest]
            for index in (0, 1, 16, 31):
                if index in indices and index not in video_seen and video_image(native, frames[index]):
                    video_seen.add(index)
                    native.e.capture(f'ending-native/{args.region}-frame-{index:02}.png')

        # Debug publication follows the completed escape draw. Its previous
        # movie phase can remain visible while that first world update runs.
        while phase() == ENDING:
            native.healthy()
            assert world_state() == before, ('movie advanced world', native.state())
            assert native.frames-first_frame <= native.hz*6, 'movie did not naturally finish'
            displayed(True)
            pages.add(int(native.banks[1]))
            native.advance()
        movie_end_frame = native.frames
        # Frame 31 can flip at the same VBlank in which the following loop
        # resumes escape. It remains visible until the first escape draw flips.
        while native.state()['phase'] != GAMEPLAY:
            native.healthy()
            displayed(False)
            native.advance()
            assert native.frames-movie_end_frame < native.hz*5, 'escape draw did not complete'
        assert native.state()['phase'] == GAMEPLAY and native.state()['mode'] == 1
        native.healthy()
        assert {0, 1, 16, 31} <= seen, ('essential native movie frames missing', sorted(seen))
        assert video_seen == {0, 1, 16, 31}, ('essential RGB output frames missing', sorted(video_seen))
        assert all(bank_checks.values()), 'both native framebuffer histories were not exercised'
        assert native.position() == before[0], 'movie completion reset escape pose'
        assert word('cvars', 12) == 1 and word('vars', 206) == 302 and not dark()
        assert native.read('inventory_count', world=True) == before[-2]
        assert native.read('in_hand', world=True) == before[-1]
        assert C.string_at(save_pointer, 131072) == saved, 'native movie changed private SRAM'
        duration = (movie_end_frame-first_frame)/native.hz
        result = dict(region=args.region, emulator_only=True, no_battery_files=True,
                      rom_sha256=hashlib.sha256((ROOT/'build/AITD32X.32x').read_bytes()).hexdigest(),
                      elf_sha256=hashlib.sha256((ROOT/'build/AITD32X.elf').read_bytes()).hexdigest(),
                      asset_sha256=hashlib.sha256((ROOT/'assets/bank.bin').read_bytes()).hexdigest(),
                      original_endseq_sha256=source_hash, original_frame_count=32,
                      visible_original_indices=sorted(seen), framebuffer_checks=bank_checks,
                      rgb_output_original_indices=sorted(video_seen),
                      visible_frames=visible, mapped_pages=sorted(pages),
                      world_ticks_frozen=frozen_ticks, original_palette=True,
                      natural_movie_seconds=round(duration, 4), target_fps=12,
                      visible_image_fps=round(len(visible)/duration, 4),
                      completed_draws=native.state()['rendered']-before_draws,
                      request_to_first_image_ms=round((first_frame-request_frame)*1000/native.hz, 1),
                      escape_preserved=True, escape_dark=False, private_sram_unchanged=True,
                      final_state=native.state())
        (output/f'report-{args.region}.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps({key: value for key, value in result.items() if key != 'visible_frames'}, indent=2))
    finally:
        native.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('core', type=Path)
    parser.add_argument('--region', choices=('NTSC', 'PAL'), default='NTSC')
    parser.add_argument('--mars', type=Path, default=ROOT/'.local/toolchain/mars')
    parser.add_argument('--game', type=Path, default=ROOT/'msdos-game/AITD_CD/INDARK')
    check(parser.parse_args())
