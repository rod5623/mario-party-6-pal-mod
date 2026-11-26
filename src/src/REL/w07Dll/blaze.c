/*
 * Pagoda Peak's Blazing Rock, ported from MP7 w02dll: setup .text 0xA54C, event 0xA9BC, prize 0xBDA0, chest
 * 0xC444, flames 0xCA34; records 24-31. Space 41 (MP7 flag 0x4000000).
 *
 * The burning rock (w07.bin FILE_ROCK_FIRE, MP7 0x15, its motion looping) stands in front of a cave all game,
 * with flames on every vertex of a hidden emitter model (FILE_EMITTER, MP7 0x18). MP7's flame callback, rebuilt
 * on MP6's Hu3DParticle: one flame per vertex, base size 220-270 (MP7: 500-600), swaying with its own phase (+30 degrees a
 * frame) and leaning into the wind; its size is base * 0.5 * (1 + intensity). When the fire goes out every
 * flame fades over 30-59 frames. The flame and smoke sprites are I8: MP6's particle draw takes their colour
 * from the vertex colour alone (white by default), so each flame gets a fire colour (r 255, g 120-199,
 * b 32) with normal blending, and the smoke grey (0x60, MP7 .rodata 0x4B8).
 *
 * The event, as in MP7: the player walks to the space's type-0x2000 side node (the stand) and is told the
 * rules (24, 25). A fan (FILE_FAN) drops into their right hand ("a-itemhook-r", the same joint name in both
 * games) and they fan with MP7's own two fanning motions. Pressing A (help line 28) adds a press, speeds the
 * fan up by 0.1 (to 3x) and blows a gust along the stand's direction; 12 frames without a press slows it
 * back down. CPUs press with a chance a frame by difficulty (0.12/0.15/0.17/0.19). The fire goes out at
 * 80 + rand(10) presses (MP7: 60) before the 10-second timer (presses stop counting then; the round lasts 560
 * frames). Out: the rock is swapped for FILE_ROCK_OUT and smoke rises (26); else "Too bad" (27).
 * The prize, in the cave (the stand's link): the player carries a treasure chest (FILE_CHEST) in, turns, and
 * it rises and opens: a Star 10% (29), 5-20 coins 70% (30), else Master Koopa's T-shirt (FILE_TSHIRT, 31).
 * Failing ("Too bad", 27) costs a Star if the player has one (this mod's rule; MP7 takes nothing).
 * When the board doesn't show CPU minigames and the player is a CPU, MP7's estimate replaces the round:
 * out with chance 0.1 + skill (0.3/0.5/0.7/0.9 + noise).
 *
 * Changed from MP7: the flames share one animation frame (MP6's particles), MP7's sparks, the chest's
 * sparkle and the white flash are left out (their sprites are in MP7's shared data), the smoke is a simple
 * rise-and-fade of MP7's smoke sprite, the T-shirt rises out of the chest without MP7's spin, and no
 * sounds. The fire is lit again when the event ends.
 */
#include "pagoda.h"
#include "game/gamemes.h"
#include "game/charman.h"
#include "stdio.h"

#define MAX_FLAMES 128
#define FLAME_RISE 150.0f          /* the flames sit this far below the emitter's vertices (.rodata 0x240) */
/* MP7's base size is 500-600; MP6's quad is the scale itself (basePos +-0.5), so that drew one big blob */
#define FLAME_SIZE 220.0f
#define FLAME_SIZE_RANGE 50.0f
#define FLAME_ALPHA 0xFF
#define WIND_GUST 5000.0f
#define WIND_FULL 7000.0f
#define WIND_DECAY 0.95f
#define SMOKE_MAX 32
#define ROUND_FRAMES 560
#define TIMER_FRAMES 500
#define PRESS_TARGET 80        /* MP7: 60 */
#define PRESS_RANGE 10
#define FAN_MAX_SPEED 3.0f
#define FAN_STEP 0.1f
#define FAN_IDLE 12
#define CAVE_FRAMES 60
#define CHEST_RISE_FRAMES 120

#define MES_WELCOME PAGODA_MES(24)
#define MES_READY PAGODA_MES(25)
#define MES_OUT PAGODA_MES(26)
#define MES_TOO_BAD PAGODA_MES(27)
#define MES_FAN PAGODA_MES(28)
#define MES_STAR PAGODA_MES(29)
#define MES_COINS PAGODA_MES(30)
#define MES_TSHIRT PAGODA_MES(31)

#define PLAYER_MOT_WALK 2

typedef struct {
    float amp, base, phase, wobble, size;
    s16 time, life;
} FLAME;

static MBOBJ rockFire = -1, rockOut = -1, emitter = -1;
static s16 flameModel = -1, smokeModel = -1;
static ANIMDATA *flameAnim, *smokeAnim;
static FLAME flames[MAX_FLAMES];
static HuVecF flamePos[MAX_FLAMES];
static s32 flameNum;
static float intensity = 1.0f;
static BOOL burning = TRUE;
static HuVecF wind;

static float cpuPress[4] = { 0.12f, 0.15f, 0.17f, 0.19f };   /* .rodata 0x434 */
static float simSkill[4] = { 0.3f, 0.5f, 0.7f, 0.9f };       /* .rodata 0xB8 */
static s32 prizeOdds[2] = { 10, 80 };                        /* .data 0x420: Star, coins, T-shirt */
static HuVecF standRot = { -10.0f, 0.0f, 0.0f };             /* .rodata 0x444 */
static HuVecF standOffset = { -400.0f, 300.0f, 0.0f };       /* .rodata 0x468 */
static HuVecF caveRot = { -30.0f, 0.0f, 0.0f };              /* .rodata 0x45C */
static HuVecF chestHold = { 0.0f, 80.0f, 80.0f };            /* .rodata 0x4A0 */
static char handJoint[] = "a-itemhook-r";

static float Rand1(void)
{
    return mbRandMod(0x10000) / 65536.0f;
}

/* MP7 .text 0xCA34 */
static void FlameHook(HU3D_MODEL *model, HU3D_PARTICLE *particle, Mtx mtx)
{
    HU3D_PARTICLE_DATA *d = particle->data;
    float lean = sqrtf(wind.x * wind.x + wind.y * wind.y + wind.z * wind.z) / WIND_FULL;
    s32 i;

    if (lean > 1.0f) {
        lean = 1.0f;
    }
    wind.x *= WIND_DECAY;
    wind.y *= WIND_DECAY;
    wind.z *= WIND_DECAY;
    for (i = 0; i < flameNum && i < particle->maxCnt; i++, d++) {
        FLAME *f = &flames[i];
        if (f->life < 0) {
            d->scale = 0.0f;
            continue;
        }
        if (f->life == 0) {
            if (!burning) {
                f->time = 0;
                f->life = 30 + mbRandMod(30);
            }
        } else {
            float t = (float)f->time / f->life;
            d->color.a = (u8)(FLAME_ALPHA * (1.0f - t));
            if (++f->time >= f->life) {
                f->life = -1;
            }
        }
        d->pos = flamePos[i];
        d->zRot = mbAngleLerp(d->zRot, lean * f->amp * (f->base + PagodaSin(f->phase) * f->wobble), 0.2f);
        f->phase = fmod(f->phase + 30.0f, 360.0);
        d->scale = 0.5f * f->size * (1.0f + intensity);
    }
}

static void FlamesLight(void)
{
    s32 i;

    for (i = 0; i < flameNum; i++) {
        FLAME *f = &flames[i];
        f->size = FLAME_SIZE + FLAME_SIZE_RANGE * Rand1();
        f->amp = 0.5f + 0.5f * Rand1();
        f->base = 45.0f + 45.0f * Rand1();
        f->phase = 360.0f * Rand1();
        f->wobble = 15.0f + 15.0f * Rand1();
        f->time = 0;
        f->life = 0;
    }
    if (flameModel >= 0) {
        HU3D_PARTICLE *p = PagodaModelParticle(flameModel);
        for (i = 0; i < flameNum && i < p->maxCnt; i++) {
            p->data[i].color.r = 0xFF;
            p->data[i].color.g = 120 + mbRandMod(80);
            p->data[i].color.b = 0x20;
            p->data[i].color.a = FLAME_ALPHA;
        }
    }
    burning = TRUE;
    intensity = 1.0f;
}

/* Every vertex of the emitter model, in world space (MP7 .text 0xA650). */
static void FlamesPlace(void)
{
    PagodaModelVertices(mbObjModelIDGet(emitter), flamePos, MAX_FLAMES, &flameNum, -FLAME_RISE);
}

static ANIMDATA *AnimRead(s32 file)
{
    return HuSprAnimRead(HuDataSelHeapReadNum(PagodaBoardDir() | file, HU_MEMNUM_OVL, HEAP_MODEL));
}

void PagodaBlazeInit(void)
{
    rockFire = mbObjCreate(PagodaBoardDir() | FILE_ROCK_FIRE, NULL, 0);
    mbObjAttrSet(rockFire, HU3D_MOTATTR_LOOP);
    rockOut = mbObjCreate(PagodaBoardDir() | FILE_ROCK_OUT, NULL, 0);
    mbObjDispSet(rockOut, FALSE);
    emitter = mbObjCreate(PagodaBoardDir() | FILE_EMITTER, NULL, 0);
    mbObjDispSet(emitter, FALSE);
    FlamesPlace();
    flameAnim = AnimRead(FILE_FLAME);
    flameModel = Hu3DParticleCreate(flameAnim, flameNum > 0 ? flameNum : 1);
    Hu3DParticleBlendModeSet(flameModel, HU3D_PARTICLE_BLEND_NORMAL);
    Hu3DParticleHookSet(flameModel, FlameHook);
    smokeAnim = AnimRead(FILE_SMOKE);
    smokeModel = -1;
    FlamesLight();
}

void PagodaBlazeKill(void)
{
    if (smokeModel >= 0) {
        Hu3DModelKill(smokeModel);
        smokeModel = -1;
    }
    if (flameModel >= 0) {
        Hu3DModelKill(flameModel);
        flameModel = -1;
    }
    if (rockFire >= 0) {
        mbObjKill(rockFire);
        mbObjKill(rockOut);
        mbObjKill(emitter);
        rockFire = rockOut = emitter = -1;
    }
}

/* After the fire goes out: MP7's smoke sprite rising and fading from the flames' places (MP7 .text 0xD50C
   does this with its own particle code). */
static s32 smokeTime;

static void SmokeHook(HU3D_MODEL *model, HU3D_PARTICLE *particle, Mtx mtx)
{
    HU3D_PARTICLE_DATA *d = particle->data;
    s32 i;

    for (i = 0; i < particle->maxCnt; i++, d++) {
        if (d->time <= 0) {
            if (smokeTime > 0 && flameNum > 0) {
                d->pos = flamePos[mbRandMod(flameNum)];
                d->time = 40 + mbRandMod(20);
                d->scaleBase = 150.0f + 100.0f * Rand1();
                d->vel.y = 3.0f + 2.0f * Rand1();
                d->speedDecay = d->time;
            } else {
                d->scale = 0.0f;
                continue;
            }
        }
        d->time--;
        d->pos.y += d->vel.y;
        d->scale = d->scaleBase * (2.0f - d->time / d->speedDecay);
        d->color.a = (u8)(160.0f * d->time / d->speedDecay);
    }
    if (smokeTime > 0) {
        smokeTime--;
    }
}

static void SmokeStart(void)
{
    s32 i;

    if (smokeModel < 0) {
        smokeModel = Hu3DParticleCreate(smokeAnim, SMOKE_MAX);
        Hu3DParticleHookSet(smokeModel, SmokeHook);
        for (i = 0; i < SMOKE_MAX; i++) {
            HU3D_PARTICLE_DATA *d = &PagodaModelParticle(smokeModel)->data[i];
            d->color.r = d->color.g = d->color.b = 0x60;   /* MP7 .rodata 0x4B8 */
        }
    }
    for (i = 0; i < SMOKE_MAX; i++) {
        PagodaModelParticle(smokeModel)->data[i].time = -mbRandMod(30);
    }
    smokeTime = 240;
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

static void WalkTo(s32 player, HuVecF *to, s32 frames)
{
    HuVecF from, pos;
    s32 i;

    mbPlayerPosGet(player, &from);
    mbPlayerRotYSet(player, atan2(to->x - from.x, to->z - from.z) * RAD_TO_DEG);
    mbPlayerMotionShiftSet(player, PLAYER_MOT_WALK, 0.0f, KOOPA_MOT_SHIFT, KOOPA_MOT_LOOP);
    for (i = 1; i <= frames; i++) {
        float t = (float)i / frames;
        pos.x = from.x + t * (to->x - from.x);
        pos.y = from.y + t * (to->y - from.y);
        pos.z = from.z + t * (to->z - from.z);
        mbPlayerPosSetV(player, &pos);
        HuPrcVSleep();
    }
    mbPlayerMotionShiftSet(player, PLAYER_MOT_IDLE, 0.0f, KOOPA_MOT_SHIFT, KOOPA_MOT_LOOP);
}

/* MP7 .text 0xB3BC: the fan drops 600 into the right hand, then hangs on it. */
static void FanDrop(s32 player, MBOBJ fan)
{
    s16 model = mbPlayerModelIDGet(player);
    Mtx hand, m;
    s32 i;

    Hu3DMotionCalc(model);
    Hu3DModelObjMtxGet(model, handJoint, hand);
    mbObjDispSet(fan, TRUE);
    for (i = 0; i < 30; i++) {
        float t = i / 29.0f;
        PSMTXCopy(hand, m);
        m[1][3] += 600.0f * (1.0f - t);
        mbObjMtxSet(fan, m);
        HuPrcVSleep();
    }
    PSMTXIdentity(m);
    mbObjMtxSet(fan, m);
    mbObjHookSet(mbPlayerObjIDGet(player), handJoint, fan);
}

/* MP7 .text 0xB614: fan until the fire is out or the round ends. Returns TRUE when it went out. */
static BOOL Fanning(s32 player, s16 motSlow, s16 motFast, HuVecF *gust)
{
    s16 help = mbWinCreateHelp(MES_FAN);
    s16 timer = GameMesTimerCreate(TIMER_FRAMES / 50);
    s32 target = PRESS_TARGET + mbRandMod(PRESS_RANGE);
    s32 left = TIMER_FRAMES, presses = 0, idle = 0, frame;
    s16 mot = motSlow, shown = motSlow;
    float speed = 1.0f;
    BOOL out = FALSE;

    for (frame = 0; frame < ROUND_FRAMES && !out; frame++) {
        BOOL press = FALSE;
        if (left >= 0) {
            if (GwPlayer[player].comF) {
                press = Rand1() < cpuPress[GwPlayer[player].comDif];
            } else {
                press = (HuPadBtnDown[GwPlayer[player].padNo] & PAD_BUTTON_A) != 0;
            }
        }
        if (press) {
            mot = motFast;
            speed += FAN_STEP;
            if (speed > FAN_MAX_SPEED) {
                speed = FAN_MAX_SPEED;
            }
            presses++;
            idle = FAN_IDLE;
            intensity = 1.0f - (float)presses / target;
            wind.x = WIND_GUST * gust->x;
            wind.z = WIND_GUST * gust->z;
        } else if (idle == 0) {
            if (speed > 1.0f) {
                speed -= FAN_STEP;
                if (speed <= 1.0f) {
                    mot = motSlow;
                    speed = 1.0f;
                }
            }
        } else {
            idle--;
        }
        if (mot != shown) {
            mbPlayerMotionShiftSet(player, mot, 0.0f, 8.0f, KOOPA_MOT_LOOP);
            shown = mot;
        }
        mbPlayerMotionSpeedSet(player, speed);
        if (left >= 0) {
            if (--left >= 0) {
                GameMesTimerValueSet(timer, (left + 49) / 50);
            } else {
                GameMesTimerEnd(timer);
            }
        }
        if (presses >= target) {
            out = TRUE;
        }
        HuPrcVSleep();
    }
    mbWinKill(help);
    if (left >= 0) {
        GameMesTimerEnd(timer);
    }
    return out;
}

/* MP7 .text 0xBDA0 and 0xC444: carry the chest into the cave, turn, and it rises and opens. */
static void ChestPrize(s32 player, s16 standMasu, s32 prize)
{
    s16 motHold = mbPlayerMotionCreate(player, MOT_CHEST_HOLD);
    s16 motCarry = mbPlayerMotionCreate(player, MOT_CHEST_CARRY);
    MBOBJ chest = mbObjCreate(PagodaBoardDir() | FILE_CHEST, NULL, 0);
    HuVecF from, cave, pos;
    float rot;
    s32 i;

    PagodaDirClose();
    CharMotionDataClose(GwPlayer[player].charNo);

    mbObjAttrSet(chest, HU3D_MOTATTR_PAUSE);
    mbPlayerPosGet(player, &from);
    mbMasuPosGet(mbMasuLinkGet(standMasu, 0), &cave);
    rot = atan2(cave.x - from.x, cave.z - from.z) * RAD_TO_DEG;
    mbPlayerRotYSet(player, rot);
    mbPlayerMotionShiftSet(player, motCarry, 0.0f, 8.0f, KOOPA_MOT_LOOP);
    for (i = 0; i < CAVE_FRAMES; i++) {
        float t = i / (float)(CAVE_FRAMES - 1);
        float e = t * t * (3.0f - 2.0f * t);
        pos.x = from.x + e * (cave.x - from.x);
        pos.y = from.y + e * (cave.y - from.y);
        pos.z = from.z + e * (cave.z - from.z);
        mbPlayerPosSetV(player, &pos);
        mbObjRotYSet(chest, rot);
        mbObjPosSet(chest, pos.x + chestHold.z * PagodaSin(rot), pos.y + chestHold.y, pos.z + chestHold.z * PagodaCos(rot));
        HuPrcVSleep();
    }
    mbPlayerMotionShiftSet(player, motHold, 0.0f, 8.0f, KOOPA_MOT_LOOP);
    for (i = 0; i < 12; i++) {
        rot = mbAngleLerp(rot, 0.0f, i / 12.0f);
        mbPlayerRotYSet(player, rot);
        mbObjRotYSet(chest, rot);
        mbObjPosSet(chest, pos.x + chestHold.z * PagodaSin(rot), pos.y + chestHold.y, pos.z + chestHold.z * PagodaCos(rot));
        HuPrcVSleep();
    }
    HuPrcSleep(12);
    for (i = 0; i < CHEST_RISE_FRAMES; i++) {
        float t = i / 119.0f;
        mbObjPosSet(chest, pos.x + chestHold.z * PagodaSin(rot), pos.y + chestHold.y + 300.0f * PagodaSin(90.0f * t),
                    pos.z + chestHold.z * PagodaCos(rot));
        HuPrcVSleep();
    }
    mbObjAttrReset(chest, HU3D_MOTATTR_PAUSE);
    HuPrcSleep(18);
    mbPlayerMotionShiftSet(player, PLAYER_MOT_IDLE, 0.0f, KOOPA_MOT_SHIFT, KOOPA_MOT_LOOP);
    if (prize == 0) {
        mbStarGetExec(player);
        PagodaSay(MES_STAR, -1);
    } else if (prize == 1) {
        char text[8];
        s32 coins = 5 + mbRandMod(16);
        s16 win;
        mbCoinAddDispExec(player, coins, 1, 0);
        mbPlayerMotionShiftSet(player, PLAYER_MOT_JOY, 0.0f, KOOPA_MOT_SHIFT, 0);
        sprintf(text, "%d", coins);
        win = mbWinCreate(2, MES_COINS, -1);
        mbWinInsertMesSet(win, (u32)text, 0);
        mbWinWait(win);
    } else {
        MBOBJ shirt = mbObjCreate(PagodaBoardDir() | FILE_TSHIRT, NULL, 0);
        HuVecF chestPos;
        PagodaDirClose();
        mbObjPosGet(chest, &chestPos);
        for (i = 0; i < 60; i++) {
            mbObjPosSet(shirt, chestPos.x, chestPos.y + 100.0f * PagodaSin(90.0f * i / 59.0f), chestPos.z);
            HuPrcVSleep();
        }
        PagodaSay(MES_TSHIRT, -1);
        mbObjKill(shirt);
    }
    mbPlayerMotionShiftSet(player, PLAYER_MOT_IDLE, 0.0f, KOOPA_MOT_SHIFT, KOOPA_MOT_LOOP);
    mbObjKill(chest);
    mbPlayerMotionKill(player, motCarry);
    mbPlayerMotionKill(player, motHold);
}

/* The mod's rule, not MP7's: failing costs a Star, with the game's popup (as the Star Trap orb takes one). */
static void StarLose(s32 player)
{
    if (mbPlayerStarGet(player) <= 0) {
        return;
    }
    mbStarDispPlayerCreate(player, -1);
    while (!mbStarDispCheck(player)) {
        HuPrcVSleep();
    }
    mbPlayerStarAdd(player, -1);
}

static BOOL Simulate(s32 player)
{
    float noise = 0.0f, skill;
    s32 i;

    for (i = 0; i < 12; i++) {
        noise += Rand1();
    }
    skill = simSkill[GwPlayer[player].comDif] + noise / 12.0f - 0.5f;
    if (skill < 0.0f) {
        skill = 0.0f;
    } else if (skill > 1.0f) {
        skill = 1.0f;
    }
    return Rand1() < 0.1f + skill;
}

s32 PagodaBlaze(s32 player, s16 masu)
{
    s16 standMasu = mbMasuAttrFindLink(masu, 0x2000);
    HuVecF masuPos, standPos, gust;
    s16 motSlow, motFast;
    MBOBJ fan;
    BOOL out;
    float len;

    if (standMasu < 0 || rockFire < 0) {
        return 1;
    }
    StatusHide(TRUE);
    mbMasuPosGet(masu, &masuPos);
    mbMasuPosGet(standMasu, &standPos);
    gust.x = standPos.x - masuPos.x;
    gust.y = 0.0f;
    gust.z = standPos.z - masuPos.z;
    len = sqrtf(gust.x * gust.x + gust.z * gust.z);
    if (len > 0.0f) {
        gust.x /= len;
        gust.z /= len;
    }

    /* MP7 .text 0xABA8-0xAD18: to the stand, and the rules */
    WalkTo(player, &standPos, 24);
    mbCameraMovePos(&standPos, &standRot, &standOffset, 3500.0f, -1.0f, 48);
    mbCameraMoveWait();
    PagodaSay(MES_WELCOME, player);
    PagodaSay(MES_READY, -1);

    if (GwPlayer[player].comF && !GwSystem.mgComDispF) {
        mbWipeFadeOut();
        out = Simulate(player);
    } else {
        motSlow = mbPlayerMotionCreate(player, MOT_FAN_SLOW);
        motFast = mbPlayerMotionCreate(player, MOT_FAN_FAST);
        CharMotionDataClose(GwPlayer[player].charNo);
        mbPlayerMotionShiftSet(player, motSlow, 0.0f, 30.0f, KOOPA_MOT_LOOP);
        fan = mbObjCreate(PagodaBoardDir() | FILE_FAN, NULL, 1);
        PagodaDirClose();
        mbObjDispSet(fan, FALSE);
        FanDrop(player, fan);
        out = Fanning(player, motSlow, motFast, &gust);
        if (out) {
            mbPlayerMotionSpeedSet(player, 0.0f);
            HuPrcSleep(60);
        }
        mbWipeDissolveFadeOut();
        mbObjHookReset(mbPlayerObjIDGet(player));
        mbObjKill(fan);
        mbPlayerMotionSpeedSet(player, 1.0f);
        mbPlayerMotionShiftSet(player, PLAYER_MOT_IDLE, 0.0f, KOOPA_MOT_SHIFT, KOOPA_MOT_LOOP);
        mbPlayerMotionKill(player, motSlow);
        mbPlayerMotionKill(player, motFast);
    }

    /* MP7 .text 0xBB70-0xBD40: the result */
    if (out) {
        mbObjDispSet(rockFire, FALSE);
        mbObjDispSet(rockOut, TRUE);
        burning = FALSE;
        intensity = 0.0f;
        SmokeStart();
    } else {
        intensity = 1.0f;
    }
    mbWipeDissolveFadeIn();
    if (out) {
        PagodaSay(MES_OUT, -1);
        mbWipeDissolveFadeOut();
        mbCameraMovePlayer(player, &caveRot, NULL, 2400.0f, -1.0f, -1);
        mbCameraMoveWait();
        mbWipeDissolveFadeIn();
        {
            s32 roll = mbRandMod(100);
            ChestPrize(player, standMasu, roll < prizeOdds[0] ? 0 : roll < prizeOdds[1] ? 1 : 2);
        }
    } else {
        PagodaSay(MES_TOO_BAD, -1);
        StarLose(player);
    }

    /* back to the space with the fire lit again */
    mbWipeFadeOut();
    mbObjDispSet(rockOut, FALSE);
    mbObjDispSet(rockFire, TRUE);
    FlamesLight();
    smokeTime = 0;
    wind.x = wind.y = wind.z = 0.0f;
    mbPlayerPosSetV(player, &masuPos);
    mbev_PlayerColMasuSet(player, masu, 1);
    mbPlayerRotYSet(player, 0.0f);
    mbCameraPlayerViewSetFast(player, 1);
    mbCameraMoveWait();
    mbWipeFadeIn();
    StatusHide(FALSE);
    return 0;
}
