/*
 * The Cannon orb (MP7 orb 5, MP6 orb id 8). plans/pagoda-peak/README.md 2c-bis; stage 2: part 1 (where it lands,
 * the shot before the dice roll, the landing event) and part 2 (MP7's cannon) confirmed in Dolphin (2026-11-25);
 * part 3 (MP7's explosion when there is nowhere to go) built 2026-11-25, not yet tested.
 *
 * apply_pagoda_board_patch.py makes orb 8 a self orb (model = MP7 capsule.bin 5, name and description from MP7
 * bank 0x1B in bank 0x4B, price 10) in Pagoda Peak's shop list, and points its event row (0x80268500 row 8) at
 * two stubs in DOL section 19 that jump through PAGODA_CANNON_EXEC_HOOK / PAGODA_CANNON_KILL_HOOK; the exec stub
 * ends the process when its hook is NULL. board.c sets the hooks at init and clears them at kill, so the orb
 * only does something on Pagoda Peak.
 *
 * The exec runs as the orb's process; its work (player at +0, orb at +8) is the process's +0x12C. It starts as
 * MP6's own movement orbs do (Warp Pipe mbev_CapDokan fn_8019C620): the use effect, a rumble, the orb-use bonus
 * coins (fn_801D527C), the wait for the use effect to end; without the bonus-coin step the effect lasts until the
 * dice roll.
 *
 * Where it lands (the user's rule, simpler than MP7's 0x801AAE34): roll CANNON_MIN_STEPS + rand(CANNON_STEP_RANGE)
 * (11-15) steps and walk forward from the player's space, counting only spaces that count as a step
 * (mbMasuDispCheck), never onto side or shop nodes, taking the branch nearer the summit at a fork. Any space type
 * may be the landing. Never past or onto the summit (MASU_SUMMIT): the walk stops before it, so the player still
 * walks onto it with the dice and gets the Star offer. Never onto a broken bridge (bowser.c): it lands on the last
 * good space before. Nowhere to go (blue space 43, right before the summit): MP7's gag (Explode): the player is shot
 * straight up and falls back into the barrel, the cannon shakes and explodes (FILE_CANNON_BOOM, MP7 capsule.bin
 * 0x42), and the player is left stunned on the same space. The player is placed, not walked, so the flown spaces don't count for the Running Star.
 *
 * The cannon, as MP7's exec (main.dol 0x801A8E7C-0x801A9C48): the body (w07.bin FILE_CANNON = MP7 capsule.bin 0x51)
 * stands on the space facing 180, hidden at scale 0, its motion paused at frame 0; the barrel (FILE_CANNON_BARREL =
 * 0x50) hangs on the body's "center" joint. The player hops up 300 (30 frames), then with MP6's mariomot 8 (byte for
 * byte MP7's) drops into the cannon, shrinking to half size, while the cannon pops up (scale t + 0.5 sin(180t),
 * 30 frames); the player is hidden. The body swivels +-45 towards the target side (90 frames) and turns to face it
 * (|heading| / 2.5 frames); the barrel nods (rotX -45 sin(180t), 120 frames) and tilts to its firing angle
 * (-90 - elevation, |90 + elevation| / 1.5 frames). 12 frames, the body's motion plays (the recoil), 9 frames, and
 * the player shoots out of the barrel and off screen (the user's direction: no visible flight) while the cannon
 * shrinks away (12 frames). Then a fade, the camera on the landing space, the player drops onto it, and the space's
 * event runs as after a move (mbev_MasuStop). Not yet: sounds (MP7's ids differ from MP6's; left for the polish step,
 * the user's choice), MP7's own flight.
 *
 * The player-collision snap keeps the model on its space; it is off around the move (as Warp Pipe does).
 *
 * CPUs: PagodaCannonComChance at the end (stage 3).
 */
#include "pagoda.h"

#define PRC_WORK(prc) (*(s32 **)((u8 *)(prc) + 0x12C))

#define CANNON_MIN_STEPS 11
#define CANNON_STEP_RANGE 5           /* 11-15 steps, as MP7 */
#define WALK_LIMIT 200                /* never loop forever on a malformed graph */
#define TYPE_OFF_PATH 0x2020          /* side nodes (0x2000) and the shop's node (0x20) */
#define PLAYER_MOT_IDLE 1
#define PLAYER_MOT_JUMP 4
#define MOT_SHIFT 4.0f
#define MOT_LOOP 0x40000001
#define MOT_INTO_CANNON (P01_DATA_mariomot | 8)  /* MP7 0xBC0008 */

#define CROUCH_FRAMES 20              /* the use effect and a rumble, before the cannon */
/* MP7's timings and sizes (main.dol 0x801A90C4-0x801A96E0) */
#define HOP_FRAMES 30
#define HOP_HEIGHT 300.0f
#define SINK_EXTRA 100.0f             /* the drop into the cannon ends this far below the hop's start */
#define SWIVEL_FRAMES 90
#define SWIVEL_ANGLE 45.0f
#define TURN_SPEED 2.5f               /* degrees per frame */
#define NOD_FRAMES 120
#define NOD_ANGLE 45.0f
#define TILT_SPEED 1.5f
#define FIRE_DELAY 12
#define RECOIL_DELAY 9
#define SHRINK_FRAMES 12
#define MUZZLE_HEIGHT 150.0f          /* where the player leaves the cannon */
#define LAUNCH_FRAMES 40              /* out of the barrel and off screen, speeding up */
#define LAUNCH_HEIGHT 4000.0f
#define LAUNCH_FORWARD 1200.0f        /* how far towards the landing the player travels before leaving the shot */
#define DROP_FRAMES 40                /* the drop onto the landing space */
#define DROP_HEIGHT 2500.0f
/* nowhere to go, MP7's gag (main.dol 0x801A988C-0x801A9BC4) */
#define GAG_FRAMES 45                 /* straight up and back down into the barrel */
#define GAG_HEIGHT 1000.0f
#define GAG_INTO 50.0f                /* where the player drops back in, above the space */
#define GAG_WAIT 60                   /* inside the cannon before it shakes */
#define SHAKE_FRAMES 60
#define SHAKE_ANGLE 10.0f             /* the shake grows to this, 4 wobbles (sin 1440t) */
#define BOOM_HEIGHT 75.0f             /* the explosion's place, above and behind the space */
#define BOOM_BACK 50.0f
#define BOOM_SCALE 1.5f
#define BOOM_HIDE 10                  /* frames into the explosion when the cannon goes */
#define BOOM_PLAYER 5                 /* then the player is back on the space, stunned */
#define BOOM_STUN 60
#define BOOM_MAX 180                  /* never wait longer than this for the explosion's motion */
#define PLAYER_MOT_STUN 6
#define CAMERA_ZOOM 2400.0f
#define TURN_PHASE (*((u8 *)&GwSystem + 0x36))   /* PlayerTurn sets 7 around mbev_MasuStop (0x80153E44) */
#define TURN_PHASE_SPACE 7
static HuVecF cannonCamRot = { -20.0f, 0.0f, 0.0f };
static char cannonJoint[] = "center";

static MBOBJ cannon = -1, barrel = -1, boom = -1;

/* The next space forward from `masu`: the on-path link nearest the summit, or -1. */
static s16 NextSpace(s16 masu)
{
    s32 count = mbMasuLinkNumGet(masu), i, steps, bestSteps = 0;
    s16 best = -1;

    for (i = 0; i < count; i++) {
        s16 link = mbMasuLinkGet(masu, i);
        if (link <= 0 || (mbMasuAttrGet(link) & TYPE_OFF_PATH)) {
            continue;
        }
        steps = (mbMasuMAttrGet(link) & MASU_SUMMIT) ? 0 : mbMasuFind_MAttrStepGet(link, MASU_SUMMIT);
        if (steps < 0) {
            steps = 0x7FFF;
        }
        if (best < 0 || steps < bestSteps) {
            best = link;
            bestSteps = steps;
        }
    }
    return best;
}

/* The landing space for a shot from `start` (see the header); `start` itself when there is nowhere to go. `prev`
   gets the counted space before the landing (the player's masuIdPrev afterwards). */
s16 PagodaCannonTarget(s16 start, s16 *prev)
{
    s32 goal = CANNON_MIN_STEPS + mbRandMod(CANNON_STEP_RANGE), steps = 0, guard;
    s16 masu = start, land = start, before = start, lastCounted = start;

    for (guard = 0; steps < goal && guard < WALK_LIMIT; guard++) {
        s16 next = NextSpace(masu);
        if (next < 0 || (mbMasuMAttrGet(next) & MASU_SUMMIT)) {
            break;
        }
        masu = next;
        if (mbMasuDispCheck(masu)) {
            steps++;
            if (!PagodaBridgeBroken(masu)) {
                before = lastCounted;
                land = masu;
            }
            lastCounted = masu;
        }
    }
    *prev = before;
    return land;
}

static float Wrap180(float a)
{
    while (a > 180.0f) {
        a -= 360.0f;
    }
    while (a < -180.0f) {
        a += 360.0f;
    }
    return a;
}

static void BarrelPitch(float angle)
{
    Mtx m;

    mtxRot(m, angle, 0.0f, 0.0f);
    mbObjMtxSet(barrel, m);
}

static void CannonCreate(HuVecF *at)
{
    cannon = mbObjCreate(PagodaBoardDir() | FILE_CANNON, NULL, 1);
    barrel = mbObjCreate(PagodaBoardDir() | FILE_CANNON_BARREL, NULL, 1);
    PagodaDirClose();
    mbObjHookSet(cannon, cannonJoint, barrel);
    mbObjPosSetV(cannon, at);
    mbObjRotSet(cannon, 0.0f, 180.0f, 0.0f);
    mbObjMotionSpeedSet(cannon, 0.0f);
    mbObjMotionTimeSet(cannon, 0.0f);
    mbObjScaleSet(cannon, 0.0f, 0.0f, 0.0f);
    mbObjDispSet(cannon, 0);
}

void PagodaCannonKill(void)
{
    if (cannon >= 0) {
        mbObjHookReset(cannon);
        mbObjKill(cannon);
        cannon = -1;
    }
    if (barrel >= 0) {
        mbObjKill(barrel);
        barrel = -1;
    }
    if (boom >= 0) {
        mbObjKill(boom);
        boom = -1;
    }
}

/* The player hops up and drops into the cannon as it pops out of the ground (MP7 0x801A90C4-0x801A9294). */
static void ClimbIn(s32 player, HuVecF *base)
{
    s16 mot = mbPlayerMotionCreate(player, MOT_INTO_CANNON);
    HuVecF pos;
    s32 i;

    CharMotionDataClose(GwPlayer[player].charNo);
    mbPlayerMotionShiftSet(player, PLAYER_MOT_JUMP, 0.0f, MOT_SHIFT, 0);
    for (i = 0; i < HOP_FRAMES; i++) {
        float t = (float)i / HOP_FRAMES;
        pos = *base;
        pos.y += HOP_HEIGHT * PagodaSin(90.0f * t);
        mbPlayerPosSetV(player, &pos);
        HuPrcVSleep();
    }
    mbPlayerMotionShiftSet(player, mot, 0.0f, 8.0f, 0);
    mbObjDispSet(cannon, 1);
    for (i = 0; i < HOP_FRAMES; i++) {
        float t = (float)i / HOP_FRAMES, size = 0.5f + 0.5f * PagodaCos(90.0f * t), grow;
        pos = *base;
        pos.y += HOP_HEIGHT * PagodaSin(90.0f + 90.0f * t) - SINK_EXTRA * t;
        mbPlayerPosSetV(player, &pos);
        mbPlayerScaleSet(player, size, size, size);
        grow = t + 0.5f * PagodaSin(180.0f * t);
        mbObjScaleSet(cannon, grow, grow, grow);
        HuPrcVSleep();
    }
    mbPlayerDispSet(player, 0);
    mbObjScaleSet(cannon, 1.0f, 1.0f, 1.0f);
    mbPlayerMotionKill(player, mot);
}

/* The body swivels and turns to `heading`, the barrel nods and tilts to `pitch` (MP7 0x801A9450-0x801A96D4). */
static void Aim(float heading, float pitch, BOOL tilt)
{
    float side = heading < 0.0f ? -1.0f : 1.0f;
    s32 i, frames;

    for (i = 1; i <= SWIVEL_FRAMES; i++) {
        float t = (float)i / SWIVEL_FRAMES;
        mbObjRotSet(cannon, 0.0f, 180.0f + side * SWIVEL_ANGLE * PagodaSin(360.0f * t), 0.0f);
        HuPrcVSleep();
    }
    frames = (s32)((heading < 0.0f ? -heading : heading) / TURN_SPEED);
    for (i = 1; i <= frames; i++) {
        float t = (float)i / frames;
        mbObjRotSet(cannon, 0.0f, 180.0f + heading * PagodaSin(90.0f * t), 0.0f);
        HuPrcVSleep();
    }
    mbObjRotSet(cannon, 0.0f, 180.0f + heading, 0.0f);
    for (i = 1; i <= NOD_FRAMES; i++) {
        float t = (float)i / NOD_FRAMES;
        BarrelPitch(-NOD_ANGLE * PagodaSin(180.0f * t));
        HuPrcVSleep();
    }
    if (tilt) {
        float to = -pitch - 90.0f;
        frames = (s32)((to < 0.0f ? -to : to) / TILT_SPEED);
        for (i = 1; i <= frames; i++) {
            float t = (float)i / frames;
            BarrelPitch(to * PagodaSin(90.0f * t));
            HuPrcVSleep();
        }
    }
}

/* The recoil, then the player out of the barrel and off screen while the cannon shrinks away; for the gag (`gag`),
   straight up and back down into the barrel, the cannon left standing. */
static void Fire(s32 player, HuVecF *base, float heading, BOOL gag)
{
    HuVecF from = *base, pos;
    float dx = PagodaSin(heading) * LAUNCH_FORWARD, dz = PagodaCos(heading) * LAUNCH_FORWARD;
    s32 i;

    HuPrcSleep(FIRE_DELAY);
    mbObjMotionSpeedSet(cannon, 1.0f);
    mbObjMotionTimeSet(cannon, 0.0f);
    HuPrcSleep(RECOIL_DELAY);
    mbCameraShakeSet(10, 60.0f);
    omVibrate(player, 15, 4, 4);
    from.y += MUZZLE_HEIGHT;
    mbPlayerScaleSet(player, 1.0f, 1.0f, 1.0f);
    mbPlayerMotionShiftSet(player, PLAYER_MOT_JUMP, 0.0f, MOT_SHIFT, 0);
    mbPlayerRotYSet(player, heading);
    mbPlayerPosSetV(player, &from);
    mbPlayerDispSet(player, 1);
    if (gag) {
        for (i = 1; i <= GAG_FRAMES; i++) {
            float t = (float)i / GAG_FRAMES;
            pos = from;
            pos.y += GAG_HEIGHT * PagodaSin(180.0f * t) - (MUZZLE_HEIGHT - GAG_INTO) * t;
            mbPlayerPosSetV(player, &pos);
            HuPrcVSleep();
        }
        mbPlayerDispSet(player, 0);
        return;
    }
    for (i = 1; i <= LAUNCH_FRAMES; i++) {
        float t = (float)i / LAUNCH_FRAMES, shrink;
        pos = from;
        pos.x += dx * t;
        pos.y += LAUNCH_HEIGHT * t * t;
        pos.z += dz * t;
        mbPlayerPosSetV(player, &pos);
        if (i <= SHRINK_FRAMES) {
            shrink = PagodaCos(90.0f * i / SHRINK_FRAMES);
            mbObjScaleSet(cannon, shrink, shrink, shrink);
        } else if (i == SHRINK_FRAMES + 1) {
            mbObjDispSet(cannon, 0);
        }
        HuPrcVSleep();
    }
}

/* The gag's end (MP7 0x801A99A0-0x801A9B90): with the player inside, the cannon shakes harder and harder with its
   recoil looping, then explodes (FILE_CANNON_BOOM at 1.5 size); it vanishes and the player is left stunned on the
   space. `yaw` is the body's facing after Aim. */
static void Explode(s32 player, HuVecF *base, float yaw)
{
    HuVecF at = *base;
    s32 i;

    HuPrcSleep(GAG_WAIT);
    mbObjAttrSet(cannon, HU3D_MOTATTR_LOOP);
    mbObjMotionTimeSet(cannon, 0.0f);
    for (i = 1; i <= SHAKE_FRAMES; i++) {
        float t = (float)i / SHAKE_FRAMES, shake = SHAKE_ANGLE * t * PagodaSin(1440.0f * t);
        mbObjRotSet(cannon, shake, yaw, -shake);
        HuPrcVSleep();
    }
    at.y += BOOM_HEIGHT;
    at.z += BOOM_BACK;
    boom = mbObjCreate(PagodaBoardDir() | FILE_CANNON_BOOM, NULL, 1);
    PagodaDirClose();
    mbObjPosSetV(boom, &at);
    mbObjLayerSet(boom, 3);
    mbObjScaleSet(boom, BOOM_SCALE, BOOM_SCALE, BOOM_SCALE);
    mbObjMotionSpeedSet(boom, 1.0f);
    mbCameraShakeSet(20, 100.0f);
    omVibrate(player, 30, 6, 6);
    HuPrcSleep(BOOM_HIDE);
    mbObjDispSet(cannon, 0);
    HuPrcSleep(BOOM_PLAYER);
    mbPlayerPosSetV(player, base);
    mbPlayerScaleSet(player, 1.0f, 1.0f, 1.0f);
    mbPlayerRotYSet(player, 0.0f);
    mbPlayerMotionShiftSet(player, PLAYER_MOT_STUN, 0.0f, MOT_SHIFT, MOT_LOOP);
    mbPlayerDispSet(player, 1);
    HuPrcSleep(BOOM_STUN);
    for (i = BOOM_HIDE + BOOM_PLAYER + BOOM_STUN; i < BOOM_MAX && !mbObjMotionEndCheck(boom); i++) {
        HuPrcVSleep();
    }
    mbPlayerMotionShiftSet(player, PLAYER_MOT_IDLE, 0.0f, MOT_SHIFT, MOT_LOOP);
}

/* From `height` above `masu` down onto it; the camera is already there. */
static void Drop(s32 player, s16 masu, s32 frames, float height)
{
    HuVecF to, pos;
    s32 i;

    mbMasuPosGet(masu, &to);
    for (i = 1; i <= frames; i++) {
        float t = (float)i / frames;
        pos = to;
        pos.y += height * (1.0f - t * t);
        mbPlayerPosSetV(player, &pos);
        HuPrcVSleep();
    }
    mbPlayerPosSetV(player, &to);
    mbCameraShakeSet(15, 100.0f);
    omVibrate(player, 15, 4, 4);
    mbPlayerMotionShiftSet(player, PLAYER_MOT_IDLE, 0.0f, MOT_SHIFT, MOT_LOOP);
}

/* The landing space's event, as PlayerTurn runs it after a move (0x80153E44-0x80153EB4): turn phase 7,
   mbev_MasuStop, then the camera back on the player, the player turned to the front and idle. */
static void SpaceEvent(s32 player, s16 masu)
{
    u8 phase = TURN_PHASE;

    TURN_PHASE = TURN_PHASE_SPACE;
    if (mbev_MasuStop(player, masu)) {
        mbCameraPlayerViewSet(player, 1);
        mbPlayerRotateStart(player, 0, 15);
        HuPrcSleep(15);
        mbCameraMoveWait();
        mbPlayerMotIdleSet(player);
    }
    TURN_PHASE = phase;
}

void PagodaCannonExec(void)
{
    s32 *work = PRC_WORK(HuPrcCurrentGet());
    s32 player = work[0];
    s16 start = GwPlayer[player].masuId, prev, land;
    HuVecF base, to;
    float heading = 180.0f, pitch = 0.0f;

    mbev_CapWait(work);
    mbCapEffUseCreate(player, work[2]);
    omVibrate(player, CROUCH_FRAMES, 4, 4);
    HuPrcSleep(CROUCH_FRAMES);
    mbev_CapRandomBonusCoin(player, work[2], 1);
    while (mbCapEffUseModeGet(player) >= 0) {
        HuPrcVSleep();
    }
    land = PagodaCannonTarget(start, &prev);
    OSReport("Pagoda Peak: Cannon orb, player %d from space %d to %d\n", player, start, land);

    mbMasuPosGet(start, &base);
    mbMasuPosGet(land, &to);
    if (land != start) {
        float dx = to.x - base.x, dz = to.z - base.z;
        heading = atan2(dx, dz) * RAD_TO_DEG;
        pitch = atan2(-(to.y - base.y), sqrtf(dx * dx + dz * dz)) * RAD_TO_DEG;
    }
    mbPlayerColSnapPlayerSet(player, 0);
    CannonCreate(&base);
    mbCameraMoveMasu(start, &cannonCamRot, NULL, CAMERA_ZOOM, -1.0f, 30);
    mbCameraMoveWait();
    ClimbIn(player, &base);
    Aim(Wrap180(heading), pitch, land != start);
    Fire(player, &base, heading, land == start);
    if (land == start) {
        Explode(player, &base, 180.0f + Wrap180(heading));
        PagodaCannonKill();
    } else {
        PagodaCannonKill();
        mbWipeFadeOut();
        GwPlayer[player].masuIdPrev = prev;
        GwPlayer[player].masuId = land;
        mbev_PlayerColMasuSet(player, land, 1);
        mbPlayerPosSetV(player, &to);   /* on the landing space before the camera moves */
        mbCameraPlayerViewSetFast(player, 1);
        mbCameraMoveWait();
        mbWipeFadeIn();
        Drop(player, land, DROP_FRAMES, DROP_HEIGHT);
    }
    mbev_PlayerColMasuSet(player, land, 1);
    mbPlayerColSnapPlayerSet(player, 1);
    if (land != start) {
        SpaceEvent(player, land);
    }
    mbCameraPlayerViewSet(player, 1);
    mbCameraMoveWait();
    HuPrcEnd();
}

/* CPU use (apply_pagoda_board_patch.py: mbCapComChanceGet's switch calls this for orb 8 through
   PAGODA_CANNON_COM_HOOK with the table's chance, MP7's own CPU row for the Cannon). As MP7's board hook does
   (w02dll .text 0x1334), it depends on where the player stands: no use when a shot can't move them (the space right
   before the summit), at least COM_FULL_CHANCE when a full shot fits before the summit, the table's chance in
   between. The CPU throws an orb away with 100 - this, so it drops a useless Cannon first. */
#define COM_FULL_CHANCE 50

static s32 RoomAhead(s16 start)
{
    s32 room = 0, guard;
    s16 masu = start;

    for (guard = 0; room < CANNON_MIN_STEPS + CANNON_STEP_RANGE - 1 && guard < WALK_LIMIT; guard++) {
        s16 next = NextSpace(masu);
        if (next < 0 || (mbMasuMAttrGet(next) & MASU_SUMMIT)) {
            break;
        }
        masu = next;
        if (mbMasuDispCheck(masu) && !PagodaBridgeBroken(masu)) {
            room++;
        }
    }
    return room;
}

s32 PagodaCannonComChance(s32 player, s32 chance)
{
    s32 room = RoomAhead(GwPlayer[player].masuId);

    if (room == 0) {
        return 0;
    }
    if (room >= CANNON_MIN_STEPS + CANNON_STEP_RANGE - 1 && chance < COM_FULL_CHANCE) {
        return COM_FULL_CHANCE;
    }
    return chance;
}

void PagodaCannonInit(void)
{
    PAGODA_CANNON_EXEC_HOOK = PagodaCannonExec;
    PAGODA_CANNON_KILL_HOOK = PagodaCannonKill;
    PAGODA_CANNON_COM_HOOK = PagodaCannonComChance;
}

void PagodaCannonClose(void)
{
    PagodaCannonKill();
    PAGODA_CANNON_EXEC_HOOK = NULL;
    PAGODA_CANNON_KILL_HOOK = NULL;
    PAGODA_CANNON_COM_HOOK = NULL;
}
