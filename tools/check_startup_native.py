#!/usr/bin/env python3
"""Focused original-startup/mapper/save checks on the actual PicoDrive ROM.

All SRAM fixtures remain in memory. Captures and the report are ignored build
artifacts. This validates emulation; the hardware mapper/RV handshake is not
validated by this check.
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
from aitdpack.startup import decode_lz4

PHASES = ["logo", "flash", "rotate", "title", "credits", "menu", "character", "biography", "arrival", "picture", "gameplay"]
DOWN, LEFT, RIGHT, B, A, START = 2, 4, 8, 16, 64, 128


def layout(mars):
    fields = {"world": "offsetof(Game,world)",
              "fault": "offsetof(World,fault_code)", "menu": "offsetof(Game,menu)",
              "selection": "offsetof(Game,selection)", "notice": "offsetof(Game,action_selection)",
              "book_line": "offsetof(Game,book_line)", "pos": "offsetof(Game,player)+offsetof(Actor,pos)",
              "vars": "offsetof(World,vars)", "since": "offsetof(Game,startup_since)",
              "time": "offsetof(Game,startup_time)"}
    source = ec.ROOT / "build/startup-native-layout.cpp"
    source.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned layout[]={' + ','.join(fields.values()) + '};\n')
    output = source.with_suffix('.s')
    subprocess.run([str(mars / "sh-elf/bin/sh-elf-g++"), "-m2", "-mb", "-std=c++17",
                    "-Wno-invalid-offsetof", "-I" + str(ec.ROOT), "-S", str(source), "-o", str(output)], check=True)
    values = re.findall(r'\.long\s+([-0-9xa-fA-F]+)', output.read_text().split('_layout:', 1)[1].split('.ident', 1)[0])
    return dict(zip(fields, (int(value, 0) for value in values)))


class Check:
    def __init__(self, core, region, offsets):
        self.e = ec.Emulator(core, region)
        self.hz = 50 if region == 'PAL' else 60
        self.region, self.offsets, self.frames = region, offsets, 1
        self.e.run(1)
        self.memory = C.c_void_p.in_dll(self.e.lib, 'Pico32xMem').value
        while not self.memory and self.frames < self.hz * 5:
            self.e.run(1)
            self.frames += 1
            self.memory = C.c_void_p.in_dll(self.e.lib, 'Pico32xMem').value
        assert self.memory, '32X did not initialize'
        self.game = ec.symbol_address('__ZL4game') & 0x3ffff
        self.debug = ec.symbol_address('_debug_state') & 0x3ffff
        self.banks = (C.c_uint8 * 8).in_dll(self.e.lib, 'carthw_ssf2_banks')
        assert C.c_int.in_dll(self.e.lib, 'carthw_ssf2_active').value, 'SSF2 mapper inactive'
        self.e.lib.retro_get_memory_data.argtypes = [C.c_uint]
        self.e.lib.retro_get_memory_data.restype = C.c_void_p
        self.e.lib.retro_get_memory_size.argtypes = [C.c_uint]
        self.e.lib.retro_get_memory_size.restype = C.c_size_t
        self.e.capture_audio = True

    def state(self):
        words = (C.c_uint16 * 64).from_address(self.memory + self.debug)
        values = [C.c_int32((words[i * 2] << 16) | words[i * 2 + 1]).value for i in range(32)]
        return dict(tick=values[0], camera=values[1], mode=values[6], paused=values[7],
                    character=values[8], rendered=values[10], floor=values[16], room=values[17],
                    menu=values[18], fault=values[19], world_ticks=values[26],
                    phase=10 if values[6] else values[27])

    def read(self, name, world=False):
        off = self.offsets[name] + (self.offsets['world'] if world else 0)
        words = (C.c_uint16 * 2).from_address(self.memory + self.game + off)
        return C.c_int32((words[0] << 16) | words[1]).value

    def position(self):
        words = (C.c_uint16 * 6).from_address(self.memory + self.game + self.offsets['pos'])
        return [C.c_int32((words[i*2] << 16) | words[i*2+1]).value for i in range(3)]

    def advance(self, frames=1, pad=0):
        self.e.run(frames, pad)
        self.frames += frames
        assert self.e.comm()[0] != 0xe001, ('native fatal', self.e.comm(), self.state())

    def wait(self, predicate, seconds=20):
        for _ in range(int(self.hz * seconds)):
            if predicate():
                return
            self.advance()
        raise AssertionError(('timeout', self.state(), self.e.comm(), self.read('book_line')))

    def settled(self):
        return (self.e.comm()[0] & 0xff00) in (0x0100, 0x1000) and self.banks[1] == 1

    def phase(self, phase, seconds=20):
        self.wait(lambda: self.state()['phase'] == phase, seconds)
        self.wait(self.settled, seconds)
        self.advance(self.hz // 3)
        self.wait(self.settled, seconds)
        assert self.banks[1] == 1, ('mapper not restored', list(self.banks))

    def press(self, pad):
        self.advance(self.hz // 5)
        self.advance(self.hz // 5, pad)
        self.advance(self.hz // 4)
        self.wait(self.settled)

    def scene(self):
        table, pixels = self.e.framebuffer()
        assert table == [256 + y * 160 for y in range(224)], 'framebuffer line table changed'
        assert not any(pixels[:320 * 12] + pixels[320 * 212:]), 'startup borders should be black'
        return pixels[320 * 12:320 * 212]

    def visible(self):
        raw = self.e.raw
        return any(raw) if self.e.pixel_format != 1 else any(raw[::4]) or any(raw[1::4]) or any(raw[2::4])

    def capture(self, name):
        # The video callback can precede the SH-2 flip in this retro_run.
        self.advance(2)
        self.e.capture('startup-' + self.region + '-' + name + '.png')

    def close(self):
        self.e.close()


def assets():
    manifest = json.loads((ec.ROOT / 'assets/manifest.json').read_text())
    bank = (ec.ROOT / 'assets/bank.bin').read_bytes()
    entries = {a['name']: a for a in manifest['assets']}
    def decode(name):
        asset = entries[name]
        raw = bank[asset['offset']:asset['offset'] + asset['packed_size']]
        flag = asset['flags'] & 0x7fff
        if flag == 2:
            return decode_lz4(raw, asset['unpacked_size'])
        if flag == 4:
            return raw[:4] + decode_lz4(raw[4:], asset['unpacked_size'] - 4)
        if flag in (1, 3):
            start = 4 if flag == 3 else 0
            return raw[:start] + b''.join(bytes((raw[i+1],)) * raw[i] for i in range(start, len(raw), 2))
        assert flag == 0
        return raw
    return decode


def menu_panel(check, decode):
    pixels = check.scene()
    raw = decode('UI_STARTUP_MENU')
    assert struct.unpack_from('>HH', raw) == (320, 80)
    panel = raw[4:]
    # Original bezel only; its interior is intentionally overlaid with text.
    for y in range(80):
        for x in range(320):
            if x < 8 or x >= 312 or y < 8 or y >= 72:
                assert pixels[(y + 60) * 320 + x] == panel[y * 320 + x], ('menu bezel', x, y)
    check.capture('menu')


def boot(check, decode):
    seen = {}
    rotate_hashes = set()
    logo_verified = False
    title_captured = False
    captured = set()
    deadline = check.hz * 45
    while check.frames < deadline:
        state = check.state()
        phase = state['phase']
        if state['rendered'] and phase not in seen:
            seen[phase] = check.frames
            print(check.region, PHASES[phase], round(check.frames / check.hz, 3), flush=True)
        if phase == 0 and check.read('time') - check.read('since') > 400 and check.settled():
            assert check.scene() == decode('STARTUP_LOGO_IMAGE'), 'original logo bitmap differs'
            logo_verified = True
        if phase == 2 and check.settled():
            rotate_hashes.add(hashlib.sha256(check.scene()).hexdigest())
        if phase == 3 and check.read('time') - check.read('since') > 400 and check.settled():
            assert check.scene() == decode('TITLE'), 'original title bitmap differs'
            if not title_captured:
                check.capture('title')
                title_captured = True
        if phase in (0, 2, 4) and phase not in captured and check.settled() and check.read('time') - check.read('since') > (1800 if phase == 2 else 800):
            check.capture(PHASES[phase])
            captured.add(phase)
        if phase == 5:
            break
        check.advance()
    assert list(seen) == list(range(6)), seen
    assert logo_verified, 'original logo bitmap was never checked'
    assert len(rotate_hashes) >= 4, '3D logo is not visibly animated'
    # Allow a few VBlanks for initialization/decode/rendering and presentation.
    assert abs((seen[1] - seen[0]) / check.hz - 212 / 60) < .35, seen
    assert abs((seen[2] - seen[1]) / check.hz - 2 / 60) < .20, seen
    assert abs((seen[3] - seen[2]) / check.hz - 150 / 60) < .40, seen
    assert abs((seen[4] - seen[3]) / check.hz - 72 / 60) < .40, seen
    check.phase(5)
    menu_panel(check, decode)
    return dict(phase_entry_seconds={PHASES[p]: round(frame / check.hz, 3) for p, frame in seen.items()},
                rotating_logo_frames=len(rotate_hashes), original_logo_title_and_menu_pixels=True)


def choose(check, decode, character):
    check.press(A)
    check.phase(6)
    check.press(LEFT if character else RIGHT)
    check.wait(lambda: check.state()['character'] == character, 5)
    selection = decode('STARTUP_SELECTION')
    scene = check.scene()
    x = 0 if character else 160
    for y in range(10, 190):
        assert scene[y*320 + x + 10:y*320 + x + 149] == selection[y*320 + x + 10:y*320 + x + 149], 'portrait pixels differ'
    check.capture('character-' + str(character))
    check.press(A)
    check.phase(7)
    check.wait(lambda: check.visible() and check.settled() and check.read('time') - check.read('since') >= 400, 5)
    pages = struct.unpack_from('>H', decode('STARTUP_BIOGRAPHY_' + str(character)), 2)[0]
    assert check.read('book_line') == 0 and pages > 1
    first = check.scene()
    check.capture('biography-' + str(character))
    check.press(RIGHT)
    assert check.read('book_line') == 1
    check.wait(lambda: check.scene() != first, 5)
    check.press(LEFT)
    assert check.read('book_line') == 0
    check.wait(lambda: check.scene() == first, 5)
    for page in range(pages):
        assert check.read('book_line') == page
        check.press(A)
    check.phase(8)
    return pages


def video_image(check, expected):
    """Compare an indexed original image with the actual libretro RGB output.

    Match each original palette index to one output color. This tolerates both
    supported 15/16-bit video formats while requiring the complete image's
    pixel pattern and a visibly varied palette.
    """
    rgb = check.e.rgb_pixels()[12 * 320 * 3:212 * 320 * 3]
    colors = {}
    for position, index in enumerate(expected):
        color = rgb[position * 3:position * 3 + 3]
        if index in colors:
            if colors[index] != color:
                return False
        else:
            colors[index] = color
    return len(set(colors.values())) > 16


def picture_hold(check, decode, number=0):
    expected = decode('STARTUP_PICTURE')
    tick = check.state()['world_ticks']
    phase_frames = video_frames = 0
    captured = False
    for _ in range(check.hz * 5):
        state = check.state()
        visible = video_image(check, expected)
        if visible:
            video_frames += 1
            if not captured:
                # The callback now contains the flipped close-up, not the
                # preceding camera frame. Do not advance its display clock.
                check.e.capture('startup-' + check.region + '-picture-' + str(number) + '.png')
                captured = True
        if state['phase'] == 9:
            assert state['world_ticks'] == tick, 'picture advanced the 25 Hz world'
            phase_frames += 1
        elif not visible:
            break
        check.advance()
    assert captured and abs(video_frames / check.hz - 20 / 60) < .12, ('frog visible duration', video_frames)
    check.wait(check.settled)
    assert check.banks[1] == 1
    return dict(world_ticks=tick, seconds=round(phase_frames / check.hz, 3),
                video_frames=video_frames, video_seconds=round(video_frames / check.hz, 3),
                original_video_pixels=True)


def arrival(check, decode, full=True):
    paths = []
    pictures = []
    before = len(check.e.audio)
    banked_frames = banked_sound_frames = 0
    deadline = check.frames + check.hz * (200 if full else 4)
    last = None
    while check.frames < deadline:
        s = check.state()
        assert not check.read('fault', world=True), ('intro LIFE error', s)
        if s['phase'] == 10:
            break
        path = (s['floor'], s['room'], s['camera'])
        if s['phase'] == 8 and path != last:
            paths.append(dict(floor=path[0], room=path[1], camera=path[2], seconds=round(check.frames/check.hz, 3), world_ticks=s['world_ticks']))
            print(check.region, 'arrival', path, 'tick', s['world_ticks'], flush=True)
            last = path
            if check.settled():
                assert check.banks[1] == 1
        if s['phase'] == 9:
            assert check.scene() == decode('STARTUP_PICTURE'), 'original frog picture differs'
            pictures.append(picture_hold(check, decode, len(pictures)))
        else:
            audio_start = len(check.e.audio)
            check.advance()
            if check.banks[1] != 1:
                banked_frames += 1
                if any(check.e.audio[audio_start:]):
                    banked_sound_frames += 1
    if full:
        assert check.state()['phase'] == 10, ('arrival did not finish', check.state(), paths)
        assert pictures, 'original arrival picture was not displayed'
        assert {p['floor'] for p in paths} >= {1, 2, 3, 7}, paths
    else:
        check.press(START)
        check.phase(10)
    s = check.state()
    assert (s['mode'], s['floor'], s['room'], s['character']) == (1, 0, 0, s['character']), s
    assert check.banks[1] == 1
    # Native audio remains autonomous while banked images are mapped/decoded.
    nonzero = any(check.e.audio[before:])
    if full:
        assert nonzero, 'arrival audio produced silence'
    check.capture('gameplay')
    return dict(path=paths, pictures=pictures, full_sequence=full, audio_nonzero=nonzero,
                banked_frame_samples=banked_frames, banked_frames_with_audio=banked_sound_frames, bank_restored=1)


def save_reload(check, core, offsets):
    check.press(START)
    assert check.state()['paused'] and check.read('menu') == 3
    off = check.memory + check.game + offsets['world'] + offsets['vars'] + 90 * 2
    C.c_int16.from_address(off).value = 17
    check.press(DOWN)
    assert check.read('selection') == 1
    check.press(A)
    check.wait(lambda: check.read('notice') == 1)
    assert check.e.lib.retro_get_memory_size(0) == 131072
    sram = C.string_at(check.e.lib.retro_get_memory_data(0), 131072)
    assert sram[:4] == b'AITD'
    pose = check.state()
    position = check.position()
    check.capture('save')
    # Replace no files: a new core receives only this transient SRAM buffer.
    region = check.region
    check.close()
    loaded = Check(core, region, offsets)
    C.memmove(loaded.e.lib.retro_get_memory_data(0), sram, len(sram))
    loaded.advance(loaded.hz)
    loaded.press(A)
    loaded.phase(5)
    loaded.press(B)
    loaded.phase(10)
    assert loaded.state()['paused'] and loaded.read('menu') == 3
    assert loaded.state()['character'] == pose['character']
    assert loaded.position() == position, 'saved player pose differs'
    assert (loaded.state()['floor'], loaded.state()['room']) == (0, 0)
    off = loaded.memory + loaded.game + offsets['world'] + offsets['vars'] + 90 * 2
    assert C.c_int16.from_address(off).value == 17
    assert loaded.banks[1] == 1
    loaded.capture('loaded')
    loaded.press(START)
    assert not loaded.state()['paused']
    return loaded, dict(sram_bytes=131072, paused_core_restart=True, world_variable_restored=True,
                        position=position, no_sram_file=True)


def return_menu(check):
    check.press(START)
    assert check.read('menu') == 3
    for _ in range(3):
        check.press(DOWN)
    check.press(A)
    check.phase(5)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('core', type=Path)
    p.add_argument('--region', choices=('NTSC', 'PAL'), default='NTSC')
    p.add_argument('--mars', type=Path, default=ec.ROOT / '.local/toolchain/mars')
    p.add_argument('--short-arrival', action='store_true', help='skip after four seconds instead of replaying the full arrival')
    args = p.parse_args()
    offsets, decode = layout(args.mars), assets()
    sha = hashlib.sha256((ec.ROOT / 'build/AITD32X.32x').read_bytes()).hexdigest()
    check = Check(args.core, args.region, offsets)
    try:
        report = dict(region=args.region, rom_sha256=sha, rom_bytes=len((ec.ROOT/'build/AITD32X.32x').read_bytes()), emulator_only=True)
        report['boot'] = boot(check, decode)
        first_character = 1 if args.region == 'PAL' else 0
        report['biography_pages_' + str(first_character)] = choose(check, decode, first_character)
        report['arrival'] = arrival(check, decode, not args.short_arrival)
        check, report['save'] = save_reload(check, args.core, offsets)
        return_menu(check)
        report['biography_pages_' + str(first_character ^ 1)] = choose(check, decode, first_character ^ 1)
        report['skip'] = arrival(check, decode, False)
        report['final_character'] = check.state()['character']
        assert report['final_character'] == first_character ^ 1
        assert hashlib.sha256((ec.ROOT/'build/AITD32X.32x').read_bytes()).hexdigest() == sha, 'ROM changed during validation'
        (ec.ROOT / 'build' / ('startup-native-' + args.region + ('-short' if args.short_arrival else '') + '.json')).write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2), flush=True)
    finally:
        check.close()


if __name__ == '__main__':
    main()
