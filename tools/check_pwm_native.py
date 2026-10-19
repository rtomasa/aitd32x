#!/usr/bin/env python3
"""Actual-ROM PWM duration, voice controls, idle output and render-cost checks.

All fixtures use private emulator RAM. No battery files or external packages.
--baseline records the preceding 8 kHz implementation without new idle checks.
"""
import argparse
import ctypes as C
import hashlib
import json
import re
import struct
import subprocess
import wave
from pathlib import Path

import check_startup_native as startup
import emulator_check as ec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('core', type=Path)
    parser.add_argument('--mars', type=Path, default=ec.ROOT / '.local/toolchain/mars')
    parser.add_argument('--region', choices=('NTSC', 'PAL'), default='NTSC')
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    label = 'before' if args.baseline else 'after'
    root = ec.ROOT
    offsets = startup.layout(args.mars)
    source = root / 'build/pwm-layout.cpp'
    source.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned pwm_layout[]={offsetof(Game,paused),offsetof(Game,dirty)};\n')
    assembly = source.with_suffix('.s')
    subprocess.run([str(args.mars / 'sh-elf/bin/sh-elf-g++'), '-m2', '-mb', '-std=c++17',
                    '-w', '-I'+str(root), '-S', str(source), '-o', str(assembly)], check=True)
    values = re.findall(r'\.long\s+([-0-9xa-fA-F]+)', assembly.read_text().split('_pwm_layout:', 1)[1].split('.ident', 1)[0])
    offsets.update(zip(('paused', 'dirty'), (int(v, 0) for v in values)))
    symbols = subprocess.check_output([str(args.mars / 'sh-elf/bin/sh-elf-nm'), str(root / 'build/AITD32X.elf')], text=True)
    queue = min(int(line.split()[0], 16) & 0x3ffff for line in symbols.splitlines()
                if line.endswith('__ZN12_GLOBAL__N_1L7storageE'))
    voice = ec.symbol_address('__ZN12_GLOBAL__N_1L6voicesE') & 0x3ffff
    running = ec.symbol_address('__ZN12_GLOBAL__N_1L7runningE') & 0x3ffff
    bank = (root / 'assets/bank.bin').read_bytes()
    manifest = json.loads((root / 'assets/manifest.json').read_text())
    sounds = {int(a['name'][6:]): struct.unpack_from('>I', bank, a['offset'])[0]
              for a in manifest['assets'] if a['name'].startswith('SOUND_')}
    check = startup.Check(args.core, args.region, offsets)
    rows = []
    try:
        check.wait(check.settled)
        check.press(startup.A);check.phase(5)
        startup.choose(check, startup.assets(), 0)
        check.press(startup.START);check.phase(10)

        def word(offset):
            a = (C.c_uint16 * 2).from_address(check.memory + offset)
            return (a[0] << 16) | a[1]

        def write(offset, value):
            a = (C.c_uint16 * 2).from_address(check.memory + offset)
            a[0], a[1] = (value >> 16) & 65535, value & 65535

        def byte(offset):
            return C.c_uint8.from_address(check.memory + (offset ^ 1)).value

        def live():
            return word(voice + 4) or word(voice + 28 + 4) or byte(running)

        def request(sample, next_sample=-1, repeat=0):
            check.wait(lambda: word(queue) == word(queue + 4))
            n = word(queue);entry = queue + 8 + (n & 7) * 8
            for i, value in enumerate((sample, next_sample, repeat, 0)):
                C.c_uint16.from_address(check.memory + entry + i*2).value = value & 65535
            write(queue, n + 1)

        def idle():
            if args.baseline:
                return
            assert check.e.regs[24] & 15 == 0, 'carrier remains enabled at idle'

        # Freeze the world through the real pause flag, without a menu overlay.
        C.c_uint8.from_address(check.memory + check.game + (offsets['paused'] ^ 1)).value = 1
        request(-2);check.wait(lambda: not live());idle()
        for sample, next_sample, repeat in ((6, -1, 0), (30, -1, 0), (31, -1, 0), (30, 31, 0), (31, -1, 1)):
            expected = (sounds[sample] * (repeat + 1) + (sounds[next_sample] if next_sample >= 0 else 0)) / 8000
            start = check.frames
            check.e.capture_audio = True;check.e.audio.clear()
            request(sample, next_sample, repeat)
            check.wait(lambda: live())
            cycle = check.e.regs[25]
            if not args.baseline:
                assert cycle == (951 if args.region == 'PAL' else 960)
            check.wait(lambda: not live(), seconds=expected + 2)
            elapsed = (check.frames - start) / check.hz
            assert abs(elapsed - expected) < 3/check.hz, (sample, elapsed, expected)
            assert any(check.e.audio), 'silent effect'
            assert word(voice + 8) == sounds[next_sample if next_sample >= 0 else sample], 'effect was truncated'
            idle()
            if sample in (30, 31) and next_sample == -1 and not repeat:
                path = root / 'build' / f'pwm-{label}-{args.region}-step-{sample}.wav'
                with wave.open(str(path), 'wb') as wav:
                    wav.setparams((2, 2, 44100, 0, 'NONE', 'not compressed'));wav.writeframes(check.e.audio)
            rows.append(dict(sample=sample, next=next_sample, repeat=repeat, expected_seconds=expected,
                             observed_seconds=elapsed, cycle=cycle))
            check.e.capture_audio = False
            check.advance(check.hz // 10)

        request(30, repeat=-1);check.wait(lambda: word(voice + 4) != 0)
        check.advance(check.hz // 3)
        request(31, repeat=-1);check.wait(lambda: word(voice + 28 + 4) != 0)
        check.advance(check.hz // 3)
        assert word(voice + 4) and word(voice + 28 + 4), 'second voice cut off the first'
        request(-2);check.wait(lambda: not live());idle()

        def benchmark(audio):
            if audio:
                request(30, repeat=-1);request(31, repeat=-1)
                check.wait(lambda: word(voice + 4) and word(voice + 28 + 4))
            ticks = check.state()['world_ticks']
            def frame():
                C.c_uint8.from_address(check.memory + check.game + (offsets['dirty'] ^ 1)).value = 1
                check.advance()
                assert check.state()['world_ticks'] == ticks
            for _ in range(check.hz):frame()
            start = check.state()['rendered']
            for _ in range(check.hz * 4):frame()
            fps = (check.state()['rendered'] - start) / 4
            request(-2);check.wait(lambda: not live());idle()
            return fps

        quiet, active = benchmark(False), benchmark(True)
        report = dict(region=args.region, label=label, checks=rows, two_voices_and_stop=True,
                      quiet_render_fps=quiet, two_voice_render_fps=active,
                      rom_sha256=hashlib.sha256((root / 'build/AITD32X.32x').read_bytes()).hexdigest(),
                      emulation_only=True, user_battery_files_touched=False)
        (root / 'build' / f'pwm-{label}-{args.region}.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2), flush=True)
    finally:
        check.close()


if __name__ == '__main__':
    main()
