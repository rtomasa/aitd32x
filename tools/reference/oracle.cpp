#include "common.h"
#include <iostream>
#include <fstream>
#include <csignal>
#include <execinfo.h>
#include <unistd.h>
extern "C" { char homePath[512]; }
void getHotPoint(int,sBody*,point3dStruct*);
s16 currentInventory,numObjInInventoryTable[NUM_MAX_INVENTORY],inHandTable[NUM_MAX_INVENTORY],inventoryTable[NUM_MAX_INVENTORY][INVENTORY_SIZE];
unsigned char* polyBackBuffer;
unsigned char frontBuffer[64000];
unsigned int musicChrono;
bool fileExists(const char* name){char path[1024];snprintf(path,sizeof path,"%s%s",homePath,name);FILE* f=fopen(path,"rb");if(f){fclose(f);return true;}return false;}
int Lire(int,int,int,int,int,int,int,int){return 0;}
void drawZv(const ZVStruct&){}
void playSequence(int,int,int){}
static unsigned ref_tick,limit=100;
static std::string scenario;
static char screens[3][64000];
void snapshot() {
    std::cout << "{\"time\":"<<timer<<",\"tick\":"<<ref_tick<<",\"floor\":"<<g_currentFloor<<",\"room\":"<<currentRoom<<",\"camera\":"<<NumCamera<<",\"variables\":[";
    for(int i=0;i<varSize/2;++i)std::cout<<(i?",":"")<<vars[i];
    std::cout<<"],\"actors\":[";bool comma=false;
    for(auto &a:ListObjets)if(a.indexInWorld>=0){if(comma)std::cout<<",";comma=true;
        std::cout<<"["<<a.indexInWorld<<","<<a.bodyNum<<","<<a.objectType<<","<<a.stage<<","<<a.room<<","<<a.roomX+a.stepX<<","<<a.roomY+a.stepY<<","<<a.roomZ+a.stepZ<<","<<a.beta<<","<<a.life<<","<<a.lifeMode<<","<<a.ANIM<<","<<a.frame<<","<<a.trackMode<<","<<a.trackNumber<<","<<a.positionInTrack<<","<<a.HARD_DEC<<","<<a.HARD_COL<<"]";
    }
    std::cout<<"],\"objects\":[";
    for(int i=0;i<maxObjects;++i){auto &o=ListWorldObjets[i];if(i)std::cout<<",";std::cout<<"["<<i<<","<<o.body<<","<<o.flags<<","<<o.stage<<","<<o.room<<","<<o.x<<","<<o.y<<","<<o.z<<","<<o.life<<","<<o.lifeMode<<","<<o.foundFlag<<"]";}
    std::cout<<"]}"<<std::endl;
}
void process_events(){if(ref_tick>=limit){snapshot();std::exit(0);}++ref_tick;timer=timeGlobal=ref_tick*60/25;key=localKey=0;JoyD=localJoyD=0;Click=localClick=0;
    int playerSlot=ListWorldObjets[1].objIndex;
    if(playerSlot>=0){currentProcessedActorIdx=playerSlot;currentProcessedActorPtr=&ListObjets[playerSlot];
        if(ref_tick==2405 && scenario=="melee") {
            setStage(0,0,2000,0,3500);currentProcessedActorPtr->beta=0;
            int dog=ListWorldObjets[21].objIndex;
            currentProcessedActorIdx=dog;currentProcessedActorPtr=&ListObjets[dog];setStage(0,0,2000,0,2850);currentProcessedActorPtr->beta=512;
            currentProcessedActorIdx=playerSlot;currentProcessedActorPtr=&ListObjets[playerSlot];
        }
        if(ref_tick==5 && scenario=="throw") {take(3);action=512;executeFoundLife(3);}
        if(ref_tick==5 && scenario=="stairs") {setStage(0,0,6830,0,2900);currentProcessedActorPtr->beta=0;}
        if(ref_tick==5 && scenario=="chest") {setStage(0,0,-6000,0,-395);currentProcessedActorPtr->beta=256;action=64;executeFoundLife(2);}
        if(ref_tick==5 && scenario=="book") {take(15);action=4;executeFoundLife(15);}
        if(ref_tick==5 && scenario=="push") {setStage(0,0,-6000,0,-395);currentProcessedActorPtr->beta=256;action=256;executeFoundLife(2);}
        if(ref_tick==5 && scenario=="zombie") {setStage(0,0,2000,0,2500);currentProcessedActorPtr->beta=512;}
    }
    if(scenario=="melee" && ref_tick>=2406 && ref_tick<=3105) {Click=1;action=0x2000;localJoyD=JoyD=1;}
    if(scenario=="chest" && ref_tick>=6 && ref_tick<=45) {Click=1;action=0x2000;localJoyD=JoyD=1;}
    if(scenario=="push" && ref_tick>=6 && ref_tick<=80) {Click=1;action=0x2000;localJoyD=JoyD=1;}
}
void AllRedraw(int){
    for(auto &a:ListObjets) if(a.indexInWorld>=0 && a.bodyNum>=0 && a.hotPointID>=0 && a.animActionType){
        sBody* body=HQR_Get(HQ_Bodys,a.bodyNum);computeScreenBox(0,0,0,a.alpha,a.beta,a.gamma,body);getHotPoint(a.hotPointID,body,&a.hotPoint);
    }
    snapshot();
}
void processInventory(){}
void processSystemMenu(){}
void makeMessage(int id){std::cerr<<"message "<<id<<"\n";}
void readBook(int id,int type){std::cerr<<"read "<<id<<" "<<type<<"\n";}
void FoundObjet(int id,int mode){std::cerr<<"found "<<id<<" "<<mode<<"\n";}
void osystem_createMask(const std::array<u8,320*200>&,int,int,int,int,int,int){}
void osystem_drawBackground(){}
void osystem_CopyBlockPhys(unsigned char*,int,int,int,int){}
void osystem_draw320x200BufferToScreen(unsigned char*){}
void osystem_setPalette(palette_t*){}
void osystem_setPalette(unsigned char*){}
void osystem_flip(unsigned char*){}
void fillpoly(s16*,int,unsigned char){}
void FadeInPhys(int,int){}
void FadeOutPhys(int,int){}
void FastCopyScreen(void* a,void*b){if(a&&b)memcpy(b,a,64000);}
void playMusic(int id){currentMusic=id;}
void playSound(int){}
void stopSound(int){}
int fadeMusic(int,int,int){return 0;}
int main(int argc,char **argv){
    if(argc<2)return 2;snprintf(homePath,sizeof homePath,"%s/",argv[1]);if(argc>2)limit=atoi(argv[2]);if(argc>4)scenario=argv[4];
    std::signal(SIGSEGV,+[](int){void* frames[30];int n=backtrace(frames,30);backtrace_symbols_fd(frames,n,2);_exit(139);});
    BufferAnim.resize(NB_BUFFER_ANIM);
    g_gameId=AITD1;currentCVarTable=AITD1KnownCVars;CVars.resize(45);CVars[CHOOSE_PERSO]=argc>3?atoi(argv[3]):0;
    aux=screens[0];aux2=screens[1];logicalScreen=screens[2];HQ_Memory=HQR_Init(65000,100);currentLifeNum=-1;
    LoadWorld();initVars();LoadEtage(0);NumCamera=-1;ChangeSalle(0);NewNumCamera=0;FlagInitView=2;InitView();snapshot();PlayWorld(1,1);snapshot();
}
