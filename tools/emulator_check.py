#!/usr/bin/env python3
"""Headless PicoDrive smoke check of the actual cartridge, with PNG captures.

No display, BIOS download, or additional Python packages are required.
Usage: python3 tools/emulator_check.py /path/to/picodrive_libretro.so --region NTSC
"""
import argparse,ctypes as C,json,struct,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def png(path,rgb,width,height):
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    raw=b''.join(b'\0'+rgb[y*width*3:(y+1)*width*3] for y in range(height))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))

def symbol_address(name):
    """Find a symbol in the build's 32-bit, big-endian SH-2 ELF."""
    elf=(ROOT/'build/AITD32X.elf').read_bytes()
    if elf[:6]!=b'\x7fELF\x01\x02':raise RuntimeError('expected SH-2 ELF32 MSB')
    start=struct.unpack_from('>I',elf,32)[0]
    stride,count=struct.unpack_from('>2H',elf,46)
    sections=[struct.unpack_from('>10I',elf,start+i*stride) for i in range(count)]
    for section in sections:
        if section[1]!=2:continue
        strings=sections[section[6]]
        names=elf[strings[4]:strings[4]+strings[5]]
        for offset in range(section[4],section[4]+section[5],section[9]):
            n,value=struct.unpack_from('>2I',elf,offset)
            if names[n:names.find(b'\0',n)].decode()==name:return value
    raise RuntimeError('missing ELF symbol '+name)

def check_borders(pixels):
    for y in range(12):
        for x in range(320):
            value=pixels[y*320+x]
            if 2<=y<10 and 4<=x<68:
                if value not in (0,1):raise RuntimeError('FPS overlay has an unexpected palette index')
            elif value:raise RuntimeError('top border changed outside FPS overlay')
    if any(pixels[212*320:]):raise RuntimeError('bottom border is not black')
    if not any(pixels[y*320+x] for y in range(2,10) for x in range(4,68)):
        raise RuntimeError('FPS overlay is missing')

class Variable(C.Structure):
    _fields_=[('key',C.c_char_p),('value',C.c_char_p)]
class GameInfo(C.Structure):
    _fields_=[('path',C.c_char_p),('data',C.c_void_p),('size',C.c_size_t),('meta',C.c_char_p)]
ENV=C.CFUNCTYPE(C.c_bool,C.c_uint,C.c_void_p)
VIDEO=C.CFUNCTYPE(None,C.c_void_p,C.c_uint,C.c_uint,C.c_size_t)
AUDIO=C.CFUNCTYPE(None,C.c_int16,C.c_int16)
BATCH=C.CFUNCTYPE(C.c_size_t,C.c_void_p,C.c_size_t)
POLL=C.CFUNCTYPE(None)
INPUT=C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)

class Emulator:
    def __init__(self,core,region):
        self.lib=C.CDLL(str(core.resolve()))
        self.pixel_format=0;self.rgb=b'';self.raw=b'';self.width=self.height=0;self.pad=0
        self.defaults={};self.buffers={};self.capture_audio=False;self.audio=bytearray()
        self.options={'picodrive_region':b'Europe' if region=='PAL' else b'US','picodrive_input1':b'3 button pad','picodrive_input2':b'3 button pad'}
        self.system=C.create_string_buffer(str((ROOT/'build').resolve()).encode())
        def env(cmd,data):
            if cmd==10:
                self.pixel_format=C.cast(data,C.POINTER(C.c_int))[0];return True
            if cmd in (9,30,31):
                C.cast(data,C.POINTER(C.c_void_p))[0]=C.addressof(self.system);return True
            if cmd==15:
                v=C.cast(data,C.POINTER(Variable)).contents
                key=v.key.decode();value=self.options.get(key,self.defaults.get(key))
                if value is None:return False
                if key not in self.buffers:self.buffers[key]=C.create_string_buffer(value)
                v.value=C.cast(self.buffers[key],C.c_char_p);return True
            if cmd==16:
                a=C.cast(data,C.POINTER(Variable));i=0
                while a[i].key:
                    k=a[i].key.decode();v=a[i].value.decode()
                    if ';' in v:self.defaults[k]=v.split(';',1)[1].strip().split('|')[0].encode()
                    i+=1
                return True
            if cmd==17:
                C.cast(data,C.POINTER(C.c_bool))[0]=False;return True
            if cmd==52:
                C.cast(data,C.POINTER(C.c_uint))[0]=0;return True
            if cmd in (1,3,11,18,32,36):return True
            return False
        def video(data,w,h,pitch):
            if not data:return
            self.width,self.height=w,h
            self.raw=b''.join(C.string_at(data+y*pitch,w*(4 if self.pixel_format==1 else 2)) for y in range(h))
        def input_state(port,device,index,key):
            bits={4:1,5:2,6:4,7:8,0:16,8:32,1:64,3:128}
            return int(port==0 and bool(self.pad&bits.get(key,0)))
        def audio_batch(data,n):
            if self.capture_audio:self.audio.extend(C.string_at(data,n*4))
            return n
        def audio_sample(l,r):
            if self.capture_audio:self.audio.extend(struct.pack('<2h',l,r))
        self.callbacks=[ENV(env),VIDEO(video),AUDIO(audio_sample),BATCH(audio_batch),POLL(lambda:None),INPUT(input_state)]
        for name,cb in zip(['environment','video_refresh','audio_sample','audio_sample_batch','input_poll','input_state'],self.callbacks):
            f=getattr(self.lib,'retro_set_'+name);f.argtypes=[type(cb)];f(cb)
        self.lib.retro_init()
        self.lib.retro_load_game.argtypes=[C.POINTER(GameInfo)];self.lib.retro_load_game.restype=C.c_bool
        self.rom=C.create_string_buffer((ROOT/'build/AITD32X.32x').read_bytes())
        self.game=GameInfo(str((ROOT/'build/AITD32X.32x').resolve()).encode(),C.addressof(self.rom),len(self.rom)-1,None)
        if not self.lib.retro_load_game(C.byref(self.game)):raise RuntimeError('PicoDrive rejected ROM')
        self.regs=(C.c_uint16*32).in_dll(self.lib,'Pico32x')
        self.vdp=(C.c_uint16*16).from_address(C.addressof(self.regs)+64)
    def rgb_pixels(self):
        rgb=bytearray()
        step=self.width*(4 if self.pixel_format==1 else 2)
        for offset in range(0,len(self.raw),step):
            row=self.raw[offset:offset+step]
            if self.pixel_format==1:
                for b,g,r,_ in struct.iter_unpack('4B',row):rgb+=bytes((r,g,b))
            else:
                for (v,) in struct.iter_unpack('<H',row):
                    if self.pixel_format==2:rgb+=bytes((((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31))
                    else:rgb+=bytes((((v>>10)&31)*255//31,((v>>5)&31)*255//31,(v&31)*255//31))
        return bytes(rgb)
    def run(self,frames,pad=0):
        self.pad=pad
        for _ in range(frames):self.lib.retro_run()
    def comm(self):return list(self.regs[16:24])
    def state(self):
        memory=C.c_void_p.in_dll(self.lib,'Pico32xMem').value
        if not hasattr(self,'debug_address'):self.debug_address=symbol_address('_debug_state')&0x3ffff
        words=(C.c_uint16*32).from_address(memory+self.debug_address)
        values=[C.c_int32((words[i*2]<<16)|words[i*2+1]).value for i in range(16)]
        return dict(zip(['tick','camera','x','y','z','beta','mode','paused','character','sequence','render_frames','fps_tenths','tick_batch','animation_frame','animation_phase','animation_asset'],values))
    def capture(self,name):
        png(ROOT/'build'/name,self.rgb_pixels(),self.width,self.height)
    def framebuffer(self):
        # This layout is for the PicoDrive DRC_SH2 build used for validation.
        memory=C.c_void_p.in_dll(self.lib,'Pico32xMem').value
        bank=self.vdp[5]&1
        ptr=memory+0x80000+bank*0x20000
        table=list((C.c_uint16*224).from_address(ptr))
        raw=C.string_at(ptr+512,320*224)
        pixels=bytearray(len(raw));pixels[::2]=raw[1::2];pixels[1::2]=raw[::2]
        return table,bytes(pixels)
    def close(self):
        self.lib.retro_unload_game();self.lib.retro_deinit()

def main():
    from gameplay_native_check import main as gameplay_main
    gameplay_main()

if __name__=='__main__':main()
