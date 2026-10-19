#!/usr/bin/env python3
"""Run real ROM save/load against extended SSF and MiSTer SRAM bus models.

Stock PicoDrive lacks extended SSF: select that backend in private RAM after
boot. This checks the compiled transport, not extended mapper autodetection,
physical arbitration or SD export. No battery files are read or written.
"""
import argparse
import ctypes as C
import hashlib
import json
import subprocess
from pathlib import Path

import check_startup_native as startup
import emulator_check as ec

READ = C.CFUNCTYPE(C.c_uint32, C.c_uint32)
WRITE = C.CFUNCTYPE(None, C.c_uint32, C.c_uint32)
FLAG = 1 << (C.sizeof(C.c_size_t) * 8 - 1)


class SRAM:
    def __init__(self, emulator, mode, saved=None):
        self.e, self.mode = emulator, mode
        self.ctrl, self.page, self.bank0, self.standard = 0xC000, 4, 0, 0
        self.reads = self.writes = self.restores = self.probes = 0
        self.errors, self.offsets = [], set()
        self.bytes = bytearray(saved or bytes(32768))
        lib = self.e.lib
        self.tables = {(kind, width): (C.c_size_t * 256).in_dll(lib, f'm68k_{kind}{width}_map')
                       for kind in ('read', 'write') for width in (8, 16)}
        self.original = {key: list(table) for key, table in self.tables.items()}
        self.io = {width: WRITE((self.original['write', width][0xA1] & ~FLAG) << 1) for width in (8, 16)}
        lib.cpu68k_map_set.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.c_void_p, C.c_int]
        self.callbacks = {('read', 8): READ(lambda a: self.read(a, 8)),
                          ('read', 16): READ(lambda a: self.read(a, 16)),
                          ('write', 8): WRITE(lambda a, v: self.write(a, v, 8)),
                          ('write', 16): WRITE(lambda a, v: self.write(a, v, 16))}
        self.controls = {width: WRITE(lambda a, v, width=width: self.control(a, v, width)) for width in (8, 16)}
        self.install()

    def install(self):
        lib = self.e.lib
        for key, callback in self.callbacks.items():
            table = self.tables[key]
            if self.active():
                lib.cpu68k_map_set(C.addressof(table), 0x200000, 0x27ffff, C.cast(callback, C.c_void_p), 1)
            else:
                for page in range(0x20,0x28): table[page]=self.original[key][page]
            if key[0] == 'read':
                if self.bank0:
                    lib.cpu68k_map_set(C.addressof(table), 0, 0xffff, C.cast(callback, C.c_void_p), 1)
                else: table[0]=self.original[key][0]
        for width, callback in self.controls.items():
            lib.cpu68k_map_set(C.addressof(self.tables['write', width]), 0xA10000, 0xA1ffff,
                              C.cast(callback, C.c_void_p), 1)

    def require(self, condition, message):
        if not condition and len(self.errors) < 10:
            self.errors.append(message)

    def rv(self):
        return self.e.regs[3] & 1

    def control(self, address, value, width):
        if address == 0xA130F0:
            self.require(width == 16 and self.rv(), 'unprotected control write')
            if self.mode != 'mister':
                self.ctrl, self.bank0 = value, value & 31
                if self.bank0 == 2:
                    self.probes += 1
                if value == 0xC000:
                    self.require(self.page == 4, '32X mode restored before bank 4')
                    self.restores += 1
                self.install()
                return
            self.standard = value & 3
        elif address == 0xA130F1:
            self.require(self.mode == 'mister', 'extended hardware used conventional SRAM')
            self.require(self.rv(), 'conventional SRAM switch without RV')
            self.standard = value & 3
            if self.standard == 2:
                self.restores += 1
        elif address == 0xA130F8 and self.mode != 'mister':
            self.require(self.rv(), 'bank write without RV')
            self.require(value in (4, 31), 'unexpected SRAM bank')
            self.page = value
            self.install()
            return
        self.io[width](address, value)
        if address not in (0xA130F0,0xA130F1): return
        # PicoDrive changes its maps when a conventional SRAM switch is written.
        self.install()

    def rom_read(self, address, width):
        if address < 0x10000 and self.mode != 'mister' and self.bank0:
            physical = self.bank0 * 0x80000 + address
            return int.from_bytes(self.e.rom.raw[physical:physical + width // 8], 'big')
        entry = self.original['read', width][address >> 16]
        if entry & FLAG:
            return READ((entry & ~FLAG) << 1)(address)
        pointer = (entry << 1) + (address ^ (width == 8))
        return (C.c_uint8 if width == 8 else C.c_uint16).from_address(pointer).value

    def active(self):
        return self.page == 31 if self.mode != 'mister' else self.standard & 1

    def offset(self, address, width, write=False):
        self.require(self.rv(), 'SRAM access without RV')
        self.require(width == 8 and address & 1, 'SRAM must use odd-byte bus cycles')
        if self.mode != 'mister':
            self.require(self.ctrl == (0xA000 if write else 0x8000), 'incorrect extended protection')
            base = 0x240001
        else:
            self.require(self.standard == (1 if write else 3), 'incorrect conventional protection')
            base = 0x200001
        self.require(base <= address < base + 65536, 'access outside documented SRAM window')
        offset = ((address - base) // 2) & 32767
        self.offsets.add(offset)
        return offset

    def read(self, address, width):
        if address < 0x200000 or not self.active():
            return self.rom_read(address, width)
        offset = self.offset(address, width)
        self.reads += 1
        return self.bytes[offset] if width == 8 else 0xff00 | self.bytes[offset]

    def write(self, address, value, width):
        self.require(self.active(), 'write outside SRAM mapping')
        offset = self.offset(address, width, True)
        self.writes += 1
        self.bytes[offset] = value & 255

    def verify(self):
        assert not self.errors, self.errors
        assert self.ctrl == 0xC000 and self.page == 4 and not self.rv()
        if self.mode == 'mister':
            assert self.standard == 2
        else:
            assert self.restores, 'extended mapping was not restored'
        assert any(offset >= 16384 for offset in self.offsets), 'second journal was not exercised'


class StockSRAM:
    def __init__(self, emulator):
        self.e = emulator
        self.reads = self.writes = 0
        # PicoDrive reports zero size for an entirely empty battery store.
        assert emulator.lib.retro_get_memory_size(0) in (0, 65536)
        raw = (C.c_uint8 * 65536).from_address(emulator.lib.retro_get_memory_data(0))
        self.bytes = memoryview(raw).cast('B')[1::2]

    def verify(self):
        assert not self.e.regs[3] & 1, 'save left RV set'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('core', type=Path)
    parser.add_argument('--mars', type=Path, default=ec.ROOT / '.local/toolchain/mars')
    parser.add_argument('--region', choices=('NTSC', 'PAL'), default='NTSC')
    parser.add_argument('--mode', choices=('stock', 'extended', 'mister'), default='extended')
    args = parser.parse_args()
    symbols = subprocess.check_output([str(args.mars / 'm68k-elf/bin/m68k-elf-nm'),
                                       '--defined-only', str(ec.ROOT / 'build/md_start.elf')], text=True)
    address = next(int(line.split()[0], 16) for line in symbols.splitlines() if line.endswith(' extended_mapper'))
    offsets, models = startup.layout(args.mars), []
    original = startup.Check

    def modeled_check(core, region, offsets):
        check = original(core, region, offsets)
        check.wait(check.settled)
        lib = check.e.lib
        lib.m68k_read16.argtypes = [C.c_uint32]
        lib.m68k_read16.restype = C.c_uint32
        lib.m68k_write16.argtypes = [C.c_uint32, C.c_uint16]
        assert lib.m68k_read16(address) == 0, 'stock PicoDrive should select conventional SRAM'
        if args.mode == 'stock':
            models.append(StockSRAM(check.e))
        else:
            lib.m68k_write16(address, int(args.mode == 'extended'))
            models.append(SRAM(check.e, args.mode))
        return check

    startup.Check = modeled_check
    check = modeled_check(args.core, args.region, offsets)
    try:
        check.press(startup.A)
        check.phase(5)
        startup.choose(check, startup.assets(), 0)
        check.press(startup.START)
        check.phase(10)
        check.press(startup.START)
        check.press(startup.DOWN)
        check.press(startup.A)
        check.wait(lambda: check.read('notice') in (1, 3), seconds=30)
        assert check.read('notice') == 1, 'first save failed'
        first_position = check.position()
        first = bytes(models[-1].bytes)
        check.press(startup.A)
        check.wait(lambda: models[-1].bytes[16384:16388] == b'AITD', seconds=30)
        check.wait(check.settled)
        check.wait(lambda: check.read('notice') == 1)
        saved = bytes(models[-1].bytes)
        assert saved[:16384] == first[:16384], 'second save overwrote previous journal'
        assert saved[:4] == saved[16384:16388] == b'AITD'
        models[-1].verify()
        check.close()
        check = startup.Check(args.core, args.region, offsets)
        models[-1].bytes[:] = saved
        check.press(startup.A)
        check.phase(5)
        check.press(startup.B)
        check.phase(10)
        assert check.state()['paused'] and check.position() == first_position
        assert not check.state()['fault'] and check.mapper_valid()
        models[-1].verify()
        check.press(startup.START)
        check.advance(check.hz)
        assert not check.state()['paused'] and not check.state()['fault']
        report = dict(region=args.region, backend=args.mode, extended_mapper_autodetection_validated=False,
                      two_journals=True, core_restart=True, no_battery_files=True,
                      hardware_and_sd_export_validated=False,
                      byte_reads=sum(m.reads for m in models), byte_writes=sum(m.writes for m in models),
                      rom_sha256=hashlib.sha256((ec.ROOT / 'build/AITD32X.32x').read_bytes()).hexdigest())
        (ec.ROOT / 'build' / f'sram-{args.mode}-{args.region}.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)
    finally:
        check.close()


if __name__ == '__main__':
    main()
