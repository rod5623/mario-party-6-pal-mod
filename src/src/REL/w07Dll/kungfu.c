/*
 * Pagoda Peak's Kung Fu Falls, ported from MP7 w02dll: setup .text 0x569C, event 0x59A8, player 0x7180,
 * CPU 0x77E8, catching 0x7E10, rocks 0x7F8C, pattern 0x8174, motion 0x862C, the Star 0x6AA8; records
 * 14-17. Space 65 (MP7 flag 0x10000000).
 *
 * The space's type-0x2000 side node (66) and its link (67) are two ledges either side of the waterfall.
 * Coins and rocks (w07.bin FILE_ROCK, MP7 w02.bin 0x10) slide along a fixed 20-point path down the falls
 * (MP7 .data 0x0, map coordinates) in four lanes, 300 units wide around the ledges' midpoint. A shared
 * clock starts at -1.6 and adds 0.0044 a frame; an object is on the path while its start (row / 10) plus
 * the clock is in [0, 0.6). One of three 16-row patterns (MP7 .data 0x53C/0x57C/0x5BC) places 10 coins and
 * 4 rocks.
 *
 * A (jump) leaps to the other ledge along a 30-frame arc that peaks 200 up: anything within 120 of the
 * jumping player (60 above their feet, ignoring depth) is caught, a coin pays 1, a rock knocks them back
 * to the nearer ledge, dizzy for 30 frames. After 10 seconds (the timer) and once everyone has landed,
 * every coin caught is paid out; catching all the coins earns a Star from Master Koopa (party mode, as on
 * MP6's party boards). In tag mode the partner plays on the other ledge, as in MP7's duo mode.
 *
 * CPU players use MP7's AI: they simulate jumping 0-14 frames from now, with a timing error by difficulty
 * (+-8, +-6, +-3, +-2 frames), and jump when the best jump catches coins, hits no rocks and is now. When
 * the board doesn't show CPU minigames and every player is a CPU, MP7's estimate is used instead of
 * playing: share * (skill by difficulty + noise), skill 0.3/0.5/0.7/0.9.
 *
 * Changed from MP7: MP6's own player motions (MP7 loads three of its own), MP7's sounds and the coin
 * sparkle left out, the rocks keep their model's orientation instead of following the path's tangent.
 */
#include "pagoda.h"
#include "game/gamemes.h"

#define PATH_POINTS 20
#define SEGMENTS (PATH_POINTS - 1)
#define COINS 20
#define ROCKS 10
#define ROWS 16
#define LANES 4
#define PATTERNS 3
#define MAX_PLAYERS 2

#define LANE_WIDTH 300.0f
#define CLOCK_START -1.6f
#define CLOCK_STEP 0.0044f
#define PATH_END 0.6f
#define FADE_IN 0.1f
#define GAME_FRAMES 500           /* 10 s at 50 Hz */
#define JUMP_FRAMES 30
#define JUMP_PEAK 200.0f
#define TURN_FRAMES 6
#define HIT_FRAMES 24
#define HIT_BOUNCE 150.0f
#define DIZZY_FRAMES 30
#define CATCH_Y 60.0f
#define CATCH_RADIUS 120.0f
#define AI_DELAYS 15
#define COIN_SPIN 4.0f
#define TAG_DEPTH 75.0f

#define MES_WELCOME PAGODA_MES(14)
#define MES_BEGIN PAGODA_MES(15)
#define MES_STAR PAGODA_MES(16)
#define MES_JUMP PAGODA_MES(17)

#define PLAYER_MOT_WALK 2
#define PLAYER_MOT_DIZZY 6

enum { ST_IDLE, ST_JUMP, ST_TURN, ST_HIT, ST_DIZZY };

typedef struct {
    s16 obj;
    BOOL active;
    BOOL shown;
    float lane;
    float start;
    float spin;
    HuVecF pos;
} FALLER;

typedef struct {
    s32 player;
    s32 state;
    s32 side;        /* the ledge they stand on (or jump from) */
    s32 frame;
    s32 caught;
    float turnTo;
    HuVecF pos;
    HuVecF from;
    HuVecF masuPos;
} JUMPER;

/* MP7 w02dll .data 0x0 */
static HuVecF path[PATH_POINTS] = {
    { -518.6f, 2532.9f, -15.8f }, { -518.6f, 2533.1f, 146.1f }, { -518.6f, 2527.5f, 307.9f },
    { -518.6f, 2498.9f, 466.8f }, { -518.6f, 2411.3f, 600.7f }, { -518.6f, 2275.1f, 686.7f },
    { -518.6f, 2119.2f, 728.6f }, { -518.6f, 1958.0f, 743.0f }, { -518.6f, 1796.3f, 749.7f },
    { -518.6f, 1634.4f, 753.6f }, { -518.6f, 1472.5f, 755.7f }, { -518.6f, 1310.6f, 756.8f },
    { -518.6f, 1148.7f, 757.2f }, { -518.6f, 986.8f, 757.3f }, { -518.6f, 824.9f, 757.1f },
    { -518.6f, 663.0f, 756.8f }, { -518.6f, 501.1f, 756.4f }, { -518.6f, 339.2f, 755.9f },
    { -518.6f, 177.3f, 755.4f }, { -518.6f, 15.4f, 754.9f },
};

/* MP7 .data 0x53C, 0x57C, 0x5BC: 1 = coin, 2 = rock */
static u8 patterns[PATTERNS][ROWS][LANES] = {
    { { 0, 0, 1, 1 }, { 2, 0, 0, 0 }, { 0, 0, 0, 0 }, { 0, 0, 1, 0 }, { 0, 1, 0, 0 }, { 0, 0, 0, 2 },
      { 2, 0, 0, 0 }, { 0, 0, 1, 0 }, { 0, 0, 0, 0 }, { 0, 0, 0, 0 }, { 1, 1, 0, 0 }, { 0, 0, 1, 0 },
      { 0, 2, 0, 0 }, { 0, 0, 0, 0 }, { 0, 1, 1, 0 }, { 0, 0, 0, 0 } },
    { { 1, 0, 1, 0 }, { 0, 0, 0, 0 }, { 0, 0, 0, 1 }, { 0, 0, 0, 0 }, { 1, 0, 0, 0 }, { 0, 0, 2, 0 },
      { 1, 0, 0, 0 }, { 0, 0, 0, 0 }, { 0, 0, 0, 1 }, { 2, 0, 0, 0 }, { 0, 0, 0, 0 }, { 0, 1, 1, 0 },
      { 0, 0, 0, 0 }, { 0, 2, 0, 1 }, { 0, 0, 0, 0 }, { 1, 0, 0, 0 } },
    { { 0, 1, 0, 0 }, { 2, 0, 0, 1 }, { 0, 0, 0, 0 }, { 1, 0, 0, 0 }, { 0, 0, 2, 0 }, { 0, 0, 0, 0 },
      { 0, 0, 0, 1 }, { 0, 1, 0, 0 }, { 0, 0, 0, 1 }, { 0, 2, 0, 0 }, { 0, 0, 0, 0 }, { 1, 0, 0, 1 },
      { 0, 0, 2, 0 }, { 0, 1, 0, 0 }, { 0, 0, 0, 0 }, { 1, 0, 0, 0 } },
};

static s32 aiError[4] = { 16, 12, 6, 4 };              /* MP7 .data 0x52C, by difficulty */
static float simSkill[4] = { 0.3f, 0.5f, 0.7f, 0.9f };  /* MP7 .rodata 0xB8 */

/* from ledge 0. MP7 (.rodata 0x1E8, 0x240) uses y 150 with a zoom of 1600, which puts him above MP6's frame:
   lowered, and the camera pulled back and up (CameraOnLedge). */
static HuVecF koopaOffset = { 100.0f, 80.0f, 0.0f };
static HuVecF walkOffset[MAX_PLAYERS] = { { -300.0f, 0.0f, 100.0f }, { -400.0f, 0.0f, -50.0f } }; /* .rodata 0x378 */
#define LEDGE_CAM_Y 200.0f      /* MP7: 100 */
#define LEDGE_CAM_ZOOM 2400.0f  /* MP7: 1600; the gong's camera uses 2400 */
static HuVecF introRot = { -20.0f, 0.0f, 0.0f };        /* .rodata 0x338 */
static HuVecF gameRot = { -10.0f, 0.0f, 0.0f };         /* .rodata 0x344 */

static FALLER coins[COINS];
static FALLER rocks[ROCKS];
static JUMPER jumpers[MAX_PLAYERS];
static s32 jumperNum;
static HuVecF ledge[2];
static HuVecF ledgeMid;
static float segLen[SEGMENTS];
static float cumLen[SEGMENTS];
static float clock;
static s32 coinTotal;
static BOOL timeUp;

static void PathInit(void)
{
    float total = 0.0f;
    s32 i;

    for (i = 0; i < SEGMENTS; i++) {
        float dx = path[i + 1].x - path[i].x;
        float dy = path[i + 1].y - path[i].y;
        float dz = path[i + 1].z - path[i].z;
        segLen[i] = sqrtf(dx * dx + dy * dy + dz * dz);
        total += segLen[i];
        cumLen[i] = total;
    }
}

/* MP7 .text 0x8418 / 0x86C4: the point `u` of the way along the path (u * length of segments 0-18), in
   lane `lane` (0..1). */
static void PathPos(float lane, float u, HuVecF *out)
{
    float dist = u * cumLen[SEGMENTS - 1];
    float frac;
    s32 i;

    for (i = 0; i < SEGMENTS - 1 && cumLen[i] < dist; i++) {
    }
    frac = i > 0 ? (dist - cumLen[i - 1]) / segLen[i] : dist / segLen[0];
    out->x = ledgeMid.x + LANE_WIDTH * (lane - 0.5f);
    out->y = path[i].y + frac * (path[i + 1].y - path[i].y);
    out->z = path[i].z + frac * (path[i + 1].z - path[i].z);
}

/* MP7 .text 0x7304: the jump from ledge `side` to the other, `t` of the way. */
static void JumpPos(s32 side, float t, HuVecF *out)
{
    HuVecF *a = &ledge[side];
    HuVecF *b = &ledge[side ^ 1];
    float h = t - 0.5f;

    out->x = a->x + t * (b->x - a->x);
    out->y = a->y + t * (b->y - a->y) - 8.0f * 100.0f * h * h + JUMP_PEAK;
}

static BOOL Touches(HuVecF *obj, float x, float y)
{
    float dx = obj->x - x;
    float dy = obj->y - y - CATCH_Y;
    return dx * dx + dy * dy < CATCH_RADIUS * CATCH_RADIUS;
}

static float SideAngle(s32 side)
{
    return side ? -90.0f : 90.0f;
}

/* MP7 .text 0x8174 */
static void PatternSet(s32 pattern)
{
    s32 row, lane, c = 0, r = 0;

    coinTotal = 0;
    for (row = 0; row < ROWS; row++) {
        for (lane = 0; lane < LANES; lane++) {
            FALLER *f = NULL;
            if (patterns[pattern][row][lane] == 1 && c < COINS) {
                f = &coins[c++];
                coinTotal++;
            } else if (patterns[pattern][row][lane] == 2 && r < ROCKS) {
                f = &rocks[r++];
            }
            if (f) {
                f->active = TRUE;
                f->shown = FALSE;
                f->lane = lane / 3.0f;
                f->start = row / 10.0f;
            }
        }
    }
}

static void FallersCreate(void)
{
    s32 i;

    for (i = 0; i < COINS; i++) {
        coins[i].obj = mbCoinCreate();
        coins[i].active = FALSE;
        coins[i].spin = mbRandMod(360);
        mbCoinObjDispSet(coins[i].obj, FALSE);
    }
    for (i = 0; i < ROCKS; i++) {
        rocks[i].obj = mbObjCreate(PagodaBoardDir() | FILE_ROCK, NULL, 1);
        rocks[i].active = FALSE;
        mbObjLayerSet(rocks[i].obj, 3);
        mbObjDispSet(rocks[i].obj, FALSE);
    }
}

static void FallersKill(void)
{
    s32 i;

    for (i = 0; i < COINS; i++) {
        if (coins[i].obj >= 0) {
            mbCoinObjKill(coins[i].obj);
            coins[i].obj = -1;
        }
    }
    for (i = 0; i < ROCKS; i++) {
        if (rocks[i].obj >= 0) {
            mbObjKill(rocks[i].obj);
            rocks[i].obj = -1;
        }
    }
}

/* MP7 .text 0x862C: move everything on the path, then advance the clock. */
static void FallersMove(void)
{
    s32 i;

    for (i = 0; i < COINS + ROCKS; i++) {
        BOOL isCoin = i < COINS;
        FALLER *f = isCoin ? &coins[i] : &rocks[i - COINS];
        float u = f->start + clock;

        if (!f->active || u < 0.0f) {
            continue;
        }
        if (u >= PATH_END) {
            f->active = FALSE;
            if (isCoin) {
                mbCoinObjDispSet(f->obj, FALSE);
            } else {
                mbObjDispSet(f->obj, FALSE);
            }
            continue;
        }
        PathPos(f->lane, u, &f->pos);
        if (isCoin) {
            if (!f->shown) {
                mbCoinObjDispSet(f->obj, TRUE);
                f->shown = TRUE;
            }
            mbCoinObjPosSetV(f->obj, &f->pos);
            f->spin += COIN_SPIN;
            mbCoinObjRotSet(f->obj, 0.0f, f->spin, 0.0f);
            mbCoinObjAlphaSet(f->obj, u < FADE_IN ? u / FADE_IN : 1.0f);
        } else {
            if (!f->shown) {
                mbObjDispSet(f->obj, TRUE);
                f->shown = TRUE;
            }
            mbObjPosSetV(f->obj, &f->pos);
        }
    }
    clock += CLOCK_STEP;
}

static void JumperMotion(JUMPER *j, s32 mot, u32 attr)
{
    mbPlayerMotionShiftSet(j->player, mot, 0.0f, KOOPA_MOT_SHIFT, attr);
}

/* MP7 .text 0x7CD4: a rock knocks the player away from it, back to a ledge. */
static void JumperHit(JUMPER *j, HuVecF *rock)
{
    j->state = ST_HIT;
    j->frame = 0;
    j->from = j->pos;
    j->side = rock->x - j->pos.x >= 0.0f ? 0 : 1;
    omVibrate(j->player, 20, 4, 4);
}

/* MP7 .text 0x7E10 and 0x7F8C: a coin goes to one of the jumping players touching it (at random), a rock
   hits every jumping player touching it. */
static void Collide(void)
{
    s32 i, k;

    for (i = 0; i < COINS; i++) {
        s32 hits[MAX_PLAYERS], n = 0;
        if (!coins[i].active || !coins[i].shown) {
            continue;
        }
        for (k = 0; k < jumperNum; k++) {
            if (jumpers[k].state == ST_JUMP && Touches(&coins[i].pos, jumpers[k].pos.x, jumpers[k].pos.y)) {
                hits[n++] = k;
            }
        }
        if (n) {
            jumpers[hits[mbRandMod(n)]].caught++;
            coins[i].active = FALSE;
            mbCoinObjDispSet(coins[i].obj, FALSE);
        }
    }
    for (i = 0; i < ROCKS; i++) {
        if (!rocks[i].active || !rocks[i].shown) {
            continue;
        }
        for (k = 0; k < jumperNum; k++) {
            if (jumpers[k].state == ST_JUMP && Touches(&rocks[i].pos, jumpers[k].pos.x, jumpers[k].pos.y)) {
                JumperHit(&jumpers[k], &rocks[i].pos);
            }
        }
    }
}

/* MP7 .text 0x77E8: try jumping 0-14 frames from now and jump if the best jump is now. */
static BOOL CpuJump(JUMPER *j)
{
    static BOOL counted[COINS + ROCKS];
    s32 err = aiError[GwPlayer[j->player].comDif];
    s32 noise = (s32)mbRandMod(err + 1) - err / 2;
    s32 best = 0, bestDelay = 0;
    s32 delay, k, i;

    for (delay = 0; delay < AI_DELAYS; delay++) {
        s32 count[2] = { 0, 0 };
        for (i = 0; i < COINS + ROCKS; i++) {
            counted[i] = FALSE;
        }
        for (k = 0; k < JUMP_FRAMES; k++) {
            HuVecF at;
            JumpPos(j->side, k / (float)(JUMP_FRAMES - 1), &at);
            for (i = 0; i < COINS + ROCKS; i++) {
                FALLER *f = i < COINS ? &coins[i] : &rocks[i - COINS];
                HuVecF pos;
                float u;
                if (!f->active || counted[i]) {
                    continue;
                }
                u = clock + f->start + CLOCK_STEP * (k + noise + delay);
                if (u < 0.0f || u >= 1.0f) {
                    continue;
                }
                PathPos(f->lane, u, &pos);
                if (Touches(&pos, at.x, at.y)) {
                    count[i < COINS ? 0 : 1]++;
                    counted[i] = TRUE;
                }
            }
        }
        if (count[0] > best && count[1] == 0) {
            best = count[0];
            bestDelay = delay;
        }
    }
    return best > 0 && bestDelay == 0;
}

static BOOL WantsJump(JUMPER *j)
{
    if (timeUp) {
        return FALSE;
    }
    if (GwPlayer[j->player].comF) {
        return CpuJump(j);
    }
    return (HuPadBtnDown[GwPlayer[j->player].padNo] & PAD_BUTTON_A) != 0;
}

/* MP7 .text 0x7180 */
static void JumperUpdate(JUMPER *j)
{
    float t;

    switch (j->state) {
    case ST_IDLE:
        if (WantsJump(j)) {
            j->state = ST_JUMP;
            j->frame = 1;
            JumperMotion(j, PLAYER_MOT_JUMP, 0);
            mbPlayerRotYSet(j->player, SideAngle(j->side));
        }
        break;
    case ST_JUMP:
        t = j->frame++ / (float)(JUMP_FRAMES - 1);
        JumpPos(j->side, t, &j->pos);
        if (j->frame >= JUMP_FRAMES) {
            j->state = ST_TURN;
            j->frame = 0;
            j->side ^= 1;
            j->turnTo = SideAngle(j->side);
            JumperMotion(j, PLAYER_MOT_IDLE, KOOPA_MOT_LOOP);
        }
        break;
    case ST_TURN:
        t = j->frame++ / (float)TURN_FRAMES;
        mbPlayerRotYSet(j->player, mbAngleLerp(mbPlayerRotYGet(j->player), j->turnTo, t));
        if (j->frame > TURN_FRAMES) {
            j->state = ST_IDLE;
        }
        break;
    case ST_HIT:
        t = j->frame++ / (float)HIT_FRAMES;
        j->pos.x = j->from.x + t * (ledge[j->side].x - j->from.x);
        j->pos.y = j->from.y + t * (ledge[j->side].y - j->from.y) + HIT_BOUNCE * PagodaSin(180.0f * t);
        if (j->frame > HIT_FRAMES) {
            j->state = ST_DIZZY;
            j->frame = 0;
            JumperMotion(j, PLAYER_MOT_DIZZY, KOOPA_MOT_LOOP);
        }
        break;
    case ST_DIZZY:
        if (++j->frame > DIZZY_FRAMES) {
            j->state = ST_IDLE;
            mbPlayerRotYSet(j->player, SideAngle(j->side));
            JumperMotion(j, PLAYER_MOT_IDLE, KOOPA_MOT_LOOP);
        }
        break;
    }
    mbPlayerPosSetV(j->player, &j->pos);
}

static BOOL AllLanded(void)
{
    s32 k;

    for (k = 0; k < jumperNum; k++) {
        if (jumpers[k].state != ST_IDLE) {
            return FALSE;
        }
    }
    return TRUE;
}

static s32 Partner(s32 player)
{
    s32 i;

    if (!GwSystem.tagF) {
        return -1;
    }
    for (i = 0; i < 4; i++) {
        if (i != player && GwPlayer[i].team == GwPlayer[player].team) {
            return i;
        }
    }
    return -1;
}

static void WalkTo(JUMPER *j, HuVecF *to, s32 frames)
{
    HuVecF from;
    s32 i;

    mbPlayerPosGet(j->player, &from);
    mbPlayerRotYSet(j->player, atan2(to->x - from.x, to->z - from.z) * RAD_TO_DEG);
    JumperMotion(j, PLAYER_MOT_WALK, KOOPA_MOT_LOOP);
    for (i = 1; i <= frames; i++) {
        float t = (float)i / frames;
        j->pos.x = from.x + t * (to->x - from.x);
        j->pos.y = from.y + t * (to->y - from.y);
        j->pos.z = from.z + t * (to->z - from.z);
        mbPlayerPosSetV(j->player, &j->pos);
        HuPrcVSleep();
    }
    JumperMotion(j, PLAYER_MOT_IDLE, KOOPA_MOT_LOOP);
}

static void PlaceBeside(HuVecF *koopaPos)
{
    s32 k;

    koopaPos->x = ledge[0].x + koopaOffset.x;
    koopaPos->y = ledge[0].y + koopaOffset.y;
    koopaPos->z = ledge[0].z + koopaOffset.z;
    for (k = 0; k < jumperNum; k++) {
        jumpers[k].pos.x = ledge[0].x + walkOffset[k].x;
        jumpers[k].pos.y = ledge[0].y + walkOffset[k].y;
        jumpers[k].pos.z = ledge[0].z + walkOffset[k].z;
    }
}

static void CameraOnLedge(s32 frames)
{
    HuVecF center;

    center.x = ledge[0].x - 100.0f;
    center.y = ledge[0].y + LEDGE_CAM_Y;
    center.z = ledge[0].z;
    mbCameraMovePos(&center, &introRot, NULL, LEDGE_CAM_ZOOM, -1.0f, frames);
    mbCameraMoveWait();
}

static void CameraOnFalls(void)
{
    HuVecF center = ledgeMid;

    center.y += 300.0f;
    mbCameraMovePos(&center, &gameRot, NULL, 1800.0f, -1.0f, -1);
    mbCameraMoveWait();
}

/* MP7 .text 0x6208: CPU-only and not shown, so estimate instead of playing. */
static void Simulate(void)
{
    s32 k, i;

    for (k = 0; k < jumperNum; k++) {
        float noise = 0.0f, skill;
        for (i = 0; i < 12; i++) {
            noise += mbRandMod(0x10000) / 65536.0f;
        }
        skill = simSkill[GwPlayer[jumpers[k].player].comDif] + noise / 12.0f - 0.5f;
        if (skill < 0.0f) {
            skill = 0.0f;
        } else if (skill > 1.0f) {
            skill = 1.0f;
        }
        jumpers[k].caught = (s32)(0.5f + (float)(coinTotal / jumperNum) * skill);
    }
}

static void Play(void)
{
    s16 help, timer;
    s32 left = GAME_FRAMES;
    s32 k;

    mbWipeFadeIn();
    help = mbWinCreateHelp(MES_JUMP);
    timer = GameMesTimerCreate(GAME_FRAMES / 50);
    do {
        for (k = 0; k < jumperNum; k++) {
            JumperUpdate(&jumpers[k]);
        }
        FallersMove();
        Collide();
        if (left >= 0) {
            if (--left >= 0) {
                GameMesTimerValueSet(timer, (left + 49) / 50);
            } else {
                timeUp = TRUE;
                GameMesTimerEnd(timer);
            }
        }
        HuPrcVSleep();
    } while (!timeUp || !AllLanded());
    mbWinKill(help);
    mbWipeFadeOut();
}

/* MP7 .text 0x6AA8: party mode's prize for catching every coin. */
static void StarPrize(s32 player)
{
    HuVecF koopaPos;
    s32 k;

    PlaceBeside(&koopaPos);
    for (k = 0; k < jumperNum; k++) {
        mbPlayerPosSetV(jumpers[k].player, &jumpers[k].pos);
        mbPlayerRotYSet(jumpers[k].player, 90.0f);
    }
    PagodaKoopaShowAt(&koopaPos, -30.0f);
    CameraOnLedge(-1);
    mbWipeFadeIn();
    PagodaKoopaMotion(KOOPA_MOT_TALK, KOOPA_MOT_LOOP);
    PagodaSay(MES_STAR, player);
    for (k = 0; k < jumperNum; k++) {
        PagodaTurn(jumpers[k].player, 0);
    }
    mbStarGetExec(player);
    HuPrcSleep(30);
    PagodaKoopaLeave(&koopaPos);
    mbWipeFadeOut();
}

s32 PagodaKungFu(s32 player, s16 masu)
{
    s16 ledgeMasu = mbMasuAttrFindLink(masu, 0x2000);
    s32 partner = Partner(player);
    HuVecF koopaPos, walkTo;
    BOOL allCpu = TRUE;
    s32 k, caught = 0;

    if (ledgeMasu < 0) {
        return 1;
    }
    mbMasuPosGet(ledgeMasu, &ledge[0]);
    mbMasuPosGet(mbMasuLinkGet(ledgeMasu, 0), &ledge[1]);
    ledge[0].x = floor(ledge[0].x);
    ledge[1].x = floor(ledge[1].x);
    ledgeMid.x = 0.5f * (ledge[0].x + ledge[1].x);
    ledgeMid.y = 0.5f * (ledge[0].y + ledge[1].y);
    ledgeMid.z = 0.5f * (ledge[0].z + ledge[1].z);
    PathInit();

    jumperNum = partner >= 0 ? 2 : 1;
    for (k = 0; k < jumperNum; k++) {
        JUMPER *j = &jumpers[k];
        j->player = k ? partner : player;
        j->state = ST_IDLE;
        j->side = k;
        j->caught = 0;
        mbPlayerPosGet(j->player, &j->masuPos);
        if (!GwPlayer[j->player].comF) {
            allCpu = FALSE;
        }
    }

    /* MP7 .text 0x59EC-0x5E98: walk over, Master Koopa drops in and explains */
    mbStatusDispSetAll(FALSE);
    while (!mbStatusOffCheckAll()) {
        HuPrcVSleep();
    }
    PlaceBeside(&koopaPos);
    CameraOnLedge(30);
    for (k = 0; k < jumperNum; k++) {
        walkTo = jumpers[k].pos;
        WalkTo(&jumpers[k], &walkTo, 30);
        mbPlayerRotYSet(jumpers[k].player, 90.0f);
    }
    PagodaKoopaArrive(&koopaPos, -30.0f);
    PagodaSay(MES_WELCOME, player);
    PagodaSay(MES_BEGIN, -1);
    mbWipeFadeOut();
    PagodaKoopaHide();

    /* MP7 .text 0x5F1C-0x6200: the falls */
    CameraOnFalls();
    FallersCreate();
    PagodaDirClose();
    for (k = 0; k < jumperNum; k++) {
        JUMPER *j = &jumpers[k];
        j->pos = ledge[k];
        if (jumperNum > 1) {
            j->pos.z += k ? -TAG_DEPTH : TAG_DEPTH;
        }
        mbPlayerPosSetV(j->player, &j->pos);
        mbPlayerRotYSet(j->player, SideAngle(k));
        JumperMotion(j, PLAYER_MOT_IDLE, KOOPA_MOT_LOOP);
    }
    clock = CLOCK_START;
    timeUp = FALSE;
    PatternSet(mbRandMod(PATTERNS));
    if (allCpu && !GwSystem.mgComDispF) {
        Simulate();
    } else {
        Play();
    }

    /* MP7 .text 0x675C-0x6A5C: pay out, and the Star for catching them all */
    FallersKill();
    CameraOnFalls();
    for (k = 0; k < jumperNum; k++) {
        JUMPER *j = &jumpers[k];
        j->pos = ledge[j->side];
        mbPlayerPosSetV(j->player, &j->pos);
        mbPlayerRotYSet(j->player, 0.0f);
        JumperMotion(j, j->caught > 0 ? PLAYER_MOT_JOY : PLAYER_MOT_DIZZY, 0);
    }
    mbWipeFadeIn();
    for (k = 0; k < jumperNum; k++) {
        caught += jumpers[k].caught;
        if (jumpers[k].caught > 0) {
            mbCoinAddDispExec(jumpers[k].player, jumpers[k].caught, 1, 0);
        }
    }
    HuPrcSleep(30);
    if (caught >= coinTotal) {
        mbWipeFadeOut();
        StarPrize(player);
    } else {
        mbWipeFadeOut();
    }

    /* back to the space, as the board expects */
    for (k = 0; k < jumperNum; k++) {
        mbPlayerPosSetV(jumpers[k].player, &jumpers[k].masuPos);
        mbev_PlayerColMasuSet(jumpers[k].player, GwPlayer[jumpers[k].player].masuId, 1);
        mbPlayerRotYSet(jumpers[k].player, 0.0f);
        JumperMotion(&jumpers[k], PLAYER_MOT_IDLE, KOOPA_MOT_LOOP);
    }
    mbCameraPlayerViewSetFast(player, 1);
    mbCameraMoveWait();
    mbWipeFadeIn();
    mbStatusDispSetAll(TRUE);
    return 0;
}

void PagodaKungFuKill(void)
{
    FallersKill();
}

void PagodaKungFuInit(void)
{
    s32 i;

    for (i = 0; i < COINS; i++) {
        coins[i].obj = -1;
    }
    for (i = 0; i < ROCKS; i++) {
        rocks[i].obj = -1;
    }
}
