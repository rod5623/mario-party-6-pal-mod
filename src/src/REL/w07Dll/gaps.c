/*
 * Pagoda Peak's two leaps, ported from MP7 w02dll: the move-end hook (.text 0xE78) runs them when a player
 * steps onto a space flagged 0x8000 (space 82: bamboo poles) or 0x2000 (space 86: a tree branch). Both carry
 * the player across a gap to the space's first link and set it as their space; the walk then carries on.
 * Without them players walked straight through the air.
 *
 * The bamboo (setup .text 0x123E8, leap 0x124B8, bend 0x126A8): three poles (w07.bin FILE_BAMBOO = MP7 w02.bin 9)
 * on the map's h_bamboo0..2 joints, motion paused. The player jumps onto each pole's top (its h_cha joint, in
 * the map joint's space: the matrix is taken at setup, as MP7 does) in 24 frames; the pole springs (its motion
 * from frame 0, speed 1) and rumbles. Then a 30-frame jump onto the space beyond (83).
 *
 * The branch (setup .text 0x1358C, leap 0x135E8, steps 0x13788 / 0x13A2C / 0x13C30): one model (FILE_BRANCH = MP7
 * w02.bin 0xA, placed by its own transform), motion paused. The player jumps up to hang below the h_branch joint
 * (offset (0, -90, -60) turned to their heading, .rodata 0x614; 30 frames, arc 300), hangs on while the branch
 * swings (motion speed 0.7, 42 frames), then is flung onto the space beyond (75; 30 frames, arc 600) with a
 * rumble.
 *
 * MP7 moves the player with its own helpers (missing in MP6); here they are plain arcs with MP6's jump motion.
 * Its sounds are left out, and the hanging player follows the joint without MP7's extra swing.
 */
#include "pagoda.h"

#define MASU_BAMBOO 0x8000
#define MASU_BRANCH 0x2000
#define BAMBOOS 3
#define BAMBOO_JUMP_FRAMES 24
#define BAMBOO_JUMP_HEIGHT 150.0f
#define LAND_FRAMES 30
#define LAND_HEIGHT 200.0f
#define BRANCH_JUMP_FRAMES 30
#define BRANCH_JUMP_HEIGHT 300.0f      /* 3 * 100 (.rodata 0x58) */
#define BRANCH_SWING_FRAMES 42
#define BRANCH_SWING_SPEED 0.7f       /* .rodata 0x62C */
#define BRANCH_FLING_FRAMES 30
#define BRANCH_FLING_HEIGHT 600.0f    /* 6 * 100 (.rodata 0x60) */

static MBOBJ bamboo[BAMBOOS] = { -1, -1, -1 };
static Mtx bambooMtx[BAMBOOS];
static MBOBJ branch = -1;
static char *bambooJoint[BAMBOOS] = { "h_bamboo0", "h_bamboo1", "h_bamboo2" };
static char bambooTop[] = "h_cha";
static char branchJoint[] = "h_branch";
static HuVecF hangOffset = { 0.0f, -90.0f, -60.0f };

void PagodaGapInit(MBOBJ map)
{
    s32 i;

    for (i = 0; i < BAMBOOS; i++) {
        bamboo[i] = mbObjCreate(PagodaBoardDir() | FILE_BAMBOO, NULL, 1);
        mbObjMotionSpeedSet(bamboo[i], 0.0f);
        mbObjHookSet(map, bambooJoint[i], bamboo[i]);
        Hu3DModelObjMtxGet(mbObjModelIDGet(map), bambooJoint[i], bambooMtx[i]);
    }
    branch = mbObjCreate(PagodaBoardDir() | FILE_BRANCH, NULL, 0);
    mbObjMotionSpeedSet(branch, 0.0f);
}

/* The map hooks the poles: board.c resets the map's hooks first. */
void PagodaGapKill(void)
{
    s32 i;

    for (i = 0; i < BAMBOOS; i++) {
        if (bamboo[i] >= 0) {
            mbObjKill(bamboo[i]);
            bamboo[i] = -1;
        }
    }
    if (branch >= 0) {
        mbObjKill(branch);
        branch = -1;
    }
}

static float Heading(HuVecF *from, HuVecF *to)
{
    return atan2(to->x - from->x, to->z - from->z) * RAD_TO_DEG;
}

static void Jump(s32 player, HuVecF *from, HuVecF *to, s32 frames, float height)
{
    HuVecF pos;
    s32 i;

    mbPlayerRotYSet(player, Heading(from, to));
    mbPlayerMotionShiftSet(player, PLAYER_MOT_JUMP, 0.0f, KOOPA_MOT_SHIFT, 0);
    for (i = 0; i < frames; i++) {
        float t = (float)i / (frames - 1);
        pos.x = from->x + t * (to->x - from->x);
        pos.y = from->y + t * (to->y - from->y) + height * PagodaSin(180.0f * t);
        pos.z = from->z + t * (to->z - from->z);
        mbPlayerPosSetV(player, &pos);
        HuPrcVSleep();
    }
}

static void BambooTop(s32 i, HuVecF *out)
{
    HuVecF local;

    Hu3DMotionCalc(mbObjModelIDGet(bamboo[i]));
    Hu3DModelObjPosGet(mbObjModelIDGet(bamboo[i]), bambooTop, &local);
    PSMTXMultVec(bambooMtx[i], &local, out);
}

/* MP7 .text 0x124B8 */
static void BambooLeap(s32 player, HuVecF *dest)
{
    HuVecF from, top;
    s32 i;

    mbPlayerPosGet(player, &from);
    for (i = 0; i < BAMBOOS; i++) {
        BambooTop(i, &top);
        Jump(player, &from, &top, BAMBOO_JUMP_FRAMES, BAMBOO_JUMP_HEIGHT);
        mbObjMotionTimeSet(bamboo[i], 0.0f);
        mbObjMotionSpeedSet(bamboo[i], 1.0f);
        omVibrate(player, 20, 4, 4);
        from = top;
    }
    Jump(player, &from, dest, LAND_FRAMES, LAND_HEIGHT);
}

/* Below the branch's joint, turned to `heading` (MP7 .text 0x13788: mbMtxRot by the heading, then .rodata
   0x614). */
static void HangPoint(float heading, HuVecF *out)
{
    s16 model = mbObjModelIDGet(branch);

    Hu3DMotionCalc(model);
    Hu3DModelObjPosGet(model, branchJoint, out);
    out->x += hangOffset.z * PagodaSin(heading) + hangOffset.x * PagodaCos(heading);
    out->y += hangOffset.y;
    out->z += hangOffset.z * PagodaCos(heading) - hangOffset.x * PagodaSin(heading);
}

/* MP7 .text 0x135E8 */
static void BranchLeap(s32 player, HuVecF *dest)
{
    HuVecF from, hang;
    float heading;
    s32 i;

    mbPlayerPosGet(player, &from);
    heading = Heading(&from, dest);
    mbObjMotionTimeSet(branch, 0.0f);
    mbObjMotionSpeedSet(branch, 0.0f);
    HangPoint(heading, &hang);
    Jump(player, &from, &hang, BRANCH_JUMP_FRAMES, BRANCH_JUMP_HEIGHT);
    mbPlayerRotYSet(player, heading);
    mbObjMotionSpeedSet(branch, BRANCH_SWING_SPEED);
    for (i = 0; i < BRANCH_SWING_FRAMES; i++) {
        HangPoint(heading, &hang);
        mbPlayerPosSetV(player, &hang);
        HuPrcVSleep();
    }
    omVibrate(player, 20, 4, 4);
    Jump(player, &hang, dest, BRANCH_FLING_FRAMES, BRANCH_FLING_HEIGHT);
}

/* The move-end hook (star.c): TRUE when `masu` is a leap's take-off space, after the player has landed on the
   space beyond and it has become their space. */
BOOL PagodaGap(s32 player, s16 masu)
{
    u32 flags = mbMasuMAttrGet(masu);
    HuVecF dest;
    s16 next;

    if (!(flags & (MASU_BAMBOO | MASU_BRANCH)) || bamboo[0] < 0) {
        return FALSE;
    }
    next = mbMasuLinkGet(masu, 0);
    if (next < 0) {
        return FALSE;
    }
    mbMasuPosGet(next, &dest);
    if (flags & MASU_BAMBOO) {
        BambooLeap(player, &dest);
    } else {
        BranchLeap(player, &dest);
    }
    mbPlayerMotionShiftSet(player, PLAYER_MOT_IDLE, 0.0f, KOOPA_MOT_SHIFT, KOOPA_MOT_LOOP);
    mbPlayerPosSetV(player, &dest);
    GwPlayer[player].masuId = next;
    return TRUE;
}
