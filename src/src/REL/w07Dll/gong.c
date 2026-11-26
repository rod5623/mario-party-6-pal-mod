/*
 * Pagoda Peak's Gong of Fate, ported from MP7 w02dll: setup .text 0x95CC, event 0x9708 (records 18-23).
 *
 * Two gongs (w07.bin FILE_GONG, MP7 w02.bin 0x13) hang on the map's h_dora0 and h_dora1 joints, motion
 * paused, each with the price sign on its h_rate1 joint (the summit's sign, one model drawn on every joint
 * that hooks it). Gong i belongs to the "?" space whose flag is index i+1 under 0x60000 (MP7 spaces 19 and
 * 38).
 *
 * The event, as in MP7: the camera frames the gong and the status boxes hide; the player turns to the gong
 * and Master Koopa drops in beside the space and explains (records 18, 19). While "Ring the gong" (20) is
 * up the sign flicks through the four prices; a human stops it with A, a CPU after 30-59 frames. The
 * player jumps at the gong, which swings and shakes the camera, and the price where the sign stopped
 * becomes the Star price (21; 22 if it didn't change). Master Koopa gives 1-10 coins (23) and flies off.
 *
 * The player's collision is put back on the space (mbev_PlayerColMasuSet) after the jump back and at the end,
 * as the events that move a player and don't sink them do: ev_MasuHatena turns the player's collision snap
 * off (mbPlayerColSnapPlayerSet(player, 0)) before the "?" hook and doesn't turn it back on.
 *
 * Changed from MP7: MP6's own player motions (the plain jump and the Star cheer; MP7's motion numbers
 * differ), MP7's sounds left out, and the sign jumps straight to each price instead of rolling.
 */
#include "pagoda.h"
#include "stdio.h"

#define GONGS 2
#define GONG_Y 250.0f            /* above the h_dora joint (MP7 .rodata 0x3B4) */
#define JUMP_FRAMES 24
#define JUMP_BACK_FRAMES 30
#define JUMP_HEIGHT 150.0f
#define CPU_WAIT_MIN 30
#define CPU_WAIT_RANGE 30
#define GIFT_MAX 10

#define MES_WELCOME PAGODA_MES(18)
#define MES_DECIDE PAGODA_MES(19)
#define MES_RING PAGODA_MES(20)
#define MES_NEW_PRICE PAGODA_MES(21)
#define MES_SAME_PRICE PAGODA_MES(22)
#define MES_GIFT PAGODA_MES(23)

typedef struct {
    MBOBJ obj;
    HuVecF pos;
    s16 masu;
} GONG;

static GONG gongs[GONGS] = { { -1 }, { -1 } };
static char *gongJoint[GONGS] = { "h_dora0", "h_dora1" };
static char signJoint[] = "h_rate1";
/* MP7 .rodata 0x23C/0x3F8 (zoom), 0x3B8 (Master Koopa beside the space), 0x3D0 and 0x3DC (camera) */
static float camZoom[GONGS] = { 2400.0f, 3000.0f };
static HuVecF koopaOffset[GONGS] = { { -400.0f, 150.0f, -400.0f }, { 500.0f, 250.0f, -200.0f } };
static HuVecF camRot = { -20.0f, 0.0f, 0.0f };
static HuVecF camOffset = { 0.0f, 300.0f, -200.0f };

void PagodaGongInit(MBOBJ map)
{
    s32 i;

    for (i = 0; i < GONGS; i++) {
        GONG *gong = &gongs[i];

        gong->obj = mbObjCreate(PagodaBoardDir() | FILE_GONG, NULL, 1);
        mbObjAttrSet(gong->obj, HU3D_MOTATTR_PAUSE);
        mbObjHookSet(map, gongJoint[i], gong->obj);
        mbObjHookSet(gong->obj, signJoint, PagodaSign());
        Hu3DModelObjPosGet(mbObjModelIDGet(map), gongJoint[i], &gong->pos);
        gong->pos.y += GONG_Y;
        gong->masu = mbMasuFind_MAttrMatchIdGet(-1, mbev_MasuAttrGet(i + 1, MASU_GONG_MASK), MASU_GONG_MASK);
    }
}

/* The map hooks the gongs: board.c resets the map's hooks first. */
void PagodaGongKill(void)
{
    s32 i;

    for (i = 0; i < GONGS; i++) {
        if (gongs[i].obj >= 0) {
            mbObjHookReset(gongs[i].obj);
            mbObjKill(gongs[i].obj);
            gongs[i].obj = -1;
        }
    }
}

static s32 FaceAngle(float dx, float dz)
{
    return (s32)(atan2(dx, dz) * RAD_TO_DEG);
}

/* The player jumps from `from` to `to` (or back) along an arc. */
static void JumpArc(s32 player, HuVecF *from, HuVecF *to, s32 frames)
{
    HuVecF pos;
    s32 i;

    for (i = 0; i < frames; i++) {
        float t = (float)i / (frames - 1);
        pos.x = from->x + t * (to->x - from->x);
        pos.y = from->y + t * (to->y - from->y) + JUMP_HEIGHT * PagodaSin(180.0f * t);
        pos.z = from->z + t * (to->z - from->z);
        mbPlayerPosSetV(player, &pos);
        HuPrcVSleep();
    }
}

/* The sign flicks through the prices until the player presses A (a CPU waits a random time). */
static s32 SpinPrice(s32 player)
{
    s16 help = mbWinCreateHelp(MES_RING);
    s32 cpuWait = CPU_WAIT_MIN + mbRandMod(CPU_WAIT_RANGE);
    s32 level;
    BOOL stop;

    do {
        if (GwPlayer[player].comF) {
            stop = cpuWait-- <= 0;
        } else {
            stop = (HuPadBtnDown[GwPlayer[player].padNo] & PAD_BUTTON_A) != 0;
        }
        level = mbRandMod(PRICE_LEVELS);
        PagodaSignShow(level);
        HuPrcVSleep();
    } while (!stop);
    mbWinKill(help);
    return level;
}

static void GongEvent(s32 player, GONG *gong)
{
    s32 g = gong - gongs;
    s32 oldLevel = PagodaPriceLevel();
    s32 level;
    HuVecF masuPos, koopaPos, playerPos;
    char price[16];

    mbCameraMoveMasu(gong->masu, &camRot, &camOffset, camZoom[g], -1.0f, 30);
    mbCameraMoveWait();
    mbStatusDispSetAll(FALSE);
    while (!mbStatusOffCheckAll()) {
        HuPrcVSleep();
    }
    mbMasuPosGet(gong->masu, &masuPos);
    PagodaTurn(player, FaceAngle(gong->pos.x - masuPos.x, gong->pos.z - masuPos.z));

    koopaPos.x = masuPos.x + koopaOffset[g].x;
    koopaPos.y = masuPos.y + koopaOffset[g].y;
    koopaPos.z = masuPos.z + koopaOffset[g].z;
    PagodaKoopaArrive(&koopaPos, FaceAngle(-koopaOffset[g].x, -koopaOffset[g].z));
    PagodaSay(MES_WELCOME, player);
    PagodaSay(MES_DECIDE, player);

    level = SpinPrice(player);
    mbPlayerPosGet(player, &playerPos);
    mbPlayerMotionShiftSet(player, PLAYER_MOT_JUMP, 0.0f, KOOPA_MOT_SHIFT, 0);
    JumpArc(player, &playerPos, &gong->pos, JUMP_FRAMES);
    mbObjAttrReset(gong->obj, HU3D_MOTATTR_PAUSE);
    mbCameraShakeSet(30, 200.0f);
    omVibrate(player, 20, 4, 4);
    PagodaPriceLevelSet(level);
    PagodaSignShow(level);
    mbPlayerMotionShiftSet(player, PLAYER_MOT_JUMP, 0.0f, KOOPA_MOT_SHIFT, 0);
    JumpArc(player, &gong->pos, &playerPos, JUMP_BACK_FRAMES);
    mbev_PlayerColMasuSet(player, gong->masu, 1);
    mbPlayerMotionShiftSet(player, PLAYER_MOT_LAND, 0.0f, KOOPA_MOT_SHIFT, 0);
    HuPrcSleep(10);
    mbPlayerMotionShiftSet(player, PLAYER_MOT_IDLE, 0.0f, KOOPA_MOT_SHIFT, KOOPA_MOT_LOOP);

    PagodaKoopaMotion(KOOPA_MOT_GIVE, 0);
    sprintf(price, "%d", PagodaStarPrice());
    {
        s16 win = mbWinCreate(2, MES_NEW_PRICE, -1);
        mbWinInsertMesSet(win, (u32)price, 0);
        mbWinWait(win);
    }
    PagodaKoopaMotion(KOOPA_MOT_TALK, KOOPA_MOT_LOOP);
    if (level == oldLevel) {
        PagodaSay(MES_SAME_PRICE, -1);
    }
    PagodaSay(MES_GIFT, -1);
    PagodaTurn(player, 0);
    mbCoinAddDispExec(player, 1 + mbRandMod(GIFT_MAX), 1, 0);
    mbPlayerMotionShiftSet(player, PLAYER_MOT_JOY, 0.0f, KOOPA_MOT_SHIFT, 0);
    HuPrcSleep(30);

    PagodaKoopaLeave(&koopaPos);
    mbPlayerPosSetV(player, &playerPos);
    mbev_PlayerColMasuSet(player, gong->masu, 1);
    mbPlayerMotionShiftSet(player, PLAYER_MOT_IDLE, 0.0f, KOOPA_MOT_SHIFT, KOOPA_MOT_LOOP);
    mbObjMotionTimeSet(gong->obj, 0.0f);
    mbObjAttrSet(gong->obj, HU3D_MOTATTR_PAUSE);
    mbStatusDispSetAll(TRUE);
    mbCameraPlayerViewSet(player, 1);
    mbCameraMoveWait();
}

/* Returns 1 if `masu` isn't a gong space (the "?" hook's "nothing happened"), else 0 after the event. */
s32 PagodaGong(s32 player, s16 masu)
{
    s32 i;

    for (i = 0; i < GONGS; i++) {
        if (gongs[i].masu == masu && gongs[i].obj >= 0) {
            GongEvent(player, &gongs[i]);
            return 0;
        }
    }
    return 1;
}
