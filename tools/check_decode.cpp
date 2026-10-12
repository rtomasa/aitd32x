// SPDX-License-Identifier: GPL-2.0-or-later
// Decoder byte parity, guard boundaries and random-access camera row indexing.
#include "../src/platform/platform_api.hpp"
#include "../src/platform/pixel_words.hpp"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
static void Check(bool ok) { if(!ok) { std::fputs("decoder/row index mismatch\n",stderr);std::exit(1); } }
static void Compare(const std::vector<uint8_t> &packed,const std::vector<uint8_t> &plain,unsigned flags,bool rows=false) {
    for(unsigned input_offset:{0u,1u,2u,3u}) for(unsigned output_offset:{4u,5u,6u,7u}) {
        std::vector<uint8_t> source(packed.size()+input_offset+4),dest(plain.size()+16,0xed);
        std::memcpy(source.data()+input_offset,packed.data(),packed.size());
        Asset a={source.data()+input_offset,(uint32_t)packed.size(),(uint32_t)plain.size(),(uint16_t)(flags>=3?13:0),(uint16_t)flags};
        uint16_t offsets[200];uint8_t skips[200];
        Check(Platform_Decode(a,dest.data()+output_offset,plain.size(),rows?offsets:nullptr,rows?skips:nullptr));
        Check(!std::memcmp(dest.data()+output_offset,plain.data(),plain.size()));
        for(unsigned i=0;i<dest.size();++i) if(i<output_offset || i>=output_offset+plain.size()) Check(dest[i]==0xed);
        if(rows) for(unsigned y=0;y<200;++y) {
            unsigned token=offsets[y],skip=skips[y],pixel=y*320;
            Check(!(token&1) && token<packed.size() && skip<packed[token]);
            // Independently resume each row from its recorded token/skip.
            for(unsigned x=0;x<320;++x) {
                while(skip>=packed[token]) { skip-=packed[token];token+=2; }
                Check(packed[token+1]==plain[pixel+x]);++skip;
            }
        }
        std::fill(dest.begin(),dest.end(),0xed);
        Check(!Platform_Decode(a,dest.data()+output_offset,plain.size()-1));
        for(auto c:dest) Check(c==0xed);
    }
}
static void Framebuffer(const std::vector<uint8_t> &packed,const std::vector<uint8_t> &plain,unsigned flags,
                        unsigned width=5,unsigned height=3,unsigned stride=8) {
    // Odd image widths and overlapping LZ4 matches cross physical row padding.
    std::vector<uint16_t> dest(stride*height/2+4,0xeded);
    Asset a={packed.data(),(uint32_t)packed.size(),(uint32_t)plain.size(),2,(uint16_t)flags};
    Check(Platform_Blit(a,dest.data()+2,width,height,stride));
    const uint8_t *bytes=(const uint8_t *)(dest.data()+2);
    for(unsigned y=0;y<height;++y) for(unsigned x=0;x<stride;++x) Check(bytes[y*stride+x]==(x<width?plain[y*width+x]:0xed));
    Check(dest[0]==0xeded && dest[1]==0xeded && dest[dest.size()-2]==0xeded && dest.back()==0xeded);
}
int main() {
    // Independent word reference checks every short alignment/tail case,
    // including black, mismatched source alignment and forward overlap.
    alignas(4) uint16_t source[264],actual[264],expected[264];
    for(unsigned i=0;i<264;++i) source[i]=i%3?uint16_t(i*913):0;
    for(unsigned count=0;count<=257;++count) for(unsigned to:{2u,3u}) for(unsigned from:{0u,1u}) {
        std::fill(actual,actual+264,0xeded);std::fill(expected,expected+264,0xeded);
        for(unsigned i=0;i<count;++i) expected[to+i]=source[from+i];
        PixelCopyWords(actual+to,source+from,count);
        Check(!std::memcmp(actual,expected,sizeof(actual)));
        for(uint16_t color:{uint16_t(0),uint16_t(0x7193)}) {
            std::fill(actual,actual+264,0xeded);std::fill(expected,expected+264,0xeded);
            for(unsigned i=0;i<count;++i) expected[to+i]=color;
            PixelFillWords(actual+to,count,color);
            Check(!std::memcmp(actual,expected,sizeof(actual)));
        }
        for(unsigned offset:{2u,3u}) {
            std::memcpy(actual,source,sizeof(actual));std::memcpy(expected,source,sizeof(expected));
            for(unsigned i=0;i<count;++i) expected[to+offset+i]=expected[to+i];
            PixelCopyWords(actual+to+offset,actual+to,count);
            Check(!std::memcmp(actual,expected,sizeof(actual)));
        }
    }
    std::vector<uint8_t> raw(103);for(unsigned i=0;i<raw.size();++i) raw[i]=(uint8_t)(i*47);Compare(raw,raw,0);
    std::vector<uint8_t> packed,plain;
    for(unsigned n=1;n<=255;++n) { packed.push_back(n);packed.push_back((uint8_t)(n*37));plain.insert(plain.end(),n,(uint8_t)(n*37)); }
    Compare(packed,plain,1);
    packed.clear();plain.clear();
    for(unsigned i=0;plain.size()<64000;++i) {
        unsigned n=1+(i*113)%255;n=Min(n,64000-plain.size());uint8_t c=(uint8_t)(i*29);
        packed.push_back(n);packed.push_back(c);plain.insert(plain.end(),n,c);
    }
    Compare(packed,plain,1,true);
    // Standard raw LZ4: overlapping match, multiple length extension bytes,
    // and a literal-only tail. This fixture is independent of the importer.
    packed={0x3f,'a','b','c',3,0,255,255,12,0xf0,16};plain={'a','b','c'};
    for(unsigned i=0;i<541;++i) plain.push_back(plain[plain.size()-3]);
    for(unsigned i=0;i<31;++i) { packed.push_back((uint8_t)(i*13));plain.push_back((uint8_t)(i*13)); }
    Compare(packed,plain,2);
    // Offset-one fill must preserve zero pixels, unaligned outputs and row
    // padding when a constant match crosses an odd-width framebuffer row.
    for(uint8_t color:{uint8_t(0),uint8_t(9)}) {
        packed={0x1a,color,1,0,0};plain.assign(15,color);
        Compare(packed,plain,2);Framebuffer(packed,plain,2);
    }
    // Paired copies: odd starting/output lengths, short overlap, and the
    // large offset used by portrait frames, with independent row padding.
    for(unsigned offset:{2u,4u,6u,3200u}) {
        unsigned literals=offset+1,total=offset<3200?48:9600,match=total-literals-2;
        packed.clear();plain.clear();
        packed.push_back((Min(literals,15)<<4)|Min(match-4,15));
        auto extension=[&](unsigned length) {
            while(length>=255) { packed.push_back(255);length-=255; }
            packed.push_back(length);
        };
        if(literals>=15) extension(literals-15);
        for(unsigned i=0;i<literals;++i) { uint8_t color=i%3?uint8_t(i*13):0;plain.push_back(color);packed.push_back(color); }
        packed.push_back(offset&255);packed.push_back(offset>>8);
        if(match-4>=15) extension(match-19);
        for(unsigned i=0;i<match;++i) plain.push_back(plain[plain.size()-offset]);
        packed.insert(packed.end(),{0x20,0,9});plain.insert(plain.end(),{0,9});
        Compare(packed,plain,2);
        if(offset<3200) Framebuffer(packed,plain,2,16,3,20);
        else Framebuffer(packed,plain,2,160,60,320);
    }
    uint8_t lz_bad[]={0x10,7,0,0,0x00};
    uint8_t lz_out[16]={};
    Check(!Platform_Decode({lz_bad,sizeof(lz_bad),5,2,2},lz_out,4));
    Check(!Platform_Decode({lz_bad,sizeof(lz_bad),5,2,2},lz_out,sizeof(lz_out)));
    Check(!Platform_Decode({lz_bad,1,5,2,2},lz_out,sizeof(lz_out)));
    uint8_t lz_far[]={0x10,7,2,0};
    Check(!Platform_Decode({lz_far,sizeof(lz_far),5,2,2},lz_out,sizeof(lz_out)));
    packed={0x34,0,7,9,3,0,0x40,11,0,13,0};plain={0,7,9};
    for(unsigned i=0;i<8;++i) plain.push_back(plain[plain.size()-3]);
    plain.insert(plain.end(),{11,0,13,0});Framebuffer(packed,plain,2);
    Framebuffer(plain,plain,0);Framebuffer({14,0,1,9},std::vector<uint8_t>{0,0,0,0,0,0,0,0,0,0,0,0,0,0,9},1);
    packed={0,5,0,3,14,0,1,9};plain={0,5,0,3};plain.insert(plain.end(),14,0);plain.push_back(9);Compare(packed,plain,3);
    packed={0,5,0,3,0xf0,0};packed.insert(packed.end(),plain.begin()+4,plain.end());Compare(packed,plain,4);
    uint8_t bad[]={0,9,2,1},out[4]={};
    Check(!Platform_Decode({bad,4,4,0,1},out,4));
    Check(!Platform_Decode({bad+2,1,2,0,1},out,4));
    Check(!Platform_Decode({bad+2,2,1,0,1},out,4));
    Check(!Platform_Decode({bad+2,2,3,0,1},out,4));
    std::puts("Raw/RLE/LZ4 byte parity, overlapping matches, packed framebuffer rows, guards and all 200 indexed camera rows passed");
}
