/* Pagoda Peak (board 11): the game functions and constants shared by board.c and star.c.
   Include first: p01_names.h maps the names below to Europe (GP6P01) addresses. */
#ifndef PAGODA_H
#define PAGODA_H

#include "p01_names.h"
#include "game/gamework.h"
#include "game/object.h"
#include "game/data.h"
#include "game/audio.h"
#include "game/hu3d.h"
#include "game/process.h"
#include "game/pad.h"
#include "game/sprite.h"
#include "math.h"

/* ---- DOL board functions without a header in this decomp (signatures from their disassembly) ---- */
typedef s16 MBOBJ;
extern OMOBJMAN *mbObjMan;
void mbObjectSetup(s32 boardNo, void (*init)(void), void (*kill)(void));
BOOL mbExitCheck(void);
void mbObjDirSet(s32 dirDay, s32 dirNight);
void mbMasuInit(s32 dataNum);
MBOBJ mbObjCreate(s32 dataNum, s32 *motTbl, s32 arg2); /* motTbl: full data numbers, -1 at the end */
void mbObjKill(MBOBJ obj);
void mbObjAttrSet(MBOBJ obj, u32 attr);
void mbObjAttrReset(MBOBJ obj, u32 attr);
void mbObjMotionTimeSet(MBOBJ obj, float time);
void mbObjDispSet(MBOBJ obj, BOOL disp);
void mbObjRotYSet(MBOBJ obj, float rotY);
/* motNo indexes motTbl from 1; attr 0x40000001 loops, 0 plays once */
void mbObjMotionSet(MBOBJ obj, s32 motNo, u32 attr);
void mbObjMotionShiftSet(MBOBJ obj, s32 motNo, float start, float shift, u32 attr);
void mbObjPosSet(MBOBJ obj, float x, float y, float z);
void mbObjPosGet(MBOBJ obj, HuVecF *pos);
void mbObjPosSetV(MBOBJ obj, HuVecF *pos);
void mbObjRotGet(MBOBJ obj, HuVecF *rot);
void mbObjRotSetV(MBOBJ obj, HuVecF *rot);
void mbObjCullRadiusSet(MBOBJ obj, float radius);
void mbObjHookSet(MBOBJ obj, char *joint, MBOBJ child);
void mbObjHookReset(MBOBJ obj);
void mbObjLayerSet(MBOBJ obj, s32 layer);
s16 mbObjModelIDGet(MBOBJ obj);
void mbScrollInit(s32 dataNum);   /* the view-board area: a hidden mesh whose outer edges bound the camera */
void mbScrollStarFindFuncSet(s16 (*func)(s32 player));   /* R "Star Space"; set after mbScrollInit, which resets it */
void mbCapThrowColCreate(s32 dataNum);
void mbLightFuncSet(void (*set)(void), void (*reset)(void));
void mbOpeningInstHookSet(void *hook);
void mbOpeningStarInstHookSet(void *hook);
void mbOpeningViewSet(HuVecF *rot, HuVecF *center, float zoom);
void mbMapCameraSet(HuVecF *rot, HuVecF *center, float zoom);
void mbev_ShopExInit(s32 dataNum, void (*setup)(MBOBJ shop));

#define BOARD_NO 11
#define SOUND_GROUP 0x19   /* Snowflake Lake's */
#define DIR_BOARD 0x01050000 /* data dir 261, w07.bin (apply_pagoda_board_patch.py), day and night alike */
/* w07.bin's files, in the order of apply_pagoda_board_patch.py FILES (tests/test_pagoda_files.py checks) */
#define FILE_SPACES 0          /* MP7 w02.bin 0 with MP7's flags (tools/pagoda/spaces.py) */
#define FILE_SPACES_BELOW 1    /* masu layer 1 (MP7 w02.bin 1): each space's link to the ledge below */
#define FILE_MAP 2             /* MP7 w02.bin 6 */
#define FILE_SHOP 3            /* Snowflake Lake's shopkeeper, its stand and the smoke on it (w04.bin 5, 6, 8) */
#define FILE_SHOP_STAND 4
#define FILE_SHOP_SMOKE 5
#define FILE_KOOPA 6      /* Master Koopa (MP7 w02.bin 0x35), then his motions 1-5 (0x36-0x3A) as files 7-11 */
#define FILE_HOUSE 12     /* the summit's house and platform (MP7 0x25) */
#define FILE_SIGN 13      /* the price sign on the house's h_rate0 joint (MP7 0x14) */
#define FILE_GONG 14      /* a Gong of Fate, on the map's h_dora0/h_dora1 joints (MP7 0x13) */
#define FILE_ROCKET 15    /* a bottle rocket on its stand (MP7 0x0B) */
#define FILE_ROCK 16      /* a rock coming down Kung Fu Falls (MP7 0x10) */
#define FILE_CLOUD 17     /* Master Koopa's cloud (MP7 0x26) */
/* Blazing Rock (MP7 0x15, 0x17, 0x18, 0x16, 0x19, 0x1A, 0x2E, 0x30) */
#define FILE_ROCK_FIRE 18 /* the burning rock in front of the cave, motion looping */
#define FILE_ROCK_OUT 19  /* the same rock with the fire out */
#define FILE_EMITTER 20   /* hidden: the flames sit on its vertices */
#define FILE_FAN 21
#define FILE_CHEST 22
#define FILE_TSHIRT 23
#define FILE_FLAME 24     /* sprite animation */
#define FILE_SMOKE 25     /* sprite animation */
/* the dragon by space 44 (MP7 0x1B, 0x1C, 0x33) */
#define FILE_DRAGON 26
#define FILE_FIREBALL 27          /* hidden: the fireball's flames sit on its vertices */
#define FILE_FIREBALL_SPRITE 28
/* Bowser Time (bowser.c): Bowser (MP7 capsulechar1.bin 0) with his motions 1-9 as files 30-38 (capsulechar1
   1, 2, 8, 5, 0x10, 6, 0x11, 0xA, 0xB), and the bridges (MP7 w02.bin 0x1D intact, 0x1E breaking, 0x1F broken) */
#define FILE_BOWSER 29
#define FILE_BRIDGE 39
#define FILE_BAMBOO 42         /* a bamboo pole on the map's h_bamboo0..2 joints (MP7 w02.bin 9) */
#define FILE_BRANCH 43         /* the tree branch by space 86 (MP7 w02.bin 0xA) */
/* the Cannon orb (cannon.c): MP7 capsule.bin 0x51 (body), 0x50 (barrel, hooked on the body's "center"), 0x42 */
#define FILE_CANNON 44
#define FILE_CANNON_BARREL 45
#define FILE_CANNON_BOOM 46
#define FILE_SCROLL 47         /* the view-board area mesh (MP7 w02.bin 4, MP7's mbScrollInit at .text 0x3FC) */
/* MP7's player motions (MP7 <char>.bin 0x82, 0x83, 0x89, 0x8B), appended to every MP6 <char>mot.bin as files
   126-129 by pagoda_board (write_char_motions); CharMotionCreate swaps mariomot for the player's own archive. */
#define MOT_FAN_SLOW (P01_DATA_mariomot | 126)
#define MOT_FAN_FAST (P01_DATA_mariomot | 127)
#define MOT_CHEST_HOLD (P01_DATA_mariomot | 128)
#define MOT_CHEST_CARRY (P01_DATA_mariomot | 129)
#define OBJ_ATTR_MAP 0x40000001
#define OBJ_ATTR_SMOKE 0x40000001

/* ---- Message windows, coins and Stars (signatures from MP6 board RELs that call them) ---- */
s16 mbWinCreate(s32 type, u32 mes, s32 speaker);
s16 mbWinCreateChoice(s32 type, u32 mes, s32 speaker, s32 arg);
void mbWinInsertMesSet(s16 win, u32 mes, s16 slot);
void mbWinWait(s16 win);
s32 mbWinChoiceGet(s16 win);
void mbComChoiceUpSet(void);
void mbComChoiceLeftSet(void);
u32 mbPlayerNameMesGet(s32 player);
s32 mbPlayerCoinGet(s32 player);
void mbCoinAddDispExec(s32 player, s32 coin, s32 arg2, s32 arg3);
void mbStarGetExec(s32 player);
void mbCameraPlayerViewSet(s32 player, s32 arg);
void mbCameraMoveWait(void);
void mbCameraMoveObj(MBOBJ obj, HuVecF *rot, HuVecF *offset, float zoom, float arg, s32 frames);
void mbCameraFocusObjSet(MBOBJ obj);   /* -1: the camera stops following an object */
void mbCameraPlayerViewSetFast(s32 player, s32 arg);
void mbCameraStackPush(void);
void mbCameraStackPop(s32 frames);   /* Snowflake Lake passes -1 */
s32 mbGuideSpeakerNoGet(void);   /* the host, as the speaker of mbWinCreate */
void mbCameraMoveMasu(s16 masu, HuVecF *rot, HuVecF *offset, float zoom, float arg, s32 frames);
void mbPlayerRotateStart(s32 player, s32 angle, s32 frames);
BOOL mbPlayerRotateCheck(s32 player);
void mbev_MasuMoveEndSet(s32 (*hook)(s32 player, s16 masu));
/* PlayerMove's step count (fn_801548D8): a space counts when mbMasuDispCheck is non-zero; the step sound is
   0x3EE, and mbMoveNumKill removes the move counter once moveNum reaches 0 */
BOOL mbMasuDispCheck(s16 masu);
void mbAudFXPlay(s32 seNo);
void mbMoveNumKill(s32 player);
void mbMoveNumDispSet(s32 player, s32 on);   /* hides or shows the move counter; does nothing without one */
#define MSM_SE_BOARD_STEP 0x3EE
/* Losing a Star with the game's popup, as the mod's Star Trap orb does: the popup above the player, then
   wait for it, then take the Star */
void mbStarDispPlayerCreate(s32 player, s32 star);
BOOL mbStarDispCheck(s32 player);
s32 mbPlayerStarGet(s32 player);
void mbPlayerStarAdd(s32 player, s32 star);
/* "?" spaces: ev_MasuHatena calls the hook as a player lands; it returns 1 when no event ran */
void mbev_MasuHatenaSet(s32 (*hook)(s32 player, s16 masu));
u32 mbMasuMAttrGet(s16 masu);
u32 mbev_MasuAttrGet(s32 index, u32 mask);   /* index packed into the bits of mask */
s16 mbMasuFind_MAttrMatchIdGet(s16 from, u32 attr, u32 mask);
s16 mbMasuAttrFindLink(s16 masu, u32 type);   /* the linked space with this type bit */
s16 mbMasuLinkGet(s16 masu, s32 index);

/* ---- Event presentation (signatures from MP6 board and DOL callers) ---- */
void mbStatusDispSetAll(BOOL disp);
BOOL mbStatusOffCheckAll(void);
s16 mbWinCreateHelp(u32 mes);
void mbWinKill(s16 win);
u32 mbRandMod(u32 n);
void mbCameraShakeSet(s32 frames, float power);
/* MP6's take radians: a 2048-entry cosine table indexed by angle * 1303.797 (= 8192 / 2pi, lbl_802E0974).
   MP7's functions match these byte for byte but read a different constant and take degrees, so MP7's
   angles go through PagodaSin / PagodaCos. */
float mbSinRad(float rad);
float mbCosRad(float rad);
#define DEG_TO_RAD 0.017453292f
#define PagodaSin(deg) mbSinRad((deg) * DEG_TO_RAD)
#define PagodaCos(deg) mbCosRad((deg) * DEG_TO_RAD)
void mbPlayerPosGet(s32 player, HuVecF *pos);
void mbPlayerMotionShiftSet(s32 player, s32 motNo, float start, float shift, u32 attr);
void mbCameraMovePos(HuVecF *pos, HuVecF *rot, HuVecF *offset, float zoom, float arg, s32 frames);
float mbAngleLerp(float from, float to, float t);
void mbPlayerRotYSet(s32 player, float rotY);
float mbPlayerRotYGet(s32 player);
s16 mbCoinCreate(void);
void mbCoinObjKill(s16 coin);
void mbCoinObjDispSet(s16 coin, BOOL disp);
void mbCoinObjPosSetV(s16 coin, HuVecF *pos);
void mbCoinObjRotSet(s16 coin, float x, float y, float z);
void mbCoinObjAlphaSet(s16 coin, float alpha);
#define PLAYER_MOT_IDLE 1
#define PLAYER_MOT_JUMP 4    /* a plain jump, for scripted arcs (PlayerDropExec) */
#define PLAYER_MOT_LAND 5
#define PLAYER_MOT_JOY 7     /* the cheer when getting a Star (mbStarGetMain); 12 sank the player into the floor */
#define RAD_TO_DEG 57.29578f

/* ---- Moving a player to another space (the same calls as the debug warp orb, mbev_CapDebugWarp) ---- */
s16 mbMasuFind_AttrIdGet(s16 from, u32 attr);
void mbMasuPosGet(s16 masu, HuVecF *pos);
void mbPlayerPosSetV(s32 player, HuVecF *pos);
void mbev_PlayerColMasuSet(s32 player, s16 masu, s32 arg);
void mbWipeFadeOut(void);
void mbWipeFadeIn(void);
void mbWipeDissolveFadeOut(void);
void mbWipeDissolveFadeIn(void);

/* Pagoda Peak's text: MP7 bank 0x14 as its own bank 0x4B, after the 75 vanilla banks
   (apply_pagoda_board_patch.py), so MP7 record n is message PAGODA_MES(n). */
#define PAGODA_MES(n) (0x004B0000 + (n))

/* board.c */
s32 PagodaBoardDir(void);
/* Reading one file of an archive loads the whole archive into the DVD heap until it is closed (data.c
   HuDataDirReadNum). w07.bin holds every event's models (about 1 MB), so close it after every model made
   during the game, as MP7 does (HuDataDirClose(0xFE0000) after its events); closing it twice is harmless. */
void PagodaDirClose(void);

/* star.c: the summit, Master Koopa and the Star price */
#define PRICE_LEVELS 4          /* 10, 20, 30, 40 coins */
/* Master Koopa's motions (MP7's numbers, the index into his motion table) */
#define KOOPA_MOT_IDLE 1
#define KOOPA_MOT_WALK 2
#define KOOPA_MOT_TALK 3
#define KOOPA_MOT_GIVE 4
#define KOOPA_MOT_BYE 5
#define KOOPA_MOT_LOOP 0x40000001
#define KOOPA_MOT_SHIFT 4.0f
void PagodaStarInit(void);
void PagodaStarKill(void);
void PagodaOpeningInst(void);   /* the board explanation (mbOpeningInstHookSet) */
MBOBJ PagodaKoopa(void);
MBOBJ PagodaSign(void);
s32 PagodaPriceLevel(void);
void PagodaPriceLevelSet(s32 level);
void PagodaSignShow(s32 level);
s32 PagodaStarPrice(void);
void PagodaSay(u32 mes, s32 player);              /* player >= 0: their name goes in slot 0 */
void PagodaTurn(s32 player, s32 angle);
void PagodaKoopaMotion(s32 motNo, u32 attr);
void PagodaKoopaArrive(HuVecF *pos, float rotY);
void PagodaKoopaLeave(HuVecF *pos);
void PagodaKoopaShowAt(HuVecF *pos, float rotY);
void PagodaKoopaHide(void);                       /* him and his cloud */
void mbObjScaleSet(MBOBJ obj, float x, float y, float z);
void mbObjMtxSet(MBOBJ obj, Mtx mtx);
MBOBJ mbPlayerObjIDGet(s32 player);
s16 mbPlayerModelIDGet(s32 player);
s16 mbPlayerMotionCreate(s32 player, s32 dataNum);
void mbPlayerMotionKill(s32 player, s16 mot);
void mbPlayerMotionSpeedSet(s32 player, float speed);
void mbObjBiriQCreate(MBOBJ obj);
void mbObjBiriQColorSet(MBOBJ obj, s32 arg, float arg2, GXColor *color);
void mbObjBiriQKill(MBOBJ obj);
void mbObjMotionStartEndSet(MBOBJ obj, s32 start, s32 end);
float mbObjMotionMaxTimeGet(MBOBJ obj);
void mbMasuPosSetV(s16 masu, HuVecF *pos);
void mbPlayerRotSet(s32 player, float x, float y, float z);
void mbCameraMovePlayer(s32 player, HuVecF *rot, HuVecF *offset, float zoom, float arg, s32 frames);
/* Hu3DData is lbl_802DDAA8 in PAL (Hu3DModelObjMtxGet, Hu3DParticleCreate). The PAL HU3D_MODEL doesn't match
   the decomp's hu3d.h (hsf is at +0xC4, hookData at +0x120, 0x134 bytes each), so models are read through
   these offsets, the ones MP7 uses too. The particle record and its data do match hu3d.h. */
extern u8 *lbl_802DDAA8;
#define PAGODA_MODEL(id) (lbl_802DDAA8 + (id) * 0x134)
#define PagodaModelHsf(id) (*(u8 **)(PAGODA_MODEL(id) + 0xC4))
#define PagodaModelParticle(id) (*(HU3D_PARTICLE **)(PAGODA_MODEL(id) + 0x120))
/* HSF data as MP7 w02dll .text 0xA650 walks it: objects at +0x4C (0x144 bytes each, name at +0x0, vertex
   buffer at +0x108: count at +0x4, HuVecF data at +0x8), object count at +0x6C. */
#define HSF_RAW_OBJECTS(hsf) (*(u8 **)((hsf) + 0x4C))
#define HSF_RAW_OBJECT_NUM(hsf) (*(s16 *)((hsf) + 0x6C))
#define HSF_RAW_OBJECT_SIZE 0x144
#define HSF_RAW_OBJ_NAME(obj) (*(char **)(obj))
#define HSF_RAW_OBJ_VERTEX(obj) (*(u8 **)((obj) + 0x108))
void PagodaModelVertices(s16 model, HuVecF *out, s32 max, s32 *count, float dy);
#define KOOPA_DROP 900.0f
#define KOOPA_DROP_FRAMES 48

/* gong.c: the Gong of Fate (spaces flagged 0x20000 and 0x40000) */
#define MASU_GONG_MASK 0x60000
void PagodaGongInit(MBOBJ map);
void PagodaGongKill(void);
s32 PagodaGong(s32 player, s16 masu);

/* rocket.c: the bottle rocket (space flagged 0x80000000) */
#define MASU_ROCKET 0x80000000
s32 PagodaRocket(s32 player, s16 masu);
void PagodaRocketKill(void);

/* kungfu.c: Kung Fu Falls (space flagged 0x10000000) */
#define MASU_KUNGFU 0x10000000
void PagodaKungFuInit(void);
void PagodaKungFuKill(void);
s32 PagodaKungFu(s32 player, s16 masu);

/* blaze.c: Blazing Rock (space flagged 0x4000000) */
#define MASU_BLAZE 0x4000000
void PagodaBlazeInit(void);
void PagodaBlazeKill(void);
s32 PagodaBlaze(s32 player, s16 masu);

/* dragon.c: the dragon (space flagged 0x2000000) */
#define MASU_DRAGON 0x2000000
void PagodaDragonInit(void);
void PagodaDragonKill(void);
s32 PagodaDragon(s32 player, s16 masu);

/* bowser.c: Bowser Time and the bridges (spaces flagged under 0xE00000) */
void mbPlayerTurnInitHookSet(void (*hook)(s32 player));
BOOL mbObjMotionEndCheck(MBOBJ obj);
void mbObjRotSet(MBOBJ obj, float x, float y, float z);
s16 mbMasuFind_MAttrIdGet(s16 from, u32 attr);
s32 mbMasuLayerGet(void);
void mbMasuLayerSet(s32 layer);
void mbMasuDataRead(s32 dataNum);
s16 mbMasuLinkNumGet(s16 masu);
void PagodaBowserInit(MBOBJ map);
void PagodaBowserKill(void);
BOOL PagodaBridgeBlocked(s32 player, s16 masu);
BOOL PagodaBridgeBroken(s16 masu);

/* gaps.c: the bamboo poles (space flagged 0x8000) and the branch (0x2000) players leap across */
void mbObjMotionSpeedSet(MBOBJ obj, float speed);
void PagodaGapInit(MBOBJ map);

/* cannon.c: the Cannon orb (orb id 8). The DOL's orb event row 8 jumps through these two words in section 19
   (apply_pagoda_board_patch.py CANNON_HOOKS); NULL = the orb does nothing (other boards). */
#define PAGODA_CANNON_EXEC_HOOK (*(void (**)(void))0x802FAAA0)
#define PAGODA_CANNON_KILL_HOOK (*(void (**)(void))0x802FAAA4)
#define PAGODA_CANNON_COM_HOOK (*(s32 (**)(s32, s32))0x802FAAA8)   /* CPU chance (mbCapComChanceGet) */
void mbev_CapWait(s32 *work);
void mbCapEffUseCreate(s32 player, s32 capsule);
s32 mbCapEffUseModeGet(s32 player);
void OSReport(const char *fmt, ...);
u16 mbMasuAttrGet(s16 masu);                        /* the space's type word (masu +0x10): 0x2000 side node, 0x20 shop */
s16 mbMasuFind_MAttrStepGet(s16 from, u32 attr);   /* steps from `from` to the nearest space with flag `attr` */
#define MASU_SUMMIT 0x10000                         /* MP7's flag on the summit (space 54) */
s32 mbev_MasuStop(s32 player, s16 masu);           /* a space's event after a move (PlayerTurn 0x80153E70) */
void mbPlayerMotIdleSet(s32 player);
void mbev_CapRandomBonusCoin(s32 player, s32 capsule, s32 arg);   /* fn_801D527C: the orb-use bonus coins (calls mbev_CapBonusCoin) */
void mbPlayerColSnapPlayerSet(s32 player, s32 on);
void mtxRot(Mtx m, float x, float y, float z);       /* degrees */
void mbPlayerScaleSet(s32 player, float x, float y, float z);
void mbPlayerDispSet(s32 player, s32 on);
void PagodaCannonInit(void);
void PagodaCannonClose(void);
void PagodaGapKill(void);
BOOL PagodaGap(s32 player, s16 masu);

#endif
