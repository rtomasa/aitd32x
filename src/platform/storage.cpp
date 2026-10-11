// SPDX-License-Identifier: GPL-2.0-or-later
#include "platform_api.hpp"
#if defined(__sh__)
#include "32x/hardware.hpp"
#endif
static const uint8_t *bank;
static uint32_t bank_size,bank_count;
static bool retain_mapping;
static unsigned mapper_page=0xffff;
void Platform_SetAssetBank(const uint8_t *data,uint32_t size) {
    bank=data; bank_size=size; bank_count=0;retain_mapping=false;mapper_page=0xffff;
    if(size>=16 && BE32(data)==0x41333258 && BE32(data+4)==2 && BE32(data+12)==size) {
        uint32_t n=BE32(data+8);
        if(n<=(size-16)/16) bank_count=n;
    }
    // Complete-game banks reserve the whole aperture. Retaining its current
    // image page avoids two 68000 handshakes on every rendered frame. Older
    // banks with fixed payloads in that slot still restore their identity map.
    if(bank_count) {
        retain_mapping=true;
        for(unsigned i=0;i<bank_count;++i) {
            const uint8_t *e=data+16+i*16;uint32_t start=BE32(e)+0x20000,bytes=BE32(e+4);
            if(!(BE16(e+14)&0x8000) && start<0x100000 && bytes && (start>=0x80000u || bytes>0x80000u-start)) retain_mapping=false;
        }
    }
}
Asset Platform_ReadAsset(unsigned id) {
    Asset a={0,0,0,0,0};
    if(id>=bank_count) return a;
    const uint8_t *e=bank+16+16*id;
    uint32_t off=BE32(e),size=BE32(e+4);
    if((off&3) || off>bank_size || size>bank_size-off) return a;
    a.data=bank+off; a.size=size; a.unpacked=BE32(e+8);
    a.type=BE16(e+12); a.flags=BE16(e+14);
    return a;
}
namespace {
constexpr unsigned BANKED=0x8000;
#if defined(__sh__)
static A32X_COLD uint16_t MapperCommand(unsigned command,unsigned value=0) {
    COMM(1)=(uint16_t)value;COMM(0)=(uint16_t)command;
    while(COMM(0)!=0x5fff) { asm volatile(".rept 24\n\tnop\n\t.endr" ::: "memory"); }
    return COMM(1);
}
#endif
static A32X_COLD Asset MapImage(const Asset &a) {
    Asset mapped=a;mapped.flags&=~BANKED;
#if defined(__sh__)
    // Only immutable images/deltas use the extension. Complete-game banks
    // retain their page; older banks restore slot 1 before world updates.
    unsigned physical=(uintptr_t)a.data-0x02000000u,offset=physical&0x7ffffu;
    if((a.type!=2 && a.type!=19) || physical<0x400000u || a.size>0x80000u-offset || physical>>19>63) return {};
    unsigned page=physical>>19;
    if(mapper_page!=page) {
        if(MapperCommand(0x5020,page)!=0x424b) return {};
        mapper_page=page;
    }
    mapped.data=(const uint8_t *)(0x22080000u+offset);
#endif
    return mapped;
}
static A32X_COLD void UnmapImage() {
#if defined(__sh__)
    if(!retain_mapping && mapper_page!=1) { MapperCommand(0x5021);mapper_page=1; }
#endif
}
static A32X_COLD __attribute__((noinline)) bool BankDecode(const Asset &a,uint8_t *dest,uint32_t capacity,uint16_t *row_offsets,uint8_t *row_skips) {
    Asset mapped=MapImage(a);if(!mapped.data) return false;
    bool ok=Platform_Decode(mapped,dest,capacity,row_offsets,row_skips);UnmapImage();return ok;
}
static A32X_COLD bool BankBlit(const Asset &a,volatile uint16_t *dest,unsigned width,unsigned height,unsigned stride) {
    Asset mapped=MapImage(a);if(!mapped.data) return false;
    bool ok=Platform_Blit(mapped,dest,width,height,stride);UnmapImage();return ok;
}
struct MemoryPixels {
    uint8_t *data;
    A32X_COLD uint8_t Read(unsigned i) const { return data[i]; }
    A32X_COLD void Write(unsigned i,uint8_t value) { data[i]=value; }
    A32X_COLD void Fill(unsigned i,unsigned count,uint8_t value) {
        while(count--) data[i++]=value;
    }
    A32X_COLD void Copy(unsigned i,unsigned offset,unsigned count) {
        // Sequential reads preserve LZ4's overlapping-match semantics.
        for(unsigned n=0;n<count;++n) { data[i]=data[i-offset];++i; }
    }
};
struct FramePixels {
    volatile uint16_t *data;unsigned width,stride;
    A32X_COLD unsigned Position(unsigned i) const { return width==stride?i:(i/width)*stride+i%width; }
    A32X_COLD uint8_t Read(unsigned i) const {
        unsigned p=Position(i);uint16_t word=data[p/2];
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
        return (uint8_t)(word>>((p&1)*8));
#else
        return (uint8_t)(word>>((1-(p&1))*8));
#endif
    }
    A32X_COLD void Write(unsigned i,uint8_t value) {
        unsigned p=Position(i);uint16_t word=data[p/2];
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
        unsigned shift=(p&1)*8;
#else
        unsigned shift=(1-(p&1))*8;
#endif
        // Byte writes of index zero are transparent on 32X framebuffers.
        data[p/2]=(uint16_t)((word&~(255u<<shift))|(unsigned(value)<<shift));
    }
    A32X_COLD void Fill(unsigned i,unsigned count,uint8_t value) {
        while(count) {
            unsigned column=i%width,n=Min(count,width-column),position=Position(i);
            count-=n;
            if(position&1) { Write(i++,value);++position;--n; }
            volatile uint16_t *words=data+position/2;uint16_t pair=(uint16_t)(value*257u);
            for(;n>=8;n-=8,i+=8) { *words++=pair;*words++=pair;*words++=pair;*words++=pair; }
            for(;n>=2;n-=2,i+=2) *words++=pair;
            if(n) Write(i++,value);
        }
    }
    A32X_COLD void Copy(unsigned i,unsigned offset,unsigned count) {
        if((width|stride|offset)&1) {
            for(unsigned n=0;n<count;++n) { uint8_t value=Read(i-offset);Write(i++,value); }
            return;
        }
        if((i&1) && count) { uint8_t value=Read(i-offset);Write(i++,value);--count; }
        while(count) {
            unsigned n=Min(count,Min(width-i%width,width-(i-offset)%width));
            volatile uint16_t *to=data+Position(i)/2;
            const volatile uint16_t *from=data+Position(i-offset)/2;
            unsigned pairs=n/2;
            // Even offsets are at least two pixels, so each paired source
            // has already been written when a short match overlaps itself.
            for(unsigned word=0;word<pairs;++word) to[word]=from[word];
            i+=pairs*2;count-=pairs*2;
            if(n&1) { uint8_t value=Read(i-offset);Write(i++,value);--count; }
        }
    }
};
static A32X_COLD bool Length(const Asset &a,unsigned &input,unsigned base,unsigned limit,unsigned &length) {
    length=base;if(length>limit) return false;
    if(base==15) {
        unsigned n;
        do {
            if(input==a.size) return false;
            n=a.data[input++];if(n>limit-length) return false;length+=n;
        } while(n==255);
    }
    return true;
}
template<class Pixels> static A32X_COLD bool LZ4(const Asset &a,Pixels &pixels) {
    unsigned input=0,output=0;
    while(input<a.size) {
        unsigned token=a.data[input++],length;
        if(!Length(a,input,token>>4,a.unpacked-output,length) || length>a.size-input) return false;
        for(unsigned n=0;n<length;++n) pixels.Write(output++,a.data[input++]);
        if(input==a.size) return output==a.unpacked;
        if(a.size-input<2) return false;
        unsigned offset=a.data[input]|(unsigned(a.data[input+1])<<8);input+=2;
        if(!offset || offset>output || a.unpacked-output<4) return false;
        if(!Length(a,input,token&15,a.unpacked-output-4,length)) return false;
        length+=4;
        // Offset-one matches are constant runs. Fill words on framebuffer
        // destinations instead of reading and modifying every repeated pixel.
        if(offset==1) { pixels.Fill(output,length,pixels.Read(output-1));output+=length; }
        else { pixels.Copy(output,offset,length);output+=length; }
    }
    return output==a.unpacked;
}
static A32X_COLD __attribute__((noinline)) bool Packed(const Asset &a,uint8_t *dest,uint32_t capacity,uint16_t *row_offsets,uint8_t *row_skips) {
    if(row_offsets || row_skips) return false;
    if(a.flags==2) { MemoryPixels pixels={dest};return LZ4(a,pixels); }
    if((a.flags==3 || a.flags==4) && a.type==13 && a.size>=4 && a.unpacked>=4) {
        unsigned width=BE16(a.data),height=BE16(a.data+2);
        if(width*height!=a.unpacked-4) return false;
        Asset pixels={a.data+4,a.size-4,a.unpacked-4,a.type,(uint16_t)(a.flags==3?1:2)};
        if(!Platform_Decode(pixels,dest+4,capacity-4)) return false;
        for(unsigned i=0;i<4;++i) dest[i]=a.data[i];
        return true;
    }
    return false;
}
}
A32X_COLD Asset Platform_MapImage(const Asset &a) {
    if(a.flags!=BANKED || a.type!=2 || a.size!=a.unpacked) return {};
    return MapImage(a);
}
A32X_COLD void Platform_UnmapImage() { UnmapImage(); }
A32X_COLD bool Platform_ApplyDelta(const Asset &source,uint8_t *dest,uint32_t capacity,Rect &damage) {
    if(!dest || source.type!=19 || source.unpacked!=GAME_WIDTH*GAME_HEIGHT || capacity<source.unpacked || source.size<4 || (source.flags!=0 && source.flags!=BANKED)) return false;
    Asset a=source;
    if(source.flags&BANKED) { a=MapImage(source);if(!a.data) return false; }
    unsigned count=BE32Aligned(a.data);bool ok=count<=(a.size-4)/6 && 4+count*6==a.size;
    // Validate the complete command list before modifying the retained image.
    for(unsigned i=0;ok && i<count;++i) {
        const uint8_t *p=a.data+4+i*6;unsigned start=BE16Aligned(p),length=BE16Aligned(p+2);
        ok=length && start<source.unpacked && length<=source.unpacked-start && p[5]==0;
    }
    if(ok) for(unsigned i=0;i<count;++i) {
        const uint8_t *p=a.data+4+i*6;unsigned start=BE16Aligned(p),length=BE16Aligned(p+2);
        MemoryPixels pixels={dest};pixels.Fill(start,length,p[4]);
        unsigned end=start+length-1,first=start/GAME_WIDTH,last=end/GAME_WIDTH;
        int left=first==last?start%GAME_WIDTH:0,right=first==last?end%GAME_WIDTH:GAME_WIDTH-1;
        damage={Min(damage.x1,left&~1),Min(damage.y1,first),Max(damage.x2,right|1),Max(damage.y2,last)};
    }
    if(source.flags&BANKED) UnmapImage();
    return ok;
}
bool Platform_Decode(const Asset &a,uint8_t *dest,uint32_t capacity,uint16_t *row_offsets,uint8_t *row_skips) {
    if(!a.data || a.unpacked>capacity) return false;
    if(a.flags&BANKED) return BankDecode(a,dest,capacity,row_offsets,row_skips);
    if(a.flags>1) return Packed(a,dest,capacity,row_offsets,row_skips);
    if(a.flags==0) {
        if(a.unpacked!=a.size) return false;
        uint32_t i=0;
        if(!(((uintptr_t)a.data|(uintptr_t)dest)&1)) {
            const uint16_t *source=(const uint16_t *)a.data;
            uint16_t *target=(uint16_t *)dest;
            for(;i+8<=a.size;i+=8) {
                *target++=*source++;*target++=*source++;
                *target++=*source++;*target++=*source++;
            }
            for(;i+2<=a.size;i+=2) *target++=*source++;
        }
        for(;i<a.size;++i) dest[i]=a.data[i];
        return true;
    }
    if(a.flags!=1 || (a.size&1)) return false;
    if((row_offsets || row_skips) && (!row_offsets || !row_skips || a.size>65535 || a.unpacked!=GAME_WIDTH*GAME_HEIGHT)) return false;
    uint32_t out=0;
    unsigned row=0;
    for(uint32_t i=0;i<a.size;i+=2) {
        unsigned n=a.data[i];
        if(!n || n>a.unpacked-out) return false;
        // Index each camera row as it is decoded. A row can begin inside a
        // run; retain that run's byte offset and the number of skipped pixels.
        if(row_offsets) while(row<GAME_HEIGHT && row*GAME_WIDTH<out+n) {
            row_offsets[row]=(uint16_t)i;row_skips[row]=(uint8_t)(row*GAME_WIDTH-out);++row;
        }
        uint8_t color=a.data[i+1],*p=dest+out;out+=n;
        if((uintptr_t)p&1) { *p++=color;--n; }
        uint16_t pair=(uint16_t)(color*257u),*words=(uint16_t *)p;
        for(;n>=8;n-=8) { *words++=pair;*words++=pair;*words++=pair;*words++=pair; }
        for(;n>=2;n-=2) *words++=pair;
        if(n) *(uint8_t *)words=color;
    }
    return out==a.unpacked;
}
A32X_COLD bool Platform_Blit(const Asset &a,volatile uint16_t *dest,unsigned width,unsigned height,unsigned stride) {
    if(!a.data || !dest || !width || (stride&1) || width>stride || width>GAME_WIDTH || height>GAME_HEIGHT || a.unpacked!=width*height) return false;
    if(a.flags&BANKED) return BankBlit(a,dest,width,height,stride);
    FramePixels pixels={dest,width,stride};
    if(a.flags==2) return LZ4(a,pixels);
    if(a.flags==0) {
        if(a.size!=a.unpacked) return false;
        if(!(width&1) && !((uintptr_t)a.data&1)) {
            const uint16_t *source=(const uint16_t *)a.data;
            for(unsigned row=0;row<height;++row) {
                volatile uint16_t *out=dest+row*(stride/2);unsigned col=0;
                for(;col+4<=width/2;col+=4) { *out++=*source++;*out++=*source++;*out++=*source++;*out++=*source++; }
                for(;col<width/2;++col) *out++=*source++;
            }
        } else for(unsigned i=0;i<a.size;++i) pixels.Write(i,a.data[i]);
        return true;
    }
    if(a.flags!=1 || (a.size&1)) return false;
    unsigned output=0;
    for(unsigned i=0;i<a.size;i+=2) {
        unsigned n=a.data[i];if(!n || n>a.unpacked-output) return false;
        uint8_t color=a.data[i+1];
        pixels.Fill(output,n,color);output+=n;
    }
    return output==a.unpacked;
}
