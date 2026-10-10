#!/usr/bin/env python3
"""Focused bezel, ASCII-text, overlay restoration and native input checks.

Host captures cover every panel. Optional PicoDrive checks the real title,
inventory/actions and pause in both framebuffer banks with controller input.
"""
import argparse,ctypes as C,hashlib,json,struct
from pathlib import Path
import emulator_check as ec

ROOT=Path(__file__).resolve().parents[1]
PANELS={'title':(8,131),'message':(8,158),'prompt':(24,61),
        'inventory':(16,16),'book':(8,8),'pause':(24,48),'status':(24,72)}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--core',type=Path)
    ap.add_argument('--region',choices=['NTSC','PAL'],default='NTSC')
    args=ap.parse_args()
    out=ROOT/'validation';out.mkdir(exist_ok=True)
    bank=(ROOT/'assets/bank.bin').read_bytes()
    manifest=json.loads((ROOT/'assets/manifest.json').read_text())
    assets={a['name']:bank[a['offset']:a['offset']+a['packed_size']] for a in manifest['assets']}
    def frame(pixels,name):
        data=assets['UI_'+name.upper()];w,h=struct.unpack_from('>2H',data)
        x,y=PANELS[name];y+=12
        for row in range(h):
            for col in range(w):
                if row<8 or row>=h-8 or col<8 or col>=w-8:
                    assert pixels[(y+row)*320+x+col]==data[4+row*w+col],(name,row,col)
                elif row<12 or row>=h-12 or col<12 or col>=w-12:
                    assert pixels[(y+row)*320+x+col]==0,('black text margin',name,row,col)
    def text(id):
        t=assets['TEXT'];n=struct.unpack_from('>I',t)[0]
        for i in range(n):
            key,size,off=struct.unpack_from('>2HI',t,4+i*8)
            if key==id:return t[off:off+size-1].decode('ascii')
        return ''
    assert text(2)=='(C)1992 I-MOTION/INFOGRAMES',text(2)
    report={'rom_sha256':hashlib.sha256((ROOT/'build/AITD32X.32x').read_bytes()).hexdigest(),
            'copyright':text(2),'host':[],'native':[]}
    lib=C.CDLL(str(ROOT/'build/libaitd32x.so'))
    lib.host_pixels.restype=lib.host_palette.restype=C.c_void_p
    b=C.create_string_buffer(bank);lib.host_init(b,len(bank))
    def pixels():return C.string_at(lib.host_pixels(),320*224)
    def capture(name):
        pal=list((C.c_uint16*256).from_address(lib.host_palette()))
        colors=[bytes(((v&31)*255//31,((v>>5)&31)*255//31,((v>>10)&31)*255//31)) for v in pal]
        ec.png(out/('ui-v14-host-'+name+'.png'),b''.join(colors[v] for v in pixels()),320,224)
    lib.host_tick(0);frame(pixels(),'title');capture('title')
    lib.host_tick(128);lib.host_tick(0);lib.host_clear_message();lib.host_draw_cached()
    baseline=pixels()
    # Find the original oil-lamp offer from its imported item-name record.
    objects=assets['OBJECTS'];lamp=next(i for i in range(len(objects)//52)
        if struct.unpack_from('>h',objects,i*52+10)[0]>=0
        and text(struct.unpack_from('>h',objects,i*52+10)[0])=='AN OIL LAMP')
    for kind,value,name,panel in [(0,2,'copyright','message'),(1,lamp,'pickup','prompt'),
            (2,0,'inventory','inventory'),(3,0,'actions','inventory'),
            (4,1,'book','book'),(5,0,'pause','pause'),(6,0,'death','status'),(7,0,'error','status')]:
        if kind==2:
            lib.host_take(lamp);lib.host_ui(-1,0);baseline=pixels()
        lib.host_ui(kind,value)
        if panel!='book':frame(pixels(),panel) # Original reading art/font: check_v15.py.
        capture(name)
        lib.host_ui(-1,0)
        # Inventory contents have no scene effect; closing each overlay restores
        # all covered pixels, including index-zero pixels, with normal damage.
        assert pixels()==baseline,('overlay restore',name)
        report['host'].append(name)
    if args.core:
        e=ec.Emulator(args.core,args.region)
        try:
            e.run(180)
            def world_ticks():
                mem=C.c_void_p.in_dll(e.lib,'Pico32xMem').value
                off=ec.symbol_address('_debug_state')&0x3ffff
                words=(C.c_uint16*64).from_address(mem+off)
                return words[52]<<16|words[53]
            def menu_state():
                mem=C.c_void_p.in_dll(e.lib,'Pico32xMem').value
                off=ec.symbol_address('_debug_state')&0x3ffff
                words=(C.c_uint16*64).from_address(mem+off)
                return words[36]<<16|words[37]
            def press(pad):e.run(12);e.run(12,pad);e.run(24)
            def native(name,panel):
                before=world_ticks()
                seen=set()
                for i in range(120):
                    e.run(1);bank_id=e.vdp[5]&1
                    if bank_id not in seen:
                        frame(e.framebuffer()[1],panel);seen.add(bank_id)
                    if len(seen)==2:break
                assert len(seen)==2,('missing bank',name)
                assert world_ticks()==before,('world clock ran in overlay',name)
                e.capture('ui-v14-'+args.region.lower()+'-'+name+'.png')
                report['native'].append({'panel':name,'banks':sorted(seen),'state':e.state()})
            # Title redraw on C exercises each bank while world simulation is idle.
            frame(e.framebuffer()[1],'title');title_banks={e.vdp[5]&1}
            for pad in [0]*12+[32]*12+[0]*24:
                e.run(1,pad);frame(e.framebuffer()[1],'title');title_banks.add(e.vdp[5]&1)
            assert e.state()['character']==1
            assert len(title_banks)==2
            e.capture('ui-v14-'+args.region.lower()+'-title.png')
            report['native'].append({'panel':'title','banks':sorted(title_banks)})
            press(128);assert e.state()['mode']==1
            e.run(60);press(32);assert menu_state()==1;native('inventory','inventory')
            press(64);assert menu_state()==2;native('actions','inventory')
            press(32);press(32);press(128);assert e.state()['paused']==1
            native('pause','pause')
            press(128);assert e.state()['paused']==0
        finally:e.close()
    path=out/('ui-v14-'+(args.region.lower() if args.core else 'host')+'.json')
    path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
