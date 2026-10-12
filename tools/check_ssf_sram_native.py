#!/usr/bin/env python3
"""Exercise the compiled extended-SSF save path with a PicoDrive bus shim.

Stock PicoDrive does not emulate EverDrive's SRAM page. This shim supplies
page-31 SRAM and checks the actual 68000's RV/control/bank write sequence.
It does not validate physical arbitration, FPGA timing, mapper autodetection
or the cartridge OS's SD save export. No battery files are read or written.
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
    def __init__(self, check):
        self.check, self.ctrl, self.page = check, 0xC000, 4
        self.reads = self.writes = self.restores = 0
        self.errors, self.offsets = [], set()
        lib = check.e.lib
        self.rmap = (C.c_size_t * 256).in_dll(lib, 'm68k_read16_map')
        self.wmap = (C.c_size_t * 256).in_dll(lib, 'm68k_write16_map')
        self.w8map = (C.c_size_t * 256).in_dll(lib, 'm68k_write8_map')
        self.original_reads = list(self.rmap)
        self.io = WRITE((int(self.wmap[0xA1]) & ~FLAG) << 1)
        self.io8 = WRITE((int(self.w8map[0xA1]) & ~FLAG) << 1)
        self.bytes = (C.c_uint8 * 131072).from_address(lib.retro_get_memory_data(0))
        lib.cpu68k_map_set.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.c_void_p, C.c_int]
        self.callbacks = [READ(self.read), WRITE(self.write), WRITE(self.control), WRITE(self.control8)]
        for table, first, last, callback in (
                (self.rmap, 0x200000, 0x21FFFF, self.callbacks[0]),
                (self.wmap, 0x200000, 0x21FFFF, self.callbacks[1]),
                (self.wmap, 0xA10000, 0xA1FFFF, self.callbacks[2]),
                (self.w8map, 0xA10000, 0xA1FFFF, self.callbacks[3])):
            lib.cpu68k_map_set(C.addressof(table), first, last, C.cast(callback, C.c_void_p), 1)

    def require(self, condition, message):
        if not condition and len(self.errors) < 10:
            self.errors.append(message)

    def rv(self):
        return self.check.e.regs[3] & 1

    def control(self, address, value):
        if address == 0xA130F0:
            self.require(self.rv(), 'control write without RV')
            self.require(value & 0x8000 and not value & 31, 'unprotected control or bank-0 remap')
            self.ctrl = value
            if value == 0xC000:
                self.require(self.page == 4, '32X mode restored before fixed ROM')
                self.restores += 1
        elif address == 0xA130F8:
            self.require(self.rv(), 'bank write without RV')
            self.require(value in (4, 31), 'unexpected save page')
            self.page = value
        else:
            self.io(address, value)

    def control8(self, address, value):
        self.require(address != 0xA130F1, 'conventional SRAM switch used on extended hardware')
        self.io8(address, value)

    def access(self, address, write=False):
        self.require(self.rv(), 'SRAM access without RV')
        self.require(self.page == 31, 'SRAM access without page 31')
        self.require(self.ctrl == (0xA000 if write else 0x8000), 'incorrect SRAM protection/mode')
        offset = address - 0x200000
        self.require(0 <= offset <= 131070 and not offset & 1, 'SRAM word outside journal')
        self.offsets.add(offset)
        return offset

    def read(self, address):
        if self.page != 31:
            entry = self.original_reads[address >> 16]
            if entry & FLAG:
                return READ((entry & ~FLAG) << 1)(address)
            return C.c_uint16.from_address((entry << 1) + address).value
        offset = self.access(address)
        self.reads += 1
        return self.bytes[offset] << 8 | self.bytes[offset + 1]

    def write(self, address, value):
        offset = self.access(address, True)
        self.writes += 1
        self.bytes[offset], self.bytes[offset + 1] = value >> 8, value & 255

    def verify(self):
        assert not self.errors, self.errors
        assert self.ctrl == 0xC000 and self.page == 4, 'save left ROM writable/remapped'
        assert not self.rv(), 'save left cartridge access with the 68000'
        assert self.restores == self.reads + self.writes
        assert self.check.mapper_valid() and self.check.banks[4] == 4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('core', type=Path)
    parser.add_argument('--mars', type=Path, default=ec.ROOT / '.local/toolchain/mars')
    args = parser.parse_args()
    symbols = subprocess.check_output([str(args.mars / 'm68k-elf/bin/m68k-elf-nm'),
                                       '--defined-only', str(ec.ROOT / 'build/md_start.elf')], text=True)
    address = next(int(line.split()[0], 16) for line in symbols.splitlines()
                   if line.endswith(' extended_mapper'))
    offsets = startup.layout(args.mars)
    original, models = startup.Check, []

    def extended_check(core, region, offsets):
        check = original(core, region, offsets)
        check.wait(check.settled)
        lib = check.e.lib
        lib.m68k_read16.argtypes = [C.c_uint32]
        lib.m68k_read16.restype = C.c_uint32
        lib.m68k_write16.argtypes = [C.c_uint32, C.c_uint16]
        assert lib.m68k_read16(address) == 0, 'stock PicoDrive should select standard SRAM'
        lib.m68k_write16(address, 1)  # Select the compiled hardware path for the shim.
        model = SRAM(check)
        models.append(model)
        return check

    startup.Check = extended_check
    check = extended_check(args.core, 'NTSC', offsets)
    try:
        check.press(startup.A)
        check.phase(5)
        startup.choose(check, startup.assets(), 0)
        startup.arrival(check, startup.assets(), False)
        check, first = startup.save_reload(check, args.core, offsets)
        # The second save uses the other 64 KiB journal, then survives core restart.
        check, second = startup.save_reload(check, args.core, offsets)
        memory = check.e.lib.retro_get_memory_data(0)
        raw = C.string_at(memory, 131072)
        assert raw[:4] == raw[65536:65540] == b'AITD'
        for model in models:
            model.verify()
        report = dict(emulator_only=True, extended_sram_bus_shim=True,
                      hardware_and_sd_export_validated=False, no_battery_files=True,
                      rom_sha256=hashlib.sha256((ec.ROOT / 'build/AITD32X.32x').read_bytes()).hexdigest(),
                      two_journals_and_core_restarts=True, first=first, second=second,
                      word_reads=sum(m.reads for m in models), word_writes=sum(m.writes for m in models),
                      fixed_rom_restores=sum(m.restores for m in models),
                      journal_banks_seen=[sorted({offset // 65536 for offset in m.offsets}) for m in models])
        (ec.ROOT / 'build/ssf-sram-native.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    finally:
        check.close()
        startup.Check = original


if __name__ == '__main__':
    main()
