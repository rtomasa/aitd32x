#!/usr/bin/env python3
"""Compare actual text/layout pixels with a preserved renderer, in private RAM.

Exercises the complete imported font, clipping, black ink, both framebuffer
banks, all layout pages, and synthetic 1..15-pixel glyphs at every bit offset.
Original assets and user battery files are never modified.
"""
import argparse
import ctypes as C
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, default=ROOT / 'build/libaitd32x.so')
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/font-spans.json')
    args = parser.parse_args()
    libraries = [C.CDLL(str(path.resolve())) for path in (args.reference, args.library)]
    data = (ROOT / 'assets/bank.bin').read_bytes()
    memory = C.create_string_buffer(data)
    entries = json.loads((ROOT / 'assets/manifest.json').read_text())['assets']
    font = next(a for a in entries if a['name'] == 'READ_FONT')
    renderers, draw, clipped, layout = [], [], [], []
    for lib in libraries:
        lib.host_init.argtypes = [C.c_void_p, C.c_uint]
        lib.host_pixels.restype = lib.host_palette.restype = C.c_void_p
        lib.host_init(memory, len(data))
        # Renderer begins with its public 320x200 byte background, then palette.
        renderers.append(lib.host_palette()-320*200)
        draw.append(getattr(lib, '_Z13Book_DrawTextR8RendereriiPKchb'))
        draw[-1].argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_char_p, C.c_ubyte, C.c_bool]
        clipped.append(getattr(lib, '_Z20Book_DrawClippedTextR8RendereriiPKcihbb'))
        clipped[-1].argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_char_p, C.c_int, C.c_ubyte, C.c_bool, C.c_bool]
        layout.append(getattr(lib, '_Z15Book_DrawLayoutR8Rendererjjh'))
        layout[-1].argtypes = [C.c_void_p, C.c_uint, C.c_uint, C.c_ubyte]
    comparisons = 0

    def compare(kind, arguments, bank):
        nonlocal comparisons
        images = []
        for i, lib in enumerate(libraries):
            lib.host_buffer(bank)
            C.memset(lib.host_pixels(), 0x35, 320*224)
            (draw if kind == 'text' else clipped if kind == 'clipped' else layout)[i](renderers[i], *arguments)
            images.append(C.string_at(lib.host_pixels(), 320*224))
        if images[0] != images[1]:
            raise AssertionError((kind, arguments, bank, 'pixel mismatch'))
        comparisons += 1

    positions = ((-9, -8, False), (0, 0, False), (1, 184, False), (319, 195, True))
    for glyph in range(32, 256):
        for x, y, center in positions:
            for color in (0, 16):
                for bank in (0, 1):
                    compare('text', (x, y, bytes([glyph]), color, center), bank)
    font_offset = font['offset']
    first, _, height, stride_high, stride_low, stride_next, table_high, table_low = data[font_offset:font_offset+8]
    stride = stride_high or (stride_low | stride_next << 8)
    table = (table_high << 8) | table_low
    glyph_entry = font_offset+table+(ord('A')-first)*2
    for bit in range(8):
        for width in range(1, 16):
            C.memmove(C.addressof(memory)+glyph_entry, struct.pack('>H', width << 12 | bit), 2)
            for row in range(height):
                pattern = bytes(((row*37+0xa5)&255, (row*19+0x5a)&255, (row*53+0x81)&255))
                C.memmove(C.addressof(memory)+font_offset+8+row*stride, pattern, 3)
            for x, y, center in positions:
                for color in (0, 255):
                    for bank in (0, 1):
                        compare('text', (x, y, b'AAA', color, center), bank)
    C.memmove(C.addressof(memory)+font_offset, data[font_offset:font_offset+font['packed_size']], font['packed_size'])
    for width in (1, 8, 24, 317):
        for center in (False, True):
            for ellipsis in (False, True):
                for bank in (0, 1):
                    compare('clipped', (1, 184, b'Original mixed Case 0123!\xe9', width, 16, center, ellipsis), bank)
    pages = 0
    for asset in entries:
        if asset['type'] != 17:
            continue
        count = struct.unpack_from('>H', data, asset['offset']+2)[0]
        for page in range(count):
            for bank in (0, 1):
                compare('layout', (asset['id'], page, 1), bank)
            pages += 1
    report = dict(passed=True, comparisons=comparisons, codepoints_32_to_255=224,
                  synthetic_bit_offsets=8, synthetic_widths=15, layout_pages=pages,
                  both_framebuffers=True, private_memory_only=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
