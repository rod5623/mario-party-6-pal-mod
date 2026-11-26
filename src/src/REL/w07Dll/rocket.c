/*
 * Pagoda Peak's bottle rocket, ported from MP7 w02dll .text 0x2450 (event), 0x284C (picking a rocket) and
 * 0x2D7C (the launch); records 1-6. Space 23 (MP7 flag 0x80000000).
 *
 * As in MP7: the screen dissolves to the stand (the space's type-0x2000 side node, 81), where two bottle
 * rockets (w07.bin FILE_ROCKET, MP7 w02.bin 0x0B) stand side by side in front of the player. The offer (1) and
 * "Will you give it a shot?" (2; CPU players say yes). On no, the player goes back to the space. On yes:
 * "Choose your favorite bottle rocket" (3), the player steps between the rockets with left/right and
 * confirms with A (help line 6; a CPU picks one at random), "One moment" (4), "Cheerio" (5), and the
 * rocket takes off. 75% of launches land on the space flagged index 1 under 0x60000000 (space 76, near
 * the top), the rest on index 2 (space 27, just above the start). The choice doesn't change the odds, in
 * MP7 either.
 *
 * Changed from MP7: the flight. MP7 swaps in a flying rocket (0x0C) and flies it along a path with smoke;
 * here the chosen rocket lifts off with the player, the screen fades, and the player drops onto the
 * landing space. MP7's sounds are left out.
 */
#include "pagoda.h"

#define ROCKETS 2
#define ROCKET_SPACING 300.0f
#define STAND_LEFT 150.0f      /* MP7 .rodata 0x240: the left rocket, the player's x offset, the rockets' height */
#define STAND_DEPTH 100.0f     /* MP7 .rodata 0x1E8 */
#define STAND_ZOOM 2400.0f
#define FACE_ROCKETS 180
#define SUCCESS_PERCENT 75
#define LAND_MASK 0x60000000
#define LIFTOFF_FRAMES 90
#define DROP_HEIGHT 1500.0f
#define DROP_FRAMES 30
#define CPU_THINK 40

#define MES_OFFER PAGODA_MES(1)
#define MES_TRY PAGODA_MES(2)
#define MES_CHOOSE PAGODA_MES(3)
#define MES_WAIT PAGODA_MES(4)
#define MES_CHEERIO PAGODA_MES(5)
#define MES_SELECT PAGODA_MES(6)

static MBOBJ rockets[ROCKETS] = { -1, -1 };

static void RocketsKill(void)
{
    s32 i;

    for (i = 0; i < ROCKETS; i++) {
        if (rockets[i] >= 0) {
            mbObjKill(rockets[i]);
            rockets[i] = -1;
        }
    }
}

void PagodaRocketKill(void)
{
    RocketsKill();
}

static void StatusRefresh(void)
{
    mbStatusDispSetAll(FALSE);
    while (!mbStatusOffCheckAll()) {
        HuPrcVSleep();
    }
    mbStatusDispSetAll(TRUE);
}

/* The player stands in front of rocket `i`. */
static void StandAt(s32 player, HuVecF *stand, s32 i)
{
    HuVecF pos;

    pos.x = stand->x - STAND_LEFT + ROCKET_SPACING * i;
    pos.y = stand->y;
    pos.z = stand->z + STAND_DEPTH;
    mbPlayerPosSetV(player, &pos);
}

/* MP7 .text 0x284C: left/right moves between the rockets, A picks one; a CPU thinks, then picks at random. */
static s32 ChooseRocket(s32 player, HuVecF *stand)
{
    s16 help = mbWinCreateHelp(MES_SELECT);
    s32 pick = 0;
    s32 wait = CPU_THINK;
    s32 pad = GwPlayer[player].padNo;

    for (;;) {
        s32 move = 0;
        HuPrcVSleep();
        if (GwPlayer[player].comF) {
            if (--wait <= 0) {
                pick = mbRandMod(ROCKETS);
                StandAt(player, stand, pick);
                break;
            }
            continue;
        }
        if ((HuPadBtnDown[pad] | HuPadDStkDown[pad]) & PAD_BUTTON_LEFT) {
            move = -1;
        } else if ((HuPadBtnDown[pad] | HuPadDStkDown[pad]) & PAD_BUTTON_RIGHT) {
            move = 1;
        }
        if (move && pick + move >= 0 && pick + move < ROCKETS) {
            pick += move;
            StandAt(player, stand, pick);
        }
        if (HuPadBtnDown[pad] & PAD_BUTTON_A) {
            break;
        }
    }
    mbWinKill(help);
    return pick;
}

static void LiftOff(s32 player, s32 pick)
{
    HuVecF rocketPos, playerPos;
    s32 i;

    mbObjPosGet(rockets[pick], &rocketPos);
    mbPlayerPosGet(player, &playerPos);
    omVibrate(player, 30, 4, 4);
    for (i = 0; i < LIFTOFF_FRAMES; i++) {
        float rise = 0.5f * i * i;   /* speeding up */
        mbObjPosSet(rockets[pick], rocketPos.x, rocketPos.y + rise, rocketPos.z);
        playerPos.y += i;
        mbPlayerPosSetV(player, &playerPos);
        HuPrcVSleep();
    }
}

/* The player drops out of the sky onto `masu`, which becomes their space. */
static void Land(s32 player, s16 masu)
{
    HuVecF pos;
    s32 i;

    GwPlayer[player].masuId = masu;
    mbMasuPosGet(masu, &pos);
    mbev_PlayerColMasuSet(player, masu, 1);
    mbCameraPlayerViewSetFast(player, 1);
    mbCameraMoveWait();
    pos.y += DROP_HEIGHT;
    mbPlayerPosSetV(player, &pos);
    mbWipeFadeIn();
    for (i = 1; i <= DROP_FRAMES; i++) {
        float t = (float)i / DROP_FRAMES;
        HuVecF at = pos;
        at.y -= DROP_HEIGHT * t * t;
        mbPlayerPosSetV(player, &at);
        HuPrcVSleep();
    }
    mbCameraShakeSet(15, 100.0f);
    omVibrate(player, 15, 4, 4);
    mbPlayerMotionShiftSet(player, PLAYER_MOT_IDLE, 0.0f, KOOPA_MOT_SHIFT, KOOPA_MOT_LOOP);
}

/* Returns 0 once the event has run. */
s32 PagodaRocket(s32 player, s16 masu)
{
    s16 standMasu = mbMasuAttrFindLink(masu, 0x2000);
    HuVecF stand, masuPos;
    s16 win;
    s32 i, pick, index;
    s16 dest;

    if (standMasu < 0) {
        return 1;
    }
    mbMasuPosGet(standMasu, &stand);
    mbMasuPosGet(masu, &masuPos);
    mbWipeDissolveFadeOut();
    mbCameraMoveMasu(standMasu, NULL, NULL, STAND_ZOOM, -1.0f, -1);
    mbCameraMoveWait();
    StandAt(player, &stand, 0);
    mbPlayerRotateStart(player, FACE_ROCKETS, 1);
    for (i = 0; i < ROCKETS; i++) {
        rockets[i] = mbObjCreate(PagodaBoardDir() | FILE_ROCKET, NULL, 1);
        mbObjPosSet(rockets[i], stand.x - STAND_LEFT + ROCKET_SPACING * i, stand.y + STAND_LEFT,
                    stand.z - STAND_DEPTH);
    }
    PagodaDirClose();
    mbWipeDissolveFadeIn();

    PagodaSay(MES_OFFER, -1);
    win = mbWinCreateChoice(2, MES_TRY, -1, 0);
    if (GwPlayer[player].comF) {
        mbComChoiceLeftSet();
    }
    mbWinWait(win);
    if (mbWinChoiceGet(win) != 0) {
        mbWipeDissolveFadeOut();
        mbPlayerPosSetV(player, &masuPos);
        mbCameraPlayerViewSetFast(player, 2);
        mbCameraMoveWait();
        RocketsKill();
        mbWipeDissolveFadeIn();
        StatusRefresh();
        return 0;
    }

    PagodaSay(MES_CHOOSE, -1);
    pick = ChooseRocket(player, &stand);
    PagodaSay(MES_WAIT, -1);
    PagodaSay(MES_CHEERIO, -1);
    LiftOff(player, pick);
    mbWipeFadeOut();
    RocketsKill();

    index = mbRandMod(100) < SUCCESS_PERCENT ? 1 : 2;
    dest = mbMasuFind_MAttrMatchIdGet(-1, mbev_MasuAttrGet(index, LAND_MASK), LAND_MASK);
    Land(player, dest >= 0 ? dest : masu);
    StatusRefresh();
    return 0;
}
