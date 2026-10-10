#!/usr/bin/env python3
"""Focused actual-ROM entrance rendering and idle-startup differential check.

The baseline route supplies two private entrance poses. The scheduler is rebased
once per VBlank while measuring those frozen poses, as in the contact check.
This measures renderer capacity independently of simulation and makes exact
before/after pixel comparisons possible. No battery saves are read or written.
"""
import argparse
import ctypes as C
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path

import emulator_check as ec
from check_startup_native import Check, DOWN, LEFT, RIGHT, B, A, START, assets, picture_hold

PROJECT = ec.ROOT
C_BUTTON = 32
FIELDS = {
    'game_size':'sizeof(Game)', 'world_size':'sizeof(World)', 'actor_size':'sizeof(Actor)',
    'g_world':'offsetof(Game,world)', 'g_player':'offsetof(Game,player)', 'g_dirty':'offsetof(Game,dirty)',
    'g_camera':'offsetof(Game,camera)', 'g_character':'offsetof(Game,character)',
    'g_static_signature':'offsetof(Game,static_signature)', 'g_static_slots':'offsetof(Game,static_slots)',
    'g_dynamic_slots':'offsetof(Game,dynamic_slots)', 'g_static_hash':'offsetof(Game,static_hash)',
    'g_static_owner':'offsetof(Game,static_owner)', 'g_static_quiet_since':'offsetof(Game,static_quiet_since)',
    'g_renderer':'offsetof(Game,renderer)', 'r_camera_id':'offsetof(Renderer,camera_id)',
    'w_player':'offsetof(World,player)', 'w_ticks':'offsetof(World,ticks)', 'w_active':'offsetof(World,active)',
    'w_inventory':'offsetof(World,inventory)', 'w_inventory_count':'offsetof(World,inventory_count)',
    'w_objects':'offsetof(World,objects)', 'w_vars':'offsetof(World,vars)',
    'w_poses':'offsetof(World,poses)', 'w_floor':'offsetof(World,floor)', 'w_room':'offsetof(World,room)', 'w_camera':'offsetof(World,camera)', 'active_size':'sizeof(ActiveObject)', 'o_id':'offsetof(ActiveObject,id)',
    'o_value':'offsetof(ActiveObject,value)', 'a_pos':'offsetof(Actor,pos)', 'a_beta':'offsetof(Actor,beta)',
    'a_floor':'offsetof(Actor,floor)', 'a_room':'offsetof(Actor,room)', 'a_frame':'offsetof(Actor,frame)',
    'a_phase':'offsetof(Actor,frame_phase)', 'a_model':'offsetof(Actor,model)',
    'a_animation':'offsetof(Actor,animation)', 'clock_phase':'offsetof(Clock,phase)', 'clock_last':'offsetof(Clock,last)',
    'world':'offsetof(Game,world)', 'fault':'offsetof(World,fault_code)', 'menu':'offsetof(Game,menu)',
    'selection':'offsetof(Game,selection)', 'notice':'offsetof(Game,action_selection)',
    'book_line':'offsetof(Game,book_line)', 'pos':'offsetof(Game,player)+offsetof(Actor,pos)',
    'vars':'offsetof(World,vars)', 'since':'offsetof(Game,startup_since)', 'time':'offsetof(Game,startup_time)',
}


def layout(mars):
    source=PROJECT/'build/startup-performance-layout.cpp'
    assembly=source.with_suffix('.s')
    source.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned perf_layout[]={' + ','.join(FIELDS.values()) + '};\n')
    subprocess.run([str(mars/'sh-elf/bin/sh-elf-g++'), '-m2', '-mb', '-std=c++17', '-Wno-invalid-offsetof',
                    '-I'+str(PROJECT), '-S', str(source), '-o', str(assembly)], check=True)
    values=re.findall(r'\.long\s+([-0-9xa-fA-F]+)', assembly.read_text().split('_perf_layout:',1)[1].split('.ident',1)[0])
    assert len(values)==len(FIELDS)
    return dict(zip(FIELDS,(int(value,0) for value in values)))


def root_for(label, rom, elf, asset_dir):
    root=PROJECT/'build/startup-performance'/label
    (root/'build').mkdir(parents=True,exist_ok=True)
    for target, source in [(root/'build/AITD32X.32x',rom),(root/'build/AITD32X.elf',elf),(root/'assets',asset_dir)]:
        if target.is_symlink():target.unlink()
        target.symlink_to(source.resolve(),target_is_directory=source.is_dir())
    return root


class Bench(Check):
    def __init__(self, core, region, offsets):
        super().__init__(core,region,offsets)
        self.clock=(ec.symbol_address('__ZL11clock_state')&0x3ffff)-self.game

    def read_bytes(self, offset, size):
        assert offset%2==0 and size%2==0
        words=(C.c_uint16*(size//2)).from_address(self.memory+self.game+offset)
        return struct.pack('>'+str(len(words))+'H',*words)

    def write_bytes(self, offset, data):
        assert offset%2==0 and len(data)%2==0
        words=(C.c_uint16*(len(data)//2)).from_address(self.memory+self.game+offset)
        for i,(value,) in enumerate(struct.iter_unpack('>H',data)):words[i]=value

    def integer(self, offset, value):
        self.write_bytes(offset,struct.pack('>I',value&0xffffffff))

    def byte(self, offset, value):
        C.c_uint8.from_address(self.memory+self.game+(offset^1)).value=value

    def word(self, offset):
        return struct.unpack('>I',self.read_bytes(offset,4))[0]

    def freeze_frame(self):
        o=self.offsets
        self.integer(self.clock+o['clock_phase'],0)
        self.write_bytes(self.clock+o['clock_last'],struct.pack('>H',self.e.comm()[6]&~1))
        self.byte(o['g_dirty'],1)
        self.advance()

    def quiesce(self):
        stable=0;last=None
        for _ in range(self.hz*3):
            self.freeze_frame()
            ticks=self.word(self.offsets['g_world']+self.offsets['w_ticks'])
            stable=stable+1 if ticks==last else 0;last=ticks
            if stable>=self.hz//3:return
        raise AssertionError(('cannot quiesce world',self.state(),last))

    def fixture(self):
        o=self.offsets
        manifest=json.loads((ec.ROOT/'assets/manifest.json').read_text())
        entries={a['name']:a for a in manifest['assets']}
        bank=(ec.ROOT/'assets/bank.bin').read_bytes()
        camera=entries['CAMERA_'+str(self.word(o['g_world']+o['w_floor']))+'_'+str(self.word(o['g_world']+o['w_camera']))]
        data=bank[camera['offset']:camera['offset']+camera['packed_size']]
        views=struct.unpack_from('>I',data,20)[0]
        rooms={struct.unpack_from('>H',data,views+16*i)[0] for i in range(struct.unpack_from('>H',data,18)[0])}
        actors=[]
        for slot in range(24):
            off=o['g_world']+o['w_active']+slot*o['active_size']
            id=C.c_int32(self.word(off+o['o_id'])).value
            if id<0:continue
            words=struct.unpack('>26h',self.read_bytes(off+o['o_value'],52))
            actor=dict(slot=slot,id=id,body=words[1],flags=words[2],floor=words[14],room=words[15],animation=words[19],
                       drawn=words[1]>=0 and words[15] in rooms,static_flags=not(words[2]&17))
            if words[1]>=0:
                model=entries['MODEL_'+str(self.state()['character'])+'_'+str(words[1])]
                actor['vertices'],actor['groups'],actor['primitives']=struct.unpack_from('>3H',bank,model['offset']+2)
            actors.append(actor)
        state=self.state()
        for field in ('floor','room','camera'):state[field]=self.word(o['g_world']+o['w_'+field])
        state['world_ticks']=self.word(o['g_world']+o['w_ticks'])
        return dict(state=state, world=self.read_bytes(o['g_world'],o['world_size']).hex(),
                    player=self.read_bytes(o['g_player'],o['actor_size']).hex(),actors=actors)

    def place(self, fixture, source_assets):
        o=self.offsets
        # Actor Assets retain native ROM pointers. A directory addition shifts
        # fixed payloads even when all model/animation bytes are unchanged.
        # Rebase by identity and verify bytes instead of replaying old pointers.
        before=json.loads((source_assets/'manifest.json').read_text())['assets']
        after={a['name']:a for a in json.loads((ec.ROOT/'assets/manifest.json').read_text())['assets']}
        old_bank=(source_assets/'bank.bin').read_bytes();new_bank=(ec.ROOT/'assets/bank.bin').read_bytes()
        pointers={}
        for a in before:
            if a['type'] not in (5,6):continue
            b=after[a['name']]
            for field in ('id','packed_size','unpacked_size','type','flags'):assert a[field]==b[field],('fixture asset changed',a['name'],field)
            assert old_bank[a['offset']:a['offset']+a['packed_size']]==new_bank[b['offset']:b['offset']+b['packed_size']],a['name']
            old=0x02020000+a['offset'];new=0x02020000+b['offset']
            assert pointers.get(old,new)==new,('deduplicated pointer changed',a['name'])
            pointers[old]=new
        world=bytearray.fromhex(fixture['world']);player=bytearray.fromhex(fixture['player']);relocated=0
        for data, starts in ((world,[o['w_poses']+slot*o['actor_size'] for slot in range(24)]),(player,[0])):
            for start in starts:
                for field in ('a_model','a_animation'):
                    offset=start+o[field];pointer=struct.unpack_from('>I',data,offset)[0]
                    if not pointer:continue
                    assert pointer in pointers,('unknown fixture pointer',hex(pointer),field)
                    struct.pack_into('>I',data,offset,pointers[pointer]);relocated+=1
        self.write_bytes(o['g_world'],world)
        self.write_bytes(o['g_player'],player)
        self.integer(o['g_world']+o['w_player'],0x06000000+self.game+o['g_player'])
        self.integer(o['g_camera'],fixture['state']['camera'])
        self.integer(o['g_character'],fixture['state']['character'])
        self.integer(o['g_renderer']+o['r_camera_id'],0xffffffff)
        for field in ('static_signature','static_slots','dynamic_slots'):self.integer(o['g_'+field],0)
        self.write_bytes(o['g_static_hash'],bytes(24*4))
        self.write_bytes(o['g_static_owner'],bytes([255])*(24*2))
        self.write_bytes(o['g_static_quiet_since'],bytes(24*2))
        return relocated

    def frozen(self, fixture, seconds):
        ticks=fixture['state']['world_ticks'];shown={};previous=self.e.vdp[5]&1;swaps=0
        # Discard any frame which was started before placement, and warm both
        # physical banks before taking capacity/parity measurements.
        for _ in range(self.hz*8):
            self.freeze_frame()
            assert self.word(self.offsets['g_world']+self.offsets['w_ticks'])==ticks,('fixture world advanced',ticks,self.word(self.offsets['g_world']+self.offsets['w_ticks']),self.state())
            bank=self.e.vdp[5]&1
            if bank!=previous:
                previous=bank;swaps+=1
                if swaps>=3:shown[bank]=self.scene()
            if len(shown)==2:break
        assert len(shown)==2 and shown[0]==shown[1],('frozen bank mismatch',self.state())
        start=self.state();swaps=0
        for _ in range(self.hz*seconds):
            self.freeze_frame()
            assert self.word(self.offsets['g_world']+self.offsets['w_ticks'])==ticks,('fixture world advanced',ticks,self.word(self.offsets['g_world']+self.offsets['w_ticks']),self.state())
            bank=self.e.vdp[5]&1
            if bank!=previous:previous=bank;swaps+=1
        end=self.state();draws=end['rendered']-start['rendered']
        assert -2<=swaps-draws<=seconds+2,(draws,swaps)
        return dict(seconds=seconds,completed_draws=draws,observed_swaps=swaps,overlay_only_swaps=max(0,swaps-draws),
                    render_capacity_fps=swaps/seconds,counted_draw_fps=draws/seconds,
                    world_ticks=ticks,world_frozen=True,both_banks_equal=True,pixels_sha256=hashlib.sha256(shown[0]).hexdigest(),
                    actors=fixture['actors']),shown[0]


def idle(check, seconds, settle=2, gameplay=False):
    check.advance(check.hz*settle);start=check.state();swaps=0;bank=check.e.vdp[5]&1
    for _ in range(check.hz*seconds):
        check.advance();current=check.e.vdp[5]&1
        if current!=bank:swaps+=1;bank=current
    end=check.state()
    pixels=check.e.framebuffer()[1][320*12:320*212] if gameplay else check.scene()
    return dict(seconds=seconds,completed_draws=end['rendered']-start['rendered'],observed_swaps=swaps,
                world_ticks=end['world_ticks']-start['world_ticks'],pixels_sha256=hashlib.sha256(pixels).hexdigest())


def navigate(check, decode, start_arrival=True):
    check.advance(check.hz);check.press(A);check.phase(5)
    menu=idle(check,3);event_start=check.state()['rendered'];check.press(DOWN);check.advance(check.hz)
    menu['selection_event_draws']=check.state()['rendered']-event_start
    check.press(1);check.press(A);check.phase(6)
    character=idle(check,3);check.press(A);check.phase(7);check.advance(check.hz*2)
    biography=idle(check,3)
    if start_arrival:
        pages=struct.unpack_from('>H',decode('STARTUP_BIOGRAPHY_0'),2)[0]
        for _ in range(pages):check.press(A)
        check.phase(8)
    return dict(menu=menu,character=character,biography=biography)


def live_arrival(check, decode):
    paths=[];pictures=[];segments={};pages=set();banked_audio=0;banked_frames=0
    previous=None;deadline=check.frames+check.hz*200
    while check.frames<deadline:
        state=check.state()
        assert not check.read('fault',world=True),('live intro LIFE fault',state)
        if state['phase']==10:break
        path=tuple(state[field] for field in ('floor','room','camera'))
        if state['phase']==8 and path!=previous:
            paths.append(dict(floor=path[0],room=path[1],camera=path[2],world_ticks=state['world_ticks'],seconds=round(check.frames/check.hz,3)))
            print('live arrival',path,'tick',state['world_ticks'],flush=True);previous=path
        if state['phase']==9:
            assert check.scene()==decode('STARTUP_PICTURE')
            pictures.append(picture_hold(check,decode,len(pictures)))
            continue
        start=check.state();bank=check.e.vdp[5]&1;audio=len(check.e.audio)
        check.advance();end=check.state();mapped=check.banks[1]
        if mapped!=1:
            pages.add(mapped);banked_frames+=1
            if any(check.e.audio[audio:]):banked_audio+=1
        if (check.e.comm()[0]&0xff00) in (0x0100,0x1000):
            assert mapped==1,('mapper completed/idle page',mapped)
        if state['phase']==8 and path[:2]==(3,1) and path[2] in (3,2):
            row=segments.setdefault(path[2],dict(frames=0,completed_draws=0,observed_swaps=0,start_ticks=state['world_ticks']))
            row['frames']+=1;row['completed_draws']+=end['rendered']-start['rendered']
            row['observed_swaps']+=int((check.e.vdp[5]&1)!=bank);row['end_ticks']=end['world_ticks']
    state=check.state()
    assert state['phase']==10 and (state['floor'],state['room'])==(0,0),('live intro incomplete',state,paths)
    assert {p['floor'] for p in paths}>={1,2,3,7} and pictures,paths
    assert pages=={8,9},('raw intro mapper pages not exercised',pages)
    assert check.banks[1]==1
    for row in segments.values():
        row['seconds']=row['frames']/check.hz
        row['presented_fps']=row['observed_swaps']/row['seconds']
        row['draw_fps']=row['completed_draws']/row['seconds']
    return dict(full_sequence=True,path=paths,pictures=pictures,entrance_live_segments=segments,
                mapped_pages=sorted(pages),bank_restored=1,script_fault=0,
                banked_frame_samples=banked_frames,banked_frames_with_pcm=banked_audio,
                audio_scope='Nonzero libretro PCM samples; not a measurement of FM music cues')


def gameplay_idle(check):
    rows={};check.press(START)
    assert check.state()['paused'] and check.read('menu')==3
    rows['pause']=idle(check,5,3,True)
    before=check.state()['rendered'];check.press(DOWN)
    rows['pause']['navigation_draws']=check.state()['rendered']-before
    assert check.read('selection')==1 and rows['pause']['navigation_draws']>=1
    # Isolated in-core fixture: put two real objects with several valid actions
    # into the otherwise empty fresh-game inventory. Never save this state.
    o=check.offsets;items=[]
    for object in range((o['w_vars']-o['w_objects'])//52):
        fields=struct.unpack('>26h',check.read_bytes(o['g_world']+o['w_objects']+object*52,52))
        if fields[4]>=0 and fields[5]>=0 and (fields[6]&0x7ff).bit_count()>=2:
            items.append(object)
            if len(items)==2:break
    assert len(items)==2,'no inventory fixture items'
    for index,object in enumerate(items):check.integer(o['g_world']+o['w_inventory']+index*4,object)
    check.integer(o['g_world']+o['w_inventory_count'],len(items))
    check.press(START);assert not check.state()['paused']
    check.press(C_BUTTON)
    assert check.read('menu')==1,('inventory did not open',check.state())
    rows['inventory']=idle(check,5,3,True)
    before=check.state()['rendered'];check.press(DOWN)
    rows['inventory']['navigation_draws']=check.state()['rendered']-before
    assert check.read('selection')==1 and rows['inventory']['navigation_draws']>=1
    check.press(A);assert check.read('menu')==2
    rows['actions']=idle(check,5,3,True)
    before=check.state()['rendered'];check.press(DOWN)
    rows['actions']['navigation_draws']=check.state()['rendered']-before
    assert check.read('notice')==1 and rows['actions']['navigation_draws']>=1
    for name,row in rows.items():
        assert row['completed_draws']==row['observed_swaps']==row['world_ticks']==0,('idle gameplay UI work',name,row)
    assert not check.read('fault',world=True) and check.banks[1]==1
    return dict(samples=rows,transient_inventory_items=items,no_sram_file=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('core',type=Path)
    p.add_argument('--mars',type=Path,default=PROJECT/'.local/toolchain/mars')
    p.add_argument('--reference',type=Path,default=PROJECT/'build/startup-fix-reference')
    p.add_argument('--label',choices=('before','after'),required=True)
    p.add_argument('--region',choices=('NTSC','PAL'),default='NTSC')
    p.add_argument('--seconds',type=int,default=5)
    p.add_argument('--ui-only',action='store_true')
    p.add_argument('--live-arrival',action='store_true',help='run the full natural route after the isolated candidate measurements')
    p.add_argument('--live-only',action='store_true',help='run the complete natural route without repeating isolated measurements')
    p.add_argument('--gameplay-idle',action='store_true',help='check idle pause/inventory/action UI after the full route')
    args=p.parse_args()
    if args.gameplay_idle and not (args.live_arrival or args.live_only):p.error('--gameplay-idle requires a live arrival')
    destination=PROJECT/'build/startup-performance';destination.mkdir(exist_ok=True)
    baseline=destination/('fixtures-'+args.region+'.json')
    if args.label=='before':
        offsets=layout(args.mars);rom=args.reference/'AITD32X.32x';elf=args.reference/'AITD32X.elf';asset_dir=args.reference/'assets'
    else:
        offsets=layout(args.mars);rom=PROJECT/'build/AITD32X.32x';elf=PROJECT/'build/AITD32X.elf';asset_dir=PROJECT/'assets'
    root=root_for(args.label+'-'+args.region,rom,elf,asset_dir);ec.ROOT=root
    check=Bench(args.core,args.region,offsets);decode=assets()
    try:
        report=dict(label=args.label,region=args.region,rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),
                    emulator_only=True,measure='Frozen native entrance renderer capacity; original world/actor fixtures; separate idle UI samples')
        report['idle']=navigate(check,decode,not args.ui_only)
        if args.live_only:
            report['measure']='Natural full native arrival, including entrance presentation rate and mapper restoration'
            report['live_arrival']=live_arrival(check,decode)
            if args.gameplay_idle:report['gameplay_idle']=gameplay_idle(check)
            assert hashlib.sha256(rom.read_bytes()).hexdigest()==report['rom_sha256'],'ROM changed during validation'
            (destination/f'{args.label}-{args.region}-live.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report,indent=2),flush=True)
            return
        if args.ui_only:
            (destination/f'{args.label}-{args.region}-ui.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report,indent=2),flush=True)
            return
        fixtures=[];rows=[]
        if args.label=='before':
            for camera in (3,2):
                check.wait(lambda:check.state()['floor']==3 and check.state()['room']==1 and check.state()['camera']==camera,85)
                check.wait(check.settled)
                check.quiesce();fixture=check.fixture();fixtures.append(fixture)
                row,pixels=check.frozen(fixture,args.seconds);row['camera']=camera;rows.append(row)
                (destination/f'before-{args.region}-camera{camera}.pixels').write_bytes(pixels)
            baseline.write_text(json.dumps(dict(offsets=offsets,rom_sha256=report['rom_sha256'],fixtures=fixtures),indent=2)+'\n')
        else:
            saved=json.loads(baseline.read_text())
            for fixture in saved['fixtures']:
                for field in ('world_size','actor_size','active_size','w_poses'):assert offsets[field]==saved['offsets'][field],('layout changed',field)
                check.quiesce();relocated=check.place(fixture,args.reference/'assets');row,pixels=check.frozen(fixture,args.seconds);camera=fixture['state']['camera'];row['camera']=camera
                row['relocated_asset_pointers']=relocated
                expected=(destination/f'before-{args.region}-camera{camera}.pixels').read_bytes()
                row['baseline_pixels_equal']=pixels==expected
                row['differing_pixels']=sum(x!=y for x,y in zip(pixels,expected))
                rows.append(row)
                (destination/f'after-{args.region}-camera{camera}.pixels').write_bytes(pixels)
        report['entrance']=rows
        if args.label=='after':
            before_ui=json.loads((destination/f'before-{args.region}-ui.json').read_text())['idle']
            for name,row in report['idle'].items():row['baseline_pixels_equal']=row['pixels_sha256']==before_ui[name]['pixels_sha256']
        if args.live_arrival:
            (destination/f'{args.label}-{args.region}.json').write_text(json.dumps(report,indent=2)+'\n')
            check.close();check=Bench(args.core,args.region,offsets)
            navigate(check,decode)
            report['live_arrival']=live_arrival(check,decode)
            if args.gameplay_idle:report['gameplay_idle']=gameplay_idle(check)
        assert hashlib.sha256(rom.read_bytes()).hexdigest()==report['rom_sha256'],'ROM changed during validation'
        (destination/f'{args.label}-{args.region}.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2),flush=True)
    finally:check.close()


if __name__=='__main__':main()
