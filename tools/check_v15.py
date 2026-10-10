#!/usr/bin/env python3
"""Focused v15 checks: window collision, CD music cues, original reading and saves."""
import argparse,ctypes as C,json,struct,hashlib,re,subprocess
from pathlib import Path
import emulator_check as ec
ROOT=Path(__file__).resolve().parents[1]
def host():
 l=C.CDLL(str(ROOT/'build/libaitd32x.so'));l.host_init.argtypes=[C.c_void_p,C.c_uint];l.host_pixels.restype=l.host_palette.restype=l.host_sram.restype=C.c_void_p
 bank=(ROOT/'assets/bank.bin').read_bytes();buf=C.create_string_buffer(bank);report={};shots={}
 def init(ch=0):
  l.host_init(buf,len(bank))
  if ch:l.host_tick(32);l.host_tick(0)
  l.host_tick(128);l.host_tick(0)
 def tick(pad=0):
  l.host_tick(pad);assert not l.host_world(3),('script',*[l.host_world(i) for i in (3,4,5)])
 def press(pad):tick(0);tick(pad);tick(0)
 for ch in (0,1):
  init(ch)
  for _ in range(1510):tick()
  assert l.host_object(21,17)==20
  assert l.host_world(15)==12 and l.host_music_track()==1,('entrance cue',l.host_world(15),l.host_music_track())
  l.host_place(21,0,0,-2840,0,4540,0);tick()
  events=[[l.host_sample_event(n,f) for f in range(3)] for n in range(l.host_sample_count())]
  assert [2,29,0] in events,events
  assert l.host_world(16)==4
  l.host_music_end()
  for _ in range(11):tick()
  assert l.host_world(15)==4 and l.host_music_track()==0
  report[str(ch)]=dict(window_sound_chain=[2,29],window_fault=False,entrance_adlib=1,queued_ambient_adlib=0)
 init();l.host_clear_message();l.host_draw_cached();baseline=C.string_at(l.host_pixels(),320*224)
 pages=json.loads((ROOT/'assets/reading_manifest.json').read_text());total=0;graphics=set()
 manifest=json.loads((ROOT/'assets/manifest.json').read_text());assets={a['name']:bank[a['offset']:a['offset']+a['packed_size']] for a in manifest['assets']}
 for doc in pages:
  l.host_ui(-1,0);baseline=C.string_at(l.host_pixels(),320*224)
  l.host_ui(4,doc['id']);start=l.host_sample_count();time=l.host_world(11)
  for page in range(doc['pages']):
   assert l.host_world(17)==page
   pixels=C.string_at(l.host_pixels(),320*224)
   bg=assets['READ_BACKGROUND_'+str(doc['type'])]
   assert pixels[12*320:13*320]==bg[:320],('original art',doc,page)
   assert l.host_world(11)==time
   a=assets['BOOK_'+str(doc['id'])];off=struct.unpack_from('>I',a,4+page*4)[0];n=struct.unpack_from('>H',a,off)[0];off+=2
   for _ in range(n):
    x,y,size=struct.unpack_from('>HBB',a,off);off+=4
    if size:
     word=a[off:off+size];off+=size
     assert x<320 and y+16<=200
    else:graphics.add(a[off]);off+=1
   if doc['id'] in (1,2,7) and page==0:shots[doc['id']]=pixels
   if page+1<doc['pages']:press(2)
   total+=1
  count=l.host_sample_count();press(2)
  assert l.host_sample_count()==count and l.host_world(17)==doc['pages']-1
  if doc['pages']>1:press(1);assert l.host_world(17)==doc['pages']-2
  tick(0);tick(32);assert l.host_world(13)==-1
  l.host_clear_message();l.host_draw_cached();assert C.string_at(l.host_pixels(),320*224)==baseline
  assert all(l.host_sample_event(n,0)==49 for n in range(start,l.host_sample_count()))
 pal=list((C.c_uint16*256).from_address(l.host_palette()));colors=[bytes(((v&31)*255//31,((v>>5)&31)*255//31,((v>>10)&31)*255//31)) for v in pal]
 for id,pixels in shots.items():ec.png(ROOT/'validation'/f'v15-reading-{id}.png',b''.join(colors[v] for v in pixels),320,224)
 assert graphics==set(range(5)),graphics
 # The actual note/book inventory READ commands emit the original page sound.
 init();l.host_take(15);count=l.host_sample_count();l.host_found_life(15,4)
 assert l.host_world(13)==1 and l.host_sample_count()>count and l.host_sample_event(count,0)==49
 report['reading']=dict(documents=len(pages),pages_checked=total,illustrations=sorted(graphics),page_sample=49,world_paused=True,closing_restores_scene=True)
 return report,shots

def native(core,mars,region,shots):
 hz=50 if region=='PAL' else 60
 fields={'world':'offsetof(Game,world)','active':'offsetof(World,active)','poses':'offsetof(World,poses)','w_ticks':'offsetof(World,ticks)','book':'offsetof(World,book)','music':'offsetof(World,music)','next':'offsetof(World,next_music)','book_page':'offsetof(Game,book_line)','pos':'offsetof(Actor,pos)','id':'offsetof(ActiveObject,id)','asize':'sizeof(ActiveObject)','psize':'sizeof(Actor)'}
 f=ROOT/'build/v15-layout.cpp';f.write_text('#include "src/engine/game.hpp"\nextern "C" const unsigned layout[]={'+','.join(fields.values())+'};\n');s=f.with_suffix('.s');subprocess.run([str(mars/'sh-elf/bin/sh-elf-g++'),'-m2','-mb','-std=c++17','-Wno-invalid-offsetof','-I'+str(ROOT),'-S',str(f),'-o',str(s)],check=True,stderr=subprocess.DEVNULL)
 o=dict(zip(fields,[int(v,0) for v in re.findall(r'\.long\s+([-0-9xa-fA-F]+)',s.read_text().split('_layout:',1)[1].split('.ident',1)[0])]))
 text=subprocess.check_output([str(mars/'m68k-elf/bin/m68k-elf-nm'),str(ROOT/'build/md_start.elf')],text=True);md={line.split()[2]:int(line.split()[0],16)&65535 for line in text.splitlines() if len(line.split())==3}
 e=ec.Emulator(core,region);e.run(hz*3);e.run(12,128);e.run(24)
 mem=C.c_void_p.in_dll(e.lib,'Pico32xMem').value;g=ec.symbol_address('__ZL4game')&0x3ffff;w=g+o['world'];ram=C.addressof((C.c_uint8*65536).in_dll(e.lib,'PicoMem'))
 def read(off):
  q=(C.c_uint16*2).from_address(mem+off);return C.c_int32(q[0]<<16|q[1]).value
 def write(off,value):
  q=(C.c_uint16*2).from_address(mem+off);q[0]=(value>>16)&65535;q[1]=value&65535
 def mdlong(name):
  q=(C.c_uint16*2).from_address(ram+md[name]);return q[0]<<16|q[1]
 def fault():assert read((ec.symbol_address('_debug_state')&0x3ffff)+19*4)==0
 def press(pad):e.run(8);e.run(8,pad);e.run(12);fault()
 write(w+o['w_ticks'],1505);e.run(24);fault()
 assert read(w+o['music'])==12
 bankbase=ec.symbol_address('_asset_bank')-0x02000000;manifest=json.loads((ROOT/'assets/manifest.json').read_text());assets={a['name']:a for a in manifest['assets']}
 a=assets['MUSIC_1'];ptr=mdlong('music_pointer');assert bankbase+a['offset']<=ptr<bankbase+a['offset']+a['packed_size'],('CD12 must play AdLib1',ptr)
 slot=next(s for s in range(24) if read(w+o['active']+s*o['asize'])==21)
 pos=w+o['poses']+slot*o['psize']+o['pos']
 for i,value in enumerate((-2840,0,4540)):write(pos+i*4,value)
 e.capture_audio=True;e.audio.clear();e.run(hz);fault();assert read(w+o['next'])==4
 assert any(e.audio),'window playback silent'
 # Restart through the real menu so the page-effect fixture has no music or
 # creature sound left over from the window encounter.
 press(128)
 for _ in range(3):press(2)
 press(64);assert e.state()['mode']==0
 press(128);e.run(hz);assert e.state()['mode']==1
 assert read(w+o['music'])==4 # Original ambient-room cue after new-game LIFE.
 write(w+o['music'],-1);e.run(hz)
 e.audio.clear();e.run(hz);quiet=[x[0] for x in struct.iter_unpack('<h',e.audio)]
 assert C.c_uint16.from_address(ram+md['music_active']).value==0
 assert max(map(abs,quiet))<64,'stopped music should be quiet'

 captures=[]
 for id in (1,2,7):
  write(w+o['book'],id);write(g+o['book_page'],0);e.run(hz)
  seen=set()
  for _ in range(hz*2):
   e.run(1);bank,pixels=e.framebuffer();seen.add(e.vdp[5]&1)
   assert pixels[12*320:212*320]==shots[id][12*320:212*320],('reading host/native parity',region,id)
   if len(seen)==2:break
  assert seen=={0,1}
  e.capture(f'v15-reading-{id}-{region}.png');captures.append(id)
  if id==2:
   e.audio.clear();press(2);assert read(g+o['book_page'])==1;assert max(abs(x[0]) for x in struct.iter_unpack('<h',e.audio))>max(64,max(map(abs,quiet))*4),'page turn silent'
  press(32);assert read(w+o['book'])==-1
 e.close();return dict(region=region,window_fault=False,entrance_adlib=1,queued_ambient_cd=4,original_reading_host_native_exact=captures,both_buffers=True,page_sound=True)

def main():
 p=argparse.ArgumentParser();p.add_argument('--core',type=Path);p.add_argument('--mars',type=Path);p.add_argument('--region',default='NTSC');args=p.parse_args();(ROOT/'validation').mkdir(exist_ok=True)
 report,shots=host()
 if args.core:report['native']=native(args.core,args.mars,args.region,shots)
 report['rom_sha256']=hashlib.sha256((ROOT/'build/AITD32X.32x').read_bytes()).hexdigest();(ROOT/'validation'/f'v15-{args.region}.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
