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
namespace {
struct OriginalFont {
    const uint8_t *data;
    unsigned table,count,first,height,stride;
    A32X_COLD OriginalFont():data(nullptr),table(0),count(0),first(0),height(16),stride(0) {
        Asset a=Platform_ReadAsset(AS_READ_FONT);
        if(!a.data || a.type!=18 || a.flags || a.size<8) return;
        table=BE16(a.data+6);first=a.data[0];height=a.data[2];
        stride=a.data[3]?a.data[3]:a.data[4]|(a.data[5]<<8);
        if(!height || height>GAME_HEIGHT || !stride || table<8 || table>a.size || height*stride>table-8) return;
        count=Min((a.size-table)/2,256-first);data=a.data;
    }
    A32X_COLD unsigned Glyph(unsigned c) const {
        if(!data || c<first || c-first>=count) return 0;
        unsigned glyph=BE16(data+table+(c-first)*2);
        return (glyph&4095)+(glyph>>12)<=stride*8?glyph:0;
    }
    A32X_COLD unsigned Advance(unsigned c) const { unsigned width=Glyph(c)>>12;return width?width:2; }
};
static A32X_COLD unsigned TextWidth(const OriginalFont &font,const char *begin,const char *end=nullptr) {
    unsigned width=0;while(begin!=end && *begin) width+=font.Advance((uint8_t)*begin++);return width;
}
static A32X_COLD unsigned Glyph(Renderer &r,const OriginalFont &font,int x,int y,unsigned c,uint8_t color) {
    unsigned glyph=font.Glyph(c),width=glyph>>12,bit=glyph&4095;
    if(!width) return 2;
    const uint8_t *pixels=font.data+8+(bit>>3);bit&=7;
    for(unsigned row=0;row<font.height;++row) {
        unsigned col=0;
        while(col<width) {
            while(col<width && !(pixels[(bit+col)>>3]&(128>>((bit+col)&7)))) ++col;
            unsigned first_col=col;
            while(col<width && (pixels[(bit+col)>>3]&(128>>((bit+col)&7)))) ++col;
            if(first_col<col) r.Span(y+row,x+first_col,x+col-1,color);
        }
        pixels+=font.stride;
    }
    return width;
}
static A32X_COLD void DrawRange(Renderer &r,const OriginalFont &font,int x,int y,const char *begin,const char *end,uint8_t color,bool center,int limit=0,bool more=false) {
    unsigned total=center || limit>0?TextWidth(font,begin,end):0,dots=more?font.Advance('.')*3:0;
    if(limit>0 && total+dots>(unsigned)limit) {
        const char *p=begin;total=0;
        while(p!=end && *p) {
            unsigned advance=font.Advance((uint8_t)*p);
            if(total+advance+dots>(unsigned)limit) break;
            total+=advance;++p;
        }
        end=p;
    }
    if(dots && dots>(unsigned)Max(0,limit)) dots=0;
    if(center) x-=(int)(total+dots)/2;
    while(begin!=end && *begin) x+=Glyph(r,font,x,y,(uint8_t)*begin++,color);
    if(dots) for(unsigned i=0;i<3;++i) x+=Glyph(r,font,x,y,'.',color);
}
}
A32X_COLD unsigned Book_TextWidth(const char *text) {
    OriginalFont font;return text?TextWidth(font,text):0;
}
A32X_COLD unsigned Book_TextHeight() { OriginalFont font;return font.height; }
A32X_COLD void Book_DrawText(Renderer &r,int x,int y,const char *text,uint8_t color,bool center) {
    OriginalFont font;if(font.data && text) DrawRange(r,font,x,y,text,nullptr,color,center);
}
A32X_COLD void Book_DrawClippedText(Renderer &r,int x,int y,const char *text,int width,uint8_t color,bool center,bool ellipsis) {
    OriginalFont font;if(!font.data || !text || width<=0) return;
    DrawRange(r,font,x,y,text,nullptr,color,center,width,ellipsis && TextWidth(font,text)>(unsigned)width);
}
A32X_COLD unsigned Book_DrawLines(Renderer &r,int x,int y,const char *text,int width,unsigned rows,uint8_t color,bool center,unsigned skip) {
    OriginalFont font;if(!font.data || !text || width<=0 || !rows) return 0;
    unsigned line=0;
    while(*text && line<skip+rows) {
        while(*text==' ') ++text;
        if(!*text) break;
        const char *begin=text,*space=nullptr;unsigned used=0;
        while(*text && *text!='\r' && *text!='\n') {
            unsigned advance=font.Advance((uint8_t)*text);
            if(used+advance>(unsigned)width) break;
            if(*text==' ') space=text;
            used+=advance;++text;
        }
        const char *end=text;
        if(*text && *text!='\r' && *text!='\n' && space && space>begin) { end=space;text=space+1; }
        else if(text==begin && *text!='\r' && *text!='\n') ++text; // A wider-than-panel glyph cannot stall wrapping.
        while(end>begin && end[-1]==' ') --end;
        while(*text==' ') ++text;
        if(*text=='\r') { ++text;if(*text=='\n') ++text; }
        else if(*text=='\n') ++text;
        if(line>=skip) DrawRange(r,font,x,y+(line-skip)*font.height,begin,end,color,center,width,line+1==skip+rows && *text);
        ++line;
    }
    return line;
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
    OriginalFont font;const uint8_t *p=a.data+start,*limit=a.data+end;
    if(!font.data) return;
    unsigned n=BE16(p);p+=2;
    for(unsigned i=0;i<n;++i) {
        if(limit-p<4) return;
        int x=BE16(p),y=p[2];unsigned length=p[3];p+=4;
        if(!length) { if(p==limit || *p>5) return;Sprite(r,AS_READ_GRAPHIC_0+*p++,x,y);continue; }
        if((unsigned)(limit-p)<length) return;
        for(unsigned j=0;j<length;++j) {
            x+=Glyph(r,font,x,y,*p++,color);
        }
    }
}
