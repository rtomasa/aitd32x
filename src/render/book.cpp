// SPDX-License-Identifier: GPL-2.0-or-later
#include "book.hpp"
#include "../platform/platform_api.hpp"
#include "../../assets/resource_ids.h"
A32X_COLD unsigned Book_Pages(int book) {
    if(book<=0 || book>A32X_BOOK_COUNT) return 0;
    return Book_LayoutPages(book_assets[book-1]);
}
A32X_COLD unsigned Book_LayoutPages(unsigned asset) {
    Asset a=Platform_ReadAsset(asset);
    if(!a.data || a.type!=17 || a.flags || a.size<8) return 0;
    unsigned count=BE16(a.data+2);return count && count<=(a.size-8)/4?count:0;
}
static A32X_COLD unsigned GlyphWidth(const uint8_t *font,unsigned c) {
    return c>=font[0]?BE16(font+BE16(font+6)+(c-font[0])*2)>>12:0;
}
static A32X_COLD void Glyph(Renderer &r,const uint8_t *font,int x,int y,unsigned c,uint8_t color) {
    unsigned first=font[0],height=font[2],stride=font[3]?font[3]:font[4]|(font[5]<<8);
    if(c<first) return;
    unsigned glyph=BE16(font+BE16(font+6)+(c-first)*2),width=glyph>>12,bit=glyph&4095;
    const uint8_t *pixels=font+8+(bit>>3);bit&=7;
    for(unsigned row=0;row<height;++row) {
        unsigned col=0;
        while(col<width) {
            while(col<width && !(pixels[(bit+col)>>3]&(128>>((bit+col)&7)))) ++col;
            unsigned first_col=col;
            while(col<width && (pixels[(bit+col)>>3]&(128>>((bit+col)&7)))) ++col;
            if(first_col<col) r.Span(y+row,x+first_col,x+col-1,color);
        }
        pixels+=stride;
    }
}
A32X_COLD void Book_DrawText(Renderer &r,int x,int y,const char *text,uint8_t color,bool center) {
    const uint8_t *font=Platform_ReadAsset(AS_READ_FONT).data;if(!font || !text) return;
    if(center) {
        unsigned total=0;for(const char *s=text;*s;++s) { unsigned width=GlyphWidth(font,(uint8_t)*s);total+=width?width:2; }
        x-=(int)total/2;
    }
    while(*text) { unsigned c=(uint8_t)*text++,width=GlyphWidth(font,c);Glyph(r,font,x,y,c,color);x+=width?width:2; }
}
static A32X_COLD void Sprite(Renderer &r,unsigned id,int x,int y) {
    Asset a=Platform_ReadAsset(id);if(!a.data || a.size<4 || a.unpacked<4) return;
    unsigned width=BE16(a.data),height=BE16(a.data+2);const uint8_t *p=a.data+4;
    if(!width || width>320 || height>200 || width*height!=a.unpacked-4) return;
    if(a.flags==3) {
        if((a.size-4)&1) return;
        unsigned output=0;
        for(unsigned i=4;i<a.size;i+=2) {
            unsigned n=a.data[i],color=a.data[i+1];if(!n || n>width*height-output) return;
            while(n) {
                unsigned col=output%width,run=Min(n,width-col);
                if(color) r.Span(y+output/width,x+col,x+col+run-1,color);
                output+=run;n-=run;
            }
        }
        return;
    }
    if(a.flags || a.size!=a.unpacked) return;
    for(unsigned row=0;row<height;++row) for(unsigned col=0;col<width;++col) { unsigned color=*p++;if(color) r.Span(y+row,x+col,x+col,color); }
}
A32X_COLD void Book_Draw(Renderer &r,int book,unsigned page) {
    unsigned count=Book_Pages(book);if(!count) return;page=Min(page,count-1);
    Asset a=Platform_ReadAsset(book_assets[book-1]);unsigned kind=BE16(a.data);
    if(!r.DrawImage(AS_READ_BACKGROUND_0+Min(kind,2))) Platform_Fatal();
    Book_DrawLayout(r,book_assets[book-1],page);
    int left=kind==0?60:kind==1?48:50,right=kind==0?245:kind==1?260:250;
    if(page) Sprite(r,AS_READ_PREVIOUS,left-19,185);
    if(page+1<count) Sprite(r,AS_READ_NEXT,right+4,185);
    r.damage[r.buffer_index]={0,0,319,199};
}
A32X_COLD void Book_DrawLayout(Renderer &r,unsigned asset,unsigned page,uint8_t color) {
    unsigned count=Book_LayoutPages(asset);if(!count) return;page=Min(page,count-1);
    Asset a=Platform_ReadAsset(asset);
    unsigned start=BE32(a.data+4+page*4),end=BE32(a.data+8+page*4);
    if(start>end || end>a.size || end-start<2) return;
    const uint8_t *font=Platform_ReadAsset(AS_READ_FONT).data,*p=a.data+start,*limit=a.data+end;
    if(!font) return;
    unsigned n=BE16(p);p+=2;
    for(unsigned i=0;i<n;++i) {
        if(limit-p<4) return;
        int x=BE16(p),y=p[2];unsigned length=p[3];p+=4;
        if(!length) { if(p==limit || *p>5) return;Sprite(r,AS_READ_GRAPHIC_0+*p++,x,y);continue; }
        if((unsigned)(limit-p)<length) return;
        for(unsigned j=0;j<length;++j) {
            unsigned c=*p++,width=GlyphWidth(font,c);
            Glyph(r,font,x,y,c,color);x+=width?width:2;
        }
    }
}
