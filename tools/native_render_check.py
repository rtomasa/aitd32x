#!/usr/bin/env python3
"""Frozen native cartridge raster snapshots, including both framebuffer banks.

Debugger placement canonicalizes pose and stops gameplay; no release code changes.
Game layout is obtained from the project's actual SH-2 compiler, never hardcoded.
Uses the same PicoDrive DRC_SH2 memory inspection as emulator_check.py.
"""
import argparse,ctypes as C,hashlib,importlib.util,json,re,struct,subprocess
from pathlib import Path

FIELDS={
'g_player':'offsetof(Game,player)','g_mode':'offsetof(Game,mode)','g_camera':'offsetof(Game,camera)','g_character':'offsetof(Game,character)',
'g_paused':'offsetof(Game,paused)','g_help':'offsetof(Game,help)','g_dirty':'offsetof(Game,dirty)','g_held':'offsetof(Game,held)','g_pending':'offsetof(Game,pending_edges)',
'r_background':'offsetof(Renderer,background)','r_palette':'offsetof(Renderer,palette)','r_camera':'offsetof(Renderer,camera)','r_room':'offsetof(Renderer,room)',
'r_camera_id':'offsetof(Renderer,camera_id)','r_palette_changed':'offsetof(Renderer,palette_changed)','r_full_restore':'offsetof(Renderer,full_restore)',
'a_pos':'offsetof(Actor,pos)','a_beta':'offsetof(Actor,beta)','a_character':'offsetof(Actor,character)','a_min':'offsetof(Actor,collision_min)','a_max':'offsetof(Actor,collision_max)',
'a_model':'offsetof(Actor,model)','a_animation':'offsetof(Actor,animation)','a_frame':'offsetof(Actor,frame)','a_phase':'offsetof(Actor,frame_phase)',
'a_anim_asset':'offsetof(Actor,anim_asset)','a_previous':'offsetof(Actor,previous)','a_state':'offsetof(Actor,state)','a_last_step':'offsetof(Actor,last_step)','a_walking':'offsetof(Actor,walking)',
'asset_size':'sizeof(Asset)','group_size':'sizeof(GroupState)'}

def layout(root,mars):
    source=root/'build/native-check-layout.cpp';assembly=source.with_suffix('.s')
    source.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned native_layout[]={'+','.join(FIELDS.values())+'};\n')
    subprocess.run([str(mars/'sh-elf/bin/sh-elf-g++'),'-m2','-mb','-std=c++17','-Wno-invalid-offsetof','-I'+str(root),'-S',str(source),'-o',str(assembly)],check=True)
    s=assembly.read_text().split('_native_layout:',1)[1].split('.ident',1)[0]
    values=[int(v,0) for v in re.findall(r'\.long\s+([-0-9xa-fA-F]+)',s)]
    assert len(values)==len(FIELDS),(values,s)
    return dict(zip(FIELDS,values))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('core',type=Path);ap.add_argument('--project',type=Path,required=True);ap.add_argument('--mars',type=Path,required=True)
    ap.add_argument('--character',choices=['edward','emily'],default='edward');ap.add_argument('--region',choices=['NTSC','PAL'],default='NTSC');ap.add_argument('--label',default='native-check');args=ap.parse_args()
    root=args.project.resolve();spec=importlib.util.spec_from_file_location('ec',root/'tools/emulator_check.py');ec=importlib.util.module_from_spec(spec);spec.loader.exec_module(ec)
    offsets=layout(root,args.mars.resolve());assert offsets['asset_size']==16 and offsets['group_size']==16
    bank=(root/'assets/bank.bin').read_bytes();manifest=json.loads((root/'assets/manifest.json').read_text());assets={a['name']:a for a in manifest['assets']}
    def raw(name):
        a=assets[name];p=bank[a['offset']:a['offset']+a['packed_size']]
        if a['flags']==1:p=b''.join(bytes([value])*count for count,value in zip(p[::2],p[1::2]))
        assert len(p)==a['unpacked_size'];return p
    e=ec.Emulator(args.core,args.region);e.run(180)
    if args.character=='emily':e.run(6,32);e.run(12)
    e.run(6,128);e.run(120);e.run(6,128);e.run(120);assert e.state()['paused']
    mem=C.c_void_p.in_dll(e.lib,'Pico32xMem').value
    game=ec.symbol_address('__ZL4game')&0x3ffff;rombank=ec.symbol_address('_asset_bank')
    def write(offset,data):
        assert offset%2==0 and len(data)%2==0
        words=(C.c_uint16*(len(data)//2)).from_address(mem+game+offset)
        for i,(v,) in enumerate(struct.iter_unpack('>H',data)):words[i]=v
    def byte(offset,value):C.c_uint8.from_address(mem+game+(offset^1)).value=value
    def u32(offset,value):write(offset,struct.pack('>I',value&0xffffffff))
    def asset(offset,name):
        a=assets[name];write(offset,struct.pack('>3I2H',rombank+a['offset'],a['packed_size'],a['unpacked_size'],a['type'],a['flags']))
    def bank_pixels(index):
        p=mem+0x80000+index*0x20000+512
        swapped=C.string_at(p,320*224);pixels=bytearray(len(swapped))
        pixels[::2]=swapped[1::2];pixels[1::2]=swapped[::2]
        return bytes(pixels[12*320:212*320])
    character=int(args.character=='emily');actor=offsets['g_player']
    asset(actor+offsets['a_model'],f'MODEL_{character}_12');asset(actor+offsets['a_animation'],f'ANIM_{character}_4')
    model=raw(f'MODEL_{character}_12');idle=raw(f'ANIM_{character}_4');ng=struct.unpack_from('>H',model,4)[0];ag=struct.unpack_from('>H',idle,2)[0];groups=struct.unpack_from('>I',model,24)[0]
    states=[]
    for i in range(40):
        if i<min(ng,ag):state=struct.unpack_from('>4h',idle,12+i*8)
        elif i<ng:state=struct.unpack_from('>4h',model,groups+i*16+8)
        else:state=(0,0,0,0)
        states.append(state)
    pose=b''.join(struct.pack('>4i',*s) for s in states)
    write(actor+offsets['a_state'],pose);write(actor+offsets['a_previous'],pose)
    extent=sum(struct.unpack_from('>h',model,o)[0]for o in [10,18])//2
    write(actor+offsets['a_min'],struct.pack('>3i',-extent,struct.unpack_from('>h',model,12)[0],-extent))
    write(actor+offsets['a_max'],struct.pack('>3i',extent,struct.unpack_from('>h',model,14)[0],extent))
    u32(actor+offsets['a_character'],character);u32(actor+offsets['a_frame'],0);u32(actor+offsets['a_phase'],0);u32(actor+offsets['a_anim_asset'],assets[f'ANIM_{character}_4']['id'])
    write(actor+offsets['a_last_step'],bytes(12));byte(actor+offsets['a_walking'],0)
    byte(offsets['g_paused'],1);byte(offsets['g_help'],0);u32(offsets['g_mode'],1);u32(offsets['g_character'],character);write(offsets['g_held'],bytes(2));write(offsets['g_pending'],bytes(2))
    asset(offsets['r_room'],'ROOM_0');write(offsets['r_palette'],raw('GAME_PALETTE'));byte(offsets['r_palette_changed'],1)
    poses=[(3231,500,0),(3231,-1548,0),(3231,-3734,0),(4500,-3500,0),(4500,-3500,260),(5000,-4000,520),(4500,-6000,0),(6000,-5000,780)]
    samples=[]
    for camera in range(5):
        asset(offsets['r_camera'],f'CAMERA_{camera}');write(offsets['r_background'],raw(f'BACKGROUND_{camera}'));u32(offsets['g_camera'],camera);u32(offsets['r_camera_id'],camera)
        for x,z,beta in poses:
            write(actor+offsets['a_pos'],struct.pack('>3i',x,0,z));u32(actor+offsets['a_beta'],beta)
            # A back buffer can still be drawing its actor / pause overlay at
            # a fixed delay. Capture each bank only after it has been presented.
            # Ignore the first completion: it may have started before placement.
            presented={};last_bank=e.vdp[5]&1;swaps=0
            def advance():
                nonlocal last_bank,swaps
                e.run(1);bank=e.vdp[5]&1
                if bank!=last_bank:
                    last_bank=bank;swaps+=1
                    if swaps>=2:presented[bank]=bank_pixels(bank)
            def redraw():
                byte(offsets['r_full_restore'],1);byte(offsets['r_full_restore']+1,1);byte(offsets['g_dirty'],1)
            for _ in range(4):
                redraw()
                for _ in range(18):advance()
            # Oversized diagnostic poses may need more time than ordinary play.
            # Requests retain this same canonical state; completed swaps, rather
            # than a chosen number of VBlanks, establish coverage of both banks.
            for extra in range(240):
                if swaps>=3:break
                if extra%18==0:redraw()
                advance()
            else:raise RuntimeError(f'redraw timeout camera={camera} pose={(x,z,beta)} swaps={swaps}')
            if set(presented)!={0,1} or presented[0]!=presented[1]:
                raise RuntimeError(f'completed bank mismatch camera={camera} pose={(x,z,beta)} swaps={swaps}')
            pix=[presented[0],presented[1]]
            samples.append({'camera':camera,'pose':[x,0,z,beta],'pixel_sha256':hashlib.sha256(pix[0]).hexdigest()})
    e.close();report={'character':args.character,'region':args.region,'cases':len(samples),'both_banks_exact':True,'settling':'capture each physical bank after completed presentation; ignore first in-flight frame','canonical':'idle key 0, paused; includes pause overlay','rom_sha256':hashlib.sha256((root/'build/AITD32X.32x').read_bytes()).hexdigest(),'samples':samples}
    p=root/'build'/f'{args.label}-{args.region.lower()}-{args.character}.json';p.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'report':str(p),'cases':len(samples)}))

if __name__=='__main__':main()
