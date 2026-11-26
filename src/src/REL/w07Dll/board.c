/*
 * Pagoda Peak (board 11): a party board in C with Pagoda Peak's Star, Master Koopa (star.c) and its events.
 *
 * It replaces dll/w07dll.rel (overlay slot 0x70, set up by apply_clone_board_patch.py) and follows the
 * skeleton every MP6 party board REL shares (plans/pagoda-peak/README.md, Route B step 1). It reads its own
 * archive, w07.bin (data dir 261, apply_pagoda_board_patch.py), for day and night alike; the files are listed
 * in pagoda.h (FILE_*): MP7 Pagoda Peak's spaces, masu layer 1 and map model, Snowflake Lake's shopkeeper, its
 * stand and the smoke attached to it, then every event's models.
 * What the engine does for every board works: walking, blue/red/Duel/DK/Bowser/Miracle/orb spaces, the
 * shops and minigames. star.c sells the Star at the summit. The "?" hook (Hatena) dispatches on the space's
 * MP7 flag as MP7's own hook does (w02dll .text 0xF5C), one file per event:
 *   0x80000000 bottle rocket (rocket.c, .text 0x2450)    0x10000000 Kung Fu Falls (kungfu.c, 0x59A8)
 *   0x60000    Gong of Fate (gong.c, 0x9708)             0x4000000  Blazing Rock (blaze.c, 0xA9BC)
 *   0x2000000  the dragon (dragon.c, 0xE1B8)
 * bowser.c brings Bowser Time every 3 turns (the turn-init hook) and keeps the three bridges; star.c's move-end
 * hook asks it first whether a broken bridge stops the player.
 * The view-board area, the opening and map cameras and the board explanation are MP7's (w02dll .text 0x3FC, 0x4C8,
 * 0x5CC, 0x9FC; the explanation is star.c PagodaOpeningInst).
 * Not here yet: day/night visuals (mbev_NextTimeSet) and the Star intro (mbOpeningStarInstHookSet). The engine checks
 * every one of those hooks for NULL.
 *
 * Built by tools/pagoda/build_pagoda_rel.py. p01_names.h maps the names below to Europe (GP6P01) addresses.
 */
#include "pagoda.h"

static MBOBJ mapObj = -1;

/* MP7's opening and map cameras (w02dll .data 0x178, 0x184, 0x1A8 and 0x160, 0x16C, 0x1B0) */
static HuVecF openingRot = { -7.7f, 0.0f, 0.0f };
static HuVecF openingCenter = { 0.0f, 2867.79f, -949.91f };
#define OPENING_ZOOM 16760.0f
static HuVecF mapRot = { -35.0f, 0.0f, 0.0f };
static HuVecF mapCenter = { 0.0f, 1420.52f, -1561.46f };
#define MAP_ZOOM 27438.0f
static char smokeJoint[] = "smoke_f1";

s32 PagodaBoardDir(void)
{
    return DIR_BOARD;
}

void PagodaDirClose(void)
{
    HuDataDirClose(PagodaBoardDir());
}

static void LightSet(void)
{
    Hu3DModelLightInfoSet(mbObjModelIDGet(mapObj), 1);
}

static void LightReset(void)
{
}

/* w04Dll fn_1_1014: the stand under each shopkeeper, and the smoke on it. */
static void ShopSetup(MBOBJ shop)
{
    HuVecF pos, rot;
    MBOBJ stand = mbObjCreate(PagodaBoardDir() | FILE_SHOP_STAND, 0, 1);
    MBOBJ smoke;

    mbObjPosGet(shop, &pos);
    mbObjRotGet(shop, &rot);
    mbObjPosSetV(stand, &pos);
    mbObjRotSetV(stand, &rot);
    smoke = mbObjCreate(PagodaBoardDir() | FILE_SHOP_SMOKE, 0, 1);
    mbObjAttrSet(smoke, OBJ_ATTR_SMOKE);
    mbObjHookSet(shop, smokeJoint, smoke);
    mbObjLayerSet(shop, 3);
    mbObjCullRadiusSet(shop, 400.0f);
}

static s32 HatenaEvent(s32 player, s16 masu)
{
    u32 flags = mbMasuMAttrGet(masu);

    if (flags & MASU_ROCKET) {
        return PagodaRocket(player, masu);
    }
    if (flags & MASU_KUNGFU) {
        return PagodaKungFu(player, masu);
    }
    if (flags & MASU_BLAZE) {
        return PagodaBlaze(player, masu);
    }
    if (flags & MASU_DRAGON) {
        return PagodaDragon(player, masu);
    }
    if (flags & MASU_GONG_MASK) {
        return PagodaGong(player, masu);
    }
    return 1;
}

/* mbev_MasuHatenaSet: returns 1 when no event ran, as MP7's does; closes the board's archive after, as MP7
   does (.text 0x101C) */
static s32 Hatena(s32 player, s16 masu)
{
    s32 result = HatenaEvent(player, masu);

    PagodaDirClose();
    return result;
}

/* Every vertex of `model` in world space, `dy` added to each height (MP7 w02dll .text 0xA650 and 0xDDBC,
   which walk the HSF the same way, without checking the object type). */
void PagodaModelVertices(s16 model, HuVecF *out, s32 max, s32 *count, float dy)
{
    u8 *hsf = PagodaModelHsf(model);
    u8 *obj;
    Mtx m;
    s32 i, k, n = 0;

    *count = 0;
    if (!hsf) {
        return;
    }
    obj = HSF_RAW_OBJECTS(hsf);
    for (i = 0; i < HSF_RAW_OBJECT_NUM(hsf); i++, obj += HSF_RAW_OBJECT_SIZE) {
        u8 *vtx = HSF_RAW_OBJ_VERTEX(obj);
        s32 num;
        if (!vtx) {
            continue;
        }
        num = *(s32 *)(vtx + 4);
        Hu3DModelObjMtxGet(model, HSF_RAW_OBJ_NAME(obj), m);
        for (k = 0; k < num && n < max; k++) {
            PSMTXMultVec(m, &(*(HuVecF **)(vtx + 8))[k], &out[n]);
            out[n].y += dy;
            n++;
        }
    }
    *count = n;
}

/* mbScrollStarFindFuncSet: R on the view-board screen goes to the summit (the engine's own finder looks for
   an MP6 Star space, and this board has none) */
static s16 ScrollStar(s32 player)
{
    return mbMasuFind_MAttrIdGet(-1, MASU_SUMMIT);
}

static void BoardFrame(OMOBJ *obj)
{
    if (mbExitCheck()) {
        omDelObjEx(HuPrcCurrentGet(), obj);
    }
}

static void BoardInit(void)
{
    HuAudSndGrpSetSet(SOUND_GROUP);
    mbObjDirSet(DIR_BOARD, DIR_BOARD);  /* one archive: the day/night swap changes nothing */
    mbMasuInit(PagodaBoardDir() | FILE_SPACES);
    {
        /* masu layer 1, loaded the way MP7 (.text 0x154) and Towering Treetop (w01Dll) load theirs: the ledge
           below each space, for Bowser Time's stomp (bowser.c) */
        s32 layer = mbMasuLayerGet();
        mbMasuLayerSet(1);
        mbMasuDataRead(PagodaBoardDir() | FILE_SPACES_BELOW);
        mbMasuLayerSet(layer);
    }
    mbCapThrowColCreate(-1);
    mapObj = mbObjCreate(PagodaBoardDir() | FILE_MAP, 0, 0);
    mbObjAttrSet(mapObj, OBJ_ATTR_MAP);
    mbObjPosSet(mapObj, 0.0f, 0.0f, 0.0f);
    mbScrollInit(PagodaBoardDir() | FILE_SCROLL);
    mbScrollStarFindFuncSet(ScrollStar);
    mbLightFuncSet(LightSet, LightReset);
    mbev_ShopExInit(PagodaBoardDir() | FILE_SHOP, ShopSetup);
    mbOpeningInstHookSet(PagodaOpeningInst);
    mbOpeningStarInstHookSet(NULL);
    mbOpeningViewSet(&openingRot, &openingCenter, OPENING_ZOOM);
    mbMapCameraSet(&mapRot, &mapCenter, MAP_ZOOM);   /* after mbScrollInit, which resets these */
    PagodaStarInit();
    PagodaGongInit(mapObj);
    PagodaKungFuInit();
    PagodaBlazeInit();
    PagodaDragonInit();
    PagodaBowserInit(mapObj);
    PagodaGapInit(mapObj);
    PagodaCannonInit();
    mbev_MasuHatenaSet(Hatena);
    omAddObjEx(mbObjMan, 0x200C, 0, 0, -1, BoardFrame);
    HuDataDirClose(PagodaBoardDir());
}

static void BoardKill(void)
{
    /* children are unhooked before they are freed: map -> gongs -> sign, map -> bridges and bamboo, house -> sign */
    if (mapObj >= 0) {
        mbObjHookReset(mapObj);
    }
    PagodaRocketKill();
    PagodaKungFuKill();
    PagodaBlazeKill();
    PagodaDragonKill();
    PagodaGongKill();
    PagodaBowserKill();
    PagodaGapKill();
    PagodaStarKill();
    PagodaCannonClose();
    if (mapObj >= 0) {
        mbObjKill(mapObj);
        mapObj = -1;
    }
}

int _prolog(void)
{
    GwSystem.partyF = 1;
    mbObjectSetup(BOARD_NO, BoardInit, BoardKill);
    return 0;
}

void _epilog(void)
{
    PagodaCannonClose();   /* never leave the orb's hooks pointing into an unloaded REL */
}

void _unresolved(void)
{
}
