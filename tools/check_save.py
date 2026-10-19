#!/usr/bin/env python3
"""Focused save round-trip, journal corruption and title restore checks."""
import ctypes as C,json,struct
def checksum(data):
 value=2166136261
 for byte in data:value=((value^byte)*16777619)&0xffffffff
 return value
from pathlib import Path
r=Path(__file__).resolve().parents[1];l=C.CDLL(str(r/'build/libaitd32x.so'));l.host_sram.restype=C.c_void_p
bank=(r/'assets/bank.bin').read_bytes();b=C.create_string_buffer(bank);l.host_init(b,len(bank));ptr=l.host_sram()
def record(n):
 h=struct.unpack('>6I',C.string_at(ptr+n*16384,24));return h,C.string_at(ptr+n*16384+24,h[3]) if h[0]==0x41495444 else b''
def newest():return max(range(2),key=lambda n:record(n)[0][2])
def snapshot():return dict(character=l.host_state(8),pose=[l.host_state(i) for i in range(2,6)],world=[l.host_world(i) for i in (0,1,2,6,7,11)],objects=[[l.host_object(o,f) for f in range(26)] for o in range(292)],vars=[l.host_variable(i) for i in range(207)],items=[l.host_inventory(i) for i in range(l.host_world(6))])
report=[]
for character in (0,1):
 C.memset(ptr,0,32768);l.host_init(b,len(bank))
 l.host_startgame(character)
 for _ in range(33):l.host_tick(1)
 l.host_set_variable(54,1);l.host_set_variable(90,17);l.host_set_object(22,12,512);l.host_delete(0)
 l.host_place(1,1,5,-1800,0,-200,256);l.host_camera(1,5,5);l.host_clear_message()
 expected=snapshot();assert l.host_save()==1;old=record(0);assert old[0][3]<16360
 l.host_set_variable(90,999);l.host_set_object(22,12,0);l.host_pose(0,0,0)
 assert l.host_load()==1 and snapshot()==expected
 # Re-saving without simulation advancing must preserve every serialized byte,
 # including RNG, animation bones/phases, effects and active-object transients.
 assert l.host_save()==1;assert record(1)[1]==old[1]
 # Make a second state then corrupt its committed payload: previous save wins.
 l.host_clear_message();l.host_set_variable(90,23);assert l.host_save()==1
 bad=newest();C.c_uint8.from_address(ptr+bad*16384+32).value^=0x80
 assert l.host_load()==1 and snapshot()==expected
 # Loading from title rebinds pointers and restores the saved character/floor.
 l.host_init(b,len(bank));assert l.host_state(6)==0;assert l.host_load()==1 and snapshot()==expected
 # Invalid saves fail without modifying the existing game.
 C.memset(ptr,0,32768);before=snapshot();assert l.host_load()==0 and snapshot()==before
 # Valid outer checksum must not allow malformed LZSS to mutate the world.
 malformed=b'\0\0\0' # back-reference before any decoded byte
 header=struct.pack('>6I',0x41495444,0x53313602,1,len(malformed),checksum(malformed),old[0][5])
 C.memmove(ptr,header+malformed,len(header)+len(malformed));assert l.host_load()==0 and snapshot()==before
 report.append(dict(character=character,payload_bytes=old[0][3],roundtrip=True,all_fields_identical=True,corrupt_newest_fallback=True,title_load=True,invalid_load_unchanged=True))
(r/'build').mkdir(exist_ok=True);(r/'build/sram-host.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
