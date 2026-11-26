/*
 * Pagoda Peak's dragon, ported from MP7 w02dll: setup .text 0xDCF8, event 0xE1B8, the throw 0xE7E0 and the
 * landing 0xEB5C. Space 44 (MP7 flag 0x2000000). No text: MP7 plays it without a word.
 *
 * The dragon (w07.bin FILE_DRAGON, MP7 0x1B) stands by space 44 all game, its motion paused. As in MP7: the
 * status boxes hide, the player turns to the dragon's head (joint h_fire) and its motion runs (to 36
 * frames from the end). For 60 frames the player, and space 44 itself, ride its h_dragon joint; the camera
 * frames the space ((-18,0,0), (-300,100,0), zoom 3500) and the player is put in its mouth (h_fire). A
 * minute later the dragon breathes: the player is charred black (MP6's mbObjBiriQ effect, the same calls as
 * MP7) and shoots off inside a fireball along MP7's direction (angles 15 and 165 degrees, 80 a frame for 53
 * frames, tumbling) with a camera shake. After a fade the dragon and the space are put back, and the player
 * comes down out of the sky onto the start space, still charred, for 2 seconds.
 *
 * The fireball is MP7's flame sprite (FILE_FIREBALL_SPRITE, MP7 0x33) on the vertices of MP7's fireball shape (FILE_FIREBALL,
 * MP7 0x1C), rebuilt on MP6's Hu3DParticle (MP7's particle code and its spark sprite don't carry over).
 * The landing drops straight down instead of MP7's Bezier path, MP6's stun motion stands in for MP7's
 * motion 28, and there are no sounds.
 */
#include "pagoda.h"

#define MAX_BALL 96
#define RIDE_FRAMES 60
#define FLY_FRAMES 53
#define FLY_SPEED 80.0f            /* 0.8 * 100 (.rodata 0x534, 0x1E8) */
#define MOTION_END_TRIM 36.0f      /* .rodata 0x528 */
#define LAND_HEIGHT 2000.0f
#define LAND_FRAMES 40
#define CHARRED_FRAMES 120
#define PLAYER_MOT_STUN 6

static MBOBJ dragon = -1, ballShape = -1;
static s16 ballModel = -1;
static HuVecF ballVtx[MAX_BALL];
static s32 ballNum;
static BOOL ballOn;
static HuVecF ballAt;
static char fireJoint[] = "h_fire";
static char rideJoint[] = "h_dragon";
static HuVecF camRot = { -18.0f, 0.0f, 0.0f };        /* .rodata 0x510 */
static HuVecF camOffset = { -300.0f, 100.0f, 0.0f };  /* .rodata 0x51C */
static GXColor charred = { 0, 0, 0, 255 };            /* .rodata 0xC8 */

static void BallHook(HU3D_MODEL *model, HU3D_PARTICLE *particle, Mtx mtx)
{
    HU3D_PARTICLE_DATA *d = particle->data;
    s32 i;

    for (i = 0; i < ballNum && i < particle->maxCnt; i++, d++) {
        if (!ballOn) {
            d->scale = 0.0f;
            continue;
        }
        d->pos.x = ballAt.x + ballVtx[i].x;
        d->pos.y = ballAt.y + ballVtx[i].y;
        d->pos.z = ballAt.z + ballVtx[i].z;
        d->scale = 80.0f + mbRandMod(40);
        d->zRot = mbRandMod(360) / RAD_TO_DEG;
    }
}

/* The fireball shape's vertices, relative to its own origin (MP7 .text 0xDDBC). */
static void BallShapeRead(void)
{
    PagodaModelVertices(mbObjModelIDGet(ballShape), ballVtx, MAX_BALL, &ballNum, 0.0f);
}

void PagodaDragonInit(void)
{
    dragon = mbObjCreate(PagodaBoardDir() | FILE_DRAGON, NULL, 0);
    mbObjAttrSet(dragon, HU3D_MOTATTR_PAUSE);
    ballShape = mbObjCreate(PagodaBoardDir() | FILE_FIREBALL, NULL, 0);
    mbObjDispSet(ballShape, FALSE);
    BallShapeRead();
    ballModel = Hu3DParticleCreate(HuSprAnimRead(HuDataSelHeapReadNum(PagodaBoardDir() | FILE_FIREBALL_SPRITE,
                                                                        HU_MEMNUM_OVL, HEAP_MODEL)),
                                   ballNum > 0 ? ballNum : 1);
    Hu3DParticleBlendModeSet(ballModel, HU3D_PARTICLE_BLEND_ADDCOL);
    Hu3DParticleHookSet(ballModel, BallHook);
    ballOn = FALSE;
}

void PagodaDragonKill(void)
{
    if (ballModel >= 0) {
        Hu3DModelKill(ballModel);
        ballModel = -1;
    }
    if (dragon >= 0) {
        mbObjKill(dragon);
        mbObjKill(ballShape);
        dragon = ballShape = -1;
    }
}

static void JointPos(char *joint, HuVecF *out)
{
    Hu3DModelObjPosGet(mbObjModelIDGet(dragon), joint, out);
}

/* MP7 .text 0xE7E0: charred, then shot off inside the fireball. */
static void Breathe(s32 player)
{
    MBOBJ obj = mbPlayerObjIDGet(player);
    HuVecF pos, dir;
    float tumble = 0.0f;
    s32 i;

    HuPrcSleep(60);
    mbObjBiriQCreate(obj);
    mbObjBiriQColorSet(obj, 0, 1.0f, &charred);
    mbPlayerRotYSet(player, 0.0f);
    mbPlayerPosGet(player, &pos);
    /* MP7 .text 0xE048: the direction from its angles 15 and 165 */
    dir.x = -PagodaSin(165.0f) * PagodaCos(15.0f);
    dir.y = PagodaSin(15.0f);
    dir.z = -PagodaCos(165.0f) * PagodaCos(15.0f);
    ballAt = pos;
    ballOn = TRUE;
    mbCameraShakeSet(18, 500.0f);
    omVibrate(player, 20, 4, 4);
    for (i = 0; i < FLY_FRAMES; i++) {
        pos.x += FLY_SPEED * dir.x;
        pos.y += FLY_SPEED * dir.y;
        pos.z += FLY_SPEED * dir.z;
        tumble += 25.0f;
        mbPlayerPosSetV(player, &pos);
        mbPlayerRotSet(player, tumble, 0.0f, 0.0f);
        ballAt = pos;
        HuPrcVSleep();
    }
}

/* MP7 .text 0xEB5C: down out of the sky onto the start space. */
static void Land(s32 player, s16 start)
{
    HuVecF pos, at;
    s32 i;

    mbMasuPosGet(start, &pos);
    for (i = 1; i <= LAND_FRAMES; i++) {
        float t = (float)i / LAND_FRAMES;
        at = pos;
        at.y += LAND_HEIGHT * (1.0f - t * t);
        mbPlayerPosSetV(player, &at);
        mbPlayerRotSet(player, 25.0f * (LAND_FRAMES - i), 0.0f, 0.0f);
        HuPrcVSleep();
    }
    mbPlayerRotSet(player, 0.0f, 0.0f, 0.0f);
    mbCameraShakeSet(18, 500.0f);
    omVibrate(player, 20, 4, 4);
    mbPlayerMotionShiftSet(player, PLAYER_MOT_STUN, 0.0f, KOOPA_MOT_SHIFT, KOOPA_MOT_LOOP);
}

s32 PagodaDragon(s32 player, s16 masu)
{
    HuVecF masuPos, playerPos, offset, joint;
    s16 start = mbMasuFind_AttrIdGet(-1, 0x8000);
    s32 i;

    if (dragon < 0 || start < 0) {
        return 1;
    }
    mbStatusDispSetAll(FALSE);
    while (!mbStatusOffCheckAll()) {
        HuPrcVSleep();
    }
    mbMasuPosGet(masu, &masuPos);
    mbPlayerPosGet(player, &playerPos);
    offset.x = playerPos.x - masuPos.x;
    offset.y = playerPos.y - masuPos.y;
    offset.z = playerPos.z - masuPos.z;

    /* MP7 .text 0xE2AC-0xE438: turn to it, and it picks the space up */
    JointPos(fireJoint, &joint);
    PagodaTurn(player, atan2(joint.x - masuPos.x, joint.z - masuPos.z) * RAD_TO_DEG);
    mbObjAttrReset(dragon, HU3D_MOTATTR_PAUSE);
    mbObjMotionStartEndSet(dragon, 0, (s32)(mbObjMotionMaxTimeGet(dragon) - MOTION_END_TRIM));
    for (i = 0; i < RIDE_FRAMES; i++) {
        JointPos(rideJoint, &joint);
        playerPos.x = joint.x + offset.x;
        playerPos.y = joint.y + offset.y;
        playerPos.z = joint.z + offset.z;
        mbPlayerPosSetV(player, &playerPos);
        mbMasuPosSetV(masu, &joint);
        HuPrcVSleep();
    }

    /* MP7 .text 0xE464-0xE578: in its mouth, and it breathes */
    mbCameraMoveMasu(masu, &camRot, &camOffset, 3500.0f, -1.0f, 30);
    mbCameraMoveWait();
    JointPos(fireJoint, &joint);
    HuPrcSleep(30);
    mbPlayerPosSetV(player, &joint);
    mbPlayerRotYSet(player, 0.0f);
    Breathe(player);

    /* MP7 .text 0xE57C-0xE7C0: everything back, and down at the start */
    mbWipeFadeOut();
    ballOn = FALSE;
    mbObjAttrSet(dragon, HU3D_MOTATTR_PAUSE);
    mbObjMotionTimeSet(dragon, 0.0f);
    mbMasuPosSetV(masu, &masuPos);
    GwPlayer[player].masuId = start;
    mbev_PlayerColMasuSet(player, start, 1);
    mbCameraMoveMasu(start, NULL, NULL, 2000.0f, -1.0f, -1);
    mbCameraMoveWait();
    mbWipeFadeIn();
    Land(player, start);
    HuPrcSleep(CHARRED_FRAMES);
    mbObjBiriQKill(mbPlayerObjIDGet(player));
    mbPlayerMotionShiftSet(player, PLAYER_MOT_IDLE, 0.0f, KOOPA_MOT_SHIFT, KOOPA_MOT_LOOP);
    mbMasuPosGet(start, &playerPos);
    mbPlayerPosSetV(player, &playerPos);
    mbCameraPlayerViewSetFast(player, 1);
    mbCameraMoveWait();
    mbStatusDispSetAll(TRUE);
    return 0;
}
