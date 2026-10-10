#!/usr/bin/env python3
"""Original key/chest requests before and after reselecting Search, both players.

Only host-memory placement/pickup shorten travel. No battery file is touched.
The native mixer check verifies that these repeated requests do not restart FX.
"""
import ctypes as C
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
lib=C.CDLL(str(root/'build/libaitd32x.so'))
bank=C.create_string_buffer((root/'assets/bank.bin').read_bytes())
lib.host_init.argtypes=[C.c_void_p,C.c_uint]
rows=[]

def tick(pad=0):
    lib.host_tick(pad)
    assert not lib.host_world(3),[lib.host_world(f) for f in (3,4,5)]

def interaction(ticks):
    start=lib.host_sample_count()
    for n in range(120):
        tick(64 if n<ticks else 0)
        if lib.host_world(8)>=0:
            # Accept the saber offered by the original chest script.
            tick();tick(64);tick()
    return [lib.host_sample_event(i,0) for i in range(start,lib.host_sample_count())]

for character in (0,1):
    lib.host_init(bank,len(bank)-1)
    if character:tick(32);tick()
    tick(128);tick()
    lib.host_place(1,1,2,1800,0,1400,256)
    for _ in range(5):tick()
    lib.host_take(37)
    lib.host_found_life(37,1)  # Inventory Use on the original key.
    assert lib.host_world(7)==37
    # Even a brief tap emits the unlock effect before the chest starts opening.
    tap=interaction(2)
    assert tap==[3,3,3] and lib.host_variable(32)==0,(character,tap)
    first=interaction(45)
    assert first.count(3)==25 and first.count(37)==1,(character,first)
    assert lib.host_variable(32)==1 and lib.host_object(36,1)==35
    assert lib.host_object(38,6)&0x8000,'saber not taken'
    again=interaction(45)
    assert again.count(3)==25 and again.count(37)==1,(character,again)
    assert lib.host_world(7)==37
    lib.host_found_life(2,64)  # Reselect Search through the original Actions LIFE.
    assert lib.host_world(7)==2
    search=interaction(45)
    assert search.count(3)==0 and search.count(37)==1,(character,search)
    rows.append(dict(character=character,brief_key_tap=tap,
                     first_unlock_requests=first.count(3),
                     next_open_unlock_requests=again.count(3),
                     search_unlock_requests=search.count(3),
                     opening_effect_once=True,automatic_close=True))

(root/'build/key-chest.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps(rows,indent=2))
