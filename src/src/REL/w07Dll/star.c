/*
 * Pagoda Peak's Star: Master Koopa sells it at the summit (space 54), ported from MP7 w02dll .text 0x100C4.
 *
 * MP7's rules (bank 0x14 records 43-46): the price starts at 10 coins and goes up by 10 every time
 * someone buys one, up to 40. The flow follows MP7's function, with MP6's own window, coin and Star
 * calls (the same ones Castaway Bay's and Snowflake Lake's RELs use):
 *   greeting with the player's name and the price (record 7) -> too few coins (11) or the Yes/No choice
 *   (8) -> declined (12) or "take the Star" (9), pay, mbStarGetExec, the price goes up -> farewell (10).
 * CPU players always buy, as in MP7 (mbComChoiceUpSet).
 *
 * After every visit (bought, declined or too poor, as in MP7) the player goes back to the start; the summit
 * counts as a step and the rest of the move carries on from the start (MoveEnd). As in MP7 (.text 0x115A8),
 * Master Koopa's cloud (w02.bin 0x26) spirals in, the player hops on, it carries them down MP7's 18-point path
 * (a Bezier curve) with the camera on them, they hop off onto the start and the cloud flies on. MP7's own
 * player helpers for boarding (missing in MP6) are plain hops here, and its trail particle is left out.
 *
 * The summit (MP7 w02dll .text 0x6E4, 0x1A70 and 0xFF08): Master Koopa's house with its platform (w07.bin
 * FILE_HOUSE, MP7 0x25), its motion paused, and the price sign (FILE_SIGN, MP7 0x14) hooked on the house's
 * h_rate0 joint. The sign's motion is paused too; its frame shows the price (signTime).
 * Master Koopa (FILE_KOOPA and the five after it, MP7 0x35-0x3A) is hidden until a player reaches the summit. Then, as in MP7:
 * the camera frames the summit, the house's motion runs (its doors open), he appears 700 units behind the
 * space, walks 300 units towards the player over 120 frames and talks; he hands over the Star with motion
 * 4 and waves goodbye with motion 5. Once the screen has faded out he is hidden, the house goes back to
 * frame 0 and the sign shows the new price (MP7 animates the sign after the fade; here it just changes).
 *
 * Not ported yet: MP7's sounds (its sound ids differ), the particles on the house and the cloud.
 */
#include "pagoda.h"
#include "stdio.h"

#define SUMMIT 54
#define MASU_START_ATTR 0x8000   /* the start space's type bit; MP7 finds it the same way */
#define PRICE_STEP 10
#define WIN_TYPE 2
#define NO_SPEAKER -1

#define MES_GREETING PAGODA_MES(7)
#define MES_BUY PAGODA_MES(8)
#define MES_TAKE PAGODA_MES(9)
#define MES_FAREWELL PAGODA_MES(10)
#define MES_NO_COINS PAGODA_MES(11)
#define MES_DECLINED PAGODA_MES(12)
/* the board explanation (MP7 .text 0x9FC): the trail and Master Koopa, the price, its rises, its cap, Bowser */
#define MES_INST_TRAIL PAGODA_MES(43)
#define MES_INST_PRICE PAGODA_MES(44)
#define MES_INST_RISE PAGODA_MES(45)
#define MES_INST_CAP PAGODA_MES(46)
#define MES_INST_BOWSER PAGODA_MES(47)
#define INST_SIGN_FRAMES 30

#define KOOPA_Y 68.0f
#define KOOPA_Z_FROM -700.0f   /* relative to the summit space; MP7 w02dll .rodata */
#define KOOPA_WALK 300.0f
#define KOOPA_WALK_FRAMES 120
#define FACE_KOOPA 180

/* The trip back down (MP7 w02dll .text 0x115A8): the cloud's path, .data 0x2A0, from above the summit to above
   the start, and its timings (.rodata 0x2AC, 0x4B0, 0x5DC, 0x334, 0x5E0, 0x498, 0x1F8) */
#define FLIGHT_POINTS 18
#define FLIGHT_IN_FRAMES 120
#define FLIGHT_IN_TURN 720.0f
#define FLIGHT_IN_RADIUS 400.0f
#define FLIGHT_IN_RISE 800.0f
#define FLIGHT_IN_Z 50.0f
#define FLIGHT_FRAMES 300
#define FLIGHT_OUT_FRAMES 60
#define FLIGHT_OUT_DIST 2000.0f
#define FLIGHT_OUT_RISE 400.0f
#define FLIGHT_ZOOM 2400.0f   /* MP7: 2000 */
#define HOP_FRAMES 30
#define HOP_HEIGHT 150.0f
static HuVecF flightPath[FLIGHT_POINTS] = {
    { -433.4f, 6317.8f, -4596.3f }, { -1099.3f, 6394.1f, -4375.3f }, { -1585.7f, 6278.9f, -3876.8f },
    { -1877.2f, 6026.5f, -3280.6f }, { -2037.8f, 5702.0f, -2667.4f }, { -2132.7f, 5355.5f, -2052.1f },
    { -2184.3f, 4997.0f, -1438.4f }, { -2207.6f, 4609.6f, -840.8f }, { -2210.1f, 4202.5f, -255.9f },
    { -2193.7f, 3795.8f, 329.1f }, { -2157.0f, 3391.7f, 914.9f }, { -2089.9f, 2986.1f, 1496.9f },
    { -1977.9f, 2577.0f, 2069.4f }, { -1803.5f, 2173.6f, 2630.0f }, { -1555.0f, 1810.2f, 3189.6f },
    { -1218.0f, 1549.4f, 3758.5f }, { -804.3f, 1429.5f, 4324.9f }, { -355.9f, 1394.6f, 4877.5f },
};
static HuVecF flightCamRot = { -35.0f, 0.0f, 0.0f };   /* .data 0x67C */

static s32 koopaMot[] = { DIR_BOARD | (FILE_KOOPA + 1), DIR_BOARD | (FILE_KOOPA + 2), DIR_BOARD | (FILE_KOOPA + 3),
                          DIR_BOARD | (FILE_KOOPA + 4), DIR_BOARD | (FILE_KOOPA + 5), -1 };
static MBOBJ koopa = -1;
static MBOBJ cloud = -1;   /* he rides it when he drops in at the events (MP7 .text 0x1498, scale 0.75) */
static MBOBJ house = -1;
static MBOBJ sign = -1;
static char signJoint[] = "h_rate0";
static float signTime[PRICE_LEVELS] = { 0.0f, 9.0f, 19.0f, 29.0f }; /* MP7 w02dll .rodata 0x200 */

/* MP7's summit camera (w02dll .text 0x10290) */
static HuVecF summitCamRot = { -20.0f, 0.0f, 0.0f };
static HuVecF summitCamOffset = { 0.0f, 200.0f, 0.0f };

/* The price level lives in this board's save work (GwSystem.boardWork), so it survives saving mid-game.
   Bits 0-1 of the first word; a new game starts it at 0. */
#define PRICE_LEVEL (GwSystem.boardWork[0] & 3)

s32 PagodaPriceLevel(void)
{
    return PRICE_LEVEL;
}

void PagodaPriceLevelSet(s32 level)
{
    GwSystem.boardWork[0] = (GwSystem.boardWork[0] & ~3) | (level & 3);
}

s32 PagodaStarPrice(void)
{
    return PRICE_STEP * (PRICE_LEVEL + 1);
}

static void PriceUp(void)
{
    if (PRICE_LEVEL < PRICE_LEVELS - 1) {
        PagodaPriceLevelSet(PRICE_LEVEL + 1);
    }
}

/* The sign's frame shows a price; it hangs on the house and on both gongs (the same model). */
void PagodaSignShow(s32 level)
{
    mbObjMotionTimeSet(sign, signTime[level & 3]);
}

MBOBJ PagodaSign(void)
{
    return sign;
}

MBOBJ PagodaKoopa(void)
{
    return koopa;
}

/* The house's motion is paused except while Master Koopa comes out. */
static void HouseClose(void)
{
    mbObjAttrSet(house, HU3D_MOTATTR_PAUSE);
    mbObjMotionTimeSet(house, 0.0f);
}

void PagodaSay(u32 mes, s32 player)
{
    s16 win = mbWinCreate(WIN_TYPE, mes, NO_SPEAKER);
    if (player >= 0) {
        mbWinInsertMesSet(win, mbPlayerNameMesGet(player), 0);
    }
    mbWinWait(win);
}

void PagodaTurn(s32 player, s32 angle)
{
    mbPlayerRotateStart(player, angle, 15);
    while (!mbPlayerRotateCheck(player)) {
        HuPrcVSleep();
    }
}

void PagodaKoopaMotion(s32 motNo, u32 attr)
{
    mbObjMotionShiftSet(koopa, motNo, 0.0f, KOOPA_MOT_SHIFT, attr);
}

/* Master Koopa drops in from KOOPA_DROP above `pos` (up = FALSE) or flies back up, easing out as MP7 does
   (w02dll .text 0x9A08 and 0xA388: y + 900 * (1 + cos(90 + 90t))). */
static void KoopaDrop(HuVecF *pos, BOOL up)
{
    s32 i;

    for (i = 0; i < KOOPA_DROP_FRAMES; i++) {
        float t = (float)i / (KOOPA_DROP_FRAMES - 1);
        float y;
        if (up) {
            t = 1.0f - t;
        }
        y = pos->y + KOOPA_DROP * (1.0f + PagodaCos(90.0f + 90.0f * t));
        mbObjPosSet(koopa, pos->x, y, pos->z);
        mbObjPosSet(cloud, pos->x, y, pos->z);
        HuPrcVSleep();
    }
}

/* The events' entrance: he drops in at `pos` facing `rotY`, then takes his talking pose. */
/* Master Koopa on his cloud at `pos`, facing `rotY`. */
void PagodaKoopaShowAt(HuVecF *pos, float rotY)
{
    mbObjRotYSet(koopa, rotY);
    mbObjRotYSet(cloud, rotY);
    mbObjMotionSet(koopa, KOOPA_MOT_IDLE, KOOPA_MOT_LOOP);
    mbObjPosSetV(koopa, pos);
    mbObjPosSetV(cloud, pos);
    mbObjDispSet(koopa, TRUE);
    mbObjDispSet(cloud, TRUE);
}

void PagodaKoopaArrive(HuVecF *pos, float rotY)
{
    HuVecF top = *pos;

    top.y += KOOPA_DROP;
    PagodaKoopaShowAt(&top, rotY);
    KoopaDrop(pos, FALSE);
    PagodaKoopaMotion(KOOPA_MOT_TALK, KOOPA_MOT_LOOP);
}

void PagodaKoopaHide(void)
{
    mbObjDispSet(koopa, FALSE);
    mbObjDispSet(cloud, FALSE);
}

/* He waves and flies off from `pos`. */
void PagodaKoopaLeave(HuVecF *pos)
{
    PagodaKoopaMotion(KOOPA_MOT_BYE, KOOPA_MOT_LOOP);
    KoopaDrop(pos, TRUE);
    PagodaKoopaHide();
}

/* MP7 w02dll .text 0x10174-0x10414: show Master Koopa behind the summit, turn the player to him, frame the
   summit, then walk him in. */
static void KoopaArrive(s32 player)
{
    HuVecF pos;
    s32 i;

    mbMasuPosGet(SUMMIT, &pos);
    pos.y += KOOPA_Y;
    pos.z += KOOPA_Z_FROM;
    mbObjPosSet(koopa, pos.x, pos.y, pos.z);
    mbObjRotYSet(koopa, 0.0f);
    mbObjMotionSet(koopa, KOOPA_MOT_IDLE, KOOPA_MOT_LOOP);
    mbObjDispSet(koopa, TRUE);
    PagodaTurn(player, FACE_KOOPA);
    mbCameraMoveMasu(SUMMIT, &summitCamRot, &summitCamOffset, 2200.0f, -1.0f, 30);
    mbCameraMoveWait();
    mbObjAttrReset(house, HU3D_MOTATTR_PAUSE);
    HuPrcSleep(30);
    PagodaKoopaMotion(KOOPA_MOT_WALK, KOOPA_MOT_LOOP);
    for (i = 0; i < KOOPA_WALK_FRAMES; i++) {
        mbObjPosSet(koopa, pos.x, pos.y, pos.z + KOOPA_WALK * i / (KOOPA_WALK_FRAMES - 1));
        HuPrcVSleep();
    }
    PagodaKoopaMotion(KOOPA_MOT_TALK, KOOPA_MOT_LOOP);
}

static void StarSale(s32 player)
{
    char price[16];
    s32 cost = PagodaStarPrice();
    s16 win;
    s32 choice;

    sprintf(price, "%d", cost);
    KoopaArrive(player);

    win = mbWinCreate(WIN_TYPE, MES_GREETING, NO_SPEAKER);
    mbWinInsertMesSet(win, mbPlayerNameMesGet(player), 0);
    mbWinInsertMesSet(win, (u32)price, 1);
    mbWinWait(win);

    if (mbPlayerCoinGet(player) < cost) {
        PagodaSay(MES_NO_COINS, -1);
        PagodaKoopaMotion(KOOPA_MOT_BYE, KOOPA_MOT_LOOP);
        return;
    }
    win = mbWinCreateChoice(WIN_TYPE, MES_BUY, NO_SPEAKER, 0);
    mbWinInsertMesSet(win, (u32)price, 0);
    if (GwPlayer[player].comF) {
        mbComChoiceUpSet();
    }
    mbWinWait(win);
    choice = mbWinChoiceGet(win);
    if (choice != 0) {
        PagodaSay(MES_DECLINED, -1);
        PagodaKoopaMotion(KOOPA_MOT_BYE, KOOPA_MOT_LOOP);
        return;
    }
    PagodaSay(MES_TAKE, -1);
    PagodaKoopaMotion(KOOPA_MOT_GIVE, 0);
    mbCoinAddDispExec(player, -cost, 1, 0);
    mbStarGetExec(player);
    PriceUp();
    PagodaKoopaMotion(KOOPA_MOT_TALK, KOOPA_MOT_LOOP);
    PagodaSay(MES_FAREWELL, player);
    PagodaKoopaMotion(KOOPA_MOT_BYE, KOOPA_MOT_LOOP);
}

/* The player jumps from `from` to `to` along an arc. */
static void Hop(s32 player, HuVecF *from, HuVecF *to)
{
    HuVecF pos;
    s32 i;

    mbPlayerRotYSet(player, atan2(to->x - from->x, to->z - from->z) * RAD_TO_DEG);
    mbPlayerMotionShiftSet(player, PLAYER_MOT_JUMP, 0.0f, KOOPA_MOT_SHIFT, 0);
    for (i = 0; i < HOP_FRAMES; i++) {
        float t = (float)i / (HOP_FRAMES - 1);
        pos.x = from->x + t * (to->x - from->x);
        pos.y = from->y + t * (to->y - from->y) + HOP_HEIGHT * PagodaSin(180.0f * t);
        pos.z = from->z + t * (to->z - from->z);
        mbPlayerPosSetV(player, &pos);
        HuPrcVSleep();
    }
    mbPlayerMotionShiftSet(player, PLAYER_MOT_IDLE, 0.0f, KOOPA_MOT_SHIFT, KOOPA_MOT_LOOP);
}

/* A point on the Bezier curve through every point of flightPath (de Casteljau, as MP7 .text 0x11B14). */
static void FlightPoint(float t, HuVecF *out)
{
    HuVecF p[FLIGHT_POINTS];
    s32 n, i;

    for (i = 0; i < FLIGHT_POINTS; i++) {
        p[i] = flightPath[i];
    }
    for (n = 1; n < FLIGHT_POINTS; n++) {
        for (i = 0; i < FLIGHT_POINTS - n; i++) {
            p[i].x += t * (p[i + 1].x - p[i].x);
            p[i].y += t * (p[i + 1].y - p[i].y);
            p[i].z += t * (p[i + 1].z - p[i].z);
        }
    }
    *out = p[0];
}

/* MP7 .text 0x115A8: Master Koopa's cloud carries the player from the summit back to the start. */
static void ReturnToStart(s32 player)
{
    HuVecF pos, prev, masuPos, dir, *top = &flightPath[0], *end = &flightPath[FLIGHT_POINTS - 1];
    s16 start = mbMasuFind_AttrIdGet(-1, MASU_START_ATTR);
    float len;
    s32 i;

    if (start < 0) {
        mbObjDispSet(koopa, FALSE);
        HouseClose();
        PagodaSignShow(PRICE_LEVEL);
        return;
    }
    mbCameraMoveObj(mbPlayerObjIDGet(player), &flightCamRot, NULL, FLIGHT_ZOOM, -1.0f, 30);
    mbCameraMoveWait();

    /* the cloud spirals in onto the first point (.text 0x117F0: 720 degrees, 400 out and 800 up at the start) */
    mbObjRotYSet(cloud, 0.0f);
    mbObjDispSet(cloud, TRUE);
    for (i = 0; i < FLIGHT_IN_FRAMES; i++) {
        float t = (float)i / (FLIGHT_IN_FRAMES - 1);
        float s = 1.0f - t;
        mbObjPosSet(cloud, top->x + FLIGHT_IN_RADIUS * s * PagodaCos(FLIGHT_IN_TURN * t), top->y + FLIGHT_IN_RISE * s,
                    top->z + FLIGHT_IN_RADIUS * s * PagodaSin(FLIGHT_IN_TURN * t) + FLIGHT_IN_Z);
        HuPrcVSleep();
    }
    mbObjPosGet(cloud, &pos);
    mbPlayerPosGet(player, &prev);
    Hop(player, &prev, &pos);
    HuPrcSleep(30);

    /* down the mountain (.text 0x11AAC: 300 frames along the curve) */
    prev = pos;
    for (i = 1; i < FLIGHT_FRAMES; i++) {
        FlightPoint((float)i / (FLIGHT_FRAMES - 1), &pos);
        mbObjPosSetV(cloud, &pos);
        mbPlayerPosSetV(player, &pos);
        if (pos.x != prev.x || pos.z != prev.z) {
            mbPlayerRotYSet(player, atan2(pos.x - prev.x, pos.z - prev.z) * RAD_TO_DEG);
        }
        prev = pos;
        HuPrcVSleep();
    }

    /* off onto the start, and the cloud flies on and up (.text 0x11C5C: 2000 along its heading, 400 up) */
    mbMasuPosGet(start, &masuPos);
    Hop(player, &pos, &masuPos);
    GwPlayer[player].masuId = start;
    mbev_PlayerColMasuSet(player, start, 1);
    mbPlayerRotYSet(player, 0.0f);
    dir.x = end->x - flightPath[FLIGHT_POINTS - 2].x;
    dir.y = end->y - flightPath[FLIGHT_POINTS - 2].y;
    dir.z = end->z - flightPath[FLIGHT_POINTS - 2].z;
    len = sqrtf(dir.x * dir.x + dir.y * dir.y + dir.z * dir.z);
    for (i = 1; i < FLIGHT_OUT_FRAMES; i++) {
        float t = (float)i / (FLIGHT_OUT_FRAMES - 1);
        float d = len > 0.0f ? FLIGHT_OUT_DIST * t / len : 0.0f;
        mbObjPosSet(cloud, end->x + dir.x * d, end->y + dir.y * d + FLIGHT_OUT_RISE * PagodaSin(90.0f * t),
                    end->z + dir.z * d);
        HuPrcVSleep();
    }
    mbObjDispSet(cloud, FALSE);

    /* the summit is off screen now */
    mbObjDispSet(koopa, FALSE);
    HouseClose();
    PagodaSignShow(PRICE_LEVEL);
    mbCameraFocusObjSet(-1);
    mbCameraPlayerViewSet(player, 1);
    mbCameraMoveWait();
}

/* mbev_MasuMoveEndSet: called (through mbev_MasuMasuStart) as a player steps onto each space. In PlayerMove
   (fn_801548D8), 0 lets the engine re-read masuId, run mbev_MasuMove on it and count the step; non-zero skips
   both, and the walk goes on while moveNum isn't 0. The next pass starts with masuIdPrev = masuId and picks
   the next space from there.
   The summit counts as the step just taken, exactly as the engine counts one (mbMasuDispCheck, the step
   sound, moveNum - 1, mbMoveNumKill at 0); returning 1 then keeps mbev_MasuMove off the start space, and the
   rest of the move carries on from the start. With 1 move left the player stops on the start. */
static s32 MoveEnd(s32 player, s16 masu)
{
    if (PagodaBridgeBlocked(player, masu)) {
        return 1;
    }
    if (PagodaGap(player, masu)) {
        return 1;    /* the take-off space and the landing are colour 0: neither counts as a step */
    }
    if (masu != SUMMIT) {
        return 0;
    }
    mbMoveNumDispSet(player, FALSE);   /* off the screen's middle while Master Koopa talks, as Snowflake Lake does */
    StarSale(player);
    PagodaDirClose();
    ReturnToStart(player);
    mbMoveNumDispSet(player, TRUE);
    if (mbMasuDispCheck(SUMMIT) && GwPlayer[player].moveNum > 0) {
        mbAudFXPlay(MSM_SE_BOARD_STEP);
        if (--GwPlayer[player].moveNum == 0) {
            mbMoveNumKill(player);
        }
    }
    return 1;
}

static void HostSay(u32 mes)
{
    mbWinWait(mbWinCreate(WIN_TYPE, mes, mbGuideSpeakerNoGet()));
}

/* mbOpeningInstHookSet: "Would you like to hear about this board?" -> Yes. MP7 w02dll .text 0x9FC: the host
   explains the trail, then the screen fades to Master Koopa on the summit while the price sign counts up to
   40, and back to the board for the warning about Bowser. */
void PagodaOpeningInst(void)
{
    HuVecF pos;
    s32 level;

    mbCameraStackPush();
    HostSay(MES_INST_TRAIL);

    mbWipeDissolveFadeOut();
    mbCameraMoveMasu(SUMMIT, &summitCamRot, &summitCamOffset, 2200.0f, -1.0f, -1);
    mbCameraMoveWait();
    mbMasuPosGet(SUMMIT, &pos);
    mbObjPosSetV(koopa, &pos);
    mbObjRotYSet(koopa, 0.0f);
    mbObjMotionSet(koopa, KOOPA_MOT_IDLE, KOOPA_MOT_LOOP);
    mbObjDispSet(koopa, TRUE);
    mbObjDispSet(cloud, FALSE);
    PagodaSignShow(0);
    mbWipeDissolveFadeIn();

    HostSay(MES_INST_PRICE);
    {
        s16 win = mbWinCreate(WIN_TYPE, MES_INST_RISE, mbGuideSpeakerNoGet());
        for (level = 1; level < PRICE_LEVELS; level++) {
            PagodaSignShow(level);
            HuPrcSleep(INST_SIGN_FRAMES);
        }
        mbWinWait(win);
    }
    PagodaSignShow(0);
    HostSay(MES_INST_CAP);

    mbWipeDissolveFadeOut();
    mbCameraStackPop(-1);
    mbCameraMoveWait();
    mbObjDispSet(koopa, FALSE);
    PagodaSignShow(PRICE_LEVEL);
    mbWipeDissolveFadeIn();
    HostSay(MES_INST_BOWSER);
}

void PagodaStarInit(void)
{
    house = mbObjCreate(PagodaBoardDir() | FILE_HOUSE, NULL, 0);
    mbObjAttrSet(house, HU3D_MOTATTR_PAUSE);
    sign = mbObjCreate(PagodaBoardDir() | FILE_SIGN, NULL, 0);
    mbObjAttrSet(sign, HU3D_MOTATTR_LOOP | HU3D_MOTATTR_PAUSE);
    PagodaSignShow(PRICE_LEVEL);
    mbObjHookSet(house, signJoint, sign);
    koopa = mbObjCreate(PagodaBoardDir() | FILE_KOOPA, koopaMot, 0);
    mbObjLayerSet(koopa, 3);
    mbObjDispSet(koopa, FALSE);
    cloud = mbObjCreate(PagodaBoardDir() | FILE_CLOUD, NULL, 0);
    mbObjScaleSet(cloud, 0.75f, 0.75f, 0.75f);
    mbObjLayerSet(cloud, 3);
    mbObjDispSet(cloud, FALSE);
    mbev_MasuMoveEndSet(MoveEnd);
}

void PagodaStarKill(void)
{
    if (house >= 0) {
        mbObjHookReset(house);
        mbObjKill(house);
        house = -1;
    }
    if (sign >= 0) {
        mbObjKill(sign);
        sign = -1;
    }
    if (koopa >= 0) {
        mbObjKill(koopa);
        koopa = -1;
    }
    if (cloud >= 0) {
        mbObjKill(cloud);
        cloud = -1;
    }
}
