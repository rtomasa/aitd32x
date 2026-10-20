#!/usr/bin/env python3
"""Verify the isolated profiler in PicoDrive, or decode its MiSTer screenshots."""
import argparse
import ctypes as C
import hashlib
import json
import struct
import zlib
from pathlib import Path

import emulator_check as ec

MAGIC = 0x41333250
STAGES = ['update', 'restore_submit', 'transform', 'sort', 'primitives_inclusive',
          'fill', 'mask', 'ui', 'palette', 'flip', 'draw_inclusive', 'queue_wait', 'worker_end_wait']
NAMES = ['live_start', 'frozen_start_quiet', 'frozen_start_two_voices',
         'frozen_near_quiet', 'frozen_near_two_voices', 'frozen_floor3_room1_camera3']


def decode(path):
    data = path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('expected PNG')
    position, compressed = 8, bytearray()
    while position < len(data):
        length, kind = struct.unpack_from('>I4s', data, position)
        chunk = data[position+8:position+8+length]
        if kind == b'IHDR':
            width, height, depth, color, _, _, interlace = struct.unpack('>2I5B', chunk)
        elif kind == b'IDAT':
            compressed.extend(chunk)
        position += length+12
    if (width, height, depth, interlace) != (320, 224, 8, 0) or color not in (2, 6):
        raise ValueError('expected lossless native 320x224 screenshot')
    channels = 3 if color == 2 else 4
    stride = width*channels
    raw, pixels, previous = zlib.decompress(compressed), [], bytearray(stride)
    for y in range(height):
        start = y*(stride+1)
        filtering, row = raw[start], bytearray(raw[start+1:start+1+stride])
        if filtering > 4:
            raise ValueError('unsupported PNG filter')
        for x in range(stride):
            left = row[x-channels] if x >= channels else 0
            above, corner = previous[x], previous[x-channels] if x >= channels else 0
            if filtering == 1:
                predictor = left
            elif filtering == 2:
                predictor = above
            elif filtering == 3:
                predictor = (left+above)//2
            elif filtering == 4:
                p = left+above-corner
                distances = (abs(p-left), abs(p-above), abs(p-corner))
                predictor = (left, above, corner)[distances.index(min(distances))]
            else:
                predictor = 0
            row[x] = (row[x]+predictor)&255
        pixels.append(row)
        previous = row
    values = []
    for word in range(32):
        value = 0
        for bit in range(word*32, word*32+32):
            x, y = (4+bit%256)*channels, 216+bit//256
            pixel = pixels[y][x:x+3]
            value = (value << 1) | (sum(pixel) > 384)
        values.append(value)
    return values


def valid(values):
    checksum = MAGIC
    for value in values[1:31]:
        checksum ^= value
    return values[0] == MAGIC and checksum == values[31]


def result(values):
    if not valid(values):
        raise ValueError('invalid profiler report or screenshot checksum')
    which, hz, draws, vb, frc, updates, fault = values[1:8]
    if which >= len(NAMES) or hz not in (50, 60) or not draws or (not frc and not values[30]) or fault:
        raise ValueError('invalid case, timer, draw count or world fault')
    scale = (vb/hz)*1000/frc/draws if frc else 0.0
    times = {name: values[8+i]*scale for i, name in enumerate(STAGES)}
    if values[30]:
        times['update'] = 0.0  # Low-overhead builds reuse word 8 for scene pixels.
    phases = None
    if values[30] == 9:
        phases = {name: values[9+i]*scale for i, name in enumerate(
                  ('draw_list', 'static_prepare', 'actor_draw', 'contact', 'effects'))}
        for name in STAGES:
            if name not in ('flip', 'draw_inclusive'):
                times[name] = 0.0
    return dict(case=which, name=NAMES[which], variant=values[30], pixel_hash=values[8] if values[30] else None,
                hz=hz, draws=draws, vblanks=vb, timer_available=bool(frc),
                frc_ticks=frc, updates=updates, fault=fault, fps=draws*hz/vb,
                stage_ms_per_draw=times, scene_phase_ms_per_draw=phases,
                raw=values)


def verify(core, project, region):
    original = ec.ROOT
    ec.ROOT = project.resolve()
    emulator = ec.Emulator(core.resolve(), region)
    hz = 50 if region == 'PAL' else 60
    address = ec.symbol_address('_debug_state') & 0x3ffff
    rows = {}
    try:
        for frame in range(hz*100):
            emulator.run(1)
            memory = C.c_void_p.in_dll(emulator.lib, 'Pico32xMem').value
            if not memory:
                continue
            words = (C.c_uint16*64).from_address(memory+address)
            values = [(words[i*2] << 16) | words[i*2+1] for i in range(32)]
            if valid(values) and values[1] not in rows:
                emulator.run(3)
                path = ec.ROOT / 'build' / f'picodrive-case-{values[1]}.png'
                emulator.capture(path.name)
                decoded = decode(path)
                if decoded != values:
                    raise AssertionError('report screenshot differs from published native RAM')
                row = result(values)
                expected_hz = (53203424 if hz == 50 else 53693175)*(int(2.4*1024)/1024)/7/128
                ratio = row['frc_ticks']/(row['vblanks']/hz)/expected_hz
                if 'frt' in core.name and not 0.97 < ratio < 1.03:
                    raise AssertionError(('FRC/VBlank calibration failed', ratio))
                if row['case'] == 0 and abs(row['updates']-75) > 3:
                    raise AssertionError(('live simulation clock', row['updates']))
                row['timer_calibration_ratio'] = ratio
                rows[row['case']] = row
                print(json.dumps(row), flush=True)
                if len(rows) == len(NAMES):
                    break
        if len(rows) != len(NAMES):
            raise AssertionError(('diagnostic did not finish', sorted(rows), values))
        report = dict(platform='PicoDrive, '+region, core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
                      rom_sha256=hashlib.sha256((ec.ROOT / 'build/AITD32X.32x').read_bytes()).hexdigest(),
                      cases=list(rows.values()), private_emulator_memory_only=True)
        (ec.ROOT / 'picodrive.json').write_text(json.dumps(report, indent=2)+'\n')
    finally:
        emulator.close()
        ec.ROOT = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', type=Path)
    parser.add_argument('--project', type=Path, default=ec.ROOT / 'build/mister-profile')
    parser.add_argument('--region', choices=('NTSC', 'PAL'), default='NTSC')
    parser.add_argument('screenshots', nargs='*', type=Path)
    args = parser.parse_args()
    if args.core:
        verify(args.core, args.project, args.region)
    for path in args.screenshots:
        print(json.dumps(dict(path=str(path), **result(decode(path)))))


if __name__ == '__main__':
    main()
