/*
 * Close Call: 4-player drop-and-stop minigame (new REL, shipped in the jbtestdll overlay slot).
 *
 * Everyone stands on a ledge at the top of a tall wall. After "Start!" they flip head-first and fall at one
 * constant speed; the camera follows them, so the floor is out of view until the very end. Press A to freeze in
 * mid-air. Whoever stops closest to the floor wins; reaching the floor is a crash and that player is out.
 *
 * Flow is driven by the game's minigame sequencer (MgSeq, DOL): it wipes in, shows "Start!" and "Finish!", shows
 * the winner/draw banner, fades out and returns from the overlay. This file only supplies the scene and the
 * per-mode callbacks (see SeqParam).
 *
 * Built by tools/build_closecall_rel.py. p01_names.h maps the US names below to Europe (GP6P01) addresses and
 * gives the Europe data directory numbers (P01_DATA_*); never use DATA_* from datadir_enum.h here.
 */
#include "p01_names.h"
#include "game/object.h"
#include "game/hu3d.h"
#include "game/pad.h"
#include "game/wipe.h"
#include "game/gamework.h"
#include "game/charman.h"
#include "game/audio.h"
#include "game/data.h"
#include "game/memory.h"
#include "game/frand.h"
#include "game/printfunc.h"
#include "datanum/mariomot.h"
#include "closecall_files.h"

/* ---- DOL functions without a header in this decomp (signatures from their disassembly) ---- */
typedef void (*SEQ_FUNC)(s16 mode, s16 frame);
typedef struct SeqParam_s {
    s16 timeLimit;   /* seconds, 0 = no timer */
    u8 timerPos;
    u8 pad;
    SEQ_FUNC func[9]; /* called every frame of modes 1..9 */
} SEQ_PARAM;
void MgSeqCreate(SEQ_PARAM *param);
void MgSeqModeNext(void);
void MgSeqWinnerSet(s16 charNo0, s16 charNo1, s16 charNo2, s16 charNo3);
void MgSeqDrawSet(void);
void MgSeqModeDelaySet(s16 mode, s16 frames); /* -1: the mode lasts until MgSeqModeNext() */
BOOL _CheckFlag(u32 flag);
void omGameSysInit(OMOBJMAN *objman);
extern int fontcolor;

#define FLAG_PRACTICE 0x1000F
#define MGDATA_TBL ((u8 *)0x802F49A0) /* MgDataTbl after apply_mgtable_move_patch.py */
#define MGDATA_SIZE 0x7C
#define MG_TYPE_BATTLE 3

/* ---- Tunables (Europe runs at 50 frames per second; 1 unit is about 1 cm) ---- */
#define FLOOR_Y 0.0f
#define FALL_HEIGHT 3000.0f            /* ledge height above the floor */
#define FALL_SPEED 13.3f               /* units per frame: about 4.5 s from the ledge to the floor */
#define FLIP_FRAMES 20                 /* hop and turn upside down before falling */
#define FLIP_HOP 60.0f
#define PLAYER_SPACING 150.0f
#define CAM_DIST 900.0f
#define CAM_LEAD -120.0f               /* aim this far above the falling heads (negative: below them, so the
                                          players sit high on screen and the floor shows ~0.75 s ahead) */
#define LEDGE_VIEW (FLOOR_Y + FALL_HEIGHT + 80.0f) /* camera height framing the players on the ledge */
#define FLOOR_VIEW (FLOOR_Y + 220.0f)  /* camera height of the floor/result view; the follow camera never goes
                                          lower, so the view angle onto the floor never changes */
#define CAM_FOV 45.0f
#define END_WAIT 40                    /* frames after the last player stops or crashes */
#define REVEAL_FRAMES 90
#define RESULT_FRAMES 150
#define BGM_STREAM 110                 /* Close Call's own track, appended to MP6_Str.pdt by apply_closecall_patch.py */
#define VOICE_STOP MSM_SE_CHAR(16)     /* the character's jump grunt (what motion 303 plays), on A */
#define DIST_DISPLAY_SCALE 0.2f        /* result shows the measured distance / 5 */
#define RESULT_COLOR_WIN FONT_COLOR_DARK_GREEN /* result labels sit on the red/white floor: dark colours read best */
#define RESULT_COLOR_LOSE FONT_COLOR_BLACK

/* CPU stop target above the floor (cm): mean +- spread, uniform. A target <= 0 means the CPU never stops. */
static const float ComTarget[4][2] = {
    { 220.0f, 230.0f }, /* easy: crashes now and then */
    { 150.0f, 150.0f }, /* normal */
    { 90.0f, 90.0f },   /* hard */
    { 45.0f, 46.0f },   /* very hard */
};

/* Head-top correction added to the game's character height (CharModelHeightGet), in units (about cm), tuned by
   eye with the CLOSECALL_DEBUG_HITBOX markers. Negative = head top closer to the feet (higher on screen when
   upside down). Indexed by GW_CHARA_*. */
static const float HeadAdjust[GW_CHARA_MAX] = {
    0.0f,   /* Mario */
    0.0f,   /* Luigi: checked, fine */
    0.0f,   /* Peach */
    0.0f,   /* Yoshi */
    -15.0f, /* Wario: marker sat below the cap */
    0.0f,   /* Daisy */
    5.0f,   /* Waluigi: tip of the hat */
    0.0f,   /* Toad */
    0.0f,   /* Boo */
    -35.0f, /* Mini Bowser */
    0.0f,   /* Toadette */
    -35.0f, /* Mini Bowser (red) */
    -35.0f, /* Mini Bowser (green) */
    -35.0f, /* Mini Bowser (blue) */
};

/* ---- Scene ---- */
#define WALL_TILES 8 /* tile 0 sits below the floor, behind its back edge */

enum { STAT_LEDGE, STAT_FALL, STAT_STOP, STAT_CRASH };

typedef struct Player_s {
    s16 charNo;
    s16 padNo;
    BOOL comF;
    s16 comDif;
    HU3D_MODELID mdlId;
    HU3D_MOTIONID motIdle, motJump, motHit, motWin;
    float x, y;        /* model origin (feet); upside down the head is at y - height */
    float height;
    float comStopY;    /* CPU stops when its head reaches this height */
    s16 stat;
    float dist;        /* head above the floor when stopped (cm) */
    s16 rank;
} PLAYER;

static OMOBJMAN *objman;
static PLAYER Player[4];
static HU3D_MODELID wallMdl[WALL_TILES];
static HU3D_MODELID floorMdl, ledgeMdl;
static HU3D_LIGHTID lightId;
static float fallY;     /* shared head height of everyone still falling */
static float camY;
static float camStart;  /* camera height when a camera move began */
static float camFollow; /* 0..1 blend from camStart into the follow camera */
static int streamNo = -1;
static s16 endWait;
static BOOL resultShown;

void ObjectSetup(void);

int _prolog(void)
{
    ObjectSetup();
    return 0;
}

void _epilog(void)
{
}

void _unresolved(void)
{
}

static float Lerp(float a, float b, float t)
{
    return a + (b - a) * t;
}

static float Ease(float t)
{
    return t * t * (3.0f - 2.0f * t);
}

static void CameraSet(float y)
{
    camY = y;
    Hu3DCameraPosSet(HU3D_CAM0, 0.0f, y + 120.0f, CAM_DIST, 0.0f, 1.0f, 0.0f, 0.0f, y, 0.0f);
}

static float HeadY(PLAYER *p)
{
    return (p->stat == STAT_LEDGE) ? p->y + p->height : p->y - p->height;
}

static void PlayerPosSet(PLAYER *p, float rotZ)
{
    Hu3DModelPosSet(p->mdlId, p->x, p->y, 0.0f);
    Hu3DModelRotSet(p->mdlId, 0.0f, 0.0f, rotZ);
}

static void MotionSet(PLAYER *p, HU3D_MOTIONID mot, u32 attr)
{
    CharMotionShiftSet(p->charNo, mot, 0.0f, 8.0f, attr);
}

/* ---- Setup ---- */
static void SceneCreate(void)
{
    s16 i;
    HU3D_MODELID base;
    base = Hu3DModelCreateData(P01_DATA_saf | CLOSECALL_FILE_WALL);
    for (i = 0; i < WALL_TILES; i++) {
        wallMdl[i] = (i == 0) ? base : Hu3DModelLink(base);
        Hu3DModelPosSet(wallMdl[i], 0.0f, FLOOR_Y + CLOSECALL_WALL_TILE_H * (i - 1), CLOSECALL_WALL_Z);
    }
    floorMdl = Hu3DModelCreateData(P01_DATA_saf | CLOSECALL_FILE_FLOOR);
    Hu3DModelPosSet(floorMdl, 0.0f, FLOOR_Y, 0.0f);
    ledgeMdl = Hu3DModelCreateData(P01_DATA_saf | CLOSECALL_FILE_LEDGE);
    Hu3DModelPosSet(ledgeMdl, 0.0f, FLOOR_Y + FALL_HEIGHT, 0.0f);
}

static void PlayersCreate(void)
{
    s16 i;
    PLAYER *p;
    float spread;
    for (i = 0; i < 4; i++) {
        p = &Player[i];
        p->charNo = GwPlayerConf[i].charNo;
        p->padNo = GwPlayerConf[i].padNo;
        p->comF = GwPlayer[i].comF;
        p->comDif = GwPlayerConf[i].comDif & 3;
        p->mdlId = CharModelCreate(p->charNo, CHAR_MODEL1);
        p->motIdle = CharMotionCreate(p->charNo, CHARMOT_FILE(c000m1_300));
        p->motJump = CharMotionCreate(p->charNo, CHARMOT_FILE(c000m1_303));
        p->motHit = CharMotionCreate(p->charNo, CHARMOT_FILE(c000m1_310));
        p->motWin = CharMotionCreate(p->charNo, CHARMOT_FILE(c000m1_306));
        CharMotionDataClose(p->charNo);
        p->height = CharModelHeightGet(p->charNo);
        if (p->charNo >= 0 && p->charNo < GW_CHARA_MAX) {
            p->height += HeadAdjust[p->charNo];
        }
        p->x = (i - 1.5f) * PLAYER_SPACING;
        p->y = FLOOR_Y + FALL_HEIGHT;
        p->stat = STAT_LEDGE;
        p->dist = -1.0f;
        p->rank = 0;
        spread = ComTarget[p->comDif][1];
        p->comStopY = FLOOR_Y + ComTarget[p->comDif][0] + (frandf() * 2.0f - 1.0f) * spread;
        CharMotionSet(p->charNo, p->motIdle);
        Hu3DModelMotLoopOn(p->mdlId);
        PlayerPosSet(p, 0.0f);
    }
}

/* ---- Sequencer callbacks ---- */
static void SeqNext(s16 mode, s16 frame)
{
    MgSeqModeNext();
}

static void SeqNone(s16 mode, s16 frame)
{
}

/* Mode 2: show how far down the floor is, then come back up to the players on the ledge. The mode lasts until
   MgSeqModeNext() (MgSeqModeDelaySet(2, -1) in ObjectSetup); by default the sequencer cuts it at 200 frames. */
#define INTRO_DOWN 110
#define INTRO_HOLD 40
#define INTRO_UP 90
static void SeqIntro(s16 mode, s16 frame)
{
    float top = LEDGE_VIEW;
    float bottom = FLOOR_VIEW;
    if (frame == 0) {
        streamNo = HuAudSStreamPlay(BGM_STREAM);
    }
    if (frame < INTRO_DOWN) {
        CameraSet(Lerp(top, bottom, Ease((float)frame / INTRO_DOWN)));
    } else if (frame < INTRO_DOWN + INTRO_HOLD) {
        CameraSet(bottom);
    } else if (frame < INTRO_DOWN + INTRO_HOLD + INTRO_UP) {
        CameraSet(Lerp(bottom, top, Ease((float)(frame - INTRO_DOWN - INTRO_HOLD) / INTRO_UP)));
    } else {
        CameraSet(top);
        MgSeqModeNext();
    }
}

static BOOL StopPressed(PLAYER *p)
{
    if (p->comF) {
        return HeadY(p) <= p->comStopY;
    }
    if (p->padNo < 0 || p->padNo >= 4) {
        return FALSE;
    }
    return (HuPadBtnDown[p->padNo] & PAD_BUTTON_A) != 0;
}

/* Mode 4: the game. */
static void SeqMain(s16 mode, s16 frame)
{
    s16 i;
    s16 active;
    PLAYER *p;
    float t;
    float target;
    if (frame == 0) {
        camStart = camY;
        camFollow = 0.0f;
    }
    if (frame < FLIP_FRAMES) {
        t = (float)frame / FLIP_FRAMES;
        for (i = 0; i < 4; i++) {
            p = &Player[i];
            if (frame == 0) {
                MotionSet(p, p->motJump, HU3D_MOTATTR_NONE);
            }
            /* hop up, then turn so the feet are where the head was */
            p->y = FLOOR_Y + FALL_HEIGHT + FLIP_HOP * HuSin(180.0f * t) + p->height * Ease(t) * 2.0f;
            PlayerPosSet(p, 180.0f * Ease(t));
        }
        return;
    }
    if (frame == FLIP_FRAMES) {
        for (i = 0; i < 4; i++) {
            p = &Player[i];
            p->stat = STAT_FALL;
            p->y = FLOOR_Y + FALL_HEIGHT + 2.0f * p->height;
            PlayerPosSet(p, 180.0f);
            /* idle pose for the fall: arms and legs trail up, so the top of the head is the lowest point */
            MotionSet(p, p->motIdle, HU3D_MOTATTR_LOOP);
        }
        fallY = FLOOR_Y + FALL_HEIGHT + Player[0].height; /* head height of the falling group */
        endWait = 0;
    }
    active = 0;
    fallY -= FALL_SPEED;
    camFollow += (1.0f - camFollow) * 0.08f; /* ease from the ledge view into the follow camera */
    for (i = 0; i < 4; i++) {
        p = &Player[i];
        if (p->stat != STAT_FALL) {
            continue;
        }
        p->y -= FALL_SPEED;
        if (HeadY(p) <= FLOOR_Y) {
            p->y = FLOOR_Y + p->height;
            p->stat = STAT_CRASH;
            p->dist = -1.0f;
            MotionSet(p, p->motHit, HU3D_MOTATTR_NONE);
            if (!p->comF) {
                omVibrate(i, 12, 6, 6);
            }
        } else if (StopPressed(p)) {
            p->stat = STAT_STOP;
            p->dist = HeadY(p) - FLOOR_Y;
            CharFXPlay(p->charNo, VOICE_STOP);
        } else {
            active++;
        }
        PlayerPosSet(p, 180.0f);
    }
    if (active) {
        target = fallY + CAM_LEAD;
        if (target < FLOOR_VIEW) {
            target = FLOOR_VIEW; /* stop at the floor view; the players fall the last stretch on screen */
        }
        CameraSet(Lerp(camStart, target, camFollow));
    } else if (++endWait >= END_WAIT) {
        MgSeqModeNext();
    }
}

/* Mode 5: "Finish!" is on screen; the sequencer moves on by itself when the message is done (as in m616). */
static void SeqFinish(s16 mode, s16 frame)
{
    if (frame == 0 && streamNo >= 0) {
        HuAudSStreamFadeOut(streamNo, 100);
        streamNo = -1;
    }
}

static s16 MgTypeGet(void)
{
    return MGDATA_TBL[GwSystem.mgNo * MGDATA_SIZE + 2];
}

/* The distance shown in the result, in tenths of a "cm": the measured distance (world units, about 1 cm each)
   times DIST_DISPLAY_SCALE, rounded. Ranking uses this same number, so players showing the same value tie. */
static s32 DistTenths(PLAYER *p)
{
    return (s32)(p->dist * DIST_DISPLAY_SCALE * 10.0f + 0.5f);
}

/* Dense rank: survivors by displayed distance (closest = 0, equal values share a rank), every crashed
   player tied after the last survivor. Everyone crashed = everyone rank 0. */
static void RankCalc(void)
{
    s16 i, j, rank, crashRank;
    s32 key[4];
    for (i = 0; i < 4; i++) {
        key[i] = (Player[i].stat == STAT_STOP) ? DistTenths(&Player[i]) : -1;
    }
    crashRank = 0;
    for (i = 0; i < 4; i++) {
        if (key[i] < 0) {
            continue;
        }
        rank = 0;
        for (j = 0; j < 4; j++) {
            /* count distinct survivor distances strictly closer than mine */
            if (key[j] >= 0 && key[j] < key[i]) {
                s16 k;
                BOOL dup = FALSE;
                for (k = 0; k < j; k++) {
                    if (key[k] == key[j]) {
                        dup = TRUE;
                        break;
                    }
                }
                if (!dup) {
                    rank++;
                }
            }
        }
        Player[i].rank = rank;
        if (rank + 1 > crashRank) {
            crashRank = rank + 1;
        }
    }
    for (i = 0; i < 4; i++) {
        if (key[i] < 0) {
            Player[i].rank = crashRank;
        }
    }
}

/* Mode 6: reveal the floor, decide and report the result. */
static void SeqWinner(s16 mode, s16 frame)
{
    s16 i, n;
    s16 win[4];
    BOOL practice, battle, anyWin;
    PLAYER *p;
    if (frame == 0) {
        RankCalc();
        practice = _CheckFlag(FLAG_PRACTICE);
        battle = MgTypeGet() == MG_TYPE_BATTLE;
        win[0] = win[1] = win[2] = win[3] = -1;
        n = 0;
        anyWin = FALSE;
        for (i = 0; i < 4; i++) {
            p = &Player[i];
            if (p->stat == STAT_STOP && p->rank == 0) {
                win[n++] = p->charNo;
                anyWin = TRUE;
            }
            if (!practice) {
                if (battle) {
                    GwPlayer[i].mgCoinBonus = p->rank;
                } else if (p->stat == STAT_STOP && p->rank == 0) {
                    GwPlayer[i].mgCoinBonus = 10;
                }
            }
        }
        if (anyWin) {
            MgSeqWinnerSet(win[0], win[1], win[2], win[3]);
        } else {
            MgSeqDrawSet();
        }
        resultShown = TRUE;
        camStart = camY;
    }
    if (frame <= REVEAL_FRAMES) {
        CameraSet(Lerp(camStart, FLOOR_VIEW, Ease((float)frame / REVEAL_FRAMES)));
    }
    if (frame == REVEAL_FRAMES) {
        for (i = 0; i < 4; i++) {
            p = &Player[i];
            if (p->stat == STAT_STOP && p->rank == 0) {
                MotionSet(p, p->motWin, HU3D_MOTATTR_NONE);
            }
        }
    }
    if (frame >= RESULT_FRAMES) {
        MgSeqModeNext();
    }
}

static SEQ_PARAM SeqParam = {
    0, 0, 0,
    {
        SeqNext,    /* 1 */
        SeqIntro,   /* 2: wipe in, intro pan */
        SeqNone,    /* 3: "Start!" */
        SeqMain,    /* 4: game */
        SeqFinish,  /* 5: "Finish!" */
        SeqWinner,  /* 6: result */
        SeqNone,    /* 7: winner banner */
        SeqNone,    /* 8: fade out */
        SeqNone,    /* 9 */
    },
};

#ifdef CLOSECALL_DEBUG_HITBOX
/* Debug build (CLOSECALL_DEBUG=1 python tools/build_closecall_rel.py): a bar at each player's computed head top,
   the point that is measured and that crashes into the floor. */
static HU3D_MODELID markerMdl[4];

static void HitboxMarkersCreate(void)
{
    s16 i;
    for (i = 0; i < 4; i++) {
        markerMdl[i] = Hu3DModelCreateData(P01_DATA_saf | CLOSECALL_FILE_MARKER);
    }
}

static void HitboxMarkersUpdate(void)
{
    s16 i;
    for (i = 0; i < 4; i++) {
        Hu3DModelPosSet(markerMdl[i], Player[i].x, HeadY(&Player[i]), 0.0f); /* players' plane, like the floor edge */
    }
}
#endif

/* Distance labels, drawn every frame once the result is known. */
static void LabelObj(OMOBJ *obj)
{
    s16 i, x;
    PLAYER *p;
#ifdef CLOSECALL_DEBUG_HITBOX
    HitboxMarkersUpdate();
#endif
    if (!resultShown) {
        return;
    }
    for (i = 0; i < 4; i++) {
        p = &Player[i];
        x = 72 + i * 132;
        if (p->stat == STAT_STOP) {
            fontcolor = (p->rank == 0) ? RESULT_COLOR_WIN : RESULT_COLOR_LOSE;
            print8(x, 400, 2.0f, "%3d.%dcm", DistTenths(p) / 10, DistTenths(p) % 10);
        } else {
            fontcolor = RESULT_COLOR_LOSE;
            print8(x, 400, 2.0f, "  OUT");
        }
    }
    fontcolor = FONT_COLOR_WHITE;
}

void ObjectSetup(void)
{
    objman = omInitObjMan(50, 8192);
    omGameSysInit(objman);
    Hu3DCameraCreate(HU3D_CAM0);
    Hu3DCameraPerspectiveSet(HU3D_CAM0, CAM_FOV, 20.0f, 15000.0f, 1.2f);
    Hu3DCameraViewportSet(HU3D_CAM0, 0.0f, 0.0f, 640.0f, 480.0f, 0.0f, 1.0f);
    lightId = Hu3DGLightCreate(0.0f, 1500.0f, 2000.0f, 0.0f, -0.5f, -1.0f, 255, 255, 255);
    Hu3DGLightInfinitytSet(lightId);
    Hu3DAmbColorSet(0.6f, 0.6f, 0.6f);
    Hu3DBGColorSet(40, 70, 120);
    resultShown = FALSE;
    SceneCreate();
    PlayersCreate();
    CameraSet(LEDGE_VIEW);
#ifdef CLOSECALL_DEBUG_HITBOX
    HitboxMarkersCreate();
#endif
    omAddObjEx(objman, 32000, 0, 0, -1, LabelObj);
    MgSeqCreate(&SeqParam);
    MgSeqModeDelaySet(2, -1); /* the intro ends when SeqIntro says so (on the ledge view), not after 200 frames */
}
