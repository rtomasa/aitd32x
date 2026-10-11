// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "actor.hpp"
#ifndef AITD_RESOURCE_IDS
#define AITD_RESOURCE_IDS "../../assets/resource_ids.h"
#endif
#include AITD_RESOURCE_IDS
// Original OBJETS.ITD words. Found-item metadata stays in the world record;
// position/animation/track state is owned by the active slot until it leaves.
enum ObjectWord { O_SLOT,O_BODY,O_FLAGS,O_ZV,O_FOUND_BODY,O_NAME,O_FOUND_FLAGS,O_FOUND_LIFE,
 O_X,O_Y,O_Z,O_ALPHA,O_BETA,O_GAMMA,O_FLOOR,O_ROOM,O_LIFE_MODE,O_LIFE,O_FLOOR_LIFE,
 O_ANIM,O_FRAME,O_ANIM_TYPE,O_NEXT_ANIM,O_TRACK_MODE,O_TRACK,O_TRACK_POS };
enum ActorFlag { F_ANIMATED=1,F_DRAWABLE=4,F_BOXIFY=8,F_MOVABLE=16,F_TRIGGER=64,F_FOUNDABLE=128,F_FALLABLE=256 };
enum { MAX_ACTIVE=50,INVENTORY_CAPACITY=30 };
struct WorldObject { int16_t v[26]; };
struct RealValue { int start,end,steps;uint32_t since; };
struct ActiveObject {
    int id;WorldObject value;
    int col[3],col_by,hard_dec,hard_col,hit,hit_by,hit_force;
    int speed,direction,mark,dyn_flags,falling,end_anim,end_frame;
    int pending_anim,pending_type,pending_next;
    int hit_anim,hit_frame,hit_group,hit_size,hit_type,throw_object;
    uint32_t chrono,room_chrono;
    RealValue rotation,vertical,speed_change;
    int speed_step;
};
struct Bounds { Vec3 lo,hi; };
struct Effect {
    struct Position { int16_t x,y,z; } points[30];
    uint32_t since;uint16_t duration;int16_t floor,room;
    uint8_t count,color,mode;
};
class World {
public:
    WorldObject objects[A32X_OBJECT_COUNT];
    int16_t vars[A32X_VAR_COUNT],cvars[45];
    Effect effects[3];uint32_t effect_serial;
    ActiveObject active[MAX_ACTIVE];Actor poses[MAX_ACTIVE];Actor *player;
    int floor,room,camera,camera_target,character;
    uint32_t ticks,now,rng;
    uint16_t pad;int action,click,music,next_music;
    int inventory[INVENTORY_CAPACITY],inventory_count,in_hand;
    int prompt,message,book,book_type;uint32_t message_until;
    // Presentation-only arrival cutscene request. Its display clock is owned
    // by the startup UI while the world simulation is paused; never saved.
    int picture_id,picture_duration;
    bool inventory_allowed,view_changed,finished,intro,dark;
    int fault_life,fault_pc,fault_code,peak_active;
    void Init(Actor &protagonist,int selected,int initial_floor=0,int initial_room=0,int target=1);
    void InitIntro(Actor &protagonist,int selected) { Init(protagonist,selected,7,1,286); }
    void Update(uint16_t controller,bool acting);
    void RefreshActors();
    Actor &Pose(int slot) { return active[slot].id==1?*player:poses[slot]; }
    int Slot(int id) const;
    int Get(int id,int word) const;
    unsigned ScriptFrame(int slot) const {
        const ActiveObject &a=active[slot];const Actor &p=a.id==1?*player:poses[slot];
        // LIFE sees the original wrap to frame zero. The pose retains the
        // final key of a one-shot across stopping and re-activation.
        return a.end_anim && !(a.value.v[O_ANIM_TYPE]&1)?0:p.frame;
    }
    void Set(int id,int word,int value);
    void RunLife(int life,int slot,bool found=false,int depth=0);
    void FoundLife(int object,int act,int depth=0);
    void Take(int object,int depth=0);
    void Drop(int object,int source);
    void StopThrow(int slot,Vec3 position);
    void Delete(int object);
    void Stage(int slot,int f,int r,Vec3 position);
    void SetBody(int slot,int body);
    void Animate(int slot,int anim,int type,int next);
    void SetBounds(int slot,int type);
    void MoveMode(int slot,int mode,int track);
    void Track(int slot);
    void ManualRotate(int slot,int duration);
    void SetAngle(int slot,int angle,int duration,bool alpha=false);
    void MoveActor(int slot,Vec3 delta,bool push=true);
    void Zones(int slot);
    void Combat(int slot);
    void Special(int slot,int mode);
    bool Visible(int r) const;
    Bounds Box(int slot,int relative_room=-1) const;
    Vec3 InRoom(Vec3 p,int source,int dest) const;
    int PosRel(int a,int b) const;
    int Distance(int a,int b) const;
    int HardCollision(const Bounds &box,int f,int r) const;
    int DrawList(int *order) const;
    Asset RoomAsset(int f,int r) const;
    void Error(int life,int pc,int code);
private:
    void Activate(int id,int slot);
    void Deactivate(int slot);
    void Advance(int slot);
    void Aim(int slot,Vec3 goal,int duration,int turn);
};
const char *GameText(int id);
