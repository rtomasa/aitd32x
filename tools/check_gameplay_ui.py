#!/usr/bin/env python3
"""Focused original-font/inventory checks; native RAM fixtures never touch SRAM."""
import argparse
import ctypes as C
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path

import emulator_check as ec
from check_startup_native import Check, layout, assets, A, B, DOWN

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/gameplay-ui-check'

def capture(lib,name):
    pixels=C.string_at(lib.host_pixels(),320*224)
    palette=(C.c_uint16*256).from_address(lib.host_palette())
    colors=[bytes(((v&31)*255//31,((v>>5)&31)*255//31,((v>>10)&31)*255//31)) for v in palette]
    ec.png(OUT/(name+'.png'),b''.join(colors[v] for v in pixels),320,224)

def host_checks():
    bank=(ROOT/'assets/bank.bin').read_bytes();buffer=C.create_string_buffer(bank)
    lib=C.CDLL(str(ROOT/'build/libaitd32x.so'))
    lib.host_pixels.restype=lib.host_palette.restype=lib.host_sram.restype=C.c_void_p
    reference=ROOT/'build/gameplay-ui-reference'
    old=C.CDLL(str(reference/'libaitd32x.so'));old.host_sram.restype=C.c_void_p
    previous=(reference/'assets/bank.bin').read_bytes();previous_buffer=C.create_string_buffer(previous)
    rows=[]
    def press(pad):lib.host_tick(0);lib.host_tick(pad);lib.host_tick(0)
    def scene():return C.string_at(lib.host_pixels(),320*224)[12*320:212*320]
    def snapshot():
        return ([lib.host_state(i) for i in range(1,9)],
                [lib.host_world(i) for i in (0,1,2,6,7,9,10,11,14,15,16)],
                [lib.host_variable(i) for i in range(207)],
                [[lib.host_object(i,j) for j in range(26)] for i in range(292)])
    for character in (0,1):
        # Re-save the preceding release's private live record without a tick.
        C.memset(old.host_sram(),0,131072)
        old.host_init(previous_buffer,len(previous));old.host_startgame(character);old.host_tick(0)
        assert old.host_save();record=C.string_at(old.host_sram(),65536)
        length=int.from_bytes(record[12:16],'big')
        lib.host_init(buffer,len(bank));C.memmove(lib.host_sram(),old.host_sram(),131072)
        assert lib.host_load() and lib.host_save()
        new=C.string_at(lib.host_sram()+65536,65536)
        assert record[4:8]==new[4:8] and record[20:24]==new[20:24]
        assert record[24:24+length]==new[24:24+length],'preceding save payload changed'
        lib.host_startgame(character);lib.host_tick(0);lib.host_clear_message()
        # Original object metadata; only acquisition is accelerated in this fixture.
        for item in (13,3,5,81,17,21):lib.host_take(item)
        lib.host_clear_message();lib.host_draw_fresh();baseline=scene();before=snapshot()
        lib.host_tick(32);lib.host_tick(0);assert lib.host_world(12)==1
        capture(lib,f'character-{character}-inventory')
        fixed=None;previews=set()
        for tick in range(60):
            lib.host_buffer(tick&1);lib.host_tick(0);pixels=scene()
            static=bytes(v for i,v in enumerate(pixels) if not(8<=i%320<=151 and 108<=i//320<=191))
            if fixed is None:fixed=static
            assert static==fixed,'item animation altered list/actions/bezel pixels'
            previews.add(hashlib.sha256(pixels[108*320:192*320]).hexdigest())
        assert len(previews)>10,'3D item preview did not rotate'
        assert snapshot()==before,'inventory animation advanced gameplay state'
        # Scroll beyond five items, then return to Actions and choose Search.
        for _ in range(6):press(DOWN)
        capture(lib,f'character-{character}-scrolled')
        for _ in range(6):press(1)
        press(A);assert lib.host_world(12)==2
        capture(lib,f'character-{character}-actions')
        press(B);assert lib.host_world(12)==1
        lib.host_tick(0);lib.host_tick(B);assert lib.host_world(12)==0
        lib.host_buffer(0);lib.host_draw_cached();assert scene()==baseline,'inventory leaked into room framebuffer 0'
        lib.host_buffer(1);lib.host_draw_cached();assert scene()==baseline,'inventory leaked into room framebuffer 1'
        # Script execution, rather than UI state alone, verifies action dispatch.
        lib.host_found_life(2,1<<4);fight=lib.host_variable(90)
        press(32);press(A);press(DOWN);press(A)
        assert lib.host_world(12)==0 and lib.host_variable(90)!=fight,'Search action did not execute original LIFE'
        lib.host_ui(0,2);capture(lib,f'character-{character}-copyright')
        lib.host_ui(1,13);capture(lib,f'character-{character}-pickup')
        lib.host_ui(5,0);capture(lib,f'character-{character}-pause')
        rows.append(dict(character=character,preview_frames=len(previews),paused_world=True,
                         scrolling=True,action_script=True,both_framebuffers_restored=True,
                         previous_save_payload_identical=True))
    return rows

def native_checks(core,mars,region):
    offsets=layout(mars)
    source=OUT/'native-layout.cpp';assembly=source.with_suffix('.s')
    source.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned ui_offsets[]={offsetof(World,inventory),offsetof(World,inventory_count)};\n')
    subprocess.run([str(mars/'sh-elf/bin/sh-elf-g++'),'-m2','-mb','-std=c++17',
                    '-Wno-invalid-offsetof','-I'+str(ROOT),'-S',str(source),'-o',str(assembly)],check=True)
    values=re.findall(r'\.long\s+([-0-9xa-fA-F]+)',assembly.read_text().split('_ui_offsets:',1)[1].split('.ident',1)[0])
    inventory,count=(int(value,0) for value in values)
    check=Check(core,region,offsets)
    def scene():return check.e.framebuffer()[1][12*320:212*320]
    def write32(offset,value):
        words=(C.c_uint16*2).from_address(check.memory+check.game+offsets['world']+offset)
        words[0]=value>>16;words[1]=value&65535
    try:
        check.advance(check.hz);check.press(A);check.phase(5);check.press(A);check.phase(6);check.press(A);check.phase(7)
        for _ in range(struct.unpack_from('>H',assets()('STARTUP_BIOGRAPHY_0'),2)[0]):check.press(A)
        check.phase(8);check.press(A);check.phase(10);check.advance(check.hz)
        check.wait(check.settled)
        # Add one item to private emulator RAM; no cartridge-save transport.
        write32(inventory,2);write32(inventory+4,13);write32(inventory+8,123);write32(count,3)
        check.press(32)
        assert check.read('menu')==1
        previews=[]
        for selection,name in enumerate(('Actions','Oil Lamp','Gramophone')):
            if selection:check.press(DOWN)
            check.wait(lambda:check.read('selection')==selection)
            # Wait for both framebuffer histories to show the new selection.
            completed=check.state()['rendered'];check.wait(lambda:check.state()['rendered']>=completed+3)
            check.e.capture(f'gameplay-ui-{region}-inventory-{selection}.png')
            world_ticks=check.state()['world_ticks'];draws=check.state()['rendered'];fixed=None;poses=set();banks=set()
            for _ in range(check.hz*3):
                check.advance()
                if not check.settled():continue
                pixels=scene();static=bytes(v for i,v in enumerate(pixels) if not(8<=i%320<=151 and 108<=i//320<=191))
                if fixed is None:fixed=static
                assert static==fixed,'native preview altered static UI pixels'
                poses.add(hashlib.sha256(pixels[108*320:192*320]).hexdigest());banks.add(check.e.vdp[5]&1)
                assert not check.state()['fault']
            assert check.state()['world_ticks']==world_ticks and len(poses)>10 and banks=={0,1}
            previews.append(dict(item=name,preview_fps=round((check.state()['rendered']-draws)/3,2),distinct_previews=len(poses)))
        check.press(A);assert check.read('menu')==2
        check.e.capture(f'gameplay-ui-{region}-actions.png')
        check.press(B);check.press(B);assert check.read('menu')==0
        check.advance(check.hz);assert not check.state()['fault'] and check.mapper_valid()
        return dict(region=region,emulator_only=True,previews=previews,
                    both_framebuffers=True,paused_world=True,menu_back=True)
    finally:check.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core',type=Path);parser.add_argument('--mars',type=Path,default=ROOT/'.local/toolchain/mars')
    parser.add_argument('--native-only',action='store_true')
    args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    report=dict(rom_sha256=hashlib.sha256((ROOT/'build/AITD32X.32x').read_bytes()).hexdigest())
    if not args.native_only:report['host']=host_checks()
    if args.core:report['native']=[native_checks(args.core,args.mars,region) for region in ('NTSC','PAL')]
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
