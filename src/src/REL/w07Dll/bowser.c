/*
 * Pagoda Peak's Bowser Time and its three bridges, ported from MP7 w02dll: bridge setup .text 0x13E90, bridge
 * models shown by state 0x140B0, the repair 0x152AC (registered at .text 0x44C), Bowser Time's bridge event
 * 0x156B4 (registered at .text 0x560 with the stomp event 0x15F00 through MP7's Bowser Time table, .data
 * 0x480: { event, weight 100 } pairs); records 32-38.
 *
 * The bridges: three sets of models (w07.bin FILE_BRIDGE and the next two = MP7 w02.bin 0x1D intact, 0x1E breaking, 0x1F
 * broken) on the map's h_bridge0..2 joints; one joint carries one model, so the one showing is hooked again
 * whenever it changes (as MP7 does). Bridge b's spaces are the flag indices 2b+1 and 2b+2 under 0xE00000:
 * 25/24, 29/30 and 33/34, all colour 0, each pair crossing one bridge.
 *
 * When Bowser Time comes: MP7's gauge rises 20% after every turn's minigame, so it fires every 5 turns. Here it
 * comes every 3 turns (the user's choice): it runs when the first player of turns 4, 7, 10 ... starts (the
 * turn-init hook), and a broken bridge is
 * repaired at the start of the next turn (record 36), so it stays out for one turn.
 *
 * The bridge event, as in MP7: Bowser (MP7 capsulechar1.bin model 0 and motions 1, 2, 8, 5, 0x10, 6, 0x11,
 * 0xA, 0xB as w07.bin FILE_BOWSER and the nine after it) appears on the summit (space flag 0x10000), laughs (32), says he'll bust a
 * bridge (33), jumps; the camera cuts to a random bridge, he crashes down through it spinning, it breaks; back
 * on the summit he gloats (34) and the board says the bridge is out for a turn (35).
 * A player who steps onto a broken bridge's first space hops back to the space they came from and their move
 * ends there (MP7 sets type 0x2000 on that space and lets its walk stop; MP6's ev_Branch would read an empty
 * candidate list then, so the move-end hook does it instead).
 *
 * The stomp event (0x15F00 and 0x166F8), as in MP7: Bowser on the summit laughs (32) and says he's out of shape
 * (37). He jumps to the space flagged index 2 under 0x180000 (space 71) and stomps it, then to the start and
 * stomps that; players standing there are stunned. The quake then knocks every player whose space has a masu
 * layer 1 link (MP7 w02.bin file 1, w07.bin FILE_SPACES_BELOW, loaded by board.c) down along it, one ledge lower, one
 * player at a time: knocked motion, a 48-frame arc 750 high, landing motion (MP6 <char>mot.bin 18 and 19,
 * byte for byte MP7's mariomot 0x11 and 0x12). Bowser says that was great exercise (38).
 * Bowser Time picks one of the two events with equal odds (MP7's weights are 100 and 100).
 *
 * Not ported: the debris particles (sprite 0xFE0034 and two processes), the music, the sounds and the stomped
 * players' own motion (MP7 slot 14; MP6's stun motion instead).
 */
#include "pagoda.h"
#include "game/charman.h"

#define BRIDGES 3
#define BRIDGE_STATES 3              /* intact, breaking, broken */
#define MASU_BRIDGE_MASK 0xE00000
#define MASU_SUMMIT 0x10000
#define BOWSER_TIME_EVERY 3        /* MP7: 5; the user asked for every 3 turns */

/* GwSystem.boardWork[0]: bits 0-1 the Star price (star.c), 2-4 the broken bridges, 8-15 the last turn handled */
#define BROKEN_SHIFT 2
#define BROKEN ((GwSystem.boardWork[0] >> BROKEN_SHIFT) & 7)
#define TURN_SHIFT 8
#define LAST_TURN ((GwSystem.boardWork[0] >> TURN_SHIFT) & 0xFF)

#define BOWSER_MOT_IDLE 1
#define BOWSER_MOT_TALK 4
#define BOWSER_MOT_LAUGH 6
#define BOWSER_MOT_JUMP 8
#define BOWSER_MOT_SHIFT 8.0f
#define BOWSER_JUMP 1000.0f          /* 10 * 100 * sin(90 t) over 30 frames (.rodata 0x2F8, 0x1E8) */
#define BOWSER_FALL_FRAMES 60
#define BOWSER_FALL_TOP 2500.0f      /* .rodata 0x678 * 0x1E8: y = 2500 cos(90 t) - 1500 */
#define BOWSER_FALL_BOTTOM 1500.0f
#define BOWSER_SPIN 1440.0f
#define HOP_FRAMES 20
#define HOP_HEIGHT 120.0f

#define MES_BOWSER_TIME PAGODA_MES(32)
#define MES_BUST PAGODA_MES(33)
#define MES_ROAD_OUT PAGODA_MES(34)
#define MES_BLOCKED PAGODA_MES(35)
#define MES_FIXED PAGODA_MES(36)
#define MES_OUT_OF_SHAPE PAGODA_MES(37)
#define MES_EXERCISE PAGODA_MES(38)

/* the stomp event (MP7 .text 0x15F00; .rodata 0x390 29 frames, 0x698 rot, 0x52C zoom 2000, 0x6A8 7.5) */
#define MASU_STOMP_MASK 0x180000
#define MASU_START_TYPE 0x8000
#define STOMPS 2
#define BOWSER_MOT_STOMP 9
#define STOMP_FRAMES 30
#define STOMP_LAND_FRAME 4
#define STOMP_HIT_FRAME 20
#define STOMP_ZOOM 2500.0f           /* MP7: 2000 */
#define PLAYER_MOT_STUN 6
#define MOT_KNOCKED (P01_DATA_mariomot | 18)
#define MOT_KNOCKED_LAND (P01_DATA_mariomot | 19)
#define FALL_FRAMES 48
#define FALL_HEIGHT 750.0f
#define PLAYERS 4

typedef struct {
    MBOBJ obj[BRIDGE_STATES];
    HuVecF pos;
    s16 masu[2];
} BRIDGE;

static BRIDGE bridges[BRIDGES];
static MBOBJ mapObj = -1;
static char *bridgeJoint[BRIDGES] = { "h_bridge0", "h_bridge1", "h_bridge2" };
static s32 bowserMot[] = { DIR_BOARD | (FILE_BOWSER + 1), DIR_BOARD | (FILE_BOWSER + 2), DIR_BOARD | (FILE_BOWSER + 3),
                           DIR_BOARD | (FILE_BOWSER + 4), DIR_BOARD | (FILE_BOWSER + 5), DIR_BOARD | (FILE_BOWSER + 6),
                           DIR_BOARD | (FILE_BOWSER + 7), DIR_BOARD | (FILE_BOWSER + 8), DIR_BOARD | (FILE_BOWSER + 9), -1 };

/* MP7's cameras (.rodata 0x650/0x65C zoom 900; 0x668 zoom 2500), pulled back for MP6's frame (see kungfu.c):
   tune in game */
static HuVecF summitRot = { -10.0f, 0.0f, 0.0f };
static HuVecF summitOffset = { 0.0f, 200.0f, 0.0f };
#define SUMMIT_ZOOM 1500.0f
static HuVecF bridgeRot = { -15.0f, 0.0f, 0.0f };
static HuVecF stompRot = { -35.0f, 0.0f, 0.0f };
#define BRIDGE_ZOOM 2500.0f

static void BrokenSet(s32 mask)
{
    GwSystem.boardWork[0] = (GwSystem.boardWork[0] & ~(7 << BROKEN_SHIFT)) | ((mask & 7) << BROKEN_SHIFT);
}

static void LastTurnSet(s32 turn)
{
    GwSystem.boardWork[0] = (GwSystem.boardWork[0] & ~(0xFF << TURN_SHIFT)) | ((turn & 0xFF) << TURN_SHIFT);
}

static void BridgeShow(s32 b, s32 state)
{
    BRIDGE *bridge = &bridges[b];
    s32 i;

    for (i = 0; i < BRIDGE_STATES; i++) {
        mbObjDispSet(bridge->obj[i], i == state);
    }
    mbObjHookSet(mapObj, bridgeJoint[b], bridge->obj[state]);
}

/* MP7 .text 0x140B0 */
static void BridgesShow(void)
{
    s32 b;

    for (b = 0; b < BRIDGES; b++) {
        BridgeShow(b, (BROKEN & (1 << b)) ? 2 : 0);
    }
}

void PagodaBridgeInit(MBOBJ map)
{
    s32 b, i;

    mapObj = map;
    for (b = 0; b < BRIDGES; b++) {
        BRIDGE *bridge = &bridges[b];
        for (i = 0; i < BRIDGE_STATES; i++) {
            bridge->obj[i] = mbObjCreate(PagodaBoardDir() | (FILE_BRIDGE + i), NULL, 1);
        }
        mbObjAttrSet(bridge->obj[1], HU3D_MOTATTR_PAUSE);
        Hu3DModelObjPosGet(mbObjModelIDGet(map), bridgeJoint[b], &bridge->pos);
        for (i = 0; i < 2; i++) {
            bridge->masu[i] = mbMasuFind_MAttrMatchIdGet(-1, mbev_MasuAttrGet(2 * b + 1 + i, MASU_BRIDGE_MASK),
                                                         MASU_BRIDGE_MASK);
        }
    }
    BridgesShow();
}

/* The map hooks the bridges: board.c resets the map's hooks first. */
void PagodaBridgeKill(void)
{
    s32 b, i;

    for (b = 0; b < BRIDGES; b++) {
        for (i = 0; i < BRIDGE_STATES; i++) {
            if (bridges[b].obj[i] >= 0) {
                mbObjKill(bridges[b].obj[i]);
                bridges[b].obj[i] = -1;
            }
        }
    }
    mapObj = -1;
}

static void CameraOnBridge(s32 b)
{
    mbCameraMovePos(&bridges[b].pos, &bridgeRot, NULL, BRIDGE_ZOOM, -1.0f, -1);
    mbCameraMoveWait();
}

static void StatusHide(BOOL hide)
{
    mbStatusDispSetAll(!hide);
    if (hide) {
        while (!mbStatusOffCheckAll()) {
            HuPrcVSleep();
        }
    }
}

/* MP7 .text 0x152AC: every broken bridge is fixed, shown one by one under record 36. */
static void BridgesRepair(void)
{
    s32 broken = BROKEN;
    s32 b;

    BrokenSet(0);
    BridgesShow();
    for (b = 0; b < BRIDGES; b++) {
        if (broken & (1 << b)) {
            mbWipeFadeOut();
            CameraOnBridge(b);
            mbWipeFadeIn();
            PagodaSay(MES_FIXED, -1);
        }
    }
    mbWipeFadeOut();
}

static void BowserMotion(MBOBJ bowser, s32 motNo, u32 attr)
{
    mbObjMotionShiftSet(bowser, motNo, 0.0f, BOWSER_MOT_SHIFT, attr);
}

static void CameraOnSummit(s16 summit)
{
    mbCameraMoveMasu(summit, &summitRot, &summitOffset, SUMMIT_ZOOM, -1.0f, -1);
    mbCameraMoveWait();
}

/* MP7 .text 0x156B4 */
static void BridgeEvent(void)
{
    s16 summit = mbMasuFind_MAttrIdGet(-1, MASU_SUMMIT);
    MBOBJ bowser = mbObjCreate(PagodaBoardDir() | FILE_BOWSER, bowserMot, 0);
    HuVecF top, pos;
    s32 b = mbRandMod(BRIDGES);
    s32 i, k;

    PagodaDirClose();
    mbObjLayerSet(bowser, 3);
    mbMasuPosGet(summit, &top);
    mbObjPosSetV(bowser, &top);
    mbObjMotionSet(bowser, BOWSER_MOT_IDLE, KOOPA_MOT_LOOP);
    CameraOnSummit(summit);
    mbWipeFadeIn();
    BowserMotion(bowser, BOWSER_MOT_LAUGH, 0);
    PagodaSay(MES_BOWSER_TIME, -1);
    BowserMotion(bowser, BOWSER_MOT_TALK, KOOPA_MOT_LOOP);
    PagodaSay(MES_BUST, -1);
    mbObjAttrReset(bowser, KOOPA_MOT_LOOP);
    while (!mbObjMotionEndCheck(bowser)) {
        HuPrcVSleep();
    }
    BowserMotion(bowser, BOWSER_MOT_JUMP, 0);
    HuPrcSleep(20);
    for (i = 0; i <= 30; i++) {
        mbObjPosSet(bowser, top.x, top.y + BOWSER_JUMP * PagodaSin(90.0f * i / 30.0f), top.z);
        HuPrcVSleep();
    }

    mbWipeFadeOut();
    CameraOnBridge(b);
    mbWipeFadeIn();
    for (i = 0; i <= BOWSER_FALL_FRAMES; i++) {
        float t = (float)i / BOWSER_FALL_FRAMES;
        if (i == BOWSER_FALL_FRAMES / 2) {
            mbCameraShakeSet(6, 500.0f);
            mbObjMotionTimeSet(bridges[b].obj[1], 0.0f);
            mbObjAttrReset(bridges[b].obj[1], HU3D_MOTATTR_PAUSE);
            BridgeShow(b, 1);
            for (k = 0; k < 4; k++) {
                omVibrate(k, 20, 4, 4);
            }
        }
        pos = bridges[b].pos;
        pos.y += BOWSER_FALL_TOP * PagodaCos(90.0f * t) - BOWSER_FALL_BOTTOM;
        mbObjPosSetV(bowser, &pos);
        mbObjRotSet(bowser, 180.0f, BOWSER_SPIN * t, 0.0f);
        HuPrcVSleep();
    }
    HuPrcSleep(30);

    mbWipeFadeOut();
    mbObjPosSetV(bowser, &top);
    mbObjRotSet(bowser, 0.0f, 0.0f, 0.0f);
    mbObjMotionSet(bowser, BOWSER_MOT_TALK, KOOPA_MOT_LOOP);
    CameraOnSummit(summit);
    mbWipeFadeIn();
    PagodaSay(MES_ROAD_OUT, -1);

    mbWipeFadeOut();
    mbObjKill(bowser);
    BrokenSet(BROKEN | (1 << b));
    mbObjAttrSet(bridges[b].obj[1], HU3D_MOTATTR_PAUSE);
    BridgesShow();
    CameraOnBridge(b);
    mbWipeFadeIn();
    PagodaSay(MES_BLOCKED, -1);
    mbWipeFadeOut();
}

/* The space below each player's (its masu layer 1 link), or -1. MP7 .text 0x166F8 */
static s16 FallTarget(s32 player)
{
    s32 layer = mbMasuLayerGet();
    s16 masu = GwPlayer[player].masuId;
    s16 below = -1;

    mbMasuLayerSet(1);
    if (mbMasuLinkNumGet(masu) > 0) {
        below = mbMasuLinkGet(masu, 0);
    }
    mbMasuLayerSet(layer);
    return below;
}

/* MP7 .text 0x167A4: the quake knocks a player down to `below` */
static void KnockDown(s32 player, s16 below)
{
    s16 mot = mbPlayerMotionCreate(player, MOT_KNOCKED);
    s16 motLand = mbPlayerMotionCreate(player, MOT_KNOCKED_LAND);
    HuVecF from, to, pos;
    s32 i;

    CharMotionDataClose(GwPlayer[player].charNo);
    mbCameraPlayerViewSetFast(player, 2);
    mbCameraShakeSet(30, 500.0f);
    mbWipeDissolveFadeIn();
    mbPlayerMotionShiftSet(player, mot, 0.0f, KOOPA_MOT_SHIFT, 0);
    mbPlayerPosGet(player, &from);
    mbMasuPosGet(below, &to);
    mbPlayerRotYSet(player, atan2(to.x - from.x, to.z - from.z) * RAD_TO_DEG);
    for (i = 0; i < FALL_FRAMES; i++) {
        float t = (float)i / (FALL_FRAMES - 1);
        pos.x = from.x + t * (to.x - from.x);
        pos.y = from.y + t * (to.y - from.y) + FALL_HEIGHT * PagodaSin(180.0f * t);
        pos.z = from.z + t * (to.z - from.z);
        mbPlayerPosSetV(player, &pos);
        HuPrcVSleep();
    }
    omVibrate(player, 20, 7, 3);
    mbPlayerMotionShiftSet(player, motLand, 0.0f, KOOPA_MOT_SHIFT, 0);
    HuPrcSleep(30);
    mbWipeDissolveFadeOut();
    mbPlayerRotYSet(player, 0.0f);
    mbPlayerMotionShiftSet(player, PLAYER_MOT_IDLE, 0.0f, KOOPA_MOT_SHIFT, KOOPA_MOT_LOOP);
    mbPlayerMotionKill(player, mot);
    mbPlayerMotionKill(player, motLand);
    GwPlayer[player].masuId = below;
    mbev_PlayerColMasuSet(player, below, 1);
}

/* MP7 .text 0x15F00 */
static void StompEvent(void)
{
    s16 summit = mbMasuFind_MAttrIdGet(-1, MASU_SUMMIT);
    MBOBJ bowser = mbObjCreate(PagodaBoardDir() | FILE_BOWSER, bowserMot, 0);
    s16 targets[STOMPS], below[PLAYERS];
    BOOL hit[PLAYERS];
    HuVecF top, cur, to;
    s32 k, i, p;

    PagodaDirClose();
    targets[0] = mbMasuFind_MAttrMatchIdGet(-1, mbev_MasuAttrGet(2, MASU_STOMP_MASK), MASU_STOMP_MASK);
    targets[1] = mbMasuFind_AttrIdGet(-1, MASU_START_TYPE);
    mbObjLayerSet(bowser, 3);
    mbMasuPosGet(summit, &top);
    mbObjPosSetV(bowser, &top);
    mbObjMotionSet(bowser, BOWSER_MOT_IDLE, KOOPA_MOT_LOOP);
    CameraOnSummit(summit);
    mbWipeFadeIn();
    BowserMotion(bowser, BOWSER_MOT_LAUGH, 0);
    PagodaSay(MES_BOWSER_TIME, -1);
    BowserMotion(bowser, BOWSER_MOT_TALK, KOOPA_MOT_LOOP);
    PagodaSay(MES_OUT_OF_SHAPE, -1);
    mbObjAttrReset(bowser, KOOPA_MOT_LOOP);
    while (!mbObjMotionEndCheck(bowser)) {
        HuPrcVSleep();
    }

    for (p = 0; p < PLAYERS; p++) {
        hit[p] = FALSE;
    }
    cur = top;
    for (k = 0; k < STOMPS; k++) {
        if (targets[k] < 0) {
            continue;
        }
        mbMasuPosGet(targets[k], &to);
        HuPrcSleep(12);
        BowserMotion(bowser, BOWSER_MOT_JUMP, 0);
        HuPrcSleep(20);
        for (i = 0; i < STOMP_FRAMES; i++) {
            mbObjPosSet(bowser, cur.x, cur.y + BOWSER_JUMP * PagodaSin(90.0f * i / (STOMP_FRAMES - 1)), cur.z);
            HuPrcVSleep();
        }
        mbWipeFadeOut();
        mbObjRotYSet(bowser, atan2(to.x - cur.x, to.z - cur.z) * RAD_TO_DEG);
        cur = to;
        mbCameraMovePos(&cur, &stompRot, NULL, STOMP_ZOOM, -1.0f, -1);
        mbCameraMoveWait();
        mbObjMotionSet(bowser, BOWSER_MOT_IDLE, KOOPA_MOT_LOOP);
        mbWipeFadeIn();
        for (i = 0; i < STOMP_FRAMES; i++) {
            float t = (float)i / (STOMP_FRAMES - 1);
            if (i == STOMP_LAND_FRAME) {
                BowserMotion(bowser, BOWSER_MOT_STOMP, 0);
            }
            if (i == STOMP_HIT_FRAME) {
                for (p = 0; p < PLAYERS; p++) {
                    if (GwPlayer[p].masuId == targets[k]) {
                        hit[p] = TRUE;
                        mbPlayerMotionShiftSet(p, PLAYER_MOT_STUN, 0.0f, KOOPA_MOT_SHIFT, KOOPA_MOT_LOOP);
                    }
                }
            }
            mbObjPosSet(bowser, cur.x, cur.y + BOWSER_JUMP * PagodaCos(90.0f * t), cur.z);
            HuPrcVSleep();
        }
        for (p = 0; p < PLAYERS; p++) {
            omVibrate(p, 20, 4, 4);
        }
        mbCameraShakeSet(30, 500.0f);
        HuPrcSleep(42);
    }

    mbWipeFadeOut();
    mbObjDispSet(bowser, FALSE);
    for (p = 0; p < PLAYERS; p++) {
        if (hit[p]) {
            mbPlayerMotionShiftSet(p, PLAYER_MOT_IDLE, 0.0f, KOOPA_MOT_SHIFT, KOOPA_MOT_LOOP);
        }
        below[p] = FallTarget(p);
    }
    for (p = 0; p < PLAYERS; p++) {
        if (below[p] > 0) {
            KnockDown(p, below[p]);
        }
    }
    mbObjDispSet(bowser, TRUE);
    mbObjPosSetV(bowser, &top);
    mbObjRotSet(bowser, 0.0f, 0.0f, 0.0f);
    mbObjMotionSet(bowser, BOWSER_MOT_TALK, KOOPA_MOT_LOOP);
    CameraOnSummit(summit);
    mbWipeDissolveFadeIn();
    PagodaSay(MES_EXERCISE, -1);
    mbWipeFadeOut();
    mbObjKill(bowser);
}

/* mbPlayerTurnInitHookSet: runs as each player's turn starts. The first one of each turn repairs the bridges
   and, every BOWSER_TIME_EVERY turns, brings Bowser Time. */
static void TurnInit(s32 player)
{
    BOOL repair, bowserTime;

    if (LAST_TURN == GwSystem.turnNo) {
        return;
    }
    LastTurnSet(GwSystem.turnNo);
    repair = BROKEN != 0;
    bowserTime = GwSystem.turnNo > 1 && (GwSystem.turnNo - 1) % BOWSER_TIME_EVERY == 0;
    if (!repair && !bowserTime) {
        return;
    }
    StatusHide(TRUE);
    mbWipeFadeOut();
    if (repair) {
        BridgesRepair();
    }
    if (bowserTime) {
        if (mbRandMod(2) == 0) {
            BridgeEvent();
        } else {
            StompEvent();
        }
    }
    PagodaDirClose();
    mbCameraPlayerViewSet(player, 1);
    mbCameraMoveWait();
    mbWipeFadeIn();
    StatusHide(FALSE);
}

void PagodaBowserInit(MBOBJ map)
{
    PagodaBridgeInit(map);
    mbPlayerTurnInitHookSet(TurnInit);
}

void PagodaBowserKill(void)
{
    PagodaBridgeKill();
}

/* TRUE when `masu` is one of a broken bridge's two spaces (the Cannon orb never lands there, cannon.c). */
BOOL PagodaBridgeBroken(s16 masu)
{
    s32 b;

    for (b = 0; b < BRIDGES; b++) {
        if ((BROKEN & (1 << b)) && (bridges[b].masu[0] == masu || bridges[b].masu[1] == masu)) {
            return TRUE;
        }
    }
    return FALSE;
}

/* The move-end hook (star.c), before anything else: TRUE when `masu` is a broken bridge's first space, after
   the player has hopped back to the space they came from and their move has ended there. */
BOOL PagodaBridgeBlocked(s32 player, s16 masu)
{
    HuVecF from, to, pos;
    s16 back;
    s32 b, i;

    for (b = 0; b < BRIDGES; b++) {
        if (bridges[b].masu[0] == masu && (BROKEN & (1 << b))) {
            break;
        }
    }
    if (b == BRIDGES) {
        return FALSE;
    }
    back = GwPlayer[player].masuIdPrev;
    PagodaSay(MES_BLOCKED, -1);
    mbMasuPosGet(masu, &from);
    mbMasuPosGet(back, &to);
    PagodaTurn(player, (s32)(atan2(to.x - from.x, to.z - from.z) * RAD_TO_DEG));
    mbPlayerMotionShiftSet(player, PLAYER_MOT_JUMP, 0.0f, KOOPA_MOT_SHIFT, 0);
    for (i = 0; i < HOP_FRAMES; i++) {
        float t = (float)i / (HOP_FRAMES - 1);
        pos.x = from.x + t * (to.x - from.x);
        pos.y = from.y + t * (to.y - from.y) + HOP_HEIGHT * PagodaSin(180.0f * t);
        pos.z = from.z + t * (to.z - from.z);
        mbPlayerPosSetV(player, &pos);
        HuPrcVSleep();
    }
    mbPlayerMotionShiftSet(player, PLAYER_MOT_IDLE, 0.0f, KOOPA_MOT_SHIFT, KOOPA_MOT_LOOP);
    GwPlayer[player].masuId = back;
    mbev_PlayerColMasuSet(player, back, 1);
    GwPlayer[player].moveNum = 0;
    return TRUE;
}
