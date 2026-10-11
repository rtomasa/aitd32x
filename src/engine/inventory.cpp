// SPDX-License-Identifier: GPL-2.0-or-later
#include "game.hpp"
#include "../render/book.hpp"
#include "../platform/platform_api.hpp"

namespace {
// These IDs cannot name a gameplay camera. The renderer's existing image ID
// also identifies which fixed UI frame is cached in its RAM background.
static constexpr unsigned INVENTORY_IMAGE=0xfffffffeu,PICKUP_IMAGE=0xfffffffdu;
static A32X_COLD unsigned Actions(const World &world,int object,int *bits) {
    unsigned count=0,flags=(uint16_t)world.objects[object].v[O_FOUND_FLAGS];
    for(unsigned bit=0;bit<11;++bit) if(flags&(1u<<bit)) bits[count++]=bit;
    return count;
}
static A32X_COLD void Arrow(Renderer &r,unsigned asset,int y) {
    Asset a=Platform_ReadAsset(asset);if(!a.data || a.flags || a.size<4) return;
    unsigned w=BE16(a.data),h=BE16(a.data+2);if(w*h+4!=a.size || w>22 || h>20) return;
    for(unsigned row=0;row<h;++row) {
        unsigned col=0;const uint8_t *p=a.data+4+row*w;
        while(col<w) {
            unsigned first=col,color=p[col++];while(col<w && p[col]==color) ++col;
            if(color) r.Span(y+row,298+first,297+col,color);
        }
    }
}
static A32X_COLD void Number(Renderer &r,int value,int x,int y) {
    char text[12],reverse[11];unsigned magnitude=value<0?0u-(unsigned)value:(unsigned)value,n=0;
    do { reverse[n++]=(char)('0'+magnitude%10);magnitude/=10; } while(magnitude);
    unsigned out=0;if(value<0) text[out++]='-';while(n) text[out++]=reverse[--n];text[out]=0;
    Book_DrawText(r,x,y,text,4);
}
}
A32X_COLD void Game::InventoryEnter() {
    menu=1;selection=action_selection=book_line=0;inventory_dirty=true;
    startup_time=startup_since=0;dirty=true;ResetCache();
}
A32X_COLD void Game::InventoryAdvance(unsigned elapsed) {
    if(menu!=1 && menu!=2) return;
    startup_time+=elapsed;
    if(!world.inventory_count || selection>=world.inventory_count ||
       world.objects[world.inventory[selection]].v[O_FOUND_BODY]<0) return;
    // Rotate at the original 60 Hz rate, presenting at most 30 times per
    // second. Slow draws do not slow the animation or advance the world.
    unsigned frame=startup_time/50;
    if(frame!=startup_since) { startup_since=frame;dirty=true; }
}
A32X_COLD void Game::InventoryUpdate(uint16_t edges) {
    if(!edges) return;
    if(edges&(PAD_C|PAD_B|PAD_START)) {
        if(menu==2) menu=1;else { menu=0;book_line=0;ResetCache(); }
        action_blocked=true;inventory_dirty=true;dirty=true;return;
    }
    int previous_menu=menu,previous_selection=selection,previous_action=action_selection;
    if(menu==1) {
        if(edges&PAD_DOWN) selection=Min(selection+1,Max(0,world.inventory_count-1));
        if(edges&PAD_UP) selection=Max(0,selection-1);
        if(selection<book_line) book_line=selection;
        if(selection>=book_line+5) book_line=selection-4;
        if((edges&PAD_A) && world.inventory_count) { menu=2;action_selection=0; }
    } else if(world.inventory_count && selection<world.inventory_count) {
        int object=world.inventory[selection],bits[11];unsigned count=Actions(world,object,bits);
        if(edges&PAD_DOWN) action_selection=Min(action_selection+1,Max(0,(int)count-1));
        if(edges&PAD_UP) action_selection=Max(0,action_selection-1);
        if((edges&PAD_A) && count) {
            world.FoundLife(object,1<<bits[action_selection]);menu=0;book_line=0;
            action_blocked=true;ResetCache();
        }
    }
    if(menu!=previous_menu || selection!=previous_selection || action_selection!=previous_action) {
        inventory_dirty=true;dirty=true;
    }
}
A32X_COLD void Game::InventoryDraw() {
    Renderer &r=renderer;int object=world.inventory_count?world.inventory[selection]:-1,bits[11];
    unsigned count=object>=0?Actions(world,object,bits):0;
    if(inventory_dirty) {
        BackgroundComposition composition(r);
        if(r.camera_id!=INVENTORY_IMAGE) {
            r.Box(0,0,320,200,0);
            r.Panel(0,0,AS_UI_ORIGINAL_INVENTORY_LIST);
            r.Panel(0,100,AS_UI_ORIGINAL_INVENTORY_SECTION);
            r.Panel(160,100,AS_UI_ORIGINAL_INVENTORY_SECTION);
            r.camera_id=INVENTORY_IMAGE;
        } else {
            // Selection changes retain the original gold rails. Clear only
            // opaque interiors; compressed panels decode once on entering.
            r.Box(8,8,304,84,0);
            r.Box(8,108,144,84,0);r.Box(168,108,144,84,0);
        }
        if(object<0) Book_DrawText(r,160,41,"Inventory is empty",4,true);
        for(int i=book_line;i<Min(book_line+5,world.inventory_count);++i) {
            int y=9+(i-book_line)*16;bool selected=i==selection;
            if(selected && menu==1) r.Box(10,y,300,16,100);
            const char *name=GameText(world.objects[world.inventory[i]].v[O_NAME]);
            if(selected) Book_DrawClippedText(r,160,y+1,name,278,4,true);
            Book_DrawClippedText(r,160,y+(selected?0:1),name,278,selected?(menu==1?15:14):4,true);
        }
        if(book_line) Arrow(r,AS_UI_INVENTORY_UP,10);
        if(book_line+5<world.inventory_count) Arrow(r,AS_UI_INVENTORY_DOWN,74);
        // Original objects have at most five actions. Keep unusual script
        // combinations accessible through a scrolling five-line section.
        int first=Max(0,action_selection-4),visible=Min(5,(int)count-first);
        for(int i=first;i<first+visible;++i) {
            int y=150-visible*8+(i-first)*16;bool selected=menu==2 && i==action_selection;
            if(selected) r.Box(170,y,140,16,100);
            const char *text=GameText(bits[i]+23);
            if(selected) Book_DrawClippedText(r,240,y+1,text,136,4,true);
            Book_DrawClippedText(r,240,y+(selected?0:1),text,136,selected?15:4,true);
        }
        // Compose in the existing RAM image, avoiding framebuffer readback.
        // Closing invalidates the scenery bake; animation restores its damage.
        inventory_dirty=false;
    }
    r.Restore();
    if(object>=0) {
        r.DrawPreview(character,world.objects[object].v[O_FOUND_BODY],-(int)(startup_time/25)*8);
        int variable=world.objects[object].v[O_FLOOR_LIFE];
        if(variable>=0 && variable<A32X_VAR_COUNT) Number(r,world.vars[variable],12,112);
    }
    // Health remains visible alongside the original item-count display.
    Book_DrawText(r,12,174,"Health",4);Number(r,Max(0,world.vars[21]),68,174);
    dirty=false;
}

A32X_COLD void Game::PickupEnter() {
    selection=1;startup_time=startup_since=0;inventory_dirty=true;dirty=true;ResetCache();
}
A32X_COLD void Game::PickupAdvance(unsigned elapsed) {
    if(world.prompt<0 || menu>=3) return;
    startup_time+=elapsed;
    if(world.objects[world.prompt].v[O_FOUND_BODY]<0) return;
    unsigned frame=startup_time/50;
    if(frame!=startup_since) { startup_since=frame;dirty=true; }
}
A32X_COLD void Game::PickupUpdate(uint16_t edges) {
    if(!edges) return;
    int previous=selection;
    if(edges&PAD_LEFT) selection=0;
    if(edges&PAD_RIGHT) selection=1;
    if(edges&(PAD_A|PAD_C|PAD_B)) {
        int object=world.prompt;world.prompt=-1;
        if((edges&PAD_A) && selection==1) world.Take(object);
        else world.objects[object].v[O_TRACK]=(int16_t)Max(1,world.now);
        selection=0;action_blocked=true;ResetCache();dirty=true;
        if(world.prompt>=0) PickupEnter();
        return;
    }
    if(selection!=previous) { inventory_dirty=true;dirty=true; }
}
A32X_COLD void Game::PickupDraw() {
    Renderer &r=renderer;
    if(inventory_dirty) {
        BackgroundComposition composition(r);
        // The original found-object window replaces the room with black,
        // rather than placing a prompt over the paused scene. The same RAM
        // background used by inventory holds its fixed frame and labels.
        if(r.camera_id!=PICKUP_IMAGE) {
            r.Box(0,0,320,200,0);r.Panel(40,40,AS_UI_ORIGINAL_PICKUP);
            r.camera_id=PICKUP_IMAGE;
        } else r.Box(48,48,224,104,0);
        Book_DrawText(r,160,48,GameText(20),1,true);
        Book_DrawClippedText(r,160,64,GameText(world.objects[world.prompt].v[O_NAME]),220,1,true);
        Book_DrawText(r,130,135,GameText(21),selection==0?1:4,true);
        Book_DrawText(r,190,135,GameText(22),selection==1?1:4,true);
        inventory_dirty=false;
    }
    r.Restore();
    r.DrawPreview(character,world.objects[world.prompt].v[O_FOUND_BODY],-(int)(startup_time/25)*8,
                  {48,48,271,151},15000,300,298,{160,100});
    // FoundObjet draws its labels after the model, inside the original clip.
    // Keep that order while restoring the cached black/frame pixels only.
    Book_DrawText(r,160,48,GameText(20),1,true);
    Book_DrawClippedText(r,160,64,GameText(world.objects[world.prompt].v[O_NAME]),220,1,true);
    for(int choice=0;choice<2;++choice) {
        int x=130+choice*60;
        if(selection==choice) Book_DrawText(r,x,136,GameText(21+choice),4,true);
        Book_DrawText(r,x,135,GameText(21+choice),selection==choice?1:4,true);
    }
    dirty=false;
}
