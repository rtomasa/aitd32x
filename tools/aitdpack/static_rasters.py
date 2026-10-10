"""Compile fixed, skeleton-free prop poses into native drawing commands.

The host uses the cartridge's integer projection, sorting and rasterizer.
Commands contain literal palette-color spans, not a compressed bitmap to decode.
Conditional camera masks are deliberately left for the runtime's current ZV.
"""
import ctypes as C
import json
import struct
import subprocess
from pathlib import Path

def compile_rasters(root, out, objects, levels):
    here=Path(__file__).resolve().parent
    sources=['engine/math','engine/trig','engine/actor','engine/collision',
             'engine/world','engine/life','platform/audio','platform/storage','render/render',
             'render/raster','render/worker','render/font']
    library=here/'raster_assets.so'
    subprocess.run(['c++','-std=c++17','-O2','-shared','-fPIC',
        '-DAITD_RASTER_BUILD',f'-DAITD_RESOURCE_IDS="{(out/"resource_ids.h").resolve()}"',
        *[str(root/'src'/(s+'.cpp')) for s in sources],
        str(here/'raster_assets.cpp'),'-o',str(library)],check=True)
    lib=C.CDLL(str(library));lib.raster_draw.restype=C.c_void_p
    lib.raster_key.restype=C.c_uint32
    bank=(out/'bank.bin').read_bytes();buf=C.create_string_buffer(bank)
    lib.raster_init(buf,len(bank))
    manifest=json.loads((out/'manifest.json').read_text())
    assets={a['name']:bank[a['offset']:a['offset']+a['packed_size']] for a in manifest['assets']}
    entries={};skipped=0
    for floor,(rooms,cameras) in enumerate(levels):
        for cam in range(cameras):
            data=assets[f'CAMERA_{floor}_{cam}'];views=struct.unpack_from('>I',data,20)[0]
            visible={struct.unpack_from('>H',data,views+16*i)[0] for i in range(struct.unpack_from('>H',data,18)[0])}
            for obj in objects:
                body=obj[1];room=obj[15]
                if obj[14]!=floor or room not in visible or body<0:continue
                # Source records include placed movable props too: their original
                # pose can use this path, and any later moved pose falls back.
                if struct.unpack_from('>H',assets[f'MODEL_0_{body}'],4)[0]:continue
                betas=sorted({obj[12],0,256,512,768}) if body in (25,34) else [obj[12]]
                for character in (0,1):
                    if struct.unpack_from('>H',assets[f'MODEL_{character}_{body}'],4)[0]:continue
                    for beta in betas:
                        lib.raster_pose(character,body,floor,room,*obj[8:12],beta,obj[13])
                        key=lib.raster_key();view=floor*256+cam
                        first=C.string_at(lib.raster_draw(floor,cam,room,253),64000)
                        second=C.string_at(lib.raster_draw(floor,cam,room,254),64000)
                        bounds=tuple(lib.raster_bound(i) for i in range(4))
                        commands=bytearray()
                        for y in range(200):
                            x=0
                            while x<320:
                                start=y*320+x
                                if first[start]!=second[start]:x+=1;continue
                                color=first[start];end=x+1
                                while end<320 and first[y*320+end]==color and second[y*320+end]==color:end+=1
                                commands+=struct.pack('>2H2B',start,end-x,color,0);x=end
                        # Glass with many alternating pixels can produce a large
                        # program. Keep those uncommon poses on the normal path.
                        if len(commands)>12288:skipped+=1;continue
                        program=struct.pack('>4hI',*bounds,len(commands)//6)+commands
                        if (view,key) in entries and entries[view,key]!=program:
                            raise ValueError('raster pose hash collision')
                        entries[view,key]=program
    result=bytearray(4+12*len(entries));struct.pack_into('>I',result,0,len(entries));shared={}
    for i,((view,key),program) in enumerate(sorted(entries.items())):
        if program not in shared:
            result.extend(bytes((-len(result))%4));shared[program]=len(result);result.extend(program)
        struct.pack_into('>3I',result,4+i*12,view,key,shared[program])
    report={'entries':len(entries),'distinct_programs':len(shared),'bytes':len(result),'oversized_poses_skipped':skipped,'scope':'fixed skeleton-free props; current masks applied at runtime'}
    (out/'raster_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Static raster commands:',json.dumps(report))
    return bytes(result)
