#!/usr/bin/env python3
"""Audit original full-house LIFE and exercise its lamp and final ritual scripts.

Host placement, puzzle prerequisites and one lamp contact shorten the route;
all actions afterwards execute the production bytecode. This is script evidence,
not a completed playthrough or hardware validation. SRAM stays in host memory.
"""
import argparse
import collections
import ctypes as C
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/aitdpack'))
from aitdpack import Pak, offsets
from life_format import FORMATS, instructions


def audit(game):
    decoder = C.CDLL(str(ROOT / 'tools/aitdpack/fitd_unpack.so'))
    lives = Pak(game / 'LISTLIFE.PAK', decoder)
    objects = (game / 'OBJETS.ITD').read_bytes()
    object_count = struct.unpack_from('<H', objects)[0]
    var_count = len((game / 'VARS.ITD').read_bytes()) // 2
    usage = collections.Counter()
    branches = expressions = 0
    lights = []
    for life in range(len(lives)):
        data = lives.get(life)
        words = struct.unpack('<' + str(len(data) // 2) + 'h', data)
        parsed = instructions(data)
        boundaries = {entry[0] for entry in parsed}
        for pc, op, arg, operands in parsed:
            usage[op] += 1
            assert 0 <= op <= 86 and op != 27, ('unsupported opcode', life, pc, op)
            if words[pc] & 0x8000:
                assert 0 <= words[pc + 1] < object_count, ('target', life, pc)
            if op in (4, 5, 6, 7, 8, 9, 10, 26, 29):
                target = arg + len(operands) + operands[-1]
                assert target in boundaries, ('branch enters operand', life, pc, target)
                branches += 1
            if op in (19, 20, 21, 22, 23):
                assert 0 <= operands[0] < var_count, ('variable', life, pc)
            if op in (30, 32, 33, 51, 59, 83):
                assert 0 <= operands[0] < object_count, ('object', life, pc)
            if op == 70:
                assert all(0 <= value < object_count for value in operands), ('PUT_AT', life, pc)
            if op == 76:
                assert 0 <= operands[3] < object_count, ('THROW', life, pc)
            if op == 64:
                lights.append(dict(life=life, word=pc, on=operands[0]))
            cursor = arg

            def raw():
                nonlocal cursor
                value = words[cursor]
                cursor += 1
                return value

            def expression():
                nonlocal expressions
                expressions += 1
                code = raw()
                if code == -1:
                    raw()
                    return
                if code == 0:
                    assert 0 <= raw() < var_count, ('evaluated variable', life, pc)
                    return
                if code & 0x8000:
                    assert 0 <= raw() < object_count, ('evaluated target', life, pc)
                    code &= 0x7fff
                assert 1 <= code <= 39, ('expression', life, pc, code)
                if code in (15, 19, 33, 39):
                    assert 0 <= raw() < object_count, ('evaluated object', life, pc)
                elif code == 37:
                    assert 0 <= raw() < 45, ('C_VAR', life, pc)
                elif code == 35:
                    assert 0 <= raw() < 305, ('animation expression', life, pc)
                    raw()
                elif code == 29:
                    raw()
                elif code == 17:
                    expression()

            if op != 29:
                for kind in FORMATS[op]:
                    expression() if kind == 'E' else raw()
                assert cursor == arg + len(operands)
    # Retain original global IDs; generated scripts may remap only their
    # audited audio operands and the previously corrected window expression.
    manifest = json.loads((ROOT / 'assets/manifest.json').read_text())
    bank = (ROOT / 'assets/bank.bin').read_bytes()
    converted = [entry for entry in manifest['assets'] if entry['name'].startswith('LIFE_')]
    assert len(converted) == len(lives), 'missing original LIFE resources'
    for entry in converted:
        data = bank[entry['offset']:entry['offset'] + entry['packed_size']]
        words = struct.unpack('>' + str(len(data) // 2) + 'h', data)
        original = instructions(lives.get(int(entry['name'][5:])))
        generated = instructions(struct.pack('<' + str(len(words)) + 'h', *words))
        assert [(a, b) for a, b, _, _ in original] == [(a, b) for a, b, _, _ in generated], entry['name']
    first_camera = {}
    for floor in range(8):
        pak = Pak(game / f'ETAGE{floor:02d}.PAK', decoder)
        rooms = pak.get(0)
        for room, offset in enumerate(offsets(rooms)):
            if struct.unpack_from('<H', rooms, offset + 10)[0]:
                first_camera[floor, room] = struct.unpack_from('<H', rooms, offset + 12)[0]
    return dict(scripts=len(lives), commands=sum(usage.values()), distinct_commands=len(usage),
                valid_branches=branches, valid_expressions=expressions,
                objects=object_count, variables=var_count,
                command_usage=dict(sorted(usage.items())), light_commands=lights,
                bank_sha256=hashlib.sha256(bank).hexdigest()), first_camera


def smoke(first_camera):
    lib = C.CDLL(str(ROOT / 'build/libaitd32x.so'))
    lib.host_init.argtypes = [C.c_void_p, C.c_uint]
    bank = (ROOT / 'assets/bank.bin').read_bytes()
    buffer = C.create_string_buffer(bank)
    lib.host_init(buffer, len(bank))
    results = []

    def begin(character, floor, room):
        lib.host_begin_world(character, floor, room, first_camera[floor, room])
        assert not lib.host_world(3), ('initial world', character, floor, room)

    def life(number, object):
        assert lib.host_run_life(number, object) == 0, (number, object, [lib.host_world(i) for i in (3, 4, 5)])

    for character in (0, 1):
        # The dark corridor and library use their actual controller scripts;
        # equipping/extinguishing the original lamp changes their visibility.
        for room, controller, script, variable in ((0, 69, 115, 70), (6, 92, 172, 85)):
            begin(character, 2, room)
            lib.host_set_cvar(13, 13)  # A legitimate LIGHT_OBJECT ID must survive LIGHT.
            life(script, controller)
            assert lib.host_dark() and lib.host_variable(variable) == 0
            assert lib.host_cvar(13) == 13, 'LIGHT overwrote the lamp object ID'
            lib.host_set_variable(7, 1)
            lib.host_take(13)
            life(script, controller)
            assert not lib.host_dark() and lib.host_variable(variable) == 1
            assert lib.host_world(7) == 13 and lib.host_cvar(13) == 13
            lib.host_set_variable(7, 0)
            life(script, controller)
            assert lib.host_dark() and lib.host_cvar(13) == 13

        # Underground's floor-wide script chooses the real light source; after
        # Pregzt dies it must not re-enter darkness while the player escapes.
        begin(character, 6, 0)
        lib.host_set_variable(7, 1)
        lib.host_take(13)
        life(509, 235)
        assert lib.host_dark() and lib.host_cvar(13) == 1
        lib.host_place(1, 6, 6, 0, 0, 0, 0)
        life(509, 235)
        assert not lib.host_dark(), 'Pregzt chamber did not restore full light'
        lib.host_set_cvar(12, 1)
        lib.host_place(1, 6, 0, 0, 0, 0, 0)
        lib.host_found_life(2, 64)  # Search selects the original Actions object.
        life(509, 235)
        assert not lib.host_dark() and lib.host_cvar(13) == -1

        # Place De Vermis Mysteriis through its original Put action. This
        # proves the found-item script feeds the final chamber controller.
        begin(character, 6, 6)
        lib.host_set_variable(21, 32000)  # Shorten combat without dying.
        lib.host_set_variable(94, 1)  # The preceding altar puzzle is solved.
        lib.host_take(110)
        lib.host_found_life(110, 1024)
        assert lib.host_variable(95) == 1
        assert (lib.host_object(110, 14), lib.host_object(110, 15)) == (6, 6)
        assert (lib.host_object(110, 8), lib.host_object(110, 9), lib.host_object(110, 10)) == (5300, -1000, -6100)
        lib.host_refresh_actors()
        life(518, 40)
        assert lib.host_object(40, 17) == 521 and lib.host_variable(0) == 0
        for _ in range(80):
            lib.host_world_tick(0, 0)
            assert not lib.host_world(3), ('ritual wait', character, [lib.host_world(i) for i in (3, 4, 5)])
            if lib.host_object(40, 17) == 522:
                break
        assert lib.host_object(40, 17) == 522 and lib.host_variable(0) == 1
        lib.host_set_variable(7, 1)
        lib.host_take(13)
        lib.host_drop(13, 1)
        assert lib.host_hit(40, 13, 0), 'lit-lamp contact requires active original objects'
        life(522, 40)
        assert lib.host_cvar(12) == 1 and lib.host_cvar(15) == 0
        assert lib.host_startup(5) == -2, 'END_SEQUENCE did not request the ending movie'
        assert not lib.host_world(14), 'END_SEQUENCE stopped original escape commands'
        assert lib.host_variable(33) == 1 and lib.host_object(40, 14) == -1
        assert lib.host_object(274, 17) == 517, 'escape pursuer was not installed'
        assert all(lib.host_object(object, 14) == -1 for object in (9, 21, 35, 62, 176, 218, 228))
        results.append(dict(character=character, corridor_and_library_lamp=True,
                            underground_light_source=True, altar_book_put=True,
                            ritual_lifes=[518, 521, 522], sorcerer_killed=True,
                            ending_request=True, escape_tail=True))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=ROOT / 'msdos-game/AITD_CD/INDARK')
    parser.add_argument('--offline-only', action='store_true')
    args = parser.parse_args()
    report, cameras = audit(args.game)
    if not args.offline_only:
        report['host_scripts'] = smoke(cameras)
    destination = ROOT / 'build/full-game-scripts.json'
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key not in ('command_usage', 'light_commands')}, indent=2))


if __name__ == '__main__':
    main()
