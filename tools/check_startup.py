#!/usr/bin/env python3
"""Focused original-arrival checks against the generated production asset bank.

The small host helper uses the actual World/LIFE/animation/camera code. It
reads assets only, writes evidence under build/, and never touches battery saves.
"""
import argparse
import ctypes as C
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    'src/engine/math.cpp', 'src/engine/trig.cpp', 'src/engine/actor.cpp',
    'src/engine/collision.cpp', 'src/engine/world.cpp', 'src/engine/life.cpp',
    'src/platform/storage.cpp', 'src/platform/audio.cpp',
)
HELPER = r'''
#include "src/engine/world.hpp"
#include "src/platform/platform_api.hpp"
#include "src/platform/audio.hpp"
#include <cstdio>
#include <cstdlib>
#include <vector>
extern "C" void Platform_Fatal() { std::abort(); }
extern "C" unsigned host_sample_count();
extern "C" int host_sample_event(unsigned,unsigned);
static World world,clean;
static Actor player,clean_player;
static void require(bool ok,const char *message) {
    if(!ok) { std::fprintf(stderr,"startup check: %s\n",message);std::exit(1); }
}
static unsigned Snapshot(const World &w) {
    unsigned hash=2166136261u;
    auto add=[&](int value) { hash=(hash^(unsigned)value)*16777619u; };
    add(w.floor);add(w.room);add(w.camera);add(w.camera_target);add(w.character);
    add(w.ticks);add(w.now);add(w.rng);add(w.inventory_count);add(w.in_hand);
    add(w.prompt);add(w.message);add(w.book);add(w.finished);add(w.intro);
    add(w.picture_id);add(w.picture_duration);
    for(int i=0;i<A32X_OBJECT_COUNT;++i) for(int j=0;j<26;++j) add(w.Get(i,j));
    for(auto value:w.vars) add(value);
    for(auto value:w.cvars) add(value);
    return hash;
}
int main(int argc,char **argv) {
    require(argc==2,"missing production bank path");
    FILE *input=std::fopen(argv[1],"rb");require(input!=nullptr,"cannot read asset bank");
    std::fseek(input,0,SEEK_END);long length=std::ftell(input);std::rewind(input);
    require(length>0,"empty asset bank");std::vector<uint8_t> bank((unsigned)length);
    require(std::fread(bank.data(),1,bank.size(),input)==bank.size(),"truncated asset bank");
    std::fclose(input);Platform_SetAssetBank(bank.data(),bank.size());
    std::printf("[");
    for(int character=0;character<2;++character) {
        Audio_Reset();Actor_Init(player,character);world.InitIntro(player,character);
        require(world.intro && world.floor==7 && world.room==1 && world.camera==3 && world.camera_target==286,"original arrival initialization");
        bool cameras[8][64]={};int pictures=0;
        while(world.ticks<5000 && !world.finished && !world.fault_code) {
            world.Update(0,false);Audio_UpdateMusic(world.music,world.next_music,world.ticks);
            require((unsigned)world.floor<8 && (unsigned)world.camera<64,"camera range");
            Asset view=Platform_ReadAsset(floor_cameras[world.floor][world.camera]);
            Asset image=Platform_ReadAsset(floor_backgrounds[world.floor][world.camera]);
            require(view.data && view.type==3,"selected sparse camera has no metadata");
            require(image.data && image.type==2 && image.unpacked==64000,"selected sparse camera has no background");
            cameras[world.floor][world.camera]=true;
            if(world.picture_id>=0) {
                require(world.picture_id==11 && world.picture_duration==20,"original frog picture request");
                ++pictures;world.picture_id=-1;
            }
        }
        require(world.finished && !world.fault_code,"arrival did not complete without a script fault");
        require(world.floor==1 && world.room==6 && world.camera_target==288,"arrival ended at an unavailable-floor boundary");
        require(world.Get(288,O_LIFE)==539 && world.Get(288,O_TRACK)==-1,"original arrival script did not finish its final track");
        require(!world.cvars[15] && pictures==1,"intro completion leaked death or repeated the picture");
        unsigned ticks=world.ticks,sounds=host_sample_count();bool frog_sound=false;
        for(unsigned i=0;i<sounds;++i) if(host_sample_event(i,0)==77) frog_sound=true;
        require(frog_sound,"frog picture sound missing");
        world.Init(player,character);Actor_Init(clean_player,character);clean.Init(clean_player,character);
        require(Snapshot(world)==Snapshot(clean),"fresh gameplay retained intro state");
        require(world.RoomAsset(2,2).data && world.RoomAsset(3,1).data && world.RoomAsset(4,0).data && world.RoomAsset(5,10).data,"full gameplay floors unavailable after arrival reset");
        std::printf("%s{\"character\":%d,\"world_ticks\":%u,\"pictures\":%d,\"sound_requests\":%u,\"death\":false,\"script_fault\":false,\"fresh_gameplay_reset\":true,\"full_gameplay_floors\":true,\"cameras\":[",character?",":"",character,ticks,pictures,sounds);
        bool comma=false;
        for(int floor=0;floor<8;++floor) for(int camera=0;camera<64;++camera) if(cameras[floor][camera]) {
            std::printf("%s[%d,%d]",comma?",":"",floor,camera);comma=true;
        }
        std::printf("]}");
    }
    std::printf("]\n");
}
'''


def world_checks():
    source = ROOT / 'build/startup-world-check.cpp'
    binary = ROOT / 'build/startup-world-check'
    source.parent.mkdir(exist_ok=True)
    source.write_text(HELPER)
    subprocess.run(
        ['c++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-I', str(ROOT)]
        + [str(ROOT / name) for name in SOURCES]
        + [str(source), '-o', str(binary)], check=True, cwd=ROOT,
    )
    output = subprocess.check_output(
        [str(binary), str(ROOT / 'assets/bank.bin')], text=True, cwd=ROOT,
    )
    return json.loads(output)


def ui_checks(captures, reference, render_reference=None):
    """Use real controller flow, including the presentation pause and old saves."""
    library = C.CDLL(str(ROOT / 'build/libaitd32x.so'))
    library.host_init.argtypes = [C.c_void_p, C.c_uint]
    library.host_pixels.restype = library.host_palette.restype = library.host_sram.restype = C.c_void_p
    bank = (ROOT / 'assets/bank.bin').read_bytes()
    buffer = C.create_string_buffer(bank)
    sram = library.host_sram()
    C.memset(sram, 0, 131072)  # This is the host library's private test array.
    snapshots = {}
    render_library = None
    render_compare = True
    render_checks = {}
    if render_reference:
        render_library = C.CDLL(str(render_reference / 'libaitd32x.so'))
        render_library.host_init.argtypes = [C.c_void_p, C.c_uint]
        render_library.host_pixels.restype = render_library.host_palette.restype = C.c_void_p
        render_bank = (render_reference / 'assets/bank.bin').read_bytes()
        render_buffer = C.create_string_buffer(render_bank)

    def initialize():
        library.host_init(buffer, len(bank))
        if render_library:
            render_library.host_init(render_buffer, len(render_bank))

    def compare_arrival():
        if not render_library or not render_compare or phase() not in (8, 9):
            return
        assert render_library.host_startup(0) == phase(), 'reference arrival phase diverged'
        fields = (0, 1, 2, 10, 11)
        state = [library.host_world(i) for i in fields]
        assert state == [render_library.host_world(i) for i in fields], ('reference world diverged', state)
        character = library.host_state(8)
        check = render_checks.setdefault(character, dict(frames=0, ticks=set(), views=set(), pixel_mismatch_frames=0, palette_mismatch_frames=0, first_pixel_mismatches=[], first_palette_mismatches=[]))
        check['frames'] += 1
        check['ticks'].add(state[-1])
        if phase() == 8:
            check['views'].add((state[0], state[2]))
        current = pixels()[12 * 320:212 * 320]
        previous = C.string_at(render_library.host_pixels(), 320 * 224)[12 * 320:212 * 320]
        # LIFE message typography intentionally changes to the original case.
        if current[:180 * 320] != previous[:180 * 320] or current[196 * 320:] != previous[196 * 320:]:
            check['pixel_mismatch_frames'] += 1
            if len(check['first_pixel_mismatches']) < 8:
                differences = [(i % 320, i // 320, a, b) for i, (a, b) in enumerate(zip(previous, current)) if a != b and not 180 <= i // 320 < 196]
                check['first_pixel_mismatches'].append(dict(world_ticks=state[-1], floor=state[0], room=state[1], camera=state[2], phase=phase(), pixels=len(differences), bounds=[min(p[0] for p in differences), min(p[1] for p in differences), max(p[0] for p in differences), max(p[1] for p in differences)], first_pixels=differences[:8]))
        if C.string_at(library.host_palette(), 512) != C.string_at(render_library.host_palette(), 512):
            check['palette_mismatch_frames'] += 1
            if len(check['first_palette_mismatches']) < 8:
                check['first_palette_mismatches'].append(dict(world_ticks=state[-1], floor=state[0], room=state[1], camera=state[2], phase=phase()))

    def phase():
        return library.host_startup(0)

    def tick(pad=0):
        library.host_tick(pad)
        if render_library:
            render_library.host_tick(pad)
        compare_arrival()
        if library.host_startup(4):
            assert not library.host_world(3), ('intro script fault', *[library.host_world(i) for i in (3, 4, 5)])

    def press(pad):
        tick()
        tick(pad)
        tick()

    def wait(expected, limit=5000):
        for _ in range(limit):
            if phase() == expected:
                return
            tick()
        raise AssertionError(('startup phase timeout', expected, phase()))

    def pixels():
        return C.string_at(library.host_pixels(), 320 * 224)

    def gameplay_state():
        return dict(
            world=[library.host_world(i) for i in (0, 1, 2, 3, 6, 7, 8, 10, 11, 13, 14)],
            variables=[library.host_variable(i) for i in range(207)],
            objects=[[library.host_object(i, word) for word in range(26)] for i in range(292)],
        )

    def capture(name):
        frame = pixels()
        snapshots[name] = hashlib.sha256(frame[12 * 320:212 * 320]).hexdigest()
        if captures:
            from emulator_check import png
            palette = list((C.c_uint16 * 256).from_address(library.host_palette()))
            colors = [bytes(((v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, ((v >> 10) & 31) * 255 // 31)) for v in palette]
            png(captures / f'{name}.png', b''.join(colors[v] for v in frame), 320, 224)

    def menu():
        initialize()
        press(128)
        wait(5)
        for _ in range(12):
            tick()

    def choose(character):
        press(64)
        wait(6)
        press(4 if character else 8)
        assert library.host_state(8) == character
        for _ in range(12):
            tick()
        capture(f'character-{character}')
        press(64)
        wait(7)
        for _ in range(12):
            tick()
        capture(f'biography-{character}')
        first = pixels()
        press(2)
        assert library.host_startup(3) == 1 and pixels() != first
        press(1)
        assert library.host_startup(3) == 0
        # Returning restores the original portrait image; selecting the other
        # character must compose a new biography rather than reuse the cache.
        press(16)
        wait(6)
        press(8 if character else 4)
        press(64)
        wait(7)
        assert library.host_state(8) == (character ^ 1)
        assert pixels() != first
        press(16)
        wait(6)
        press(4 if character else 8)
        press(64)
        wait(7)
        assert library.host_state(8) == character and pixels() == first
        for _ in range(32):
            if phase() != 7 or library.host_startup(2) != 255:
                break
            press(64)
        wait(8)

    # Natural boot must visit the animated logo, title and timed credit pages.
    initialize()
    seen = {phase()}
    rotating = []
    credit_pages = set()
    for _ in range(2500):
        tick()
        seen.add(phase())
        if phase() == 2 and len(rotating) < 2:
            rotating.append(pixels())
            if len(rotating) == 1:
                capture('animated-logo')
        if phase() == 4:
            credit_pages.add(library.host_startup(3))
        if phase() == 5:
            break
    assert seen == set(range(6)), ('missing boot screen', seen)
    assert len(rotating) == 2 and rotating[0] != rotating[1], 'logo is static'
    assert len(credit_pages) > 1, 'credits did not advance automatically'
    for _ in range(12):
        tick()
    capture('start-menu')

    # The third menu entry replays the opening sequence.
    press(2)
    press(2)
    press(64)
    wait(0)
    press(128)
    wait(5)

    characters = []
    for character in (0, 1):
        menu()
        choose(character)
        paused = 0
        while phase() == 8:
            tick()
        assert phase() == 9, ('frog picture missing', phase())
        world_time = library.host_world(11)
        assert library.host_startup(5) == 11 and library.host_startup(6) == 20
        capture(f'frog-{character}')
        frog = pixels()[12 * 320:212 * 320]
        # Both physical framebuffer histories must show the same picture.
        for index in (0, 1):
            library.host_buffer(index)
            library.host_draw_cached()
            if render_library:
                render_library.host_buffer(index)
                render_library.host_draw_cached()
            assert pixels()[12 * 320:212 * 320] == frog
        while phase() == 9:
            tick()
            if phase() == 9:
                assert library.host_world(11) == world_time, 'picture advanced the world simulation'
                paused += 1
        assert paused >= 5, ('picture hold too short', paused)
        for _ in range(5000):
            if library.host_state(6):
                break
            tick()
        assert library.host_state(6) == 1 and phase() == 10
        assert library.host_state(8) == character and library.host_world(10) == 1
        assert not library.host_startup(4) and not library.host_startup(7)
        assert library.host_startup(5) == -1 and library.host_world(11) < 3
        assert library.host_world(0) == 0 and library.host_world(1) == 0
        assert not library.host_world(3) and not library.host_world(14)
        assert library.host_variable(90) == 16
        capture(f'gameplay-{character}')
        gameplay_ticks = library.host_world(11)
        reached = gameplay_state()
        library.host_startgame(character)
        if render_library:
            render_library.host_startgame(character)
        for _ in range(gameplay_ticks):
            tick()
        assert gameplay_state() == reached, 'intro state leaked into fresh gameplay'
        characters.append(dict(character=character, biography_paging=True, biography_back_reselect=True, picture_world_paused_ticks=paused, both_picture_buffers=True, complete_arrival=True, fresh_gameplay=True))
    assert snapshots['character-0'] != snapshots['character-1']
    render_compare = False

    # Skip an active arrival, then ensure the confirmation does not become an
    # immediate gameplay action and the world starts from its original state.
    menu()
    choose(0)
    press(128)
    wait(10)
    assert library.host_world(11) < 3 and library.host_world(10) == 1

    # A pre-startup save produced by the preserved library must load without a
    # schema migration, and re-saving must preserve every serialized byte.
    baseline = C.CDLL(str(reference / 'libaitd32x.so'))
    baseline.host_init.argtypes = [C.c_void_p, C.c_uint]
    baseline.host_sram.restype = C.c_void_p
    old_bank = (reference / 'assets/bank.bin').read_bytes()
    old_buffer = C.create_string_buffer(old_bank)
    old_sram = baseline.host_sram()
    saves = []
    for character in (0, 1):
        C.memset(old_sram, 0, 131072)
        baseline.host_init(old_buffer, len(old_bank))
        if character:
            baseline.host_tick(32)
            baseline.host_tick(0)
        baseline.host_tick(128)
        baseline.host_tick(0)
        baseline.host_set_variable(90, 17)
        assert baseline.host_save() == 1
        old_record = C.string_at(old_sram, 65536)
        C.memmove(sram, old_sram, 131072)
        menu()
        # Resume is selected through the actual new start menu.
        press(2)
        tick()
        tick(64)  # Save immediately; a release tick changes Game.tick.
        assert library.host_state(6) == 1 and library.host_state(7) == 1
        assert library.host_state(8) == character and library.host_variable(90) == 17
        assert not library.host_startup(4) and library.host_startup(5) == -1 and not library.host_startup(7)
        assert library.host_save() == 1
        old_length = int.from_bytes(old_record[12:16], 'big')
        new_record = C.string_at(sram + 65536, 65536)
        assert old_record[4:8] == new_record[4:8], 'save schema changed'
        assert old_record[20:24] == new_record[20:24], 'save fingerprint changed'
        assert old_record[24:24 + old_length] == new_record[24:24 + old_length], 'legacy payload changed after load/save'
        saves.append(dict(character=character, previous_save_loaded=True, payload_identical=True, payload_bytes=old_length))
    result = dict(boot_phases=sorted(seen), logo_animated=True, credit_pages=len(credit_pages), replay_intro=True, characters=characters, arrival_skip=True, old_saves=saves, screenshots=snapshots)
    if render_library:
        result['arrival_render_comparison'] = dict(reference_host_sha256=hashlib.sha256((render_reference / 'libaitd32x.so').read_bytes()).hexdigest(), excluded_rows=[180, 195], characters=[])
        for character, check in sorted(render_checks.items()):
            check['world_ticks_compared'] = len(check.pop('ticks'))
            check['views'] = sorted(check['views'])
            result['arrival_render_comparison']['characters'].append(dict(character=character, **check))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/startup-host.json')
    parser.add_argument('--world-only', action='store_true', help='Check the original scripted arrival without UI/library checks')
    parser.add_argument('--skip-world', action='store_true', help='Reuse a prior World check while checking UI-only changes')
    parser.add_argument('--captures', type=Path, default=ROOT / 'build/startup-host-captures')
    parser.add_argument('--reference', type=Path, default=ROOT / 'build/startup-reference', help='Preserved pre-startup library and assets for save compatibility')
    parser.add_argument('--render-reference', type=Path, help='Preserved startup library/bank for full arrival pixel and palette comparisons')
    args = parser.parse_args()
    bank = (ROOT / 'assets/bank.bin').read_bytes()
    report = {
        'scope': 'Focused production-bank host startup checks; not hardware validation',
        'bank_sha256': hashlib.sha256(bank).hexdigest(),
    }
    if not args.skip_world:
        report['world'] = world_checks()
    if not args.world_only:
        args.captures.mkdir(parents=True, exist_ok=True)
        report['host_library_sha256'] = hashlib.sha256((ROOT / 'build/libaitd32x.so').read_bytes()).hexdigest()
        report['ui'] = ui_checks(args.captures, args.reference, args.render_reference)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    comparison = report.get('ui', {}).get('arrival_render_comparison', {})
    if any(check['pixel_mismatch_frames'] or check['palette_mismatch_frames'] for check in comparison.get('characters', [])):
        raise SystemExit('Arrival render comparison differed; inspect the saved report.')


if __name__ == '__main__':
    main()
