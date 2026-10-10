// SPDX-License-Identifier: GPL-2.0-or-later
// Decoder byte parity, guard boundaries and random-access camera row indexing.
#include "../src/platform/platform_api.hpp"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
static void Check(bool ok) { if(!ok) { std::fputs("decoder/row index mismatch\n",stderr);std::exit(1); } }
static void Compare(const std::vector<uint8_t> &packed,const std::vector<uint8_t> &plain,unsigned flags,bool rows=false) {
    for(unsigned input_offset:{0u,1u}) for(unsigned output_offset:{4u,5u}) {
        std::vector<uint8_t> source(packed.size()+input_offset+4),dest(plain.size()+16,0xed);
        std::memcpy(source.data()+input_offset,packed.data(),packed.size());
        Asset a={source.data()+input_offset,(uint32_t)packed.size(),(uint32_t)plain.size(),0,(uint16_t)flags};
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
int main() {
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
    uint8_t bad[]={0,9,2,1},out[4]={};
    Check(!Platform_Decode({bad,4,4,0,1},out,4));
    Check(!Platform_Decode({bad+2,1,2,0,1},out,4));
    Check(!Platform_Decode({bad+2,2,1,0,1},out,4));
    Check(!Platform_Decode({bad+2,2,3,0,1},out,4));
    std::puts("Raw/RLE byte parity, aligned/unaligned tails, capacity guards and all 200 indexed camera rows passed");
}
