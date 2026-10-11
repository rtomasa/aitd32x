#!/usr/bin/env python3
"""Focused original death movie and mapper check on the actual PicoDrive ROM.

Controller input starts and skips the arrival; only player health is modified
in private emulator RAM to shorten combat. No SRAM is read, written or loaded.
"""
import argparse
import ctypes as C
import hashlib
import json
import struct
from pathlib import Path

import emulator_check as ec
from check_startup_native import Check,layout,assets,video_image,A,START


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('core',type=Path)
    parser.add_argument('--mars',type=Path,default=ec.ROOT/'.local/toolchain/mars')
    args=parser.parse_args()
    offsets,decode=layout(args.mars),assets()
    rom=ec.ROOT/'build/AITD32X.32x'
    sha=hashlib.sha256(rom.read_bytes()).hexdigest()
    check=Check(args.core,'NTSC',offsets)
    try:
        # Exercise the same real startup controls as the player before the
        # single health fixture. The selected character is Edward by default.
        check.advance(check.hz);check.press(A);check.phase(5)
        check.press(A);check.phase(6);check.press(A);check.phase(7)
        pages=struct.unpack_from('>H',decode('STARTUP_BIOGRAPHY_0'),2)[0]
        for _ in range(pages):check.press(A)
        check.phase(8);check.press(START);check.phase(10)
        assert check.state()['character']==0 and check.state()['floor']==0
        check.wait(check.settled)
        health=check.memory+check.game+offsets['world']+offsets['vars']+21*2
        C.c_int16.from_address(health).value=0

        phases=[];views=[];mapped_frames=completed_draws=0;last_rendered=-1
        death_start=check.frames;picture_start=None;picture_tick=None
        drag_captured=False
        while check.frames-death_start<check.hz*90:
            state=check.state()
            assert not check.read('fault',True),('death LIFE fault',state)
            if state['phase']>=11 and (not phases or phases[-1]!=state['phase']):
                phases.append(state['phase'])
                print('death phase',state['phase'],'tick',state['world_ticks'],flush=True)
            if state['phase']==11:
                view=(state['floor'],state['camera'])
                if not views or views[-1]!=view:views.append(view)
                if check.settled() and state['rendered']!=last_rendered:
                    assert check.mapper_valid(),'invalid mapper page after cemetery draw'
                    completed_draws+=1;last_rendered=state['rendered']
                if state['floor']==6 and state['camera']==8 and check.settled() and not drag_captured:
                    check.capture('death-drag');drag_captured=True
            if check.banks[1]!=1:mapped_frames+=1
            if state['phase']==12:
                picture_start=check.frames;picture_tick=state['world_ticks'];break
            check.advance()
        assert phases[:2]==[11,12] and picture_start is not None,('death movie did not reach original picture',phases,views,check.state())
        assert drag_captured and set(views)>={(6,0),(6,8),(6,13)},views
        expected=decode('DEATH_PICTURE')
        visible_frames=phase_frames=0;picture_captured=False;restored=False
        while check.frames-picture_start<check.hz*6:
            state=check.state()
            assert not check.read('fault',True),('picture LIFE fault',state)
            if state['phase']==12:
                assert state['world_ticks']==picture_tick,'death picture advanced world simulation'
                phase_frames+=1
                if check.settled():
                    assert check.scene()==expected,'death picture indexed pixels differ from original'
                    assert check.mapper_valid();restored=True
                if video_image(check,expected):
                    visible_frames+=1
                    if not picture_captured:
                        check.e.capture('startup-NTSC-death-picture.png');picture_captured=True
            elif state['phase']==13:
                phases.append(13);break
            else:raise AssertionError(('unexpected death picture phase',state))
            check.advance()
        assert phases==[11,12,13] and restored and picture_captured,phases
        assert abs(phase_frames/check.hz-4)<.15,('death picture duration',phase_frames)
        # GAME_OVER uses a presentation hold with no world or image updates.
        end_start=check.frames;rendered=check.state()['rendered']
        for _ in range(check.hz*3):
            state=check.state()
            if state['phase']==5:break
            assert state['phase']==13 and state['world_ticks']==picture_tick,state
            assert check.mapper_valid(),'invalid mapper page during GAME_OVER hold'
            check.advance()
        assert check.state()['phase']==5,'death did not return to title menu'
        phases.append(5)
        end_frames=check.frames-end_start
        assert abs(end_frames/check.hz-2)<.15,('GAME_OVER hold duration',end_frames)
        # One final frame is allowed when entering the hold. Static content
        # must not generate repeated scene jobs while the world is stopped.
        idle_draws=check.state()['rendered']-rendered
        assert idle_draws<=2,('GAME_OVER hold redrew repeatedly',idle_draws)
        check.wait(check.settled);check.capture('death-title')
        assert check.mapper_valid()
        assert hashlib.sha256(rom.read_bytes()).hexdigest()==sha,'ROM changed during death validation'
        report=dict(passed=True,region='NTSC',emulator_only=True,rom_sha256=sha,
                    character=0,phases=phases,views=views,biography_pages=pages,
                    death_world_ticks=picture_tick,mapper_retained_safe=check.retained_mapper,
                    completed_cemetery_draws=completed_draws,banked_frame_samples=mapped_frames,
                    original_picture_pixels=True,picture_world_paused=True,
                    picture_phase_seconds=phase_frames/check.hz,
                    picture_visible_seconds=visible_frames/check.hz,
                    game_over_seconds=end_frames/check.hz,game_over_idle_draws=idle_draws,
                    return_to_title=True,no_sram_fixture=True)
        (ec.ROOT/'build/death-native-NTSC.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2),flush=True)
    finally:check.close()


if __name__=='__main__':main()
