#!/usr/bin/env python3
"""Validate the built cartridge's fixed assets and SSF2 presentation pages.

Reads generated files only; writes its report under build/. This checks linked
ROM layout and protected audio/code ranges, not mapper operation on hardware.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM_BASE = 0x02000000
ASSET_PHYSICAL = 0x20000
EXTRA_PHYSICAL = 0x400000
PAGE_BYTES = 0x80000
APERTURE = (0x80000, 0x100000)
ROM_LIMIT = 0x2000000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def intersects(start, size, bounds):
    return start < bounds[1] and start + size > bounds[0]


class Elf:
    """The small subset of ELF32 big-endian needed for this SH2 layout check."""
    def __init__(self, data):
        require(data[:6] == b'\x7fELF\x01\x02', 'expected ELF32 big-endian image')
        header = struct.unpack_from('>16sHHIIIIIHHHHHH', data)
        require(header[2] == 42, 'ELF machine is not SuperH')
        program_offset, section_offset = header[5], header[6]
        program_stride, program_count = header[9], header[10]
        section_stride, section_count, strings_index = header[11:14]
        require(program_stride >= 32 and section_stride >= 40, 'invalid ELF table strides')
        require(section_offset + section_count * section_stride <= len(data), 'truncated ELF sections')
        require(program_offset + program_count * program_stride <= len(data), 'truncated ELF segments')
        sections = [struct.unpack_from('>10I', data, section_offset + i * section_stride)
                    for i in range(section_count)]
        require(strings_index < len(sections), 'invalid ELF section string table')

        def bytes_at(offset, size):
            require(offset + size <= len(data), 'truncated ELF payload')
            return data[offset:offset + size]

        def string(table, offset):
            require(offset < len(table), 'invalid ELF name offset')
            end = table.find(b'\0', offset)
            require(end >= 0, 'unterminated ELF name')
            return table[offset:end].decode('ascii', errors='replace')

        names = bytes_at(sections[strings_index][4], sections[strings_index][5])
        self.sections = {string(names, s[0]): s for s in sections}
        self.segments = [struct.unpack_from('>8I', data, program_offset + i * program_stride)
                         for i in range(program_count)]
        self.symbols, self.functions = {}, []
        for section in sections:
            if section[1] != 2:
                continue
            require(section[6] < len(sections) and section[9] >= 16, 'invalid ELF symbol table')
            table = sections[section[6]]
            names = bytes_at(table[4], table[5])
            require(section[5] % section[9] == 0, 'invalid ELF symbol-table size')
            for position in range(section[4], section[4] + section[5], section[9]):
                name, value, size, info, _, _ = struct.unpack_from('>IIIBBH', data, position)
                name = string(names, name)
                self.symbols[name] = value
                if info & 15 == 2 and value:
                    self.functions.append((name, value, size))

    def section(self, name):
        require(name in self.sections, f'missing ELF section {name}')
        return self.sections[name]

    def lma(self, name):
        section = self.section(name)
        for kind, offset, _, physical, file_size, _, _, _ in self.segments:
            if kind == 1 and offset <= section[4] and section[4] + section[5] <= offset + file_size:
                return physical + section[4] - offset
        raise ValueError(f'no load segment contains ELF section {name}')

    def symbol(self, name):
        require(name in self.symbols, f'missing ELF symbol {name}')
        return self.symbols[name]


def check(rom, elf_data, bank, main, extra, manifest):
    require(len(rom) <= ROM_LIMIT and len(rom) % 65536 == 0, 'invalid cartridge size/padding')
    require(rom[0x100:0x110] == b'SEGA 32X        ', 'missing 32X header')
    require(struct.unpack_from('>I', rom, 0x1A4)[0] == len(rom) - 1, 'incorrect ROM end header')
    checksum = sum(value for (value,) in struct.iter_unpack('>H', rom[512:])) & 65535
    require(struct.unpack_from('>H', rom, 0x18E)[0] == checksum, 'incorrect Mega Drive checksum')
    elf = Elf(elf_data)
    require(elf.symbol('_asset_bank') == ROM_BASE + ASSET_PHYSICAL, 'asset bank origin changed')
    require(elf.section('.assets')[3] == ROM_BASE + ASSET_PHYSICAL, 'incorrect fixed asset VMA')
    require(elf.lma('.assets') == ASSET_PHYSICAL, 'incorrect fixed asset LMA')
    require(elf.section('.assets')[5] == len(main), 'fixed asset section size mismatch')
    require(rom[ASSET_PHYSICAL:ASSET_PHYSICAL + len(main)] == main, 'fixed asset bytes differ from ROM')
    require(elf.section('.romextra')[3] == ROM_BASE + EXTRA_PHYSICAL, 'incorrect extra asset VMA')
    require(elf.lma('.romextra') == EXTRA_PHYSICAL, 'incorrect extra asset LMA')
    require(elf.section('.romextra')[5] == len(extra), 'extra asset section size mismatch')
    require(rom[EXTRA_PHYSICAL:EXTRA_PHYSICAL + len(extra)] == extra, 'extra asset bytes differ from ROM')
    require(elf.symbol('_asset_bank_end') - elf.symbol('_asset_bank') == len(bank), 'asset-bank span mismatch')
    require(bank[:len(main)] == main and bank[EXTRA_PHYSICAL - ASSET_PHYSICAL:] == extra,
            'full host bank differs from its fixed/extra parts')

    magic, version, count, size = struct.unpack_from('>4s3I', bank)
    require(magic == b'A32X' and version == 2 and size == len(bank), 'invalid asset-bank header')
    require(16 + count * 16 <= len(main), 'directory leaves fixed asset region')
    require(ASSET_PHYSICAL + 16 + count * 16 <= APERTURE[0], 'directory overlaps mapper aperture')
    require(len(manifest['assets']) == count, 'manifest asset count mismatch')
    require(manifest['bank_sha256'] == hashlib.sha256(bank).hexdigest(), 'manifest bank hash mismatch')
    banked, audio, render_sources = [], [], []
    for index in range(count):
        offset, packed, unpacked, kind, flags = struct.unpack_from('>3I2H', bank, 16 + index * 16)
        entry = manifest['assets'][index]
        require(entry['id'] == index and (entry['offset'], entry['packed_size'], entry['unpacked_size'],
                entry['type'], entry['flags']) == (offset, packed, unpacked, kind, flags),
                f'directory/manifest mismatch at asset {index}')
        name = entry['name']
        require(offset % 4 == 0 and offset >= 16 + count * 16 and offset + packed <= size,
                f'invalid payload bounds/alignment: {name}')
        physical = ASSET_PHYSICAL + offset
        if name.startswith('BACKGROUND_') and int(name.split('_')[1]) >= 2:
            require(kind == 2 and flags == 0x8000 and packed == unpacked == 64000,
                    f'intro background is not raw/banked: {name}')
        if flags & 0x8000:
            require(kind == 2 and flags in (0x8000, 0x8002) and packed and unpacked == 64000,
                    f'unsupported banked asset: {name}')
            require(flags != 0x8000 or packed == unpacked, f'invalid raw banked image: {name}')
            require(physical >= EXTRA_PHYSICAL and physical + packed <= len(rom),
                    f'banked asset outside ROM: {name}')
            require(physical // PAGE_BYTES == (physical + packed - 1) // PAGE_BYTES,
                    f'banked image crosses a mapper page: {name}')
            banked.append(dict(name=name, physical_offset=physical, page=physical // PAGE_BYTES,
                               packed_bytes=packed, codec='raw' if flags == 0x8000 else 'lz4'))
        else:
            require(offset + packed <= len(main), f'fixed asset outside fixed section: {name}')
        if kind in (5, 6, 14) or kind in (3, 4) and int(name.split('_')[1]) >= 2:
            require(flags == 0 and not intersects(physical, packed, APERTURE),
                    f'intro rendering source leaves fixed ROM: {name}')
            render_sources.append(kind)
        if kind in (15, 16):
            require(flags == 0 and physical + packed <= EXTRA_PHYSICAL,
                    f'audio asset is not fixed/raw: {name}')
            require(not intersects(physical, packed, APERTURE), f'audio intersects mapper aperture: {name}')
            audio.append((kind, physical, packed))

    require(elf.lma('.text') == 0 and elf.section('.text')[5] <= ASSET_PHYSICAL,
            'ROM code overlaps fixed assets')
    functions = 0
    for name, value, length in elf.functions:
        if ROM_BASE <= value < ROM_BASE + ROM_LIMIT:
            require(not intersects(value - ROM_BASE, max(1, length), APERTURE),
                    f'ROM function intersects mapper aperture: {name}')
            functions += 1
    module_lma, module_bytes = elf.lma('.data'), elf.section('.data')[5]
    require(module_lma == elf.symbol('_stext') == ASSET_PHYSICAL + len(main), 'BIOS module LMA changed')
    require(module_bytes == elf.symbol('_sdata'), 'BIOS module size mismatch')
    require(module_lma + module_bytes <= EXTRA_PHYSICAL, 'BIOS module exceeds direct ROM window')
    require(elf.symbol('__end') <= 0x0603C000, 'SDRAM overlaps reserved stacks')

    return dict(scope='Linked ROM layout checks; mapper execution and hardware are separate validations',
                rom_sha256=hashlib.sha256(rom).hexdigest(), rom_bytes=len(rom), checksum=checksum,
                bank_sha256=hashlib.sha256(bank).hexdigest(), asset_count=count,
                asset_physical_origin=ASSET_PHYSICAL, fixed_bytes=len(main),
                extra_physical_origin=EXTRA_PHYSICAL, extra_bytes=len(extra),
                banked_images=banked, mapper_aperture=list(APERTURE),
                protected_rom_functions=functions,
                protected_model_assets=render_sources.count(5),
                protected_animation_assets=render_sources.count(6),
                protected_static_raster_assets=render_sources.count(14),
                protected_intro_camera_assets=render_sources.count(3),
                protected_intro_room_assets=render_sources.count(4),
                protected_sound_assets=sum(kind == 15 for kind, _, _ in audio),
                protected_music_assets=sum(kind == 16 for kind, _, _ in audio),
                audio_physical_range=[min(start for _, start, _ in audio),
                                      max(start + length for _, start, length in audio)],
                module_lma=module_lma, module_bytes=module_bytes,
                module_physical_end=module_lma + module_bytes,
                static_sdram_end=elf.symbol('__end'), stack_margin=0x0603C000 - elf.symbol('__end'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, default=ROOT / 'build/AITD32X.32x')
    parser.add_argument('--elf', type=Path, default=ROOT / 'build/AITD32X.elf')
    parser.add_argument('--assets', type=Path, default=ROOT / 'assets')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/bank-layout.json')
    args = parser.parse_args()
    try:
        report = check(args.rom.read_bytes(), args.elf.read_bytes(),
                       (args.assets / 'bank.bin').read_bytes(),
                       (args.assets / 'bank-main.bin').read_bytes(),
                       (args.assets / 'bank-extra.bin').read_bytes(),
                       json.loads((args.assets / 'manifest.json').read_text()))
    except (OSError, ValueError, struct.error) as error:
        raise SystemExit(f'bank layout check: {error}') from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
