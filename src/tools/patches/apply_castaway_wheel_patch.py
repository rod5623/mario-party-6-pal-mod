"""Castaway Bay: the Wheel o' Fortune scaffolding (a passing event, no space of its own).

When any player enters space 20 (from space 16, on the right end of the bottom pier, two blue spaces
after the start pad chain 14 -> 78 -> 66 -> 16 -> 20, just before the fork at 19) the game says "Time for
the Wheel o' Fortune!", spins the 4-slice wheel automatically (nobody chooses) and shows a placeholder
line for the slice it landed on. It fires on every pass, whether the player stops on 20 or walks on.

What was built:
  * Space 20 gets flag 0x4000 in root/data/w05.bin and w05n.bin (day and night are identical).
  * w05Dll .text 0x2300, the `li r3,0` at the common exit of the per-step handler fn_1_2238 (r30 =
    player, r31 = space just entered; registered with fn_80179A0C = lbl_802DE704, which the movement loop
    calls on every step), becomes a module-0 call to the cave below, which ends with the displaced
    `li r3,0`.
  * The cave tests flag 0x4000 on r31, holds the player (as the 0x400 branch of fn_1_2238 does), shows the
    intro, rolls 0-3, runs the Wheel of Fortune's own spin routine (the DOL roulette support and the
    sprite icons are Faire Square's: gold Star, Super 'Shroom, dark Star, Bowser, placeholders) and shows
    "outcome" line 0-3 for the slice the arrow really landed on. The four outcomes are stubs (text only).
  * Text: records 51-55 of bank 0x33 (51 records originally), English in every language file.

The floating wheel marker between spaces 16 and 20 is NOT part of this script yet.
Code space: the dead old MgDataTbl (0x802307A0.., its old rows are not zero, just unused), after the Luck Wheel rewards. Run after
apply_wheel_of_fortune_patch.py and apply_luck_wheel_rewards_patch.py. Idempotent.
Nothing here has been run in Dolphin.
"""
import shutil
import struct

from tools.patches import apply_star_trap_orb_patch as trap
from tools.patches import apply_wheel_of_fortune_patch as wheel
from tools.lib import mpdata
from tools.lib.paths import BUILD, DOL, ROOT
from tools.lib.dol import dol_offset
from tools.lib.minigames import NEW_BASE, OLD_BASE, SECTION_SLOT
from tools.lib.paths import MESS_NAMES, MESS_OUTPUT_DIR, MESS_SOURCE_DIR, REL_DIR, REL_ORIG
from tools.patches.apply_star_shuffle_bet_patch import edit_bank
from tools.lib.messages import encode, record
from tools.lib.ppc import i_li, i_rlwinm
from tools.lib.ppc import Asm, BLR, LWZ, MFLR, MTLR, STW, STWU, i_addi, i_cmpwi, i_lis, i_mem, i_mr, ha, lo
from tools.lib.rel import R_PPC_REL24
from tools.lib.ppc import prologue, epilogue, i_fadds
from tools.lib.boards import flag_offset
from tools.lib.paths import GAME_DATA as DATA_DIR, BACKUPS as BACKUP_DIR
from tools.lib.boards import lz_decode
from tools.lib.game import (
    FN_COINS, FN_MESSAGE, FN_ORB_ADD, FN_ORB_COUNT, FN_ORB_MAX, FN_PLAYER_HOLD, FN_PLAYER_MOTION,
    FN_RANDOM, FN_WAIT_MESSAGE, GW_PLAYER, PLAYER_SIZE,
)
from tools.lib.paths import DATA_ORIG, DATA_OUT
from tools.lib.ppc import LFS, LHA, STB, i_addis, i_extsh, i_lbzx, i_subf
from tools.lib.rel import add_calls, check_words, import_blocks, retarget_call, walk_relocs
from tools.lib.paths import ASSETS

REL_NAME = "w05Dll.rel"
BOARDS = ("w05", "w05n")

TRIGGER_SPACE = 20           # entering it (from 16) fires the wheel
TRIGGER_FLAG = 0x4000        # unused by w05Dll and the main DOL
SITE_HOOK = 0x2300           # w05Dll .text: `li r3,0` at the common exit of fn_1_2238
WORD_HOOK = "38600000"

CAVE_SHOW = 0x802307A0       # 0x40 bytes
CAVE_PASS = 0x802307E0       # 0x130 bytes of code, then the float table at +0x130
CAVE_FLOATS = CAVE_PASS + 0x130
CAVE_END = CAVE_FLOATS + 8
DEAD_END = 0x80232744        # end of the relocated MgDataTbl rows (OLD_BASE + 83 * 0x7C)

# the floating wheel model: created when the board initialises, then turned every frame by an object-manager
# callback (the same mechanism fn_1_F4 / mbCapMasuObjCreate use). All code is in the dead MgDataTbl.
CAVE_MODEL = 0x80230940      # model + object creation (0xA0 bytes)
CAVE_TURN = 0x802309E0       # per-frame callback (0x80 bytes)
CAVE_INIT_HOOK = 0x80230A60  # replaces the board's last init call (0x60 bytes)
CAVE_DATA = 0x80230AC0       # position (3 floats), spin step (float), model id (word), angle (float), zero
MODEL_END = CAVE_DATA + 0x20
CAVE_SPIN = 0x80230B00       # spin with the Castaway icons (0xE0 bytes)
CAVE_OUTCOME = 0x80230BE0    # dispatch on the slice (0x220 bytes)
CAVE_TELEPORT = 0x80230E00   # random special-space teleport (0x200 bytes)
CAVE_ICONS = 0x80231000      # 4 Castaway sprite ids, then Faire's 4 (0x20 bytes)
FN_SPACE_COUNT = 0x80176F28
FN_SPACE_KIND = 0x80177100    # (space id) -> kind: 3 "?", 4 miracle, 5 duel, 6 DK/Bowser
FN_SPACE_POS = 0x80177378     # (space id, float[3])
FN_PLAYER_POS = 0x8015BAD0    # (player, float[3]): put the player there
FN_SOUND = 0x8016FE84
FN_WAIT = 0x8000E244          # (frames)
FN_ADD_COINS = 0x8017E03C     # (player, amount, 1, 1)
TELEPORT_KINDS = (3, 4, 5, 6)
TELEPORT_EXCLUDED = (36, 54)  # 36: fork node by the boats; 54: top cliff "?" - in the data as "?" but not wanted as destinations
SOUND_TELEPORT = 0x5C1
CAVE_ORB = 0x80230720         # Luck Wheel's one-orb routine (r3 = player); not used by this board any more
CAVE_RANDOM_ORB = 0x80231040  # gives one orb from ORB_POOL (0x60 bytes: code, then the id table at +0x50)
# orb ids (plans/orbs/README.md): Mushroom 0, Sluggish 2, Warp Pipe 5, Klepto 13, Podoboo 20, Thwomp 23
ORB_POOL = (13, 0, 23, 5, 20, 2)  # Klepto, Mushroom, Thwomp, Warp Pipe, Podoboo, Sluggish 'Shroom
OUTCOME_END = CAVE_RANDOM_ORB + 0x60
COINS_FINE = 10
COINS_GAIN = 10
NEW_ICON_FILES = (185, 186, 187, 188)
ICON_NAMES = ("orb", "minus10", "warp", "plus10")
# icons by slice: orb, +10 coins, -10 coins, warp
CASTAWAY_ICONS = (0x50000 | NEW_ICON_FILES[0], 0x50000 | NEW_ICON_FILES[3], 0x50000 | NEW_ICON_FILES[1], 0x50000 | NEW_ICON_FILES[2])
ICON_PNG = ASSETS
SITE_INIT = 0x1D34           # w05Dll .text: bl fn_8017461C, the last call of the board init fn_1_F4
FN_INIT_TAIL = 0x8017461C
FN_MODEL_CREATE = 0x801687F4  # (data number, motion list or 0, share flag) -> model id
FN_MODEL_LAYER = 0x80168F60   # (id, layer)
FN_MODEL_POS = 0x80169064     # (id, float[3])
FN_MODEL_ROT = 0x80169328     # (id, f1 x, f2 y, f3 z degrees)
FN_OBJ_ADD = 0x8003AB3C       # (object manager, priority, models, motions, group, callback) -> object
FN_OBJ_DEL = 0x8003AEA4       # (object manager, object)
FN_EXIT_REQ = 0x8014A544      # nonzero while the board is closing
SDA_OBJMAN = -0x6838          # lbl_802DE5C8 (r13-relative): the board's object manager
MODEL_DATA_NUM = 0x00140056   # capsule.bin entry 86, appended by this script
WHEEL_POS = (-919.0, 26.0 + 225.0, 4241.0)  # above space 20 (the second blue space), well above head height
SPIN_STEP = 2.0               # degrees per frame about the vertical axis
CAPSULE_SOURCE = ROOT / "orig" / "GP6P01" / "files" / "data" / "capsule.bin"
CAPSULE_OUTPUT = BUILD / "files" / "data" / "capsule.bin"
WHEEL_HSF = ASSETS / "castaway_wheel.hsf"

BANK = 51
BANK_RECORDS = 51
MSG_BASE = 0x330000
MSG_INTRO = 51               # then 52-55 are the outcome lines for slices 0-3
MSG_FULL = 56                # orb slice with the pockets full
MSG_NO_COINS = 57            # coin fine with no coins
MSG_NO_STARS = 58            # lose-a-Star slice with no Stars
SPEAKER = 0xF                # the Spirits' speaker in fn_1_12D14 / fn_1_13C30 (placeholder)
OUTCOMES = 4
ODDS = None                  # 25% each: FN_RANDOM(4); a weighted table comes with the real outcomes

INDENT = b"    "
TEXT = [
    "Time for the Wheel o' Fortune!",
    "A free orb, just for you!",
    "Lucky you! Ten coins, on the house!",
    "Pay up! Ten coins, please!",
    "Off you go! Time to teleport!",
    "Pockets full, no orb for you!",
    "No coins to fine, lucky you!",
    "No Stars to lose, lucky you!",  # unused since the lose-a-Star slice was replaced; kept so the bank size is unchanged
]
V1_TEXT = ["Time for the Wheel o' Fortune!"] + [f"Outcome {n} (placeholder)" for n in range(1, 5)]
V2_TEXT = ["Time for the Wheel o' Fortune!"] + [f"Slice {name} came up!" for name in ("one", "two", "three", "four")]
V3_TEXT = [  # the +5 coins version
    "Time for the Wheel o' Fortune!", "A free orb, just for you!", "Five coins, on the house!",
    "Pay up! Ten coins, please!", "Off you go! Time to teleport!", "Pockets full, no orb for you!",
    "No coins to fine, lucky you!",
]
V4_TEXT = [  # the lose-a-Star version
    "Time for the Wheel o' Fortune!", "A free orb, just for you!", "Ouch! You lose a Star!",
    "Pay up! Ten coins, please!", "Off you go! Time to teleport!", "Pockets full, no orb for you!",
    "No coins to fine, lucky you!", "No Stars to lose, lucky you!",
]


def records(texts):
    return [record("00150003", INDENT + encode(text.replace("'", "\\")), bytes([0xFF, 0x00])) for text in texts]


RECORDS = records(TEXT)
OLD_TAILS = (records(V1_TEXT), records(V2_TEXT), records(V3_TEXT), records(V4_TEXT))  # earlier versions (placeholder lines)


def build_show(address, msg_base=MSG_BASE, speaker=SPEAKER):
    """r3 = record index in the bank msg_base >> 16 (0x33 here): show that line and wait for it."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x10))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x14))
    a.word(i_addis(4, 3, msg_base >> 16))
    a.word(i_li(3, 2))
    a.word(i_li(5, speaker))
    a.call(FN_MESSAGE)
    a.call(FN_WAIT_MESSAGE)
    a.word(i_mem(LWZ, 0, 1, 0x14))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x10))
    a.word(BLR)
    return a.assemble()


def pass_body(a, show, spin, outcome, floats=CAVE_FLOATS, flag=TRIGGER_FLAG, intro=MSG_INTRO):
    """r30 = player, r31 = space (both live), r29 free: if the space has `flag`, hold, intro, spin, effect.
    Ends at the label "return" (the caller places it)."""
    bit = 31 - (flag.bit_length() - 1)
    if flag != 1 << (31 - bit):
        raise ValueError("the trigger flag must be a single bit")
    a.word(i_mr(3, 31))
    a.call(0x80176FCC)  # fn_80176FCC(space) = flags
    a.word(i_rlwinm(0, 3, 0, bit, bit) | 1)  # rlwinm. r0, r3, 0, bit, bit  (the trigger flag)
    a.branch("beq", "return")
    # hold the player, as fn_1_2238 does for flag 0x400 (fn_801565EC(p,0) ... fn_801565EC(p,1)),
    # and stop the walking animation (Star Shuffle: fn_8015BFB4(p,1,0.0,8.0,0x40000001))
    a.word(i_mr(3, 30))
    a.word(i_li(4, 0))
    a.call(FN_PLAYER_HOLD)
    a.word(i_mr(3, 30))
    a.word(i_li(4, 1))
    a.word(i_lis(5, ha(floats)))
    a.word(i_mem(LFS, 1, 5, lo(floats)))
    a.word(i_mem(LFS, 2, 5, lo(floats) + 4))
    a.word(i_lis(5, 0x4000))
    a.word(i_addi(5, 5, 1))
    a.call(FN_PLAYER_MOTION)
    a.word(i_li(3, intro))
    a.call(show)
    a.word(i_li(3, OUTCOMES))
    a.call(FN_RANDOM)  # 0..3
    a.word(i_mr(4, 3))
    a.word(i_mr(3, 30))
    a.call(spin)  # r3 = the slice the arrow landed on
    a.word(i_mr(29, 3))
    a.word(i_cmpwi(29, 0))
    a.branch("bge", "inrange")
    a.word(i_li(29, 0))
    a.label("inrange")
    a.word(i_cmpwi(29, OUTCOMES - 1))
    a.branch("ble", "known")
    a.word(i_li(29, 0))
    a.label("known")
    a.word(i_mr(3, 30))
    a.word(i_mr(4, 29))
    a.call(outcome)  # the slice's effect: line, then orb / coins / teleport
    a.word(i_mr(3, 30))
    a.word(i_li(4, 1))
    a.call(FN_PLAYER_HOLD)


def build_pass(address, show, spin, outcome):
    """End of fn_1_2238 (r30 = player, r31 = space just entered). Space 20 only: hold, intro, spin, effect."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x20))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x24))
    a.word(i_mem(STW, 29, 1, 0x1C))
    pass_body(a, show, spin, outcome)
    a.label("return")
    a.word(i_li(3, 0))  # the displaced instruction
    a.word(i_mem(LWZ, 0, 1, 0x24))
    a.word(i_mem(LWZ, 29, 1, 0x1C))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x20))
    a.word(BLR)
    code = a.assemble()
    if len(code) > 0x130:
        raise RuntimeError(f"pass cave is {len(code):#x} bytes, too big for 0x130")
    return code


def build_spin(address, spin):
    """r3 = player, r4 = slice: run the wheel with the Castaway icons, put Faire's icons back, return the slice hit."""
    a = Asm(address)
    saved = (29, 30, 31)
    prologue(a, 0x20, saved)
    a.word(i_mr(31, 3))
    a.word(i_mr(30, 4))
    for k in range(4):  # Castaway icons into the shared Kane table
        a.word(i_lis(5, ha(CAVE_ICONS)))
        a.word(i_mem(LWZ, 0, 5, lo(CAVE_ICONS) + 4 * k))
        a.word(i_lis(6, ha(wheel.ICON_TABLE)))
        a.word(i_mem(STW, 0, 6, lo(wheel.ICON_TABLE) + 4 * k))
    a.word(i_mr(3, 31))
    a.word(i_mr(4, 30))
    a.call(spin)
    a.word(i_mr(29, 3))
    for k in range(4):  # Faire Square's icons back
        a.word(i_lis(5, ha(CAVE_ICONS)))
        a.word(i_mem(LWZ, 0, 5, lo(CAVE_ICONS) + 16 + 4 * k))
        a.word(i_lis(6, ha(wheel.ICON_TABLE)))
        a.word(i_mem(STW, 0, 6, lo(wheel.ICON_TABLE) + 4 * k))
    a.word(i_mr(3, 29))
    epilogue(a, 0x20, saved)
    code = a.assemble()
    if len(code) > CAVE_OUTCOME - CAVE_SPIN:
        raise RuntimeError("spin cave overlaps the outcome cave")
    return code


def build_outcome(address, show, teleport, intro=MSG_INTRO, full=MSG_FULL, no_coins=MSG_NO_COINS,
                  limit=CAVE_TELEPORT - CAVE_OUTCOME):
    """r3 = player, r4 = slice (0 orb, 1 +10 coins, 2 -10 coins, 3 teleport): show the line, then apply it."""
    a = Asm(address)
    saved = (29, 30, 31)
    prologue(a, 0x20, saved)
    a.word(i_mr(31, 3))
    a.word(i_mr(30, 4))
    a.word(i_cmpwi(30, 0))
    a.branch("bne", "coins_up")
    # 0: orb, only with a free slot
    a.word(i_mr(3, 31))
    a.call(FN_ORB_MAX)
    a.word(i_mr(29, 3))
    a.word(i_mr(3, 31))
    a.call(FN_ORB_COUNT)
    a.word(wheel.i_x(0, 0, 3, 29))  # cmpw r3, r29
    a.branch("blt", "room")
    a.word(i_li(3, full))
    a.call(show)
    a.branch("b", "done")
    a.label("room")
    a.word(i_li(3, intro + 1))
    a.call(show)
    a.word(i_mr(3, 31))
    a.call(CAVE_RANDOM_ORB)
    a.branch("b", "done")
    a.label("coins_up")
    a.word(i_cmpwi(30, 1))
    a.branch("bne", "coins_down")
    a.word(i_li(3, intro + 2))
    a.call(show)
    a.word(i_mr(3, 31))
    a.word(i_li(4, COINS_GAIN))
    a.word(i_li(5, 1))
    a.word(i_li(6, 1))
    a.call(FN_ADD_COINS)
    a.branch("b", "done")
    a.label("coins_down")
    a.word(i_cmpwi(30, 2))
    a.branch("bne", "warp")
    a.word(i_mr(3, 31))
    a.call(FN_COINS)
    a.word(i_mr(29, 3))
    a.word(i_cmpwi(29, 0))
    a.branch("bgt", "pay")
    a.word(i_li(3, no_coins))
    a.call(show)
    a.branch("b", "done")
    a.label("pay")
    a.word(i_cmpwi(29, COINS_FINE))
    a.branch("ble", "fine")
    a.word(i_li(29, COINS_FINE))  # never more than ten
    a.label("fine")
    a.word(i_li(3, intro + 3))
    a.call(show)
    a.word(i_mr(3, 31))
    a.word(i_li(4, 0))
    a.word(i_subf(4, 29, 4))  # r4 = -r29
    a.word(i_li(5, 1))
    a.word(i_li(6, 1))
    a.call(FN_ADD_COINS)
    a.branch("b", "done")
    a.label("warp")
    a.word(i_li(3, intro + 4))
    a.call(show)
    a.word(i_mr(3, 31))
    a.call(teleport)
    a.label("done")
    epilogue(a, 0x20, saved)
    code = a.assemble()
    if len(code) > limit:
        raise RuntimeError(f"outcome cave is {len(code):#x} bytes, too big")
    return code


def build_random_orb(address):
    """r3 = player: add one orb drawn evenly from ORB_POOL (the caller has checked there is a free slot)."""
    a = Asm(address)
    saved = (31,)
    prologue(a, 0x20, saved)
    a.word(i_mr(31, 3))
    a.word(i_li(3, len(ORB_POOL)))
    a.call(FN_RANDOM)  # 0..5
    a.word(i_lis(4, ha(address + 0x50)))
    a.word(i_addi(4, 4, lo(address + 0x50)))
    a.word(i_lbzx(4, 4, 3))  # r4 = ORB_POOL[r3]
    a.word(i_mr(3, 31))
    a.call(FN_ORB_ADD)  # (player, orb id)
    epilogue(a, 0x20, saved)
    code = a.assemble()
    if len(code) > 0x50:
        raise RuntimeError("random orb routine overlaps its table")
    return code.ljust(0x50, b"\0") + bytes(ORB_POOL).ljust(0x20, b"\0")


def build_teleport(address, excluded=TELEPORT_EXCLUDED, limit=CAVE_ICONS - CAVE_TELEPORT):
    """r3 = player: move them to a random "?", miracle, duel or DK/Bowser space and end their move there."""
    a = Asm(address)
    saved = tuple(range(26, 32))
    frame = 0x40
    prologue(a, frame, saved)
    a.word(i_mr(31, 3))
    # r30 = the space they are on (GwPlayer +0xC), r29 = how many spaces the board has
    a.word(wheel.i_mulli(4, 31, PLAYER_SIZE))
    a.word(i_lis(5, ha(GW_PLAYER)))
    a.word(i_addi(5, 5, lo(GW_PLAYER)))
    a.word(wheel.i_add(5, 5, 4))
    a.word(i_mem(LHA, 30, 5, 0xC))
    a.call(FN_SPACE_COUNT)
    a.word(i_mr(29, 3))
    # pass 1: how many candidates
    a.word(i_li(28, 0))
    a.word(i_li(27, 1))
    a.label("count")
    a.word(wheel.i_x(0, 0, 27, 29))  # cmpw r27, r29
    a.branch("bgt", "counted")
    a.word(i_extsh(3, 27))
    a.call(FN_SPACE_KIND)
    a.word(i_cmpwi(3, TELEPORT_KINDS[0]))
    a.branch("blt", "count_next")
    a.word(i_cmpwi(3, TELEPORT_KINDS[-1]))
    a.branch("bgt", "count_next")
    a.word(wheel.i_x(0, 0, 27, 30))  # not the space they are standing on
    a.branch("beq", "count_next")
    for space in excluded:
        a.word(i_cmpwi(27, space))
        a.branch("beq", "count_next")
    a.word(i_addi(28, 28, 1))
    a.label("count_next")
    a.word(i_addi(27, 27, 1))
    a.branch("b", "count")
    a.label("counted")
    a.word(i_cmpwi(28, 0))
    a.branch("ble", "done")
    a.word(i_mr(3, 28))
    a.call(FN_RANDOM)
    a.word(i_mr(26, 3))  # which candidate
    # pass 2: find it
    a.word(i_li(27, 1))
    a.label("find")
    a.word(wheel.i_x(0, 0, 27, 29))
    a.branch("bgt", "done")  # cannot happen: the count said there were enough
    a.word(i_extsh(3, 27))
    a.call(FN_SPACE_KIND)
    a.word(i_cmpwi(3, TELEPORT_KINDS[0]))
    a.branch("blt", "find_next")
    a.word(i_cmpwi(3, TELEPORT_KINDS[-1]))
    a.branch("bgt", "find_next")
    a.word(wheel.i_x(0, 0, 27, 30))
    a.branch("beq", "find_next")
    for space in excluded:
        a.word(i_cmpwi(27, space))
        a.branch("beq", "find_next")
    a.word(i_cmpwi(26, 0))
    a.branch("beq", "found")
    a.word(i_addi(26, 26, -1))
    a.label("find_next")
    a.word(i_addi(27, 27, 1))
    a.branch("b", "find")
    a.label("found")
    # r27 = destination
    a.word(i_li(3, SOUND_TELEPORT))
    a.call(FN_SOUND)
    a.word(i_extsh(3, 27))
    a.word(i_addi(4, 1, 0x10))
    a.call(FN_SPACE_POS)
    a.word(i_mr(3, 31))
    a.word(i_addi(4, 1, 0x10))
    a.call(FN_PLAYER_POS)
    a.word(wheel.i_mulli(4, 31, PLAYER_SIZE))
    a.word(i_lis(5, ha(GW_PLAYER)))
    a.word(i_addi(5, 5, lo(GW_PLAYER)))
    a.word(wheel.i_add(5, 5, 4))
    a.word(i_mem(wheel.STH, 27, 5, 0xC))  # GwPlayer.masuId = destination
    a.word(i_li(0, 0))
    a.word(i_mem(STB, 0, 5, 0xA))  # no steps left: the move ends on the destination
    a.word(i_li(3, 20))
    a.call(FN_WAIT)
    a.label("done")
    epilogue(a, frame, saved)
    code = a.assemble()
    if len(code) > limit:
        raise RuntimeError(f"teleport cave is {len(code):#x} bytes, too big")
    return code


def wheel_end():
    from tools.patches import apply_luck_wheel_rewards_patch as luck
    return luck.CAVE_END


STFS = 52
D_POS, D_STEP, D_MODEL, D_ANGLE, D_ZERO = 0x00, 0x0C, 0x10, 0x14, 0x18   # offsets in CAVE_DATA


def build_model(address, data=CAVE_DATA, turn=CAVE_TURN, limit=CAVE_TURN - CAVE_MODEL):
    """Board init: create the wheel model above the pier, store its id and start the turning callback."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x20))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x24))
    a.word(i_mem(STW, 31, 1, 0x1C))
    a.word(i_lis(3, MODEL_DATA_NUM >> 16))
    a.word(i_addi(3, 3, MODEL_DATA_NUM & 0xFFFF))
    a.word(i_li(4, 0))
    a.word(i_li(5, 0))
    a.call(FN_MODEL_CREATE)
    a.word(i_extsh(31, 3))
    a.word(i_mr(3, 31))
    a.word(i_li(4, 3))
    a.call(FN_MODEL_LAYER)
    a.word(i_mr(3, 31))
    a.word(i_lis(4, ha(data)))
    a.word(i_addi(4, 4, lo(data)))
    a.call(FN_MODEL_POS)
    a.word(i_lis(4, ha(data)))
    a.word(i_mem(STW, 31, 4, lo(data) + D_MODEL))
    a.word(i_mem(LFS, 0, 4, lo(data) + D_ZERO))
    a.word(i_mem(STFS, 0, 4, lo(data) + D_ANGLE))
    a.word(i_mem(LWZ, 3, 13, SDA_OBJMAN))
    a.word(i_li(4, 0x104))
    a.word(i_li(5, 0))
    a.word(i_li(6, 0))
    a.word(i_li(7, -1))
    a.word(i_lis(8, ha(turn)))
    a.word(i_addi(8, 8, lo(turn)))
    a.call(FN_OBJ_ADD)
    a.word(i_mem(LWZ, 0, 1, 0x24))
    a.word(i_mem(LWZ, 31, 1, 0x1C))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x20))
    a.word(BLR)
    code = a.assemble()
    if len(code) > limit:
        raise RuntimeError("model cave overlaps the turn callback")
    return code


def build_turn(address, data=CAVE_DATA, limit=CAVE_INIT_HOOK - CAVE_TURN):
    """Object-manager callback (r3 = object), once per frame: turn the wheel; remove itself when the board closes."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x20))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x24))
    a.word(i_mem(STW, 31, 1, 0x1C))
    a.word(i_mr(31, 3))
    a.call(FN_EXIT_REQ)
    a.word(i_cmpwi(3, 0))
    a.branch("bne", "leave")
    a.word(i_lis(4, ha(data)))
    a.word(i_addi(4, 4, lo(data)))
    a.word(i_mem(LFS, 2, 4, D_ANGLE))
    a.word(i_mem(LFS, 0, 4, D_STEP))
    a.word(i_fadds(2, 2, 0))
    a.word(i_mem(STFS, 2, 4, D_ANGLE))
    a.word(i_mem(LFS, 1, 4, D_ZERO))
    a.word(i_mem(LFS, 3, 4, D_ZERO))
    a.word(i_mem(LWZ, 3, 4, D_MODEL))
    a.call(FN_MODEL_ROT)
    a.branch("b", "done")
    a.label("leave")
    a.word(i_mem(LWZ, 3, 13, SDA_OBJMAN))
    a.word(i_mr(4, 31))
    a.call(FN_OBJ_DEL)
    a.label("done")
    a.word(i_mem(LWZ, 0, 1, 0x24))
    a.word(i_mem(LWZ, 31, 1, 0x1C))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x20))
    a.word(BLR)
    code = a.assemble()
    if len(code) > limit:
        raise RuntimeError("turn callback overlaps the init hook")
    return code


def build_init_hook(address, model=CAVE_MODEL, limit=CAVE_DATA - CAVE_INIT_HOOK):
    """Replaces `bl fn_8017461C` at the end of fn_1_F4: create the wheel, then make the original call."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x20))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x24))
    a.word(i_mem(STW, 3, 1, 0x08))
    a.word(i_mem(STW, 4, 1, 0x0C))
    a.word(i_mem(STFS, 1, 1, 0x10))
    a.call(model)
    a.word(i_mem(LWZ, 3, 1, 0x08))
    a.word(i_mem(LWZ, 4, 1, 0x0C))
    a.word(i_mem(LFS, 1, 1, 0x10))
    a.call(FN_INIT_TAIL)
    a.word(i_mem(LWZ, 0, 1, 0x24))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x20))
    a.word(BLR)
    code = a.assemble()
    if len(code) > limit:
        raise RuntimeError("init hook overlaps the data table")
    return code


def build_data():
    return struct.pack(">3ffIff", *WHEEL_POS, SPIN_STEP, 0, 0.0, 0.0)


def patch_dol():
    dol = bytearray(DOL.read_bytes())
    section = struct.unpack_from(">I", dol, 0x48 + 4 * SECTION_SLOT)[0]
    if section != NEW_BASE:
        raise SystemExit("Run apply_mgtable_move_patch.py first: the old MgDataTbl is only free code space once it is relocated")
    if CAVE_SHOW < wheel_end() or OUTCOME_END > DEAD_END:
        raise RuntimeError("cave overlaps the Luck Wheel code or runs past the dead MgDataTbl")
    spin = wheel.CAVES["spin"][0]
    at = dol_offset(dol, spin)
    if not any(dol[at:at + 16]):
        raise SystemExit("Run apply_wheel_of_fortune_patch.py first: the wheel's spin routine is missing")
    pieces = {
        CAVE_SHOW: build_show(CAVE_SHOW),
        CAVE_PASS: build_pass(CAVE_PASS, CAVE_SHOW, CAVE_SPIN, CAVE_OUTCOME).ljust(0x130, b"\0") + struct.pack(">ff", 0.0, 8.0),
        CAVE_SPIN: build_spin(CAVE_SPIN, spin),
        CAVE_OUTCOME: build_outcome(CAVE_OUTCOME, CAVE_SHOW, CAVE_TELEPORT),
        CAVE_TELEPORT: build_teleport(CAVE_TELEPORT),
        CAVE_ICONS: struct.pack(">8I", *CASTAWAY_ICONS, *wheel.ICONS),
        CAVE_RANDOM_ORB: build_random_orb(CAVE_RANDOM_ORB),
        CAVE_MODEL: build_model(CAVE_MODEL),
        CAVE_TURN: build_turn(CAVE_TURN),
        CAVE_INIT_HOOK: build_init_hook(CAVE_INIT_HOOK),
        CAVE_DATA: build_data(),
    }
    for address, code in pieces.items():
        position = dol_offset(dol, address)
        dol[position:position + len(code)] = code
    DOL.write_bytes(dol)
    print(f"Castaway Bay wheel code at show {CAVE_SHOW:#x}, pass {CAVE_PASS:#x}, model {CAVE_MODEL:#x} ({OUTCOME_END - CAVE_SHOW:#x} bytes)")


def patch_rel():
    path = REL_DIR / REL_NAME
    data = bytearray((path if path.exists() else REL_ORIG / REL_NAME).read_bytes())
    from tools.patches import apply_castaway_spare_change_patch as spare
    check_words(data, SITE_HOOK, WORD_HOOK, "48000001")
    block = import_blocks(data)[0]
    hooked = {addend for _, section, cursor, kind, _, addend in walk_relocs(data, block)
              if section == 1 and cursor == SITE_HOOK and kind == R_PPC_REL24}
    changed = 0 if spare.CAVE_PASS in hooked else add_calls(data, [(SITE_HOOK, CAVE_PASS)])
    # 0x80230A20: an earlier layout of the caves; the last: where apply_mgtable_move_patch.py (re-run) moves a
    # relocation that points into the old table
    for previous in (FN_INIT_TAIL, 0x80230A20, NEW_BASE + CAVE_INIT_HOOK - OLD_BASE):
        try:
            changed += retarget_call(data, SITE_INIT, previous, CAVE_INIT_HOOK)
            break
        except RuntimeError:
            continue
    else:
        raise RuntimeError("the board init call at text 0x1D34 is not hooked as expected")
    if changed:
        REL_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f"Hooked fn_1_2238 and the board init ({REL_NAME})")
    else:
        print("fn_1_2238 and the board init already hooked")


def patch_board(board):
    path = DATA_DIR / f"{board}.bin"
    data, offsets = mpdata.read_archive(path)
    start, end = mpdata.file_bounds(data, offsets, 0)
    size, kind = struct.unpack_from(">II", data, start)
    blob = bytearray(lz_decode(data[start + 8:end], size) if kind == 1 else mpdata.read_file(data, offsets, 0))
    at = flag_offset(blob, TRIGGER_SPACE)
    current = struct.unpack_from(">I", blob, at)[0]
    if current & TRIGGER_FLAG:
        print(f"{board}: space {TRIGGER_SPACE} already has flag {TRIGGER_FLAG:#x}")
        return
    if current != 0:
        raise RuntimeError(f"{board}: space {TRIGGER_SPACE} already has flags {current:#x}")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"{board}.bin.bak_before_castaway_wheel"
    if not backup.exists():
        shutil.copy2(path, backup)
    struct.pack_into(">I", blob, at, TRIGGER_FLAG)
    packed = mpdata.pack_file(bytes(blob))
    delta = len(packed) - (end - start)
    out = data[:start] + packed + data[end:]
    new_offsets = [o + delta if o > start else o for o in offsets]
    out = struct.pack(">I", len(offsets)) + struct.pack(f">{len(offsets)}I", *new_offsets) + out[4 + 4 * len(offsets):]
    path.write_bytes(out)
    print(f"{board}: space {TRIGGER_SPACE} flag {TRIGGER_FLAG:#x} set")


def patch_messages():
    from tools.patches import apply_castaway_broom_patch as broom
    from tools.patches import apply_castaway_spare_change_patch as spare
    from tools.patches import apply_castaway_troll_patch as troll
    MESS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in MESS_NAMES:
        chained = MESS_OUTPUT_DIR / name
        source = chained if chained.exists() else MESS_SOURCE_DIR / name
        tails = OLD_TAILS + tuple(RECORDS + tail for tail in (broom.RECORDS, *broom.OLD_TAILS))
        tails += (RECORDS + broom.RECORDS + spare.RECORDS,)
        tails += tuple(old + broom.RECORDS + spare.RECORDS for old in OLD_TAILS)
        tails += (RECORDS + broom.RECORDS + spare.RECORDS + troll.RECORDS,)
        tails += tuple(old + broom.RECORDS + spare.RECORDS + troll.RECORDS for old in OLD_TAILS)
        edited = edit_bank(source.read_bytes(), {}, name, bank=BANK, bank_records=BANK_RECORDS, append=RECORDS, known_tails=tails)
        (MESS_OUTPUT_DIR / name).write_bytes(edited)
    print(f"Added records {MSG_INTRO}-{MSG_INTRO + len(RECORDS) - 1} to bank {BANK:#x} in {MESS_OUTPUT_DIR}")


def patch_capsule():
    """Append the wheel model as capsule.bin entry 86 (0x140056), after the Star Trap orb's entry 85."""
    source = CAPSULE_OUTPUT if CAPSULE_OUTPUT.exists() else CAPSULE_SOURCE
    entries = trap.capsule_entries(source.read_bytes())
    # 88, 89: pagoda_board's entries 87 (orb list) and 88 (Cannon model); dropped here, re-added when it runs later
    if len(entries) not in (86, 87, 88, 89):
        raise SystemExit(f"capsule.bin has {len(entries)} entries: run apply_star_trap_orb_patch.py first (expected 86)")
    entries = entries[:86] + [trap.compress_entry(WHEEL_HSF.read_bytes())]
    CAPSULE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    CAPSULE_OUTPUT.write_bytes(trap.pack_capsule(entries))
    print(f"Wheel model is capsule.bin entry 86 ({MODEL_DATA_NUM:#x}) in {CAPSULE_OUTPUT}")


def patch_icons():
    """Add the four Castaway icons as files 185-188 of every board*.bin (after Faire's Super 'Shroom icon, 184)."""
    from PIL import Image
    from tools.lib import battle_thumbnails as bt
    first = NEW_ICON_FILES[0]
    for name in bt.BOARD_FILES:
        out = DATA_OUT / f"{name}.bin"
        source = out if out.exists() else DATA_ORIG / f"{name}.bin"
        data, offsets = mpdata.read_archive(source)
        while len(offsets) > first:  # drop an earlier build of these icons
            data, offsets = wheel.drop_last_file(data, offsets)
        if len(offsets) != first:
            raise SystemExit(f"{source}: {len(offsets)} files, expected {first} (run apply_wheel_of_fortune_patch.py first)")
        template = mpdata.read_file(data, offsets, 0x79)
        payloads = []
        for icon in ICON_NAMES:
            image = Image.open(ICON_PNG / f"castaway_wheel_icon_{icon}.png").convert("RGBA")
            payloads.append(icon_payload(template, image))
        patched, _ = mpdata.append_files(data, offsets, payloads)
        DATA_OUT.mkdir(parents=True, exist_ok=True)
        out.write_bytes(patched)
    print(f"Added the Castaway wheel icons as files {first}-{NEW_ICON_FILES[-1]} of {len(bt.BOARD_FILES)} board archives")


def icon_payload(template, image):
    """An 84x84 CMPR sprite: a copy of an existing icon with the bitmap replaced (as the Faire wheel does)."""
    from PIL import Image
    info = mpdata.parse_anm(template)["bmps"][0]
    if (info["w"], info["h"], info["fmt"], info["size"]) != (84, 84, 10, 3872):
        raise RuntimeError(f"Unexpected template sprite: {info}")
    canvas = Image.new("RGBA", (88, 88), (0, 0, 0, 0))
    canvas.paste(image, (0, 0))
    bitmap = mpdata.encode_cmpr(canvas)
    if len(bitmap) != info["size"]:
        raise RuntimeError("Encoded icon has the wrong size")
    return template[:info["data_o"]] + bitmap


def main():
    patch_dol()
    patch_rel()
    for board in BOARDS:
        patch_board(board)
    patch_messages()
    patch_capsule()
    patch_icons()


if __name__ == "__main__":
    main()
