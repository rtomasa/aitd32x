#!/usr/bin/env python3
"""AITD1 -> aligned, pointer-free, big-endian AITD32X assets.

Format interpretation follows yaz0r/FITD 543e22b (pak/hqr/floor/main).
The PKWARE decoder is vendored from FITD; it only runs on the host.
"""
import argparse
import ctypes
import hashlib
import json
import struct
import subprocess
import zlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = 'yaz0r/FITD@543e22bc78b64405537ae545ecd382dcdf2c12b2'
U16 = lambda b, o=0: struct.unpack_from('<H', b, o)[0]
U32 = lambda b, o=0: struct.unpack_from('<I', b, o)[0]

class Pak:
    def __init__(self, path, decoder):
        self.path, self.decoder = path, decoder
        self.b = path.read_bytes()
        if len(self.b) < 8:
            raise ValueError(f'{path}: truncated directory')
        end = U32(self.b, 4)
        if end < 8 or end % 4 or end > len(self.b):
            raise ValueError(f'{path}: invalid directory size')
        self.offsets = [U32(self.b, i) for i in range(4, end, 4)]
        if self.offsets != sorted(set(self.offsets)):
            raise ValueError(f'{path}: invalid resource offsets')

    def __len__(self):
        return len(self.offsets)

    def get(self, index):
        if not 0 <= index < len(self):
            raise ValueError(f'{self.path}: missing entry {index}')
        o = self.offsets[index]
        extra = U32(self.b, o)
        if extra and extra < 4:
            raise ValueError('invalid extra descriptor')
        o += extra if extra else 4
        packed, size, mode, flags, skip = struct.unpack_from('<IIBBH', self.b, o)
        o += 12 + skip
        limit = self.offsets[index+1] if index+1 < len(self) else len(self.b)
        if o + packed > limit or size > 8 * 1024 * 1024:
            raise ValueError(f'{self.path}:{index}: invalid resource length')
        data = self.b[o:o+packed]
        if mode == 0:
            result = data
        elif mode == 1:
            dst = ctypes.create_string_buffer(size)
            # FITD's original decoder requires lookahead beyond the input.
            src = ctypes.create_string_buffer(data + bytes(32))
            self.decoder.PAK_explode(src, dst, packed, size, flags)
            result = dst.raw
        elif mode == 4:
            result = zlib.decompress(data, -15)
        else:
            raise ValueError(f'{self.path}:{index}: unknown compression {mode}')
        if len(result) != (packed if mode == 0 else size):
            raise ValueError('decoded resource size mismatch')
        return result

class Writer:
    def __init__(self, initial=b''):
        self.b = bytearray(initial)
    def align(self):
        self.b.extend(bytes((-len(self.b)) % 4))
    def add(self, data):
        self.align()
        o = len(self.b)
        self.b.extend(data)
        return o
    def patch(self, o, fmt, *values):
        struct.pack_into('>'+fmt, self.b, o, *values)

def native_text(data, original_font=False):
    entries=[]
    for match in re.finditer(rb'@(\d+):([^\x00-\x1f]*)',data):
        if original_font:
            # Proportional text uses the source's glyph indices directly:
            # A9 is the small copyright sign and FA the I-Motion separator.
            value=match[2]
        else:
            source=match[2].replace(b'\xa9',b'(C)').replace(b'\xfa',b'-')
            value=source.decode('cp437').upper().encode('ascii','replace')
        entries.append((int(match[1]),value+b'\0'))
    entries.sort();words=Writer(bytes(4+8*len(entries)));words.patch(0,'I',len(entries))
    for i,(id,value) in enumerate(entries):words.patch(4+i*8,'2HI',id,len(value),words.add(value))
    return bytes(words.b)

def offsets(data):
    result = []
    for i in range(U32(data)//4):
        o = U32(data, 4*i)
        if not 0 < o < len(data) or (result and o <= result[-1]):
            break
        result.append(o)
    return result

def native_room(data):
    hard, scenario, wx, wy, wz, nc = struct.unpack_from('<2H3hH', data)
    nh, ns = U16(data, hard), U16(data, scenario)
    w = Writer(bytes(32))
    co = w.add(struct.pack('>'+str(nc)+'H', *struct.unpack_from('<'+str(nc)+'H', data, 12)))
    def boxes(o, n):
        return b''.join(struct.pack('>6h2H', *struct.unpack_from('<6h2H', data, o+2+16*i)) for i in range(n))
    ho, so = w.add(boxes(hard, nh)), w.add(boxes(scenario, ns))
    w.patch(0, '3h3H3I', wx, wy, wz, nc, nh, ns, co, ho, so)
    return bytes(w.b)

def poly_spans(polygons):
    """Compile foreground polygons into clipped, unioned scanline runs."""
    rows = [[] for _ in range(200)]
    for pts in polygons:
        for y in range(200):
            xs = []
            for (x1,y1),(x2,y2) in zip(pts, pts[1:]+pts[:1]):
                if min(y1,y2) <= y < max(y1,y2):
                    xs.append(x1 + (y-y1)*(x2-x1)/(y2-y1))
            xs.sort()
            for a,b in zip(xs[::2],xs[1::2]):
                a,b = max(0,int(a)), min(319,int(b))
                if a <= b:
                    rows[y].append((a,b))
    runs = []
    for y,row in enumerate(rows):
        merged = []
        for a,b in sorted(row):
            if merged and a <= merged[-1][1]+1:
                merged[-1] = (merged[-1][0],max(b,merged[-1][1]))
            else:
                merged.append((a,b))
        runs.extend((y,a,b) for a,b in merged)
    return b''.join(struct.pack('>3H',*r) for r in runs), len(runs)

def native_camera(data):
    h = struct.unpack_from('<9hH',data)
    w = Writer(bytes(24))
    vo = w.add(bytes(h[9]*16))
    for i in range(h[9]):
        room, mo, zo = struct.unpack_from('<3H', data, 20+12*i)
        nz = U16(data,zo)
        p = zo+2
        zones = bytearray()
        for _ in range(nz):
            n = U16(data,p); p += 2
            zones += struct.pack('>H',n)
            for _ in range(n):
                zones += struct.pack('>2h',*struct.unpack_from('<2h',data,p)); p += 4
        zoff = w.add(zones)
        nm = U16(data,mo)
        maskoff = w.add(bytes(nm*12))
        p = mo+2
        for j in range(nm):
            nt, po = struct.unpack_from('<2H',data,p)
            tests = b''.join(struct.pack('>4h',*struct.unpack_from('<4h',data,p+4+8*k)) for k in range(nt))
            to = w.add(tests)
            pp = mo+po
            np = U16(data,pp); pp += 2
            polys = []
            for _ in range(np):
                n = U16(data,pp); pp += 2
                pts = [struct.unpack_from('<2h',data,pp+4*k) for k in range(n)]
                pp += 4*n
                polys.append(pts)
            spans, nr = poly_spans(polys)
            sp = w.add(spans)
            w.patch(maskoff+j*12,'2H2I',nt,nr,to,sp)
            p += 4+8*nt
        w.patch(vo+i*16,'4H2I',room,nz,nm,0,zoff,maskoff)
    w.patch(0,'9hHI',*h,vo)
    return bytes(w.b)

def native_model(b):
    flags = U16(b)
    if flags & 12:
        raise ValueError('AITD2/3 or tortue body is outside this importer')
    p = 16+U16(b,14)
    nv = U16(b,p); p+=2
    vertices = b[p:p+nv*6]; p+=nv*6
    groups, order = [], []
    ng = 0
    if flags & 2:
        ng = U16(b,p); p+=2
        order = [U16(b,p+2*i)//16 for i in range(ng)];p+=ng*2
        for _ in range(ng):
            start,n,base,org,num,typ,x,y,z = struct.unpack_from('<3h2b4h',b,p);p+=16
            if start % 6 or base % 6 or start//6+n > nv or base//6 >= nv:
                raise ValueError('invalid bone vertex range')
            groups.append(struct.pack('>3H2b4h',start//6,n,base//6,org,num,typ,x,y,z))
        if sorted(order) != list(range(ng)):
            raise ValueError('invalid bone order')
    np = U16(b,p);p+=2
    prims = []
    for _ in range(np):
        typ=b[p];p+=1
        size=0
        if typ == 1:
            n,material,col=b[p:p+3];p+=3
        elif typ in (0,2,3,6,7):
            material,col,_=b[p:p+3];p+=3;n=2 if typ==0 else 1
            if typ==3:
                size=U16(b,p);p+=2
        else:
            raise ValueError(f'unsupported AITD1 primitive {typ}')
        ids=[U16(b,p+2*i)//6 for i in range(n)];p+=2*n
        if n > 32 or max(ids) >= nv:
            raise ValueError('primitive exceeds renderer limits')
        prims.append(struct.pack('>4BH'+str(n)+'H',typ,n,col,material,size,*ids))
    w=Writer(bytes(36))
    verts=w.add(b''.join(struct.pack('>3h',*struct.unpack_from('<3h',vertices,i*6)) for i in range(nv)))
    go=w.add(b''.join(groups)); oo=w.add(struct.pack('>'+str(ng)+'H',*order)); po=w.add(bytes(np*4))
    for i,primitive in enumerate(prims):w.patch(po+i*4,'I',w.add(primitive))
    w.patch(0,'4H6h4I',flags,nv,ng,np,*struct.unpack_from('<6h',b,2),verts,go,oo,po)
    return bytes(w.b)

def native_animation(b):
    nf,ng=struct.unpack_from('<2H',b)
    if len(b) != 4+nf*(8+ng*8):
        raise ValueError('unsupported animation format')
    return b''.join(struct.pack('>h',v) for (v,) in struct.iter_unpack('<h',b))

def rle(b):
    out=bytearray();i=0
    while i<len(b):
        j=i+1
        while j<len(b) and b[j]==b[i] and j-i<255:j+=1
        out.extend((j-i,b[i]));i=j
    return bytes(out)

def native_panel(gfx, width, height, remap=None):
    """Original ITD_RESS:4 corners, tiled rails and title plaque (FITD aitdBox).

    Precompose the original layout before lossless encoding. Runtime overlays
    need no additional bitmap buffer. Small panels crop the rails to fit.
    """
    pixels=bytearray(width*height)
    def sprite(index, x, y, opaque=False):
        off=U16(gfx,index*2)
        w,h=struct.unpack_from('<2H',gfx,off+4)
        data=gfx[off+8:off+8+w*h]
        if len(data)!=w*h:raise ValueError('truncated bezel sprite')
        for row in range(h):
            for col in range(w):
                c=data[row*w+col]
                if (c or opaque) and 0<=x+col<width and 0<=y+row<height:
                    pixels[(y+row)*width+x+col]=c
    # Rails first, then corners conceal the seams; plaque is centered last.
    for x in range(0,width,20):
        sprite(4,x,0);sprite(5,x,height-8)
    for y in range(0,height,20):
        sprite(6,0,y);sprite(7,width-8,y)
    for i,x,y in [(0,0,0),(1,width-20,0),(2,0,height-20),(3,width-20,height-20)]:
        sprite(i,x,y,True)
    sprite(8,(width-44)//2,height-8,True)
    if remap is not None:pixels=bytearray(remap[c] for c in pixels)
    return struct.pack('>2H',width,height)+pixels

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('game',type=Path,help='original INDARK directory')
    ap.add_argument('--out',type=Path,default=ROOT/'assets')
    args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    here=Path(__file__).resolve().parent
    so=here/'fitd_unpack.so'
    if not so.exists() or so.stat().st_mtime < (here/'fitd_unpack.c').stat().st_mtime:
        subprocess.run(['cc','-O2','-shared','-fPIC',str(here/'fitd_unpack.c'),'-o',str(so)],check=True)
    decoder=ctypes.CDLL(str(so))
    decoder.PAK_explode.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint,ctypes.c_ushort]
    paks={}
    def get(name,index):
        if name not in paks:paks[name]=Pak(args.game/(name+'.PAK'),decoder)
        return paks[name].get(index)
    assets=[]
    def add(name,typ,data,compress=False):
        packed=rle(data) if compress else data
        use=compress and len(packed)<len(data)
        assets.append((name,typ,packed if use else data,len(data),int(use)))
        return len(assets)-1
    palette=get('ITD_RESS',3)
    if len(palette)!=768:raise ValueError('invalid game palette')
    add('GAME_PALETTE',1,b''.join(struct.pack('>H',(r>>3)|((g>>3)<<5)|((b>>3)<<10)) for r,g,b in zip(palette[::3],palette[1::3],palette[2::3])))
    title=get('ITD_RESS',13)
    if len(title)!=64770 or title[:2]!=b'VP':raise ValueError('invalid title')
    add('TITLE_PALETTE',1,b''.join(struct.pack('>H',(r>>3)|((g>>3)<<5)|((b>>3)<<10)) for r,g,b in zip(title[2:770:3],title[3:770:3],title[4:770:3])))
    from startup import lz4_block,compile_startup,build_bank,BANK_PHYSICAL_BASE,BANK_EXTRA_ORIGIN
    title_pixels=title[770:]
    assets.append(('TITLE',2,lz4_block(title_pixels),len(title_pixels),2))
    levels=[]
    for floor in (0,1):
        rawrooms,rawcams=get(f'ETAGE{floor:02d}',0),get(f'ETAGE{floor:02d}',1)
        rooms,cams=offsets(rawrooms),offsets(rawcams);levels.append((len(rooms),len(cams)))
        for i,o in enumerate(rooms):add(f'ROOM_{floor}_{i}',4,native_room(rawrooms[o:]))
        for i,o in enumerate(cams):
            add(f'CAMERA_{floor}_{i}',3,native_camera(rawcams[o:]))
            bg=get(f'CAMERA{floor:02d}',i)
            if len(bg)!=64000:raise ValueError('background is not 320x200')
            # The native cartridge has room for raw camera images. Direct
            # aligned copies avoid RLE expansion/indexing on every view change.
            add(f'BACKGROUND_{floor}_{i}',2,bg)
            (args.out/f'camera{floor}_{i}.raw').write_bytes(bg)
    objects=(args.game/'OBJETS.ITD').read_bytes()
    count=U16(objects)
    if len(objects)!=2+count*52:raise ValueError('unsupported object record size')
    objs=[struct.unpack_from('<26h',objects,2+i*52) for i in range(count)]
    defines_data=(args.game/'DEFINES.ITD').read_bytes()
    defines=struct.unpack('>'+str(len(defines_data)//2)+'h',defines_data)
    player=defines[7]
    model_count,animation_count=272,305
    for char,bodybank,animbank in [(0,'LISTBODY','LISTANIM'),(1,'LISTBOD2','LISTANI2')]:
        for i in range(model_count):
            native=native_model(get(bodybank,i))
            nv,ng,np=struct.unpack_from('>3H',native,2)
            if nv>384 or ng>40 or np>384:raise ValueError(f'{bodybank}:{i} exceeds fixed actor workspace')
            add(f'MODEL_{char}_{i}',5,native)
        for i in range(animation_count):
            native=native_animation(get(animbank,i))
            if U16(get(animbank,i),2)>40:raise ValueError('animation exceeds fixed bone workspace')
            add(f'ANIM_{char}_{i}',6,native)
    add('OBJECTS',7,b''.join(struct.pack('>26h',*o) for o in objs))
    for name,count,typ in [('LISTLIFE',563,8),('LISTTRAK',45,10)]:
        for i in range(count):
            d=get(name,i)
            add(('LIFE' if typ==8 else 'TRACK')+f'_{i}',typ,b''.join(struct.pack('>h',v) for (v,) in struct.iter_unpack('<h',d)))
    variables=(args.game/'VARS.ITD').read_bytes()
    add('VARS_INITIAL',11,b''.join(struct.pack('>h',v) for (v,) in struct.iter_unpack('<h',variables)))
    add('DEFINES_INITIAL',11,defines_data)
    # Gameplay and presentation share the original font's case and glyph IDs.
    # The two directory IDs remain stable and their identical payload deduplicates.
    add('TEXT',12,native_text(get('ENGLISH',0),original_font=True))
    book_count=len(paks['ENGLISH'])-1
    from books import compile_books
    books,reading_assets,reading_report=compile_books(get,book_count)
    for i,data in enumerate(books):add(f'BOOK_{i+1}',17,data)
    (args.out/'reading_manifest.json').write_text(json.dumps(reading_report,indent=2)+'\n')
    spawn=objs[player]
    add('PLAYER_SPAWN',9,struct.pack('>8h',*spawn[8:14],spawn[1],spawn[19]))
    bezel=get('ITD_RESS',4)
    title_palette=get('ITD_RESS',13)[2:770]
    # Keep the title image's own palette, matching gold to its nearest colors.
    colors=list(zip(*[iter(title_palette)]*3))
    remap=[0]+[min(range(1,256),key=lambda j:sum((palette[i*3+k]-colors[j][k])**2 for k in range(3))) for i in range(1,256)]
    for name,width,height in [('TITLE',304,68),('MESSAGE',304,58),('PROMPT',272,82),('INVENTORY',288,177),('BOOK',2,2),('PAUSE',272,132),('STATUS',272,66)]:
        panel=struct.pack('>2H',2,2)+bytes(4) if name=='BOOK' else native_panel(bezel,width,height,remap if name=='TITLE' else None)
        # Preserve existing gameplay overlays' direct aligned-copy fast path.
        add('UI_'+name,13,panel)
    # Write a complete bootstrap bank/header before compiling the host renderer.
    # The final native command asset replaces this placeholder at the same ID.
    raster_id=add('STATIC_RASTERS',14,struct.pack('>I',0))
    sys.path.insert(0,str(ROOT/'tools/audio'))
    from compile_audio import compile_audio
    audio,audio_report=compile_audio(get,paks)
    for name,typ,data in audio:add(name,typ,data)
    for name,typ,data in reading_assets:
        if name.startswith('READ_BACKGROUND_'):
            assets.append((name,typ,lz4_block(data),len(data),2))
        else:add(name,typ,data)
    (args.out/'audio_manifest.json').write_text(json.dumps(audio_report,indent=2)+'\n')
    # Appending preserves every existing resource ID and the save fingerprint.
    startup_assets,startup_levels,startup_report=compile_startup(get,defines_data,native_model,native_room,native_camera,offsets,native_panel,rle,native_text)
    assets.extend(startup_assets)
    gameplay_levels=list(levels)
    levels.extend([startup_levels.get(floor,(0,0)) for floor in range(2,8)])
    startup_report['existing_presentation_compression']=[dict(name=name,packed_bytes=len(data),unpacked_bytes=usize,flags=flags)
        for name,typ,data,usize,flags in assets if name=='TITLE' or name.startswith('UI_') or name.startswith('READ_BACKGROUND_')]
    (args.out/'startup_manifest.json').write_text(json.dumps(startup_report,indent=2)+'\n')
    def write_bank():
        full,fixed,extra,manifest,layout=build_bank(assets)
        for name,data in [('bank.bin',full),('bank-main.bin',fixed),('bank-extra.bin',extra)]:
            (args.out/name).write_bytes(data)
        return full,manifest,dict(layout,main_sha256=hashlib.sha256(fixed).hexdigest(),extra_sha256=hashlib.sha256(extra).hexdigest())
    bank,manifest,bank_layout=write_bank()
    header=['/* Generated by aitdpack. Never edit. */','#pragma once',f'#define A32X_ASSET_COUNT {len(assets)}','#define A32X_BANK_VERSION 2',f'#define A32X_SAVE_FINGERPRINT 0x{hashlib.sha256(objects+variables+defines_data+paks["LISTLIFE"].b+paks["LISTTRAK"].b).hexdigest()[:8]}u',f'#define A32X_SOUND_COUNT {len(paks["LISTSAMP"])}',f'#define A32X_MUSIC_COUNT {len(paks["LISTMUS"])}',f'#define A32X_OBJECT_COUNT {len(objs)}',f'#define A32X_VAR_COUNT {len(variables)//2}',f'#define A32X_MODEL_COUNT {model_count}',f'#define A32X_ANIMATION_COUNT {animation_count}','#define A32X_LIFE_COUNT 563','#define A32X_TRACK_COUNT 45',f'#define A32X_FLOOR_COUNT {len(levels)}',f'#define A32X_BOOK_COUNT {book_count}',f'#define A32X_CAMERA_COUNT {levels[0][1]}',f'#define A32X_ROOM_COUNT {levels[0][0]}','enum AssetId {']
    header += [f'    AS_{name} = {i},' for i,(name,*_) in enumerate(assets)]
    header += ['};']
    header += [f'#define A32X_BANK_PHYSICAL_BASE 0x{BANK_PHYSICAL_BASE:x}u',f'#define A32X_BANK_EXTRA_ORIGIN 0x{BANK_EXTRA_ORIGIN:x}u']
    available={name for name,*_ in assets}
    def table(label,names):header.append('static const unsigned short '+label+'[] = {'+','.join('AS_'+n if n in available else '65535' for n in names)+'};')
    for floor,(nr,nc) in enumerate(levels):
        if not nr:continue
        table(f'room_assets_{floor}',[f'ROOM_{floor}_{i}' for i in range(nr)])
        table(f'camera_assets_{floor}',[f'CAMERA_{floor}_{i}' for i in range(nc)])
        table(f'background_assets_{floor}',[f'BACKGROUND_{floor}_{i}' for i in range(nc)])
    header += ['#define AS_ROOM_0 AS_ROOM_0_0','#define camera_assets camera_assets_0','#define background_assets background_assets_0']
    header += ['static const unsigned short room_counts[]={'+','.join(str(x[0]) for x in levels)+'};','static const unsigned short camera_counts[]={'+','.join(str(x[1]) for x in levels)+'};']
    for label,base in [('floor_rooms','room_assets'),('floor_cameras','camera_assets'),('floor_backgrounds','background_assets')]:
        header.append('static const unsigned short *const '+label+'[]={'+','.join(f'{base}_{floor}' if nr else '0' for floor,(nr,nc) in enumerate(levels))+'};')
    for char in (0,1):
        table(f'model_assets_{char}',[f'MODEL_{char}_{i}' for i in range(model_count)])
        table(f'animation_assets_{char}',[f'ANIM_{char}_{i}' for i in range(animation_count)])
    header += ['static const unsigned short *const model_assets[]={model_assets_0,model_assets_1};','static const unsigned short *const animation_assets[]={animation_assets_0,animation_assets_1};']
    table('sound_assets',[f'SOUND_{i}' for i in range(len(paks['LISTSAMP']))])
    table('music_assets',[f'MUSIC_{i}' for i in range(len(paks['LISTMUS']))])
    table('book_assets',[f'BOOK_{i+1}' for i in range(book_count)])
    table('life_assets',[f'LIFE_{i}' for i in range(563)]);table('track_assets',[f'TRACK_{i}' for i in range(45)])
    table('player_model_assets',['MODEL_0_12','MODEL_1_12'])
    for label,id in [('walk',254),('idle',4),('run',255),('back',256),('right',257),('left',258)]:table(f'player_{label}_assets',[f'ANIM_0_{id}',f'ANIM_1_{id}'])
    (args.out/'resource_ids.h').write_text('\n'.join(header)+'\n')
    input_hashes={n+'.PAK':hashlib.sha256(p.b).hexdigest() for n,p in paks.items()}
    input_hashes.update({'OBJETS.ITD':hashlib.sha256(objects).hexdigest(),'DEFINES.ITD':hashlib.sha256(defines_data).hexdigest(),'VARS.ITD':hashlib.sha256(variables).hexdigest()})
    (args.out/'manifest.json').write_text(json.dumps(dict(version=2,levels=levels,reference=REFERENCE,bank_sha256=hashlib.sha256(bank).hexdigest(),bank_layout=bank_layout,rooms=sum(x[0] for x in levels),cameras=sum(x[1] for x in levels),player_object=player,assets=manifest,input_sha256=input_hashes),indent=2)+'\n')
    from static_rasters import compile_rasters
    # Introduction scenery is decoded once and not baked into gameplay caches.
    raster=compile_rasters(ROOT,args.out,objs,gameplay_levels)
    name,typ,*_=assets[raster_id];assets[raster_id]=(name,typ,raster,len(raster),0)
    bank,manifest,bank_layout=write_bank()
    metadata=json.loads((args.out/'manifest.json').read_text())
    metadata.update(bank_sha256=hashlib.sha256(bank).hexdigest(),bank_layout=bank_layout,assets=manifest)
    (args.out/'manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
    startup_report['bank_layout']=bank_layout
    (args.out/'startup_manifest.json').write_text(json.dumps(startup_report,indent=2)+'\n')
    print(f'{len(assets)} native assets; floors {levels}; {len(bank):,} bank bytes; {bank_layout["fixed_bytes"]:,} fixed + {bank_layout["extra_bytes"]:,} extra; player object {player}')

if __name__=='__main__':
    main()
