#!/usr/bin/env python3
"""Migrate real preceding-release saves and retain full-house lantern state.

Both libraries use isolated host SRAM arrays. No emulator battery files are
read or written. The canonical comparison includes every serialized field,
including actor interpolation, collision/combat transients, RNG and effects.
"""
import ctypes as C
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'build/full-game-reference'


class Reader:
    def __init__(self, data):
        self.data, self.offset = data, 0

    def number(self, width=4, signed=True):
        value = int.from_bytes(self.data[self.offset:self.offset + width], 'big', signed=signed)
        self.offset += width
        return value

    def numbers(self, count, width=4, signed=True):
        return [self.number(width, signed) for _ in range(count)]


def newest(lib):
    records = []
    ptr = lib.host_sram()
    for slot in range(2):
        header = struct.unpack('>6I', C.string_at(ptr + slot * 65536, 24))
        if header[0] == 0x41495444:
            assert 0 < header[3] <= 65512
            records.append((header[2], header, C.string_at(ptr + slot * 65536 + 24, header[3])))
    assert records, 'no committed private SRAM record'
    return max(records, key=lambda entry: entry[0])[1:]


def canonical(header, payload):
    old = header[1] == 0x53313401
    assert old or header[1] == 0x53313601, hex(header[1])
    reader = Reader(payload)
    result = dict(world=reader.numbers(22), inventory=reader.numbers(31),
                  objects=[reader.numbers(26, 2) for _ in range(292)],
                  variables=reader.numbers(207, 2), cvars=reader.numbers(45, 2))
    actors = []
    for slot in range(24 if old else 50):
        identity = reader.number()
        if identity == -1:
            continue
        active = dict(slot=slot, object=identity, words=reader.numbers(26, 2),
                      collisions=reader.numbers(3), transients=reader.numbers(24),
                      interpolators=reader.numbers(12), speed_step=reader.number())
        active['pose'] = dict(position_and_angles=reader.numbers(8),
                              end_flags=reader.numbers(2, 1, False),
                              collision_bounds=reader.numbers(6), frame_phase=reader.numbers(2),
                              animation=reader.number(4, False), last_step=reader.numbers(3),
                              walking=reader.number(1, False))
        groups = reader.number(2, False)
        assert groups <= 28
        active['pose']['bones'] = [reader.numbers(8, 4 if old else 2) for _ in range(groups)]
        actors.append(active)
    result['actors'] = actors
    result['effects'] = []
    for _ in range(3):
        result['effects'].append(dict(since=reader.number(), duration=reader.number(2, False),
                                      floor=reader.number(2), room=reader.number(2),
                                      flags=reader.numbers(3, 1, False), points=reader.numbers(90, 2)))
    dark = False if old else bool(reader.number(1, False))
    assert reader.offset == len(payload), ('canonical parser length', reader.offset, len(payload))
    return result, dark


def load_library(path, bank_path):
    lib = C.CDLL(str(path))
    lib.host_init.argtypes = [C.c_void_p, C.c_uint]
    lib.host_sram.restype = C.c_void_p
    bank = bank_path.read_bytes()
    buffer = C.create_string_buffer(bank)
    lib.host_init(buffer, len(bank))
    return lib, bank, buffer


def main():
    old, old_bank, old_buffer = load_library(OLD / 'libaitd32x.so', OLD / 'assets/bank.bin')
    new, bank, buffer = load_library(ROOT / 'build/libaitd32x.so', ROOT / 'assets/bank.bin')
    rows = []
    for character in (0, 1):
        for scenario in ('moving', 'combat', 'reading', 'inventory'):
            C.memset(old.host_sram(), 0, 131072)
            old.host_init(old_buffer, len(old_bank))
            old.host_startgame(character)
            for frame in range(40):
                old.host_tick(1 if scenario == 'moving' else 0)
            if scenario != 'moving':
                old.host_place(1, 1, 2, 1000, 0, -500, 512)
                old.host_tick(0)
            if scenario == 'combat':
                old.host_take(38)
                old.host_found_life(38, 1)
                for frame in range(9):
                    old.host_tick(65)
            elif scenario == 'reading':
                old.host_take(15)
                old.host_found_life(15, 4)
                assert old.host_world(13) >= 0, 'book fixture did not use original Read action'
            elif scenario == 'inventory':
                for item in (3, 13, 17):
                    old.host_take(item)
                old.host_tick(32)
                assert old.host_world(12) == 1, 'inventory fixture did not open the original menu'
            assert not old.host_world(3) and not old.host_world(14)
            assert old.host_save()
            old_header, old_payload = newest(old)
            assert old_header[1] == 0x53313401
            expected, _ = canonical(old_header, old_payload)
            legacy_sram = C.string_at(old.host_sram(), 131072)
            new.host_init(buffer, len(bank))
            C.memmove(new.host_sram(), legacy_sram, len(legacy_sram))
            assert new.host_load(), ('legacy load rejected', character, scenario)
            assert new.host_state(8) == character and new.host_state(7), 'restored save must stay paused'
            assert new.host_save(), 'cannot rewrite migrated save'
            new_header, new_payload = newest(new)
            assert C.string_at(new.host_sram(), 65536) == legacy_sram[:65536], 'migration overwrote the valid legacy journal'
            actual, dark = canonical(new_header, new_payload)
            assert new_header[1] == 0x53313601 and new_header[5] == old_header[5]
            if expected != actual:
                differences = [key for key in expected if expected[key] != actual[key]]
                raise AssertionError(('legacy state changed', character, scenario, differences))
            assert not dark, 'floor 0/1 legacy save acquired darkness'
            # A second load/new save proves the converted record is stable.
            assert new.host_load() and new.host_save()
            after_header, after_payload = newest(new)
            assert canonical(after_header, after_payload) == (actual, dark)
            rows.append(dict(character=character, scenario=scenario,
                             legacy_bytes=len(old_payload), migrated_bytes=len(new_payload),
                             active_actors=len(actual['actors']), all_saved_fields_identical=True,
                             new_format_roundtrip=True, legacy_journal_preserved=True))

    lighting = []
    for character in (0, 1):
        for source in (1, 13):
            C.memset(new.host_sram(), 0, 131072)
            new.host_begin_world(character, 6, 0, 0)
            new.host_set_variable(7, 1)
            new.host_take(13)
            if source == 13:
                new.host_drop(13, 1)
            assert new.host_run_life(509, 235) == 0
            assert new.host_dark() and new.host_cvar(13) == source
            assert new.host_save()
            saved_header, saved_payload = newest(new)
            expected = canonical(saved_header, saved_payload)
            new.host_startgame(character)
            assert not new.host_dark()
            assert new.host_load() and new.host_dark() and new.host_cvar(13) == source
            assert new.host_save()
            restored_header, restored_payload = newest(new)
            assert canonical(restored_header, restored_payload) == expected
            lighting.append(dict(character=character, source=source, darkness_preserved=True,
                                 light_object_preserved=True, all_saved_fields_identical=True))
    report = dict(bank_sha256=hashlib.sha256(bank).hexdigest(), legacy=rows, lighting=lighting,
                  legacy_format='53313401', new_format='53313601', user_save_files_touched=False)
    (ROOT / 'build/full-game-save.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
