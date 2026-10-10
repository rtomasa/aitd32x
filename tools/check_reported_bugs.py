#!/usr/bin/env python3
"""Original-data checks for the reported hatch, doors, opening and saber faults.

Host SRAM is an in-memory fixture. No frontend battery file is read or written.
Placement shortens travel; the original LIFE/animation code handles interactions.
"""
import ctypes as C
import hashlib
import json
import struct
from pathlib import Path
import emulator_check as ec

ROOT = Path(__file__).resolve().parents[1]


def host():
    lib = C.CDLL(str(ROOT/'build/libaitd32x.so'))
    bank = (ROOT/'assets/bank.bin').read_bytes()
    buffer = C.create_string_buffer(bank)
    lib.host_init.argtypes = [C.c_void_p, C.c_uint]
    lib.host_pixels.restype = lib.host_palette.restype = C.c_void_p
    manifest = json.loads((ROOT/'assets/manifest.json').read_text())
    assets = {a['name']: bank[a['offset']:a['offset']+a['packed_size']]
              for a in manifest['assets']}
    report = []

    def init(character):
        lib.host_init(buffer, len(bank))
        if character:
            lib.host_tick(32)
            lib.host_tick(0)
        lib.host_tick(128)
        lib.host_tick(0)

    def tick(pad=0):
        lib.host_tick(pad)
        assert not lib.host_world(3), ('script', *[lib.host_world(f) for f in (3,4,5)])

    def pixels():
        return C.string_at(lib.host_pixels(), 320*224)

    def capture(name):
        pal = (C.c_uint16*256).from_address(lib.host_palette())
        colors = [bytes(((v&31)*255//31, ((v>>5)&31)*255//31,
                         ((v>>10)&31)*255//31)) for v in pal]
        ec.png(ROOT/'build'/name, b''.join(colors[v] for v in pixels()), 320, 224)

    for character in (0,1):
        # A saber hit breaks the item, spawns its blade and refreshes actors.
        # The remainder of LIFE49 must still update the original saber's weight.
        init(character)
        lib.host_place(1,1,3,-400,0,300,0)
        for _ in range(3): tick()
        lib.host_set_variable(33,1)
        lib.host_take(38)
        lib.host_found_life(38,1)
        for n in range(150):
            tick([65,66,68][n//50])
            lib.host_clear_message()
        assert lib.host_variable(38) == 1
        assert lib.host_object(38,25) == 15

        # A stationary cupboard starts at key zero, then holds its final key.
        init(character)
        lib.host_set_object(6,17,-1)
        lib.host_set_object(6,2,0)
        lib.host_animate(6,9,0,-1)
        tick()
        animation = assets[f'ANIM_{character}_9']
        frames, groups = struct.unpack_from('>2H', animation)
        for group in range(1,groups):
            expected = list(struct.unpack_from('>4h', animation, 12+group*8))
            actual = [lib.host_group(6,group,f) for f in range(4)]
            assert actual == expected, ('opening bind-pose glitch', character, group, actual, expected)
        for _ in range(120): tick()
        assert not lib.host_object(6,2)&1
        assert lib.host_object(6,19) == 9 and lib.host_object(6,20) == frames-1
        pose = [[lib.host_group(6,g,f) for f in range(4)] for g in range(groups)]
        for _ in range(30): tick()
        assert pose == [[lib.host_group(6,g,f) for f in range(4)] for g in range(groups)]
        assert lib.host_save() == 1 and lib.host_load() == 1
        assert pose == [[lib.host_group(6,g,f) for f in range(4)] for g in range(groups)]

        # Attic chest keeps the DOS opening/offer/automatic-closing sequence.
        init(character)
        lib.host_place(1,0,0,-6000,0,-395,256)
        lib.host_found_life(2,64)
        for n in range(160):
            tick(65 if n<65 else 0)
            if lib.host_world(8)>=0:
                tick(); tick(64); tick()
        assert lib.host_object(0,1) == 0
        sounds = [lib.host_sample_event(i,0) for i in range(lib.host_sample_count())]
        assert sounds.count(37) == 1, ('chest sound retrigger', sounds)

        # The distant hallway door must precede the player in painter order.
        # The rotating hatch needs per-pixel depth even in the standing pose.
        scenes = []
        for name, floor, room, camera, x, z, prop, alpha in (
            ('hall',1,1,2,100,-650,63,0),
            ('hatch-opening',0,0,3,-5200,2500,8,400),
            ('hatch-open',0,0,3,-5200,2500,8,700)):
            init(character)
            lib.host_place(1,floor,room,x,0,z,0)
            for _ in range(3): tick()
            if prop == 8:
                lib.host_set_object(8,11,alpha)
                lib.host_bounds(8,3)
            lib.host_clear_message()
            lib.host_camera(floor,room,camera)
            lib.host_draw_cached()
            original = pixels()
            capture(f'reported-{name}-{character}.png')
            a = [lib.host_render_bound(1,f) for f in range(4)]
            b = [lib.host_render_bound(prop,f) for f in range(4)]
            area = (max(a[0],b[0]), max(a[1],b[1]), min(a[2],b[2]), min(a[3],b[3]))
            assert area[0]<=area[2] and area[1]<=area[3], ('non-overlapping fixture', name, a, b)
            if prop == 63:
                order = [lib.host_draw_order(i) for i in range(24)]
                assert order.index(prop) < order.index(1), ('hallway door hides player', order)
                lib.host_draw_actor(1)
            else:
                assert lib.host_resolve_pair(1,prop)
            reference = pixels()
            difference = sum(original[y*320+x] != reference[y*320+x]
                             for y in range(area[1]+12,area[3]+13)
                             for x in range(area[0],area[2]+1))
            assert difference == 0, ('wrong character/prop depth', name, character, difference)
            lib.host_draw_fresh()
            assert pixels() == original, ('cache rebuild', name, character)
            scenes.append(name)
        report.append(dict(character=character, saber_break=True, opening_pose=True,
                           stopped_pose_save_load=True, original_auto_close=True,
                           chest_sound_requests=1, depth_scenes=scenes))
    return report


if __name__ == '__main__':
    report = dict(host=host(), rom_sha256=hashlib.sha256((ROOT/'build/AITD32X.32x').read_bytes()).hexdigest())
    (ROOT/'build/reported-bugs.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
