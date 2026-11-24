"""Castaway Bay: a green "?" space on the bottom-left pier (space 26) with Faire Square's broom ride.

Landing on space 26 (any player, human or CPU) plays the start of Faire Square's broom space (w03Dll fn_1_BDC8,
space 20 there): the player turns to the front, the broom swoops down, the player jumps at broom frame 148 and
hangs from its hook ("fook") from frame 166, carried along the broom's baked flight. At frame CUT_FRAME the ride
is cut: three sparkles where the player is, the player vanishes, the broom fades out over 30 frames. The player
then reappears ARRIVE_HEIGHT above a random space of DESTINATIONS and drops onto it the way Faire drops riders
(mbev_PlayerColReserve + mbPlayerMoveMain, 30 frames), with three more sparkles, and their turn ends there
(GwPlayer.masuId). Option (c) of the investigation: the broom path is not re-aimed, only the take-off is shown.

What was built:
  * root/data/w05.bin and w05n.bin: space 26 kind 1 (blue) -> 3 ("?", green, so the board's landing handler
    runs), flag 0x8000 (unused by the board data, w05Dll and the main DOL). Faire Square's broom models are
    appended as files 46 (the stand, w03 file 0x1B: day copy in w05, night copy in w05n) and 47 (the broom,
    w03 file 0x1C, identical by day and night). Backups: backups/w05*.bin.bak_before_castaway_broom.
  * w05Dll .text 0x21BC, the `li r3,1` at the common exit of the landing handler fn_1_20F8 (r30 = player,
    r31 = space), becomes a module-0 call to CAVE_LAND, which ends with li r3,1.
  * w05Dll .text 0x1D18 (`bl mbOpeningViewSet` in the board init fn_1_F4) is retargeted to CAVE_INIT, which makes
    the original call and then creates both models (data dir 0xEB by day, 0xEC by night) moved by MODEL_OFFSET =
    space 26 - Faire space 20, so their board-space geometry and the broom's flight start at space 26. The
    wheel's init hook (.text 0x1D34) is left alone.
  * The sparkles are Faire's: effect.bin file 3 (data 0x290003, shared) with the particle callback fn_1_F744
    copied out of w03Dll into CAVE_SPARK (its rodata floats into CAVE_POOL, its DOL calls re-aimed).

Code space: the dead old MgDataTbl after the Boo-house caves (0x80231860..0x802326F0 of 0x80232744). Run after
apply_castaway_wheel_patch.py and apply_boo_day_orbs_patch.py (cave layout) and after apply_mgtable_move_patch.py.
Idempotent. Nothing here has been run in Dolphin.
"""
import shutil
import struct

from tools.patches import apply_boo_day_orbs_patch as boo
from tools.patches import apply_castaway_wheel_patch as cw
from tools.patches import apply_wheel_of_fortune_patch as wheel
from tools.lib import mpdata
from tools.lib.paths import DOL, ROOT
from tools.lib.dol import dol_offset
from tools.lib.paths import GAME_DATA as DATA_DIR, BACKUPS as BACKUP_DIR
from tools.patches.apply_castaway_wheel_patch import DEAD_END
from tools.lib.boards import flag_offset
from tools.lib.ppc import prologue, epilogue
from tools.lib.minigames import NEW_BASE, OLD_BASE, SECTION_SLOT
from tools.lib.paths import MESS_NAMES, MESS_OUTPUT_DIR, MESS_SOURCE_DIR, REL_DIR, REL_ORIG
from tools.patches.apply_star_shuffle_bet_patch import edit_bank
from tools.lib.messages import encode, record
from tools.lib.ppc import i_li, i_rlwinm
from tools.lib.ppc import Asm, LWZ, MTCTR, STW, i_addi, i_cmpwi, i_lis, i_mem, i_mr, i_ori, i_slwi, ha, lo
from tools.lib.rel import R_PPC_REL24
from tools.lib.boards import load_spaces, replace_file0
from tools.lib.game import FN_CHOICE, FN_PROMPT, FN_RANDOM, FN_WAIT_MESSAGE, GW_PLAYER, PLAYER_SIZE
from tools.lib.ppc import i_addis, i_extsh
from tools.lib.rel import add_calls, check_words, import_blocks, walk_relocs

BCTRL = 0x4E800421

REL_NAME = "w05Dll.rel"
BOARDS = ("w05", "w05n")
SOURCE_BOARDS = {"w05": "w03", "w05n": "w03n"}  # where the models come from

SPACE = 26                    # bottom-left pier, (-2704, -99, 4241), blue
SPACE_KIND_OLD, SPACE_KIND = 1, 3
BROOM_FLAG = 0x8000
FAIRE_SPACE_POS = (-2345.0, 926.0, -561.0)  # Faire Square space 20, where the broom picks riders up
SPACE_POS = (-2704.0, -99.0, 4241.0)
MODEL_OFFSET = tuple(s - f for s, f in zip(SPACE_POS, FAIRE_SPACE_POS))
# the menu, in order (boards/castaway bay/broom-spots.png): Fans -> 1, the blue space after the ladder on the top
# cliff; Glory -> 3, the "?" on the ruins island by the boats (its event runs on arrival); Heart -> 2, the red
# space on the stepping stones
OPTIONS = ("Fans", "Glory", "Heart")
DESTINATIONS = (48, 36, 56)
GLORY = 1               # the option whose destination's landing event is run after the drop
QUESTION_V1 = "Where shall the broom take you?"  # the first menu had this line above the options

STAND_FILE, BROOM_FILE = 46, 47   # new files of w05.bin / w05n.bin
SOURCE_STAND, SOURCE_BROOM = 0x1B, 0x1C
BOARD_FILES = 46                  # files in the vanilla archives
DIR_DAY, DIR_NIGHT = 0xEB, 0xEC   # data/w05.bin, data/w05n.bin in the DOL's data directory table

PICKUP_FRAME = 166.0   # Faire: from this broom frame the rider hangs from the hook
JUMP_FRAME = 148.0     # Faire: the rider jumps (player motion 9)
CUT_FRAME = 226.0      # ours: end of the ride (one second of carrying)
ARRIVE_HEIGHT = 300.0  # the drop onto the destination starts this far above it
FADE_FRAMES = 30

SITE_LAND = 0x21BC     # w05Dll .text: `li r3,1` at the common exit of fn_1_20F8
WORD_LAND = "38600001"
SITE_INIT = 0x1D18     # w05Dll .text: bl mbOpeningViewSet in fn_1_F4
FN_OPENING = 0x8018F5B0

CAVE_SPARK = 0x80231860  # fn_1_F744 copied from w03Dll (0x5B0 bytes)
SPARK_SOURCE = (0xF744, 0x5B0)
CAVE_POOL = 0x80231E10   # its rodata (up to 0xA0 bytes)
CAVE_INIT = 0x80231EB0   # board init hook (0xD0)
CAVE_RIDE = 0x80231F80   # the ride (0x610)
CAVE_LAND = 0x80232590   # landing hook: menu or CPU pick, ride, Glory's event (0x100)
CAVE_DATA = 0x80232690   # constants (0x60)
CAVE_END = CAVE_DATA + 0x60
# where the hooks pointed in the first layout (random destinations), accepted when re-pointing them
OLD_LAND, OLD_INIT = 0x80231EB0, 0x80231F10
LAND_TO_HANDLER = SITE_LAND + 4 - 0x20F8  # fn_1_20F8 = (return address of the hook's bl) - this

BANK = cw.BANK                                 # 0x33, after the Castaway wheel's records
BANK_RECORDS = cw.BANK_RECORDS + len(cw.RECORDS)
MSG_MENU = BANK_RECORDS
SPEAKER = cw.SPEAKER


def options_only(options):
    """A choice window with just the options (no question line)."""
    body = b"".join(boo.CHOICE + encode(option + ("\n" if i < len(options) - 1 else "")) for i, option in enumerate(options))
    return record("00150003", body, bytes([0]))


RECORDS = [options_only(OPTIONS)]
OLD_TAILS = ([boo.menu(QUESTION_V1, list(OPTIONS))],)

# CAVE_DATA layout
D_OFFSET, D_STAND, D_BROOM = 0x00, 0x0C, 0x10
F_ZERO, F_ONE, F_FOUR, F_32, F_JUMP, F_PICKUP, F_CUT, F_255, F_FADE, F_DROP = range(0x14, 0x3C, 4)
D_SPARK_X = 0x3C       # x offsets of the three sparkles (Faire lbl_1_data_808)
D_FOOK = 0x48
D_DEST = 0x50          # destination ids, u16
SPARK_X = (-50.0, 0.0, 200.0)

# main DOL (P01) functions; names from the GP6E01 symbols
FN_FLAGS = 0x80176FCC          # mbMasuMAttrGet
FN_SLEEP = 0x8000E244          # HuPrcSleep
FN_VSLEEP = 0x8000E2C4         # HuPrcVSleep
FN_DATA_READ = 0x80008638      # HuDataReadNum
FN_DATA_CLOSE = 0x800097F8     # HuDataDirClose
FN_SPR_ANIM = 0x8000F07C       # HuSprAnimRead
FN_MODEL_LAYER = 0x80026B90    # Hu3DModelLayerSet
FN_MODEL_POS = 0x80026764      # Hu3DModelPosSet(id, f1, f2, f3)
FN_OBJ_MTX = 0x8002339C        # Hu3DModelObjMtxGet(model, name, mtx): world matrix of a named object
FN_MTX_ROT = 0x800396EC        # Hu3DMtxRotGet
FN_OBJ_CREATE = 0x801687F4     # mbObjCreate
FN_OBJ_DISP = 0x80168ED4       # mbObjDispSet
FN_OBJ_MODEL = 0x8016901C      # mbObjModelIDGet
FN_OBJ_POS = 0x80169064        # mbObjPosSetV
FN_OBJ_ALPHA = 0x80169780      # mbObjAlphaSet
FN_OBJ_TIME_GET = 0x8016A204   # mbObjMotionTimeGet -> f1
FN_OBJ_TIME_SET = 0x8016A288   # mbObjMotionTimeSet
FN_OBJ_SPEED = 0x8016A3B0      # mbObjMotionSpeedSet
FN_SOUND = 0x8016FE84          # mbAudFXPlay
FN_SOUND_STOP = 0x8016FF5C     # mbAudFXStop
FN_MOVE = 0x801550C8           # mbPlayerMoveMain (waits for the move)
FN_TURN_START = 0x801559C4     # mbPlayerRotateStart
FN_TURN_CHECK = 0x80155D74     # mbPlayerRotateCheck
FN_COL_RESERVE = 0x80157AC8    # mbev_PlayerColReserve
FN_PLAYER_POS = 0x8015BB20     # mbPlayerPosSet(p, f1, f2, f3)
FN_PLAYER_ROT_V = 0x8015BBD0   # mbPlayerRotSetV
FN_PLAYER_ROT = 0x8015BC20     # mbPlayerRotSet(p, f1, f2, f3)
FN_MOTION_SHIFT = 0x8015BFB4   # mbPlayerMotionShiftSet(p, motion, f1 start, f2 shift, attr)
FN_MOTION_CREATE = 0x8015C0C4  # mbPlayerMotionCreate
FN_MOTION_KILL = 0x8015C114    # mbPlayerMotionKill
FN_PLAYER_DISP = 0x8015E4C4    # mbPlayerDispSet
FN_SPACE_POS = 0x80177378      # mbMasuPosGet
FN_PARTICLE_CREATE = 0x801F7A9C
FN_PARTICLE_KILL = 0x801F7EC0
FN_PARTICLE_HOOK = 0x801F8BC0
GW_SYSTEM = 0x80283290
SOUND_BROOM = 0x5CB
SPARK_DATA = 0x00290003        # effect.bin file 3
MOT_HANG, MOT_FALL, MOT_TAKEOFF = 0x9B0022, 0x9B0011, 0x9B0017  # mariomot (per character)
MOT_IDLE, MOT_JUMP = 1, 9
LOOP = 0x40000001              # motion attribute: loop

LFS, STFS, STFD, LHZ, LBZ = 48, 52, 54, 40, 34


def i_fp(xo, d, a, b, op=63):
    return (op << 26) | (d << 21) | (a << 16) | (b << 11) | (xo << 1)


def i_fadds(d, a, b):
    return i_fp(21, d, a, b, op=59)


def i_fsubs(d, a, b):
    return i_fp(20, d, a, b, op=59)


def i_fcmpu(a, b):
    return i_fp(0, 0, a, b)


def i_fcmpo(a, b):
    return i_fp(32, 0, a, b)


def i_fctiwz(d, b):
    return i_fp(15, d, 0, b)


def i_lhzx(d, a, b):
    return (31 << 26) | (d << 21) | (a << 16) | (b << 11) | (279 << 1)


def load_const(a, reg, address):
    a.word(i_lis(reg, ha(address)))
    a.word(i_addi(reg, reg, lo(address)))


def shift_motion(a, motion_reg=None, motion=None, shift=F_FOUR, attr=LOOP):
    """mbPlayerMotionShiftSet(r31, motion, 0.0, shift, attr); r29 = CAVE_DATA."""
    a.word(i_mr(3, 31))
    a.word(i_mr(4, motion_reg) if motion_reg is not None else i_li(4, motion))
    a.word(i_mem(LFS, 1, 29, F_ZERO))
    a.word(i_mem(LFS, 2, 29, shift))
    if attr:
        a.word(i_lis(5, attr >> 16))
        a.word(i_addi(5, 5, attr & 0xFFFF))
    else:
        a.word(i_li(5, 0))
    a.call(FN_MOTION_SHIFT)


def face_front(a, name):
    a.word(i_mr(3, 31))
    a.word(i_li(4, 0))
    a.word(i_li(5, 15))
    a.call(FN_TURN_START)
    a.label(name)
    a.call(FN_VSLEEP)
    a.word(i_mr(3, 31))
    a.call(FN_TURN_CHECK)
    a.word(i_cmpwi(3, 0))
    a.branch("beq", name)


def obj_float(a, obj_reg, fn, const):
    a.word(i_extsh(3, obj_reg))
    a.word(i_mem(LFS, 1, 29, const))
    a.call(fn)


SLOTS = 0x30  # six particle ids on the ride's stack frame


def sparks(a, first, x, y, z, drop):
    """Three of Faire's sparkle particles around (x, y, z) (stack offsets); r22 = the sparkle sprite."""
    for k in range(3):
        slot = SLOTS + 4 * (first + k)
        a.word(i_mr(3, 22))
        a.word(i_li(4, 0x80))
        a.call(FN_PARTICLE_CREATE)
        a.word(i_extsh(3, 3))
        a.word(i_mem(STW, 3, 1, slot))
        load_const(a, 4, CAVE_SPARK)
        a.call(FN_PARTICLE_HOOK)
        a.word(i_mem(LWZ, 3, 1, slot))
        a.word(i_li(4, 5))
        a.call(FN_MODEL_LAYER)
        a.word(i_mem(LWZ, 3, 1, slot))
        a.word(i_mem(LFS, 1, 1, x))
        a.word(i_mem(LFS, 0, 29, D_SPARK_X + 4 * k))
        a.word(i_fadds(1, 1, 0))
        a.word(i_mem(LFS, 2, 1, y))
        if drop:
            a.word(i_mem(LFS, 0, 29, F_DROP))
            a.word(i_fadds(2, 2, 0))
        a.word(i_mem(LFS, 3, 1, z))
        a.call(FN_MODEL_POS)


def build_ride(address):
    """r3 = player, r4 = destination space: broom take-off at space 26, then a drop onto the destination."""
    a = Asm(address)
    frame = 0xC0
    saved = tuple(range(20, 32))
    # stack: 0x08 destination position, 0x18 hook rotation, 0x28 fctiwz scratch, 0x30 six particle ids,
    # 0x50 hook matrix (translation at 0x5C/0x6C/0x7C), 0x88 broom frame, 0x8C broom alpha
    POS, ROT, TMP, MTX, TIME, ALPHA = 0x08, 0x18, 0x28, 0x50, 0x88, 0x8C
    prologue(a, frame, saved)
    a.word(i_mr(31, 3))
    a.word(i_mr(30, 4))
    load_const(a, 29, CAVE_DATA)
    a.word(i_mem(LWZ, 28, 29, D_BROOM))
    a.word(i_mem(LWZ, 20, 29, D_STAND))
    for reg, motion in ((26, MOT_HANG), (25, MOT_FALL), (24, MOT_TAKEOFF)):
        a.word(i_mr(3, 31))
        a.word(i_lis(4, motion >> 16))
        a.word(i_addi(4, 4, motion & 0xFFFF))
        a.call(FN_MOTION_CREATE)
        a.word(i_mr(reg, 3))
    face_front(a, "turn")
    shift_motion(a, motion=MOT_IDLE, shift=F_32)
    a.word(i_li(3, 10))
    a.call(FN_SLEEP)
    # broom and stand: start both motions from frame 0
    a.word(i_extsh(3, 28))
    a.call(FN_OBJ_MODEL)
    a.word(i_extsh(27, 3))
    a.word(i_extsh(3, 28))
    a.word(i_li(4, 1))
    a.call(FN_OBJ_DISP)
    a.word(i_extsh(3, 28))
    a.word(i_li(4, 255))
    a.call(FN_OBJ_ALPHA)
    for obj in (28, 20):
        obj_float(a, obj, FN_OBJ_SPEED, F_ONE)
        obj_float(a, obj, FN_OBJ_TIME_SET, F_ZERO)
    shift_motion(a, motion_reg=24)
    a.word(i_li(3, SOUND_BROOM))
    a.call(FN_SOUND)
    a.word(i_mr(23, 3))
    # carried by the hook until CUT_FRAME
    a.label("ride")
    a.word(i_extsh(3, 27))
    a.word(i_addi(4, 29, D_FOOK))
    a.word(i_addi(5, 1, MTX))
    a.call(FN_OBJ_MTX)
    a.word(i_addi(3, 1, MTX))
    a.word(i_addi(4, 1, ROT))
    a.call(FN_MTX_ROT)
    a.word(i_extsh(3, 28))
    a.call(FN_OBJ_TIME_GET)
    a.word(i_mem(STFS, 1, 1, TIME))
    a.word(i_mem(LFS, 0, 29, F_JUMP))
    a.word(i_fcmpu(0, 1))
    a.branch("bne", "no_jump")
    shift_motion(a, motion=MOT_JUMP, attr=0)
    a.label("no_jump")
    a.word(i_mem(LFS, 1, 1, TIME))
    a.word(i_mem(LFS, 0, 29, F_PICKUP))
    a.word(i_fcmpo(1, 0))
    a.branch("blt", "not_yet")
    shift_motion(a, motion_reg=26)
    a.word(i_mr(3, 31))
    a.word(i_mem(LFS, 1, 1, MTX + 0x0C))
    a.word(i_mem(LFS, 2, 1, MTX + 0x1C))
    a.word(i_mem(LFS, 3, 1, MTX + 0x2C))
    a.call(FN_PLAYER_POS)
    a.word(i_mr(3, 31))
    a.word(i_addi(4, 1, ROT))
    a.call(FN_PLAYER_ROT_V)
    a.label("not_yet")
    a.word(i_mem(LFS, 1, 1, TIME))
    a.word(i_mem(LFS, 0, 29, F_CUT))
    a.word(i_fcmpo(1, 0))
    a.branch("bge", "cut")
    a.call(FN_VSLEEP)
    a.branch("b", "ride")
    # the cut: sparkles, the rider vanishes, the broom fades out
    a.label("cut")
    a.word(i_mr(3, 23))
    a.call(FN_SOUND_STOP)
    a.word(i_lis(3, SPARK_DATA >> 16))
    a.word(i_addi(3, 3, SPARK_DATA & 0xFFFF))
    a.word(i_lis(4, 0x1000))
    a.call(FN_DATA_READ)
    a.call(FN_SPR_ANIM)
    a.word(i_mr(22, 3))
    sparks(a, 0, MTX + 0x0C, MTX + 0x1C, MTX + 0x2C, drop=False)
    a.word(i_mr(3, 31))
    a.word(i_li(4, 0))
    a.call(FN_PLAYER_DISP)
    a.word(i_mem(LFS, 0, 29, F_255))
    a.word(i_mem(STFS, 0, 1, ALPHA))
    a.word(i_li(21, FADE_FRAMES))
    a.label("fade")
    a.word(i_mem(LFS, 1, 1, ALPHA))
    a.word(i_mem(LFS, 0, 29, F_FADE))
    a.word(i_fsubs(1, 1, 0))
    a.word(i_mem(STFS, 1, 1, ALPHA))
    a.word(i_fctiwz(0, 1))
    a.word(i_mem(STFD, 0, 1, TMP))
    a.word(i_mem(LWZ, 4, 1, TMP + 4))
    a.word(i_cmpwi(4, 0))
    a.branch("bge", "alpha_ok")
    a.word(i_li(4, 0))
    a.label("alpha_ok")
    a.word(i_extsh(3, 28))
    a.call(FN_OBJ_ALPHA)
    a.call(FN_VSLEEP)
    a.word(i_addi(21, 21, -1))
    a.word(i_cmpwi(21, 0))
    a.branch("bgt", "fade")
    # the arrival: reappear above the destination and drop onto it
    a.word(i_extsh(3, 30))
    a.word(i_addi(4, 1, POS))
    a.call(FN_SPACE_POS)
    a.word(i_mr(3, 31))
    for f in (1, 2, 3):
        a.word(i_mem(LFS, f, 29, F_ZERO))
    a.call(FN_PLAYER_ROT)
    a.word(i_mr(3, 31))
    a.word(i_mem(LFS, 1, 1, POS))
    a.word(i_mem(LFS, 2, 1, POS + 4))
    a.word(i_mem(LFS, 0, 29, F_DROP))
    a.word(i_fadds(2, 2, 0))
    a.word(i_mem(LFS, 3, 1, POS + 8))
    a.call(FN_PLAYER_POS)
    a.word(i_li(3, 10))
    a.call(FN_SLEEP)
    sparks(a, 3, POS, POS + 4, POS + 8, drop=True)
    a.word(i_mr(3, 31))
    a.word(i_li(4, 1))
    a.call(FN_PLAYER_DISP)
    a.word(i_mr(3, 31))
    a.word(i_mr(4, 30))
    a.word(i_li(5, 0))
    a.call(FN_COL_RESERVE)
    a.word(i_mr(3, 31))
    a.word(i_li(4, 0))
    a.word(i_addi(5, 1, POS))
    a.word(i_mr(6, 25))
    a.word(i_mem(LFS, 1, 29, F_ONE))
    a.word(i_li(7, 0))
    a.word(i_li(8, 30))
    a.word(i_li(9, 0))
    a.word(i_li(10, 1))
    a.call(FN_MOVE)
    shift_motion(a, motion=MOT_IDLE, shift=F_32)
    # the turn ends on the destination
    a.word(wheel.i_mulli(4, 31, PLAYER_SIZE))
    load_const(a, 5, GW_PLAYER)
    a.word(wheel.i_add(5, 5, 4))
    a.word(i_mem(wheel.STH, 30, 5, 0xC))
    face_front(a, "turn_back")
    a.word(i_mr(3, 31))
    for f in (1, 2, 3):
        a.word(i_mem(LFS, f, 29, F_ZERO))
    a.call(FN_PLAYER_ROT)
    for reg in (26, 25, 24):
        a.word(i_mr(3, 31))
        a.word(i_mr(4, reg))
        a.call(FN_MOTION_KILL)
    a.word(i_li(3, 20))
    a.call(FN_SLEEP)
    for k in range(6):
        a.word(i_mem(LWZ, 3, 1, SLOTS + 4 * k))
        a.call(FN_PARTICLE_KILL)
    a.word(i_lis(3, SPARK_DATA >> 16))
    a.call(FN_DATA_CLOSE)
    # park the broom and the stand on frame 0, as Faire does (the broom stays faded out until the next ride)
    for obj in (20, 28):
        obj_float(a, obj, FN_OBJ_SPEED, F_ZERO)
        obj_float(a, obj, FN_OBJ_TIME_SET, F_ZERO)
    epilogue(a, frame, saved)
    code = a.assemble()
    if len(code) > CAVE_LAND - CAVE_RIDE:
        raise RuntimeError(f"ride cave is {len(code):#x} bytes, too big")
    return code


def build_land(address):
    """End of fn_1_20F8 (r30 = player, r31 = space). Space 26 only: a human picks Fans / Glory / Heart from a menu
    (B shows it again), a CPU picks at random; ride there. For Glory, then run fn_1_20F8 for the destination, so
    its "?" event plays as on a normal landing (that call comes back through this hook with no broom flag)."""
    a = Asm(address)
    frame = 0x20
    prologue(a, frame, (29,))
    a.word(i_mr(3, 31))
    a.call(FN_FLAGS)
    a.word(i_rlwinm(0, 3, 0, 16, 16) | 1)  # rlwinm. r0, r3, 0, 16, 16  (flag 0x8000)
    a.branch("beq", "return")
    a.word(wheel.i_mulli(4, 30, PLAYER_SIZE))
    load_const(a, 5, GW_PLAYER)
    a.word(wheel.i_add(5, 5, 4))
    a.word(i_mem(LBZ, 0, 5, 0))
    a.word(i_rlwinm(0, 0, 0, 26, 26) | 1)  # CPU (as in apply_boo_day_orbs_patch.py)
    a.branch("beq", "menu")
    a.word(i_li(3, len(DESTINATIONS)))
    a.call(FN_RANDOM)
    a.word(i_mr(29, 3))
    a.branch("b", "go")
    a.label("menu")
    a.word(i_li(3, 2))
    a.word(i_addis(4, 0, cw.MSG_BASE >> 16))
    a.word(i_addi(4, 4, MSG_MENU))
    a.word(i_li(5, SPEAKER))
    a.word(i_li(6, 0))
    a.call(FN_PROMPT)
    a.call(FN_WAIT_MESSAGE)
    a.call(FN_CHOICE)
    a.word(i_mr(29, 3))
    a.word(i_cmpwi(29, 0))
    a.branch("blt", "menu")  # cancelled: ask again
    a.word(i_cmpwi(29, len(DESTINATIONS) - 1))
    a.branch("bgt", "menu")
    a.label("go")
    a.word(i_slwi(3, 29, 1))
    load_const(a, 4, CAVE_DATA + D_DEST)
    a.word(i_lhzx(4, 4, 3))
    a.word(i_mr(3, 30))
    a.call(CAVE_RIDE)
    a.word(i_cmpwi(29, GLORY))
    a.branch("bne", "return")
    a.word(i_mem(LWZ, 12, 1, frame + 4))  # our return address, inside fn_1_20F8
    a.word(i_addi(12, 12, -LAND_TO_HANDLER))
    a.word(MTCTR(12))
    a.word(i_mr(3, 30))
    a.word(i_li(4, DESTINATIONS[GLORY]))
    a.word(BCTRL)
    a.label("return")
    a.word(i_li(3, 1))  # the displaced instruction
    epilogue(a, frame, (29,))
    code = a.assemble()
    if len(code) > CAVE_DATA - CAVE_LAND:
        raise RuntimeError(f"landing cave is {len(code):#x} bytes, too big")
    return code


def build_init(address):
    """Replaces `bl mbOpeningViewSet` in fn_1_F4: make that call, then create the stand and the broom."""
    a = Asm(address)
    saved = (30, 31)
    prologue(a, 0x30, saved)
    a.call(FN_OPENING)  # its arguments (r3, r4, f1) are still in place
    load_const(a, 31, CAVE_DATA)
    load_const(a, 3, GW_SYSTEM)
    a.word(i_mem(LBZ, 0, 3, 0x10))
    a.word(i_rlwinm(0, 0, 0, 25, 25) | 1)  # night bit 0x40
    a.word(i_li(30, DIR_DAY))
    a.branch("beq", "day")
    a.word(i_li(30, DIR_NIGHT))
    a.label("day")
    for file, slot in ((STAND_FILE, D_STAND), (BROOM_FILE, D_BROOM)):
        a.word(i_slwi(3, 30, 16))
        a.word(i_ori(3, 3, file))
        a.word(i_li(4, 0))
        a.word(i_li(5, 0))
        a.call(FN_OBJ_CREATE)
        a.word(i_extsh(3, 3))
        a.word(i_mem(STW, 3, 31, slot))
        if slot == D_BROOM:  # as fn_1_F4 in w03Dll: visible, stopped on frame 0
            a.word(i_li(4, 1))
            a.call(FN_OBJ_DISP)
            a.word(i_mem(LWZ, 3, 31, slot))
            a.word(i_mem(LFS, 1, 31, F_ZERO))
            a.call(FN_OBJ_TIME_SET)
            a.word(i_mem(LWZ, 3, 31, slot))
        a.word(i_mem(LFS, 1, 31, F_ZERO))
        a.call(FN_OBJ_SPEED)
        a.word(i_mem(LWZ, 3, 31, slot))
        a.word(i_addi(4, 31, D_OFFSET))
        a.call(FN_OBJ_POS)
    epilogue(a, 0x30, saved)
    code = a.assemble()
    if len(code) > CAVE_RIDE - CAVE_INIT:
        raise RuntimeError("init cave overlaps the ride")
    return code


def build_data():
    floats = (0.0, 1.0, 4.0, 32.0, JUMP_FRAME, PICKUP_FRAME, CUT_FRAME, 255.0, 255.0 / FADE_FRAMES, ARRIVE_HEIGHT)
    data = struct.pack(">3fII", *MODEL_OFFSET, 0, 0) + struct.pack(">10f", *floats) + struct.pack(">3f", *SPARK_X)
    data += b"fook".ljust(8, b"\0")
    if len(DESTINATIONS) > 8:
        raise ValueError("at most 8 destinations")
    data += struct.pack(f">{len(DESTINATIONS)}H", *DESTINATIONS).ljust(0x10, b"\0")
    assert len(data) == 0x60
    return data


def rel_sections(rel):
    table, count = struct.unpack_from(">I", rel, 0x10)[0], struct.unpack_from(">I", rel, 0x0C)[0]
    return [struct.unpack_from(">I", rel, table + 8 * i)[0] & ~1 for i in range(count)]


def symbol_sizes():
    """(REL section, offset) -> size from the w03Dll symbols (sections numbered as in the REL)."""
    numbers = {".rodata": 4, ".data": 5}
    sizes = {}
    path = ROOT / "config" / "GP6P01" / "rels" / "w03Dll" / "symbols.txt"
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) > 2 and ":" in parts[2] and "size:" in line:
            section, offset = parts[2].rstrip(";").split(":")
            if section in numbers:
                size = int(line.split("size:")[1].split()[0], 16)
                sizes[(numbers[section], int(offset, 16))] = size
    return sizes


def build_spark():
    """fn_1_F744 of w03Dll, moved to CAVE_SPARK: rodata into CAVE_POOL, module-0 calls re-aimed."""
    rel = (REL_ORIG / "w03Dll.rel").read_bytes()
    sections = rel_sections(rel)
    start, size = SPARK_SOURCE
    code = bytearray(rel[sections[1] + start:sections[1] + start + size])
    self_id = struct.unpack_from(">I", rel, 0)[0]
    sizes = symbol_sizes()
    pool, placed = bytearray(), {}
    for module, block in import_blocks(rel).items():
        for _, section, cursor, kind, target_section, addend in walk_relocs(rel, block):
            if section != 1 or not start <= cursor < start + size:
                continue
            at = cursor - start
            if module == 0:
                target = addend
            elif module == self_id and target_section in (4, 5):
                key = (target_section, addend)
                if key not in placed:
                    length = sizes[key]
                    pool.extend(b"\0" * (-len(pool) % 8))
                    placed[key] = CAVE_POOL + len(pool)
                    pool.extend(rel[sections[target_section] + addend:sections[target_section] + addend + length])
                target = placed[key]
            else:
                raise RuntimeError(f"fn_1_F744: unexpected relocation to module {module} section {target_section}")
            if kind == R_PPC_REL24:
                word = struct.unpack_from(">I", code, at)[0]
                word = (word & 0xFC000003) | ((target - (CAVE_SPARK + at)) & 0x03FFFFFC)
                struct.pack_into(">I", code, at, word)
            elif kind in (4, 6):  # R_PPC_ADDR16_LO / _HA: the offset is that of the low halfword itself
                struct.pack_into(">H", code, at, lo(target) if kind == 4 else ha(target))
            else:
                raise RuntimeError(f"fn_1_F744: relocation kind {kind} at {cursor:#x}")
    if len(pool) > CAVE_INIT - CAVE_POOL:
        raise RuntimeError(f"sparkle rodata is {len(pool):#x} bytes, too big")
    return bytes(code), bytes(pool)


def patch_dol():
    dol = bytearray(DOL.read_bytes())
    if struct.unpack_from(">I", dol, 0x48 + 4 * SECTION_SLOT)[0] != NEW_BASE:
        raise SystemExit("Run apply_mgtable_move_patch.py first: the old MgDataTbl is only free code space once it is relocated")
    if CAVE_SPARK < boo.CAVE_COPY + 0x460 or CAVE_END > DEAD_END:
        raise RuntimeError("cave overlaps the Boo-house code or runs past the dead MgDataTbl")
    spark, pool = build_spark()
    pieces = {
        CAVE_SPARK: spark,
        CAVE_POOL: pool,
        CAVE_LAND: build_land(CAVE_LAND),
        CAVE_INIT: build_init(CAVE_INIT),
        CAVE_RIDE: build_ride(CAVE_RIDE),
        CAVE_DATA: build_data(),
    }
    for address, code in pieces.items():
        position = dol_offset(dol, address)
        dol[position:position + len(code)] = code
    DOL.write_bytes(dol)
    print(f"Broom ride code at {CAVE_SPARK:#x}-{CAVE_END:#x} (ride {len(pieces[CAVE_RIDE]):#x} bytes, sparkle pool {len(pool):#x})")


def point_call(rel, offset, target, originals=(), earlier=()):
    """Make the module-0 call at a text offset go to target: retarget it (from an original target, an earlier cave
    layout's target, or where a re-run of apply_mgtable_move_patch.py moved one of ours), or add it when the site
    has none."""
    ours = (target,) + tuple(earlier)
    moved = {NEW_BASE + (t - OLD_BASE) for t in ours}
    block = import_blocks(rel)[0]
    hits = [(position, addend) for position, section, cursor, kind, _, addend in walk_relocs(rel, block)
            if section == 1 and cursor == offset and kind == R_PPC_REL24]
    if not hits:
        if originals:
            raise RuntimeError(f"no module-0 call at text {offset:#x}")
        return add_calls(rel, [(offset, target)])
    changed = 0
    for position, addend in hits:
        if addend == target:
            continue
        if addend not in originals and addend not in ours and addend not in moved:
            raise RuntimeError(f"call at text {offset:#x} goes to {addend:#x}, expected one of {originals} or {target:#x}")
        struct.pack_into(">I", rel, position + 4, target)
        changed += 1
    return changed


def patch_rel():
    path = REL_DIR / REL_NAME
    data = bytearray((path if path.exists() else REL_ORIG / REL_NAME).read_bytes())
    check_words(data, SITE_LAND, WORD_LAND, "48000001")
    from tools.patches import apply_castaway_troll_patch as troll
    changed = point_call(data, SITE_LAND, CAVE_LAND, earlier=(OLD_LAND, troll.CAVE_LAND))
    changed += point_call(data, SITE_INIT, CAVE_INIT, (FN_OPENING,), earlier=(OLD_INIT,))
    if changed:
        REL_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f"Hooked fn_1_20F8 and the board init ({REL_NAME})")
    else:
        print("fn_1_20F8 and the board init already hooked")


def patch_board(board):
    path = DATA_DIR / f"{board}.bin"
    data, offsets = mpdata.read_archive(path)
    source, source_offsets = mpdata.read_archive(DATA_DIR / f"{SOURCE_BOARDS[board]}.bin")
    models = [mpdata.read_file(source, source_offsets, n) for n in (SOURCE_STAND, SOURCE_BROOM)]
    blob, start, end = load_spaces(data, offsets)
    at = flag_offset(blob, SPACE)
    flags, kind = struct.unpack_from(">I", blob, at)[0], struct.unpack_from(">H", blob, at + 4)[0]
    space_done = flags & BROOM_FLAG and kind == SPACE_KIND
    if not space_done and (flags != 0 or kind != SPACE_KIND_OLD):
        raise RuntimeError(f"{board}: space {SPACE} has flags {flags:#x}, kind {kind} (expected 0, {SPACE_KIND_OLD})")
    if len(offsets) in (BOARD_FILES + 2, BOARD_FILES + 3, BOARD_FILES + 4):  # + 3: the spare change guy's card is file 48; + 4: the troll's is 49
        present = [mpdata.read_file(data, offsets, n) for n in (STAND_FILE, BROOM_FILE)]
        if present != models:
            raise RuntimeError(f"{board}: files {STAND_FILE}-{BROOM_FILE} are not the broom models")
    elif len(offsets) != BOARD_FILES:
        raise RuntimeError(f"{board}: {len(offsets)} files, expected {BOARD_FILES} or {BOARD_FILES + 2} to {BOARD_FILES + 4}")
    if space_done and len(offsets) > BOARD_FILES:
        print(f"{board}: space {SPACE} and the broom models already in place")
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"{board}.bin.bak_before_castaway_broom"
    if not backup.exists():
        shutil.copy2(path, backup)
    if not space_done:
        struct.pack_into(">I", blob, at, BROOM_FLAG)
        struct.pack_into(">H", blob, at + 4, SPACE_KIND)
        data, offsets = replace_file0(data, offsets, start, end, blob)
    if len(offsets) == BOARD_FILES:
        data, offsets = mpdata.append_files(data, offsets, models)
    path.write_bytes(data)
    print(f"{board}: space {SPACE} is a broom \"?\" space (flag {BROOM_FLAG:#x}); broom models are files {STAND_FILE}-{BROOM_FILE}")


def patch_messages():
    """The menu as record 59 of bank 0x33, after the Castaway wheel's records 51-58."""
    from tools.patches import apply_castaway_spare_change_patch as spare
    MESS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    from tools.patches import apply_castaway_troll_patch as troll
    tails = OLD_TAILS + (RECORDS + spare.RECORDS, RECORDS + spare.RECORDS + troll.RECORDS)
    for name in MESS_NAMES:
        chained = MESS_OUTPUT_DIR / name
        source = chained if chained.exists() else MESS_SOURCE_DIR / name
        edited = edit_bank(source.read_bytes(), {}, name, bank=BANK, bank_records=BANK_RECORDS, append=RECORDS, known_tails=tails)
        (MESS_OUTPUT_DIR / name).write_bytes(edited)
    print(f"Added record {MSG_MENU} (the broom menu) to bank {BANK:#x}")


def main():
    patch_dol()
    patch_rel()
    for board in BOARDS:
        patch_board(board)
    patch_messages()


if __name__ == "__main__":
    main()
