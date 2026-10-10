// SPDX-License-Identifier: GPL-2.0-or-later
#include "book.hpp"
#include "../platform/platform_api.hpp"
#include "../../assets/resource_ids.h"
A32X_COLD unsigned Book_Pages(int book) {
    if(book<=0 || book>A32X_BOOK_COUNT) return 0;
    Asset a=Platform_ReadAsset(book_assets[book-1]);return a.type==17?BE16(a.data+2):0;
}
static A32X_COLD void Glyph(Renderer &r,const uint8_t *font,int x,int y,unsigned c) {
    unsigned first=font[0],height=font[2],stride=font[3]?font[3]:font[4]|(font[5]<<8);
    if(c<first) return;
    unsigned glyph=BE16(font+BE16(font+6)+(c-first)*2),width=glyph>>12,bit=glyph&4095;
    const uint8_t *pixels=font+8+(bit>>3);bit&=7;
    for(unsigned row=0;row<height;++row) {
        for(unsigned col=0;col<width;++col) if(pixels[(bit+col)>>3]&(128>>((bit+col)&7))) r.Span(y+row,x+col,x+col,26);
        pixels+=stride;
    }
}
static A32X_COLD void Sprite(Renderer &r,unsigned id,int x,int y) {
    Asset a=Platform_ReadAsset(id);unsigned width=BE16(a.data),height=BE16(a.data+2);const uint8_t *p=a.data+4;
    for(unsigned row=0;row<height;++row) for(unsigned col=0;col<width;++col) { unsigned color=*p++;if(color) r.Span(y+row,x+col,x+col,color); }
}
A32X_COLD void Book_Draw(Renderer &r,int book,unsigned page) {
    unsigned count=Book_Pages(book);if(!count) return;page=Min(page,count-1);
    Asset a=Platform_ReadAsset(book_assets[book-1]);unsigned kind=BE16(a.data);
    Asset bg=Platform_ReadAsset(AS_READ_BACKGROUND_0+Min(kind,2));const uint16_t *pixels=(const uint16_t *)bg.data;
    for(unsigned i=0;i<32000;i+=4) { r.target[i]=pixels[i];r.target[i+1]=pixels[i+1];r.target[i+2]=pixels[i+2];r.target[i+3]=pixels[i+3]; }
    const uint8_t *font=Platform_ReadAsset(AS_READ_FONT).data,*p=a.data+BE32(a.data+4+page*4);
    unsigned n=BE16(p);p+=2;
    for(unsigned i=0;i<n;++i) {
        int x=BE16(p),y=p[2];unsigned length=p[3];p+=4;
        if(!length) { Sprite(r,AS_READ_GRAPHIC_0+*p++,x,y);continue; }
        for(unsigned j=0;j<length;++j) {
            unsigned c=*p++,first=font[0],width=c>=first?BE16(font+BE16(font+6)+(c-first)*2)>>12:0;
            Glyph(r,font,x,y,c);x+=width?width:2;
        }
    }
    int left=kind==0?60:kind==1?48:50,right=kind==0?245:kind==1?260:250;
    if(page) Sprite(r,AS_READ_PREVIOUS,left-19,185);
    if(page+1<count) Sprite(r,AS_READ_NEXT,right+4,185);
    r.damage[r.buffer_index]={0,0,319,199};
}
