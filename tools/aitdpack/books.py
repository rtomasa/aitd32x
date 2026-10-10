"""Original AITD1 reading art/font and offline proportional page layout."""
import re,struct
from life_format import instructions
U16=lambda b,o=0:struct.unpack_from('<H',b,o)[0]
class Font:
    def __init__(self,data):self.data=data;self.start=U16(data)&255;self.table=int.from_bytes(data[6:8],'big');self.height=data[2];self.stride=data[3] or U16(data,4)
    def width(self,code):return int.from_bytes(self.data[self.table+(code-self.start)*2:self.table+(code-self.start)*2+2],'big')>>12 if code>=self.start else 0
    def size(self,word):return sum(self.width(c) or 2 for c in word)
def sprite(data,index):
    off=U16(data,index*2);w,h=struct.unpack_from('<HH',data,off+4);image=data[off+8:off+8+w*h]
    assert len(image)==w*h
    return w,h,image

def layout(text,kind,font,graphics,rectangle=None):
    left,top,right,bottom=rectangle or [(60,10,245,190),(48,2,260,197),(50,20,250,199)][kind]
    width=right-left+4;pages=[];commands=[];y=top
    def page():
        nonlocal commands,y
        pages.append(commands);commands=[];y=top
    def line(words,center=False,justify=False):
        nonlocal y
        if y>bottom-16:page()
        total=sum(font.size(w)+3 for w in words);x=left+(width-total)//2 if center else left
        gap=(width-total)//(len(words)-1) if justify and len(words)>1 else 0
        for word in words:
            if word:commands.append((x,y,word))
            x+=font.size(word)+3+gap
        y+=16
    # CRLF is a line delimiter only for centered lines; ordinary prose flows
    # across single CRLFs, exactly as Lire. Blank paragraphs add eight pixels.
    for chunk in re.split(rb'(#P|#G\d+)',text.split(b'\x1a',1)[0].split(b'\0',1)[0]):
        if chunk==b'#P':
            if commands or y>top:page()
            continue
        if chunk.startswith(b'#G'):
            i=int(chunk[2:]);w,h,_=sprite(graphics,i)
            if y+h>bottom:page()
            commands.append(((left+right-w)//2,y,('graphic',i)));y+=h+8
            continue
        # Each centered title line keeps its own alignment. Prose paragraphs
        # wrap and justify at the original glyph widths instead of 8px cells.
        lines=chunk.replace(b'\r\n',b'\n').split(b'\n');prose=[]
        def flush():
            nonlocal prose
            if not prose:return
            words=[];used=0
            for word in prose:
                n=font.size(word)+3
                if words and used+n>width:line(words,justify=True);words=[];used=0
                words.append(word);used+=n
            if words:line(words)
            prose=[]
        for index,source in enumerate(lines):
            if source.startswith(b'#C'):
                flush();words=source[2:].split();line(words,center=True)
            elif not source.strip():
                # Empty chunks around #P/#G are separators, not extra pages.
                if prose:flush();y+=8
                elif index<len(lines)-1:y+=8 if commands else 16
            else:
                tabs=0
                while source.startswith(b'#T'):tabs+=1;source=source[2:]
                if tabs:
                    flush();prose.extend([b'    ']*tabs)
                prose.extend(source.split())
        flush()
    if commands or not pages:pages.append(commands)
    out=bytearray(struct.pack('>HH',kind,len(pages))+bytes((len(pages)+1)*4))
    for i,commands in enumerate(pages):
        struct.pack_into('>I',out,4+i*4,len(out));out+=struct.pack('>H',len(commands))
        for x,y,word in commands:
            if isinstance(word,tuple):out+=struct.pack('>HBBB',x,y,0,word[1])
            else:
                assert len(word)<256 and 0<=x<=319 and 0<=y<200,(x,y,word)
                out+=struct.pack('>HBB',x,y,len(word))+word
    struct.pack_into('>I',out,4+len(pages)*4,len(out))
    return bytes(out),len(pages)

def compile_books(get,book_count):
    font=Font(get('ITD_RESS',5));graphics=get('ITD_RESS',9);types={1:0,7:2}
    for i in range(563):
        for _,op,_,args in instructions(get('LISTLIFE',i)):
            if op==35:
                kind,index=args[:2];types[index+1]=kind
    assets=[('READ_FONT',18,font.data)]
    for kind,index in enumerate((6,7,8)):assets.append((f'READ_BACKGROUND_{kind}',2,get('ITD_RESS',index)))
    for i in range(6):
        w,h,pixels=sprite(graphics,i);assets.append((f'READ_GRAPHIC_{i}',13,struct.pack('>HH',w,h)+pixels))
    for name,index in [('PREVIOUS',12),('NEXT',11)]:
        w,h,pixels=sprite(get('ITD_RESS',4),index);assets.append(('READ_'+name,13,struct.pack('>HH',w,h)+pixels))
    books=[];report=[]
    for i in range(1,book_count+1):
        kind=types.get(i,1);data,count=layout(get('ENGLISH',i),kind,font,graphics)
        books.append(data);report.append(dict(id=i,type=kind,pages=count,bytes=len(data)))
    return books,assets,report
