"""AITD1 wordcode operand formats, also used for offline CD/AdLib cue matching."""
import struct
# R: raw signed word, E: evaluated operand (possibly an object-qualified one).
FORMATS={0:'',1:'RR',2:'RR',3:'E',4:'EER',5:'EER',6:'EER',7:'EER',8:'EER',9:'EER',10:'R',11:'',12:'',13:'R',14:'RRRRRRR',15:'RR',16:'RRRRER',17:'R',18:'RR',19:'RE',20:'R',21:'R',22:'RE',23:'RE',24:'R',25:'E',26:'RR',27:'R',28:'',29:None,30:'R',31:'R',32:'R',33:'R',34:'R',35:'RRR',36:'ERR',37:'R',38:'',39:'E',40:'R',41:'',42:'',43:'R',44:'R',45:'RR',46:'',47:'RRRRR',48:'R',49:'R',50:'R',51:'R',52:'ER',53:'RRRRRR',54:'R',55:'R',56:'RR',57:'',58:'',59:'RRRRRRRRR',60:'RE',61:'',62:'',63:'EE',64:'R',65:'R',66:'R',67:'R',68:'',69:'R',70:'RR',71:'RRRRRR',72:'RR',73:'',74:'RRR',75:'ER',76:'RRRRRRR',77:'R',78:'RRR',79:'',80:'R',81:'R',82:'',83:'R',84:'',85:'EE',86:''}
def instructions(data,cd=True):
    words=struct.unpack('<'+str(len(data)//2)+'h',data);pc=0;result=[]
    def raw():
        nonlocal pc
        value=words[pc];pc+=1;return value
    def ev():
        code=raw()
        if code in (-1,0):raw();return
        if code&0x8000:raw();code&=0x7fff
        if code in (15,19,29,33,37,39):raw()
        elif code==35:raw();raw()
        elif code==17:ev()
        elif not 1<=code<=39:raise ValueError(('eval',pc-1,code))
    while pc<len(words):
        start=pc;op=raw()
        if op&0x8000:raw();op&=0x7fff
        if op not in FORMATS:raise ValueError(('opcode',start,op))
        arg=pc
        if op==29:
            n=raw()
            if not 0<=n<=128:raise ValueError(('cases',start,n))
            for _ in range(n+1):raw()
        else:
            for kind in ('RR' if op==35 and not cd else FORMATS[op]):ev() if kind=='E' else raw()
        result.append((start,op,arg,words[arg:pc]))
    return result

def adlib_cues(cd,floppy):
    """Match each script's ordered music commands, never infer by track number."""
    a=[i for i in instructions(cd) if i[1] in (44,80,81)]
    b=[i for i in instructions(floppy,False) if i[1] in (44,80,81)]
    if len(a)!=len(b):
        raise ValueError(('music command mismatch',a,b))
    words=list(struct.unpack('<'+str(len(cd)//2)+'h',cd));changes=[]
    for x,y in zip(a,b):
        if not -1<=y[3][0]<8:raise ValueError(('AdLib track',y))
        words[x[2]]=y[3][0]
        changes.append(dict(word=x[2],opcode=x[1],cd=x[3][0],adlib=y[3][0]))
    return struct.pack('<'+str(len(words))+'h',*words),changes
