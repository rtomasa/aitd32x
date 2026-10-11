// SPDX-License-Identifier: GPL-2.0-or-later
#include "game.hpp"
#include "../render/divide.hpp"
namespace {
// Prepared ellipse avoids division/square roots in the per-frame lamp mask.
static const uint8_t light_half_width[]={96,95,95,95,95,95,95,95,95,95,95,94,94,94,94,93,93,93,92,92,92,91,91,90,90,90,89,88,88,87,87,86,85,85,84,83,83,82,81,80,79,78,77,76,75,74,73,72,71,70,69,67,66,64,63,61,60,58,56,55,53,50,48,46,43,41,38,35,31,27,22,15,0};
}
A32X_COLD Rect Game::PrepareLighting(const int *order,int count,Point &center) {
    Rect empty={320,200,-1,-1};int source=world.Slot(world.cvars[13]);
    bool visible=false;for(int i=0;i<count;++i) if(order[i]==source) { visible=true;break; }
    // A retained screen bound belongs to the previous pose and may outlive an
    // offscreen/deactivated lamp. Project its current collision center once,
    // using the same room translation and Q15 camera rotation as geometry.
    if(!visible || !renderer.camera.data || world.Pose(source).floor!=world.floor) return empty;
    const Actor &a=world.Pose(source);Asset room=world.RoomAsset(a.floor,a.room);
    if(!room.data) return empty;
    const uint8_t *c=renderer.camera.data,*r=room.data;
    Vec3 v={a.pos.x+(a.collision_min.x+a.collision_max.x)/2-(BS16Aligned(c+6)-BS16Aligned(r))*10,
            a.pos.y+(a.collision_min.y+a.collision_max.y)/2-(BS16Aligned(r+2)-BS16Aligned(c+8))*10,
            a.pos.z+(a.collision_min.z+a.collision_max.z)/2-(BS16Aligned(r+4)-BS16Aligned(c+10))*10};
    Rotate(v,PrepareRotation(BS16Aligned(c),BS16Aligned(c+2),BS16Aligned(c+4)));v.z+=BS16Aligned(c+12);
    if(v.z<51) return empty;
    center={Clamp(160+RenderDivide(v.x*BS16Aligned(c+14),v.z),-4096,4096),
            Clamp(100+RenderDivide(v.y*BS16Aligned(c+16),v.z),-4096,4096)};
    Rect light={Max(0,center.x-96)&~1,Max(0,center.y-72),Min(319,center.x+96)|1,Min(199,center.y+72)};
    return light.x1<=light.x2 && light.y1<=light.y2?light:empty;
}
A32X_COLD void Game::DrawLighting(Rect restored,Rect light,Point center) {
    Rect drawn=renderer.damage[renderer.buffer_index];
    Rect area={Max(0,Min(restored.x1,drawn.x1)),Max(0,Min(restored.y1,drawn.y1)),Min(319,Max(restored.x2,drawn.x2)),Min(199,Max(restored.y2,drawn.y2))};
    int cx=center.x,cy=center.y;
    for(int y=area.y1;y<=area.y2;++y) {
        int dy=y-cy;if(dy<0) dy=-dy;
        if(light.x1>light.x2 || dy>72) renderer.Span(y,area.x1,area.x2,0);
        else {
            int width=light_half_width[dy];
            if(area.x1<cx-width) renderer.Span(y,area.x1,Min(area.x2,cx-width-1),0);
            if(area.x2>cx+width) renderer.Span(y,Max(area.x1,cx+width+1),area.x2,0);
        }
    }
    // Pixels outside the lamp remain black in that physical framebuffer.
    // Restore only the previous lit footprint on its next use, then mask the
    // new draw damage. This avoids a full-scene clear/restore every dark frame.
    renderer.damage[renderer.buffer_index]=light;
}
