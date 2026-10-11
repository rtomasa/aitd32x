#!/usr/bin/env python3
"""Controller-to-visible menu latency on the linked PicoDrive ROM.

Fixtures add inventory items only to private emulator RAM. No cartridge SRAM
or frontend save files are read or written. This measures emulation, not physical
32X hardware. Run before and after menu changes to retain comparable reports.
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
from check_startup_native import Check, layout, assets, A, B, DOWN, LEFT, RIGHT, START


def offsets(mars):
    result = layout(mars)
    source = ec.ROOT / 'build/menu-latency-layout.cpp'
    assembly = source.with_suffix('.s')
    fields = ('offsetof(World,inventory)', 'offsetof(World,inventory_count)', 'offsetof(Game,character)',
              'offsetof(World,prompt)', 'offsetof(World,book)', 'offsetof(Game,inventory_dirty)', 'offsetof(Game,dirty)')
    source.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned ui_offsets[]={' + ','.join(fields) + '};\n')
    subprocess.run([str(mars / 'sh-elf/bin/sh-elf-g++'), '-m2', '-mb', '-std=c++17',
                    '-Wno-invalid-offsetof', '-I' + str(ec.ROOT), '-S', str(source), '-o', str(assembly)],
                   check=True, stderr=subprocess.DEVNULL)
    values = re.findall(r'\.long\s+([-0-9xa-fA-F]+)', assembly.read_text().split('_ui_offsets:', 1)[1].split('.ident', 1)[0])
    result.update(zip(('inventory', 'inventory_count', 'character', 'prompt', 'book', 'inventory_dirty', 'dirty'),
                      (int(v, 0) for v in values)))
    return result


def glyph_pixel(text_id, center, y):
    """One exact label pixel detects its selected color despite 3D animation."""
    decode = assets()
    text_asset, font = decode('TEXT'), decode('READ_FONT')
    text = None
    for entry in range(struct.unpack_from('>I', text_asset)[0]):
        key = struct.unpack_from('>H', text_asset, 4 + 8 * entry)[0]
        if key == text_id:
            start = struct.unpack_from('>I', text_asset, 8 + 8 * entry)[0]
            text = text_asset[start:text_asset.index(0, start)]
            break
    assert text
    table = struct.unpack_from('>H', font, 6)[0]
    stride = font[3] or (font[4] | font[5] << 8)
    glyphs = [struct.unpack_from('>H', font, table + 2 * (char - font[0]))[0] for char in text]
    x = center - sum((glyph >> 12) or 2 for glyph in glyphs) // 2
    for glyph in glyphs:
        width, bit = glyph >> 12, glyph & 4095
        for row in range(font[2]):
            for col in range(width):
                if font[8 + row * stride + (bit + col) // 8] & (128 >> ((bit + col) & 7)):
                    return x + col, y + row, 1
        x += width or 2
    raise AssertionError('label contains no pixels')


def measure(core, region, off):
    check = Check(core, region, off)
    rows = []

    def move(name, button, field, expected, pixel=None):
        check.advance(5)
        start = check.frames
        before = check.e.framebuffer()[1][12 * 320:212 * 320]
        accepted = visible = None
        for _ in range(check.hz * 3):
            check.advance(1, button)
            if accepted is None and check.read(field) == expected:
                accepted = check.frames - start
            pixels = check.e.framebuffer()[1]
            shown = (pixels[(12 + pixel[1]) * 320 + pixel[0]] == (pixel[2] if len(pixel) > 2 else 100)
                     if pixel else pixels[12 * 320:212 * 320] != before)
            if accepted is not None and shown and check.settled():
                visible = check.frames - start
                break
        assert visible is not None, ('menu did not respond', name, check.state())
        rows.append(dict(menu=name, frames_to_state=accepted, frames_to_visible=visible,
                         ms_to_visible=round(visible * 1000 / check.hz, 1)))
        # A held direction changes one option; each subsequent sample uses a
        # released button and its own press edge, rather than an auto-repeat.
        check.advance(5)

    def write_world(offset, value):
        words = (C.c_uint16 * 2).from_address(check.memory + check.game + off['world'] + offset)
        words[0], words[1] = value >> 16, value & 65535

    def write_game(name, value):
        words = (C.c_uint16 * 2).from_address(check.memory + check.game + off[name])
        words[0], words[1] = value >> 16, value & 65535

    def flag(name):
        C.c_uint8.from_address(check.memory + check.game + (off[name] ^ 1)).value = 1

    try:
        check.advance(check.hz)
        check.press(A)
        check.phase(5)
        move('start-menu', DOWN, 'selection', 1, (10, 92))
        move('start-menu', 1, 'selection', 0, (10, 76))
        check.press(A)
        check.phase(6)
        move('character-selection', LEFT, 'character', 1)
        move('character-selection', RIGHT, 'character', 0)
        check.press(A)
        check.phase(7)
        pages = struct.unpack_from('>H', assets()('STARTUP_BIOGRAPHY_0'), 2)[0]
        if pages > 1:
            move('biography', DOWN, 'book_line', 1)
            move('biography', 1, 'book_line', 0)
        for _ in range(pages):
            check.press(A)
        check.phase(8)
        check.press(A)
        check.phase(10)
        check.advance(check.hz)
        check.press(START)
        world_ticks = check.state()['world_ticks']
        move('pause', DOWN, 'selection', 1, (38, 96))
        assert check.state()['world_ticks'] == world_ticks, 'pause input advanced world'
        check.press(B)
        write_world(off['inventory'], 2)
        write_world(off['inventory'] + 4, 13)
        write_world(off['inventory'] + 8, 123)
        write_world(off['inventory_count'], 3)
        check.press(32)
        world_ticks = check.state()['world_ticks']
        move('inventory', DOWN, 'selection', 1, (10, 25))
        move('inventory', DOWN, 'selection', 2, (10, 41))
        check.press(A)
        move('object-actions', DOWN, 'notice', 1, (170, 150))
        assert check.state()['world_ticks'] == world_ticks, 'inventory input advanced world'
        check.press(B)
        check.press(B)
        # Pause first so a preceding gameplay draw cannot clear the fixture's
        # dirty flag while it is still in progress. Resume supplies a real UI
        # edge and draws the requested first page through the normal path.
        check.press(START)
        write_world(off['book'], 2)
        write_game('book_line', 0)
        check.press(B)
        check.advance(check.hz)
        world_ticks = check.state()['world_ticks']
        move('book', DOWN, 'book_line', 1)
        move('book', 1, 'book_line', 0)
        assert check.state()['world_ticks'] == world_ticks, 'book input advanced world'
        check.press(A)
        check.press(START)
        # Enter exactly the presentation state of PickupEnter in private RAM.
        write_world(off['prompt'], 13)
        write_game('selection', 1)
        write_game('time', 0)
        write_game('since', 0)
        flag('inventory_dirty')
        flag('dirty')
        check.press(B)
        check.advance(check.hz)
        world_ticks = check.state()['world_ticks']
        move('pickup', LEFT, 'selection', 0, glyph_pixel(21, 130, 135))
        move('pickup', RIGHT, 'selection', 1, glyph_pixel(22, 190, 135))
        assert check.state()['world_ticks'] == world_ticks, 'pickup input advanced world'
        assert not check.state()['fault'], check.state()
        return dict(region=region, emulator_only=True, paused_world=True, rows=rows)
    finally:
        check.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('core', type=Path)
    parser.add_argument('--mars', type=Path, default=ec.ROOT / '.local/toolchain/mars')
    parser.add_argument('--label', default='after')
    parser.add_argument('--region', choices=('NTSC', 'PAL', 'both'), default='both')
    args = parser.parse_args()
    off = offsets(args.mars)
    regions = ('NTSC', 'PAL') if args.region == 'both' else (args.region,)
    report = dict(rom_sha256=hashlib.sha256((ec.ROOT / 'build/AITD32X.32x').read_bytes()).hexdigest(),
                  native=[measure(args.core, region, off) for region in regions])
    output = ec.ROOT / 'build' / ('menu-latency-' + args.label + '.json')
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
