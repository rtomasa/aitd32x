#!/usr/bin/env python3
"""Actual-ROM save persistence and autonomous audio checks on PicoDrive."""
import argparse,ctypes as C,json,re,struct,subprocess,wave
from pathlib import Path
import emulator_check as ec
p=argparse.ArgumentParser();p.add_argument('core',type=Path);p.add_argument('--region',default='NTSC');p.add_argument('--mars',type=Path,default=(ec.ROOT.parents[1]/'work/toolchain/mars' if (ec.ROOT.parents[1]/'work/toolchain/mars').exists() else Path.home()/'mars'));a=p.parse_args();root=ec.ROOT;hz=50 if a.region=='PAL' else 60
fields={'world':'offsetof(Game,world)','music':'offsetof(World,music)','next':'offsetof(World,next_music)','menu':'offsetof(Game,menu)','selection':'offsetof(Game,selection)','notice':'offsetof(Game,action_selection)','tick':'offsetof(Game,tick)','pos':'offsetof(Game,player)+offsetof(Actor,pos)','vars':'offsetof(World,vars)','dirty':'offsetof(Game,dirty)'}
f=root/'build/audio-save-layout.cpp';f.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned layout[]={'+','.join(fields.values())+'};\n');out=f.with_suffix('.s')
subprocess.run([str(a.mars/'sh-elf/bin/sh-elf-g++'),'-m2','-mb','-std=c++17','-Wno-invalid-offsetof','-I'+str(root),'-S',str(f),'-o',str(out)],check=True)
o=dict(zip(fields,[int(v,0) for v in re.findall(r'\.long\s+([-0-9xa-fA-F]+)',out.read_text().split('_layout:',1)[1].split('.ident',1)[0])]))
e=None

def open_emulator():
 global e,mem,game
 e=ec.Emulator(a.core,a.region);e.run(hz*3);mem=C.c_void_p.in_dll(e.lib,'Pico32xMem').value;game=ec.symbol_address('__ZL4game')&0x3ffff
 e.lib.retro_get_memory_data.argtypes=[C.c_uint];e.lib.retro_get_memory_data.restype=C.c_void_p;e.lib.retro_get_memory_size.argtypes=[C.c_uint];e.lib.retro_get_memory_size.restype=C.c_size_t

def read(off):
 w=(C.c_uint16*2).from_address(mem+game+off);return C.c_int32(w[0]<<16|w[1]).value

def write(off,v):
 w=(C.c_uint16*2).from_address(mem+game+off);w[0]=(v>>16)&65535;w[1]=v&65535

def press(pad):e.run(12);e.run(12,pad);e.run(24)

def wait(pred,seconds=30):
 for i in range(hz*seconds):
  if pred():return i
  e.run(1)
 raise AssertionError(('timeout',e.comm(),e.state(),read(o['menu']),read(o['notice'])))

open_emulator();press(128);e.run(hz);assert e.state()['mode']==1
# The original LIFE scripts trigger actual effects while walking.
e.capture_audio=True;e.audio.clear();e.run(hz*3,1);e.run(hz)
walking_sound=any(e.audio);print('walking sound',walking_sound,'state',e.state(),flush=True)
# Enable an imported music track, retaining real game/68000 playback paths.
write(o['world']+o['music'],4);e.audio.clear();e.run(hz*3)
assert any(e.audio),'FM stream produced silence';music=bytes(e.audio)
press(128);assert e.state()['paused'];position=[read(o['pos']+i*4) for i in range(3)]
C.c_int16.from_address(mem+game+o['world']+o['vars']+90*2).value=17
press(2);assert read(o['selection'])==1
press(64);saved_frames=wait(lambda:read(o['notice'])==1)
size=e.lib.retro_get_memory_size(0);sram=e.lib.retro_get_memory_data(0);assert size==131072,(size,sram)
raw=C.string_at(sram,size);assert raw[:4]==b'AITD';e.run(hz);e.capture('v15-save-menu-'+a.region+'.png')
# Relaunch core, restore battery SRAM just as a frontend does, then title B load.
e.close();open_emulator();C.memmove(e.lib.retro_get_memory_data(0),raw,size);press(16);wait(lambda:e.state()['mode']==1)
assert e.state()['paused'] and [read(o['pos']+i*4) for i in range(3)]==position
assert C.c_int16.from_address(mem+game+o['world']+o['vars']+90*2).value==17
e.capture('v15-loaded-'+a.region+'.png');press(128);e.run(hz);assert not e.state()['paused']
assert e.comm()[0]!=0xe001
(root/'validation').mkdir(exist_ok=True)
with wave.open(str(root/'validation'/('music-native-'+a.region+'.wav')),'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(44100);w.writeframes(music)
report=dict(region=a.region,sram_bytes=size,persistent_core_restart=True,pose=position,world_variable_restored=True,walking_sound=walking_sound,fm_nonzero=True,save_wait_extra_frames=saved_frames,rom_sha256=__import__('hashlib').sha256((root/'build/AITD32X.32x').read_bytes()).hexdigest())
(root/'validation'/('audio-save-native-'+a.region+'.json')).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));e.close()
