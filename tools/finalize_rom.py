#!/usr/bin/env python3
"""Pad the cartridge, fill its ROM end and standard Mega Drive checksum."""
import sys,struct
from pathlib import Path
b=bytearray(Path(sys.argv[1]).read_bytes())
if b[0x100:0x110]!=b'SEGA SSF        ':raise SystemExit('Invalid extended SSF header')
b.extend(bytes((-len(b))%65536))
if len(b)>0xf00000:raise SystemExit('ROM overlaps reserved extended SSF pages 30/31')
struct.pack_into('>I',b,0x1a4,len(b)-1)
struct.pack_into('>H',b,0x18e,sum(struct.unpack('>'+str((len(b)-512)//2)+'H',b[512:]))&65535)
Path(sys.argv[2]).write_bytes(b)
print(f'{sys.argv[2]}: {len(b):,} bytes, checksum {struct.unpack_from(">H",b,0x18e)[0]:04X}')

