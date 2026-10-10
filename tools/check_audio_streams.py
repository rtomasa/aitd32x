#!/usr/bin/env python3
"""Native FM track end timing and PWM duration, independent of game draw rate."""
import argparse,ctypes as C,json,re,subprocess,struct
from pathlib import Path
import emulator_check as ec
p=argparse.ArgumentParser();p.add_argument('core',type=Path);p.add_argument('--region',default='NTSC');p.add_argument('--mars',type=Path,default=(ec.ROOT.parents[1]/'work/toolchain/mars' if (ec.ROOT.parents[1]/'work/toolchain/mars').exists() else Path.home()/'mars'));a=p.parse_args();root=ec.ROOT;hz=50 if a.region=='PAL' else 60
mars=a.mars
text=subprocess.check_output([str(mars/'m68k-elf/bin/m68k-elf-nm'),str(root/'build/md_start.elf')],text=True)
md={name:int(address,16)&65535 for address,kind,name in (line.split() for line in text.splitlines() if len(line.split())==3)}
layout_text=(root/'build/audio-save-layout.s').read_text();offsets=[int(x,0) for x in re.findall(r'\.long\s+([-0-9xa-fA-F]+)',layout_text.split('_layout:',1)[1].split('.ident',1)[0])];world,music,next_music,menu,selection,notice,tick,pos,vars,dirty=offsets
manifest=json.loads((root/'assets/manifest.json').read_text());assets={x['name']:x for x in manifest['assets']};report=[]
e=ec.Emulator(a.core,a.region);e.run(hz*3);e.run(12,128);e.run(24);e.run(12,128);e.run(24);assert e.state()['paused']
mem=C.c_void_p.in_dll(e.lib,'Pico32xMem').value;game=ec.symbol_address('__ZL4game')&0x3ffff;ram=C.addressof((C.c_uint8*65536).in_dll(e.lib,'PicoMem'))
def readmd(name):return C.c_uint16.from_address(ram+md[name]).value
def writesh(off,v):
 w=(C.c_uint16*2).from_address(mem+game+off);w[0]=(v>>16)&65535;w[1]=v&65535
def writemd(name,value,long=False):
 words=(C.c_uint16*(2 if long else 1)).from_address(ram+md[name])
 if long:words[0]=(value>>16)&65535;words[1]=value&65535
 else:words[0]=value
for i,m in enumerate(json.loads((root/'assets/audio_manifest.json').read_text())['music']):
 # Exercise physical streams independently of the CD-to-AdLib cue mapping.
 # Selection through LIFE is covered by check_v15.py; this also tests the
 # piano stream, whose CD edition uses a PCM musical effect instead.
 asset=assets['MUSIC_'+str(i)];data=(root/'assets/bank.bin').read_bytes()[asset['offset']:asset['offset']+asset['packed_size']]
 pointer=ec.symbol_address('_asset_bank')-0x02000000+asset['offset']
 writemd('music_pointer',pointer+9,True);writemd('music_commands',struct.unpack_from('>I',data,4)[0],True)
 writemd('music_wait',data[8]);writemd('music_phase',0);writemd('fade_frames',0);writemd('fade_gain',0);writemd('music_active',1)
 elapsed=0
 remaining=round(m['seconds']*hz)-elapsed
 e.capture_audio=True;e.audio.clear();e.run(min(remaining-30,hz*6));played=min(remaining-30,hz*6)
 samples=list(struct.iter_unpack('<h',e.audio));peak=max(abs(x[0]) for x in samples);assert peak>0,(i,'silent')
 e.capture_audio=False;e.run(max(0,remaining-played-60));assert readmd('music_active')==1,(i,'early end')
 for frames in range(hz*3):
  if not readmd('music_active'):break
  e.run(1)
 else:raise AssertionError((i,'no end',readmd('music_wait')))
 report.append(dict(track=i,duration_seconds=m['seconds'],peak=peak,autonomous_while_paused=True,ends_on_time=True));print(report[-1],flush=True)
# PWM fixture: directly queue one imported effect, with gameplay still paused.
# Shared queue follows the audio voices (the second symbol of this name is renderer).
shtext=subprocess.check_output([str(mars/'sh-elf/bin/sh-elf-nm'),str(root/'build/AITD32X.elf')],text=True)
queues=[int(line.split()[0],16)&0x3ffff for line in shtext.splitlines() if line.endswith('__ZN12_GLOBAL__N_1L7storageE')];queue=min(queues)
def readsh(off):
 w=(C.c_uint16*2).from_address(mem+off);return (w[0]<<16)|w[1]
def write32(off,v):
 w=(C.c_uint16*2).from_address(mem+off);w[0]=v>>16;w[1]=v&65535
write=readsh(queue);entry=queue+8+(write&7)*8
for n,v in enumerate((0,-1,0,0)):C.c_uint16.from_address(mem+entry+n*2).value=v&65535
write32(queue,write+1);e.capture_audio=True;e.audio.clear();e.run(hz//2)
voice=ec.symbol_address('__ZN12_GLOBAL__N_1L6voicesE')&0x3ffff
assert readsh(voice+4)==6600 and 3500<=readsh(voice+8)<=4300,('PWM sample timing',readsh(voice+4),readsh(voice+8))
e.run(hz*2-hz//2)
# FIFO/ISR playback count and predicted duration: 6600 samples /8000Hz.
voice=ec.symbol_address('__ZN12_GLOBAL__N_1L6voicesE')&0x3ffff
assert readsh(voice+4)==0 and readsh(voice+28+4)==0
assert any(e.audio),'PWM sample produced silence'
assert readsh(voice+8)==6600
report.append(dict(effect=0,pcm_samples=6600,duration_seconds=.825,completed=True,sample_clock_verified=True))
(root/'validation'/('audio-streams-'+a.region+'.json')).write_text(json.dumps(dict(rom_sha256=__import__('hashlib').sha256((root/'build/AITD32X.32x').read_bytes()).hexdigest(),checks=report),indent=2)+'\n');e.close()
