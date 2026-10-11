#!/usr/bin/env python3
"""Original death LIFE, cemetery movie, picture hold, skip and saved-game return.

Only health is set to zero to shorten combat; the production scripts choose
the death animation and sequence. SRAM is the host's private memory array.
"""
import ctypes as C
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/aitdpack'))
from startup import decode_lz4
from emulator_check import png

lib=C.CDLL(str(ROOT/'build/libaitd32x.so'))
lib.host_init.argtypes=[C.c_void_p,C.c_uint]
lib.host_pixels.restype=lib.host_palette.restype=lib.host_sram.restype=C.c_void_p
bank=(ROOT/'assets/bank.bin').read_bytes()
buffer=C.create_string_buffer(bank)
manifest=json.loads((ROOT/'assets/manifest.json').read_text())
asset=next(a for a in manifest['assets'] if a['name']=='DEATH_PICTURE')
packed=bank[asset['offset']:asset['offset']+asset['packed_size']]
picture=decode_lz4(packed,asset['unpacked_size'])
output=ROOT/'build/death-check';output.mkdir(exist_ok=True)

def tick(pad=0):
    lib.host_tick(pad)
    assert not lib.host_world(3),dict(fault=[lib.host_world(i) for i in (3,4,5)],phase=lib.host_startup(0))

def capture(name):
    pixels=C.string_at(lib.host_pixels(),320*224)
    colors=list((C.c_uint16*256).from_address(lib.host_palette()))
    rgb=[bytes(((c&31)*255//31,((c>>5)&31)*255//31,((c>>10)&31)*255//31)) for c in colors]
    png(output/(name+'.png'),b''.join(rgb[c] for c in pixels),320,224)

def sram_hash():
    return hashlib.sha256(C.string_at(lib.host_sram(),131072)).hexdigest()

rows=[]
for character in (0,1):
    lib.host_init(buffer,len(bank));lib.host_startgame(character);tick()
    assert lib.host_save(),'cannot create private saved-game fixture'
    saved=sram_hash()
    lib.host_set_variable(21,0)
    views=set();lifes=set();zombie_lifes=set();frames=0;captured=False
    while lib.host_startup(0)!=12 and frames<5000:
        tick();frames+=1
        if lib.host_startup(0)==11:
            lifes.add(lib.host_object(1,17))
            zombie_lifes.add(lib.host_object(291,17))
            views.add((lib.host_world(0),lib.host_world(2)))
            assert not lib.host_state(6),'death world still accepts gameplay menus'
            if lib.host_world(0)==6 and lib.host_world(2)==8 and lib.host_object(291,17)==557 and not captured:
                capture(f'character-{character}-drag');captured=True
    assert lib.host_startup(0)==12,('original death movie did not reach its picture',character,frames,lifes,views)
    assert captured and {39,555,556,558,554}<=lifes and 557 in zombie_lifes,('missing original movie LIFE',character,lifes,zombie_lifes)
    assert lib.host_world(0)==6 and lib.host_world(1)==6
    assert lib.host_startup(5)==12 and lib.host_startup(6)==240
    assert lib.host_world(14),'original GAME_OVER did not finish the death world'
    pixels=C.string_at(lib.host_pixels(),320*224)[12*320:212*320]
    assert pixels==picture,'death picture differs from the original ITD_RESS:12 pixels'
    capture(f'character-{character}-picture')
    world_ticks=lib.host_world(11)
    for _ in range(100):
        tick();assert lib.host_startup(0)==12 and lib.host_world(11)==world_ticks,'picture did not freeze simulation'
    tick();assert lib.host_startup(0)==13,'original picture duration was not respected'
    for _ in range(49):tick()
    assert lib.host_startup(0)==13 and lib.host_world(11)==world_ticks
    tick();assert lib.host_startup(0)==5,'death did not return to title after GAME_OVER hold'
    assert sram_hash()==saved,'death or returning to title overwrote the saved game'
    assert lib.host_load() and lib.host_variable(21)>0,'saved live game could not be restored after death'
    assert lib.host_state(6) and lib.host_world(0)==0,'restored game retained cemetery presentation state'
    # A second death exercises controller skip before the cemetery sequence.
    tick(128);tick()  # Resume the loaded pause menu with Start.
    lib.host_set_variable(21,0)
    for _ in range(20):
        tick()
        if lib.host_startup(0)==11:break
    assert lib.host_startup(0)==11
    tick(128);assert lib.host_startup(0)==5 and sram_hash()==saved
    rows.append(dict(character=character,frames_to_picture=frames,views=sorted(views),
                     player_lifes=sorted(lifes),zombie_lifes=sorted(zombie_lifes),picture_original_pixels=True,
                     picture_world_paused=True,title_return=True,skip=True,
                     saved_game_preserved=True))

report=dict(passed=True,rom_sha256=hashlib.sha256((ROOT/'build/AITD32X.32x').read_bytes()).hexdigest(),characters=rows)
(output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
