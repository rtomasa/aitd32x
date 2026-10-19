#!/usr/bin/env python3
"""Round-trip every compact-save field and retain full-house lantern state.

Uses private host SRAM, never emulator battery files. Checks both characters
in moving/combat/reading/inventory states and an independent LZSS decoder.
"""
import ctypes as C
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def decode(data):
    output, position = bytearray(), 0
    while position < len(data):
        flags = data[position]; position += 1
        for token in range(8):
            if position == len(data):
                assert not flags >> token
                break
            if flags & (1 << token):
                output.append(data[position]); position += 1
            else:
                assert position + 2 <= len(data)
                pair = int.from_bytes(data[position:position+2], 'big'); position += 2
                back, count = (pair >> 6) + 1, (pair & 63) + 3
                assert back <= len(output)
                for _ in range(count): output.append(output[-back])
            assert len(output) <= 65512
    return bytes(output)


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
    stride = 16384
    records = []
    ptr = lib.host_sram()
    for slot in range(2):
        header = struct.unpack('>6I', C.string_at(ptr + slot * stride, 24))
        if header[0] == 0x41495444:
            assert 0 < header[3] <= 16360
            records.append((header[2], header, C.string_at(ptr + slot * stride + 24, header[3])))
    assert records, 'no committed private SRAM record'
    return max(records, key=lambda entry: entry[0])[1:]


def canonical(header, payload):
    assert header[1] == 0x53313602, hex(header[1])
    payload = decode(payload)
    reader = Reader(payload)
    result = dict(world=reader.numbers(22), inventory=reader.numbers(31),
                  objects=[reader.numbers(26, 2) for _ in range(292)],
                  variables=reader.numbers(207, 2), cvars=reader.numbers(45, 2))
    actors = []
    for slot in range(50):
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
        active['pose']['bones'] = [reader.numbers(8, 2) for _ in range(groups)]
        actors.append(active)
    result['actors'] = actors
    result['effects'] = []
    for _ in range(3):
        result['effects'].append(dict(since=reader.number(), duration=reader.number(2, False),
                                      floor=reader.number(2), room=reader.number(2),
                                      flags=reader.numbers(3, 1, False), points=reader.numbers(90, 2)))
    dark = bool(reader.number(1, False))
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
    new, bank, buffer = load_library(ROOT / 'build/libaitd32x.so', ROOT / 'assets/bank.bin')
    rows = []
    for character in (0, 1):
        for scenario in ('moving', 'combat', 'reading', 'inventory'):
            C.memset(new.host_sram(), 0, 32768)
            new.host_init(buffer, len(bank));new.host_startgame(character)
            for frame in range(40):
                new.host_tick(1 if scenario == 'moving' else 0)
            if scenario != 'moving':
                new.host_place(1, 1, 2, 1000, 0, -500, 512)
                new.host_tick(0)
            if scenario == 'combat':
                new.host_take(38)
                new.host_found_life(38, 1)
                for frame in range(9):
                    new.host_tick(65)
            elif scenario == 'reading':
                new.host_take(15)
                new.host_found_life(15, 4)
                assert new.host_world(13) >= 0, 'book fixture did not use original Read action'
            elif scenario == 'inventory':
                for item in (3, 13, 17):
                    new.host_take(item)
                new.host_tick(32)
                assert new.host_world(12) == 1, 'inventory fixture did not open the original menu'
            assert not new.host_world(3) and not new.host_world(14)
            assert new.host_save()
            header, payload = newest(new);expected = canonical(header, payload)
            original_record = C.string_at(new.host_sram(), 16384)
            new.host_startgame(character ^ 1)
            assert new.host_load() and new.host_state(7), 'load must restore a paused game'
            assert new.host_save()
            restored_header, restored_payload = newest(new)
            assert canonical(restored_header, restored_payload) == expected
            assert C.string_at(new.host_sram(), 16384) == original_record
            rows.append(dict(character=character, scenario=scenario,
                             packed_bytes=len(payload), raw_bytes=len(decode(payload)),
                             all_saved_fields_identical=True, previous_journal_preserved=True))

    lighting = []
    for character in (0, 1):
        for source in (1, 13):
            C.memset(new.host_sram(), 0, 32768)
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
    report = dict(bank_sha256=hashlib.sha256(bank).hexdigest(), states=rows, lighting=lighting,
                  format='53313602', user_save_files_touched=False)
    (ROOT / 'build/full-game-save.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
