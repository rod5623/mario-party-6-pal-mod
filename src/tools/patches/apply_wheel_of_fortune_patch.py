"""Faire Square space 30: the Wheel of Fortune (replaces "send the player back to the start").

Landing on space 30 asks "Spin the wheel?" (Yes/No; CPUs always spin) and then spins the Warp Pipe
Orb's pie-chart roulette (arrow spinning over a pie), extended to 4 slices. Passing it does nothing.
The outcome is rolled first and the wheel is forced to land on it:
  Jackpot (20%)        +2 Stars                           (Star icon)
  Item Windfall (30%)  fill every empty orb slot with a random Super 'Shroom / Sluggish / Flutter
                       orb                                (rendered Super 'Shroom icon)
  Fine (30%)           -1 Star (nothing if they have none) (dark Star icon)
  Send-back (20%)      the old behaviour, fn_1_C5DC       (Bowser head, placeholder)
The spin is automatic for everyone; nobody presses a button.

How the roulette was extended (all DOL, P01 addresses; see boards/faire-square/faire-square.md):
  * Warp Pipe only knows 2 and 3 slices. Five switch statements fall through to a "default" for 4,
    reading garbage. Their `bge` (count > 3) branches are redirected to small handlers.
  * 4 slices are centred on top, right, bottom and left (the existing divider sprite board 0x78 is an
    X): slot = floor(((degrees + 45) mod 360) / 90). The arrow's bearing equals its angle.
  * The wheel is forced with the game's own "ComValue" flag (lbl_802DE7FE): it also makes the user
    take the automatic path. Warp Pipe never sets it, so Warp Pipe is unchanged. The stop decision
    for 4 slices uses roulette_sim.py's measured landing offset: the wheel lands 208 degrees (plus
    or minus 1) after the angle at which the stop is commanded, so it stops when
    (angle + 208 - 90*slot + 30) mod 360 < 60, i.e. lands within +-30 degrees of the slice centre.
  * "Kane" mode (lbl_802DE7FC) makes the icon of slice i come from table lbl_802662B8+0x5C indexed
    by the choice value instead of by the player's character; nothing else uses that table.
New code lives in the old MgDataTbl at 0x8022FF44, which is dead once apply_mgtable_move_patch.py
has relocated the table (this script refuses to run before that). Two REL hooks (module-0 calls):
  * .text 0x1D3C, the `li r3,0` at the end of the landing handler fn_1_1CD4 (r29 = player, r31 =
    space, r30 = flags): the landing cave does the prompt (flag 0x20 only) and calls the wheel with
    the address of fn_1_C5DC (= LR + 0xA89C), which the wheel calls for the send-back outcome.
  * .text 0x1C70, the `bl fn_1_C5DC` in the passing handler fn_1_1C30: now a call to a bare `blr`.

The rendered Super 'Shroom icon is appended to every board*.bin as file 184 (sprite 0x500B8).
Messages are records 80-86 of bank 49, added by apply_star_shuffle_bet_patch.py.
Run after apply_mgtable_move_patch.py, apply_battle_thumbs_patch.py and apply_double_or_nothing_patch.py.
Idempotent. Nothing here has been run in Dolphin.
"""
import struct

from tools.lib.paths import DOL
from tools.lib.dol import dol_offset, encode_branch, replace_bytes
from tools.lib.ppc import (
    Asm, BLR, LBZ, LWZ, MFLR, MTLR, STH, STW, STWU, i_add, i_addi, i_cmpwi, i_lis, i_mem, i_mr, i_mulli,
    i_x, ha, lo,
)
from tools.lib import mpdata
from tools.lib.minigames import NEW_BASE, SECTION_SLOT
from tools.lib.paths import REL_DIR, REL_ORIG
from tools.patches.apply_star_shuffle_bet_patch import REL_NAME
from tools.lib.ppc import i_li, i_rlwinm
from tools.lib import battle_thumbnails as bt
from tools.lib.paths import DATA_ORIG, DATA_OUT
from tools.lib.ppc import (
    LHA, STB, LFS, i_mullw, i_divw, i_subf, i_or, i_srawi, i_lbzx, i_addis, b_to, i_extsh, i_extsb,
    i_slwi,
)
from tools.lib.game import (
    FN_MESSAGE, FN_WAIT_MESSAGE, FN_RANDOM, FN_STARS, FN_ADD_STARS, FN_ORB_MAX, FN_ORB_COUNT, FN_ORB_ADD,
    FN_PLAYER_HOLD, FN_PLAYER_MOTION, FN_PROMPT, FN_CHOICE, GW_PLAYER, PLAYER_SIZE,
)
from tools.lib.rel import add_calls, check_words
from tools.lib.paths import ASSETS

# ---- roulette (main DOL) ---------------------------------------------------------------------

HOOK_INIT_COUNT = 0x80196A14  # Init: bge (count > 3) over the slice-count setup
HOOK_INIT_ICONS = 0x80196E30  # Init: bge over the icon positions
HOOK_SPIN_WIDTH = 0x80197120  # fn_80196FF4: bge over the slice width
HOOK_CPU_WIDTH = 0x80197AC4   # fn_80197A98: bge over the slice width
HOOK_SLOT = 0x80197B3C        # fn_80197B28: bge over the slot divisor
HOOK_CPU_TEST = 0x801977D0    # fn_80197738: cmplwi r0,0 (is the user a CPU?)
HOOK_STOP = 0x80197818        # fn_80197738: lha r0, lbl_802DE7FE (forced-stop flag)
HOOK_COUNT = 0x80196450       # fn_801963B8: `li r28,3` threw away the slice count argument (always 3 opponents)
WORD_COUNT = 0x3B800003
WORD_NOP = 0x60000000

RET_INIT_COUNT = 0x80196A40
RET_INIT_ICONS = 0x80196F0C
RET_SPIN_WIDTH = 0x8019713C
RET_CPU_WIDTH = 0x80197AE0
RET_SLOT = 0x80197B90
RET_STOP_DONE = 0x801978E0    # mr r3, r28 (r28 = the stop decision)

WORD_BGE = {  # original `bge` words (a 4-slice wheel took these branches into garbage)
    HOOK_INIT_COUNT: 0x4080002C, HOOK_INIT_ICONS: 0x408000DC, HOOK_SPIN_WIDTH: 0x4080001C,
    HOOK_CPU_WIDTH: 0x4080001C, HOOK_SLOT: 0x40800054,
}
WORD_CPU_TEST = 0x28000000   # cmplwi r0,0
WORD_STOP = 0xA80D99FE       # lha r0,-0x6602(r13)

FN_ICON_POS = 0x8000FD7C     # fn_8000FD7C(group, sprite, x, y)
FN_ROULETTE_CREATE = 0x801963B8  # (player, count, kane)
FN_ROULETTE_WAIT = 0x80196690
FN_ROULETTE_RESULT = 0x801966E0  # -> lbl_802DE810[result slot]
FN_ROULETTE_COM = 0x8019793C  # sets the forced-stop flag and the target choice value

ICON_TABLE = 0x802662B8 + 0x5C  # 4 sprite ids, indexed by the choice value (kane mode)
ICON_ORIGINAL = (0x50079, 0x5007A, 0x5007B, 0x5007C)
SPRITE_BOARD = 0x50000
NEW_ICON_FILE = 184  # first free file of the board archives (the thumbnails use 176-183)
ICONS = (SPRITE_BOARD | 0xA6, SPRITE_BOARD | NEW_ICON_FILE, SPRITE_BOARD | 0xA7, SPRITE_BOARD | 0xA8)
# outcome value: 0 Jackpot (gold Star), 1 Item Windfall (Super 'Shroom), 2 Fine (dark Star), 3 Send-back (Bowser)

# ---- the space 30 handler (code in the dead MgDataTbl) ---------------------------------------

BASE = 0x80230000
CAVES = {
    "init_count": (BASE + 0x000, 0x20),
    "init_icons": (BASE + 0x020, 0x80),   # code + 8 floats
    "spin_width": (BASE + 0x0A0, 0x10),
    "cpu_width": (BASE + 0x0B0, 0x10),
    "slot": (BASE + 0x0C0, 0x40),
    "cpu_test": (BASE + 0x100, 0x20),
    "stop": (BASE + 0x120, 0xC0),
    "show": (BASE + 0x1E0, 0x40),
    "stars": (BASE + 0x220, 0x80),
    "orbs": (BASE + 0x2A0, 0xA0),
    "spin": (BASE + 0x340, 0x80),
    "wheel": (BASE + 0x3C0, 0x1C0),
    "landing": (BASE + 0x580, 0x100),
    "noop": (BASE + 0x680, 0x10),
}
END_OF_CAVES = BASE + 0x690

FN_STAR_POPUP = 0x80181DDC
FN_POPUP_DONE = 0x80182258
FN_YIELD = 0x8000E2C4

SPEAKER = 8
MSG_BASE = 0x310000
MSG_INTRO = 80   # bank 49 records 80-86, see apply_star_shuffle_bet_patch.WHEEL
MSG_JACKPOT = 81
MSG_ITEMS = 82
MSG_FULL = 83
MSG_FINE = 84
MSG_NO_STARS = 85
MSG_BACK = 86
MSG_ASK = 87     # "Spin the wheel?" with Yes/No

SITE_PASS = 0x1C70           # w03Dll .text: bl fn_1_C5DC in the passing handler fn_1_1C30
WORD_PASS = "4800A96D"
SITE_LAND = 0x1D3C           # w03Dll .text: li r3,0 at the end of the landing handler fn_1_1CD4
WORD_LAND = "38600000"
SEND_BACK_FROM_LR = 0xA89C   # fn_1_C5DC = (LR after the bl at SITE_LAND, i.e. 0x1D40) + this

# ---- instruction helpers ----------------------------------------------------------------------

SDA = {  # r13-relative offsets (lbl@sda21)
    "kane": -0x6604,    # lbl_802DE7FC
    "force": -0x6602,   # lbl_802DE7FE
    "value": -0x65FC,   # lbl_802DE804
    "table": -0x65F0,   # lbl_802DE810
    "group": -0x780E,   # lbl_802DD5F2
}
MTCTR_R12 = 0x7D8903A6
BCTRL = 0x4E800421


def build_init_count(address):
    """Init, 4 slices: slice count local = 4 (sp+0xA) and f29 = 60.0 as the 2/3 cases do."""
    a = Asm(address)
    a.word(i_li(0, 4))
    a.word(i_mem(STH, 0, 1, 0xA))
    a.word(0xC3A2AB0C)  # lfs f29, lbl_802E14AC (60.0)
    a.word(b_to(address + 12, RET_INIT_COUNT))
    return a.assemble()


ICON_XY = ((0.0, -50.0), (50.0, 0.0), (0.0, 50.0), (-50.0, 0.0))  # top, right, bottom, left (y down)


def build_init_icons(address):
    """Init icon loop, 4 slices: r30 = slice, place sprite 5+slice at its position."""
    a = Asm(address)
    table = address + 0x30
    a.word(i_lis(5, ha(table)))
    a.word(i_addi(5, 5, lo(table)))
    a.word(i_extsh(0, 30))
    a.word(i_slwi(0, 0, 3))
    a.word(i_add(5, 5, 0))
    a.word(i_mem(LFS, 1, 5, 0))
    a.word(i_mem(LFS, 2, 5, 4))
    a.word(i_mem(LHA, 3, 13, SDA["group"]))
    a.word(i_addi(0, 30, 5))
    a.word(i_extsh(4, 0))
    a.call(FN_ICON_POS)
    a.word(0)  # placeholder, replaced below
    code = bytearray(a.assemble())
    struct.pack_into(">I", code, len(code) - 4, b_to(address + len(code) - 4, RET_INIT_ICONS))
    code += b"\0" * (0x30 - len(code))
    for x, y in ICON_XY:
        code += struct.pack(">ff", x, y)
    return bytes(code)


def build_const_branch(address, reg, value, target):
    a = Asm(address)
    a.word(i_li(reg, value))
    a.word(0)
    code = bytearray(a.assemble())
    struct.pack_into(">I", code, 4, b_to(address + 4, target))
    return bytes(code)


def build_slot(address):
    """fn_80197B28, 4 slices: r3 = state, result r31 = floor(((angle + 45) mod 360) / 90)."""
    a = Asm(address)
    # (addi with rA = r0 means "load immediate", so the angle lives in r5, not r0)
    a.word(i_mem(LHA, 5, 3, 8))
    a.word(i_addi(5, 5, 45))
    a.word(i_li(4, 360))
    a.word(i_divw(6, 5, 4))
    a.word(i_mullw(6, 6, 4))
    a.word(i_subf(5, 6, 5))
    a.word(i_li(4, 90))
    a.word(i_divw(31, 5, 4))
    a.word(0)
    code = bytearray(a.assemble())
    struct.pack_into(">I", code, len(code) - 4, b_to(address + len(code) - 4, RET_SLOT))
    return bytes(code)


def build_cpu_test(address):
    """fn_80197738 (r0 = CPU bit): also take the automatic path when the forced-stop flag is set."""
    a = Asm(address)
    a.word(i_mem(LHA, 12, 13, SDA["force"]))
    a.word(i_or(0, 0, 12))
    a.word((10 << 26) | (0 << 16))  # cmplwi r0,0
    a.word(BLR)
    return a.assemble()


def build_stop(address):
    """fn_80197738 stop decision. r29 = roulette state. Flag clear: original behaviour.
    Flag set: stop when the predicted landing is within +-30 degrees of the target slice's centre."""
    a = Asm(address)
    a.word(i_mem(LHA, 0, 13, SDA["force"]))
    a.word(i_cmpwi(0, 0))
    a.branch("bne", "forced")
    a.word(0)  # b RET_STOP_DONE (original `beq`)
    a.label("forced")
    a.word(i_mem(LHA, 8, 29, 8))
    a.word(i_srawi(8, 8, 4))  # r8 = angle in whole degrees
    a.word(i_mem(LHA, 4, 13, SDA["value"]))  # target choice value
    a.word(i_addi(6, 13, SDA["table"]))
    a.word(i_li(5, 0))
    a.label("scan")
    a.word(i_lbzx(7, 6, 5))
    a.word(i_extsb(7, 7))
    a.word(i_x(0, 0, 7, 4))  # cmpw r7, r4
    a.branch("beq", "found")
    a.word(i_addi(5, 5, 1))
    a.word(i_cmpwi(5, 4))
    a.branch("blt", "scan")
    a.word(i_li(5, 0))
    a.label("found")
    a.word(i_mulli(5, 5, 90))
    a.word(i_addi(8, 8, 208 + 30))
    a.word(i_subf(8, 5, 8))  # r8 = angle + 238 - 90 * slot
    a.word(i_li(4, 360))
    a.word(i_divw(7, 8, 4))
    a.word(i_mullw(7, 7, 4))
    a.word(i_subf(8, 7, 8))
    a.word(i_cmpwi(8, 0))
    a.branch("bge", "positive")
    a.word(i_addi(8, 8, 360))
    a.label("positive")
    a.word(i_li(28, 0))
    a.word(i_cmpwi(8, 60))
    a.branch("bge", "done")
    a.word(i_li(28, 0x100))
    a.label("done")
    a.word(0)  # b RET_STOP_DONE
    code = bytearray(a.assemble())
    struct.pack_into(">I", code, 12, b_to(address + 12, RET_STOP_DONE))
    struct.pack_into(">I", code, len(code) - 4, b_to(address + len(code) - 4, RET_STOP_DONE))
    return bytes(code)


def build_show(address):
    """r3 = record index in bank 49: show that line and wait for it."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x10))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x14))
    a.word(i_addis(4, 3, MSG_BASE >> 16))
    a.word(i_li(3, 2))
    a.word(i_li(5, SPEAKER))
    a.call(FN_MESSAGE)
    a.call(FN_WAIT_MESSAGE)
    a.word(i_mem(LWZ, 0, 1, 0x14))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x10))
    a.word(BLR)
    return a.assemble()


def build_stars(address):
    """r3 = player, r4 = delta: change the Stars with the game's popup, wait for it."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x20))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x24))
    a.word(i_mem(STW, 30, 1, 0x18))
    a.word(i_mem(STW, 29, 1, 0x14))
    a.word(i_mr(29, 3))
    a.word(i_mr(30, 4))
    a.call(FN_ADD_STARS)
    a.word(i_mr(3, 29))
    a.word(i_mr(4, 30))
    a.call(FN_STAR_POPUP)
    a.word(i_mr(30, 3))
    a.label("wait")
    a.word(i_mr(3, 30))
    a.call(FN_POPUP_DONE)
    a.word(i_cmpwi(3, 0))
    a.branch("bne", "end")
    a.call(FN_YIELD)
    a.branch("b", "wait")
    a.label("end")
    a.word(i_mem(LWZ, 0, 1, 0x24))
    a.word(i_mem(LWZ, 30, 1, 0x18))
    a.word(i_mem(LWZ, 29, 1, 0x14))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x20))
    a.word(BLR)
    return a.assemble()


def build_orbs(address):
    """r3 = player: fill every empty orb slot with Super 'Shroom (1), Sluggish (2) or Flutter (6). Returns the count."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x20))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x24))
    a.word(i_mem(STW, 31, 1, 0x1C))
    a.word(i_mem(STW, 30, 1, 0x18))
    a.word(i_mem(STW, 29, 1, 0x14))
    a.word(i_mr(31, 3))
    a.call(FN_ORB_MAX)
    a.word(i_mr(30, 3))
    a.word(i_mr(3, 31))
    a.call(FN_ORB_COUNT)
    a.word(i_subf(30, 3, 30))  # free slots
    a.word(i_li(29, 0))
    a.label("loop")
    a.word(i_cmpwi(30, 0))
    a.branch("ble", "done")
    a.word(i_li(3, 3))
    a.call(FN_RANDOM)
    a.word(i_cmpwi(3, 2))
    a.branch("bne", "pick")
    a.word(i_li(3, 5))
    a.label("pick")
    a.word(i_addi(4, 3, 1))  # 0 -> 1, 1 -> 2, 5 -> 6
    a.word(i_mr(3, 31))
    a.call(FN_ORB_ADD)
    a.word(i_addi(29, 29, 1))
    a.word(i_addi(30, 30, -1))
    a.branch("b", "loop")
    a.label("done")
    a.word(i_mr(3, 29))
    a.word(i_mem(LWZ, 0, 1, 0x24))
    a.word(i_mem(LWZ, 31, 1, 0x1C))
    a.word(i_mem(LWZ, 30, 1, 0x18))
    a.word(i_mem(LWZ, 29, 1, 0x14))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x20))
    a.word(BLR)
    return a.assemble()


def build_spin(address):
    """r3 = player, r4 = outcome value: run the 4-slice wheel to that slice; returns the value it landed on."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x20))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x24))
    a.word(i_mem(STW, 31, 1, 0x1C))
    a.word(i_mr(31, 4))
    a.word(i_li(4, 4))
    a.word(i_li(5, 0))
    a.call(FN_ROULETTE_CREATE)
    a.word(i_cmpwi(3, 0))
    a.branch("beq", "end")  # not created: report the rolled value
    a.word(i_li(0, 1))
    a.word(i_mem(STB, 0, 13, SDA["kane"]))  # icons by choice value
    a.word(i_mr(3, 31))
    a.call(FN_ROULETTE_COM)  # force the stop on that value
    a.call(FN_ROULETTE_WAIT)
    a.call(FN_ROULETTE_RESULT)
    a.word(i_mr(31, 3))
    a.word(i_li(0, 0))
    a.word(i_mem(STB, 0, 13, SDA["kane"]))
    a.word(i_mem(STH, 0, 13, SDA["force"]))
    a.label("end")
    a.word(i_mr(3, 31))
    a.word(i_mem(LWZ, 0, 1, 0x24))
    a.word(i_mem(LWZ, 31, 1, 0x1C))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x20))
    a.word(BLR)
    return a.assemble()


def build_wheel(address, spin, show, stars, orbs):
    """The wheel itself. r3 = player, r4 = space, r5 = address of fn_1_C5DC (the send-back outcome)."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x30))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x34))
    a.word(i_mem(STW, 31, 1, 0x2C))
    a.word(i_mem(STW, 30, 1, 0x28))
    a.word(i_mem(STW, 29, 1, 0x24))
    a.word(i_mem(STW, 28, 1, 0x20))
    a.word(i_mr(28, 5))  # fn_1_C5DC
    a.word(i_mr(31, 3))
    a.word(i_mr(30, 4))

    a.word(i_li(3, 100))
    a.call(FN_RANDOM)
    a.word(i_li(29, 0))  # Jackpot 0-19
    a.word(i_cmpwi(3, 20))
    a.branch("blt", "rolled")
    a.word(i_li(29, 1))  # Item Windfall 20-49
    a.word(i_cmpwi(3, 50))
    a.branch("blt", "rolled")
    a.word(i_li(29, 2))  # Fine 50-79
    a.word(i_cmpwi(3, 80))
    a.branch("blt", "rolled")
    a.word(i_li(29, 3))  # Send-back 80-99
    a.label("rolled")

    a.word(i_mr(3, 31))
    a.word(i_mr(4, 29))
    a.call(spin)
    a.word(i_mr(29, 3))  # what the arrow really landed on

    a.word(i_cmpwi(29, 0))
    a.branch("bne", "not_jackpot")
    a.word(i_li(3, MSG_JACKPOT))
    a.call(show)
    a.word(i_mr(3, 31))
    a.word(i_li(4, 2))
    a.call(stars)
    a.branch("b", "end")

    a.label("not_jackpot")
    a.word(i_cmpwi(29, 1))
    a.branch("bne", "not_items")
    a.word(i_mr(3, 31))
    a.call(FN_ORB_COUNT)
    a.word(i_mr(30, 3))
    a.call(FN_ORB_MAX)
    a.word(i_x(0, 0, 30, 3))  # cmpw r30, r3: already full when count >= max
    a.branch("blt", "has_room")
    a.word(i_li(3, MSG_FULL))
    a.call(show)
    a.branch("b", "end")
    a.label("has_room")
    a.word(i_li(3, MSG_ITEMS))
    a.call(show)
    a.word(i_mr(3, 31))
    a.call(orbs)
    a.branch("b", "end")

    a.label("not_items")
    a.word(i_cmpwi(29, 2))
    a.branch("bne", "send_back")
    a.word(i_mr(3, 31))
    a.call(FN_STARS)
    a.word(i_cmpwi(3, 0))
    a.branch("bgt", "pay")
    a.word(i_li(3, MSG_NO_STARS))
    a.call(show)
    a.branch("b", "end")
    a.label("pay")
    a.word(i_li(3, MSG_FINE))
    a.call(show)
    a.word(i_mr(3, 31))
    a.word(i_li(4, -1))
    a.call(stars)
    a.branch("b", "end")

    a.label("send_back")
    a.word(i_li(3, MSG_BACK))
    a.call(show)
    a.word(i_mr(3, 31))
    a.word(i_mr(4, 30))
    a.word(i_mr(12, 28))
    a.word(MTCTR_R12)
    a.word(BCTRL)

    a.label("end")
    a.word(i_mem(LWZ, 0, 1, 0x34))
    a.word(i_mem(LWZ, 31, 1, 0x2C))
    a.word(i_mem(LWZ, 30, 1, 0x28))
    a.word(i_mem(LWZ, 29, 1, 0x24))
    a.word(i_mem(LWZ, 28, 1, 0x20))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x30))
    a.word(BLR)
    return a.assemble()


def build_landing(address, show, wheel):
    """End of fn_1_1CD4 (r29 = player, r30 = space flags, r31 = space). Landing on space 30 only: ask, then spin."""
    a = Asm(address)
    a.word(i_rlwinm(0, 30, 0, 26, 26) | 1)  # rlwinm. r0, r30, 0, 26, 26  (flag 0x20)
    a.branch("beq", "return")
    # fn_1_1CD4 runs on every step of a move; the game decrements the remaining-steps byte (GwPlayer
    # +0xA) only after it returns, so the last step (the landing) is the one where it is still 1
    a.word(i_mulli(4, 29, PLAYER_SIZE))
    a.word(i_lis(5, ha(GW_PLAYER)))
    a.word(i_addi(5, 5, lo(GW_PLAYER)))
    a.word(i_add(5, 5, 4))
    a.word(i_mem(LBZ, 0, 5, 0xA))
    a.word(i_cmpwi(0, 1))
    a.branch("bne", "return")
    a.word(i_mem(STWU, 1, 1, -0x20))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x24))
    a.word(i_mr(5, 0))
    a.word(i_addis(5, 5, 1))
    a.word(i_addi(5, 5, SEND_BACK_FROM_LR - 0x10000))  # fn_1_C5DC
    a.word(i_mem(STW, 5, 1, 0x10))
    # stop the walking animation (Star Shuffle: fn_801565EC(p,0); fn_8015BFB4(p,1,0.0,8.0,0x40000001))
    floats = address + 0xE0
    a.word(i_mr(3, 29))
    a.word(i_li(4, 0))
    a.call(FN_PLAYER_HOLD)
    a.word(i_mr(3, 29))
    a.word(i_li(4, 1))
    a.word(i_lis(5, ha(floats)))
    a.word(i_mem(LFS, 1, 5, lo(floats)))
    a.word(i_mem(LFS, 2, 5, lo(floats) + 4))
    a.word(i_lis(5, 0x4000))
    a.word(i_addi(5, 5, 1))
    a.call(FN_PLAYER_MOTION)
    # CPU players (bit 0x20 of GwPlayer byte 0) always spin; humans are asked
    a.word(i_mulli(4, 29, PLAYER_SIZE))
    a.word(i_lis(5, ha(GW_PLAYER)))
    a.word(i_addi(5, 5, lo(GW_PLAYER)))
    a.word(i_add(5, 5, 4))
    a.word(i_mem(LBZ, 0, 5, 0))
    a.word(i_rlwinm(0, 0, 0, 26, 26) | 1)  # rlwinm. r0, r0, 0, 26, 26
    a.branch("bne", "cpu")
    a.word(i_li(3, 2))
    a.word(i_addis(4, 0, MSG_BASE >> 16))
    a.word(i_addi(4, 4, MSG_ASK))
    a.word(i_li(5, SPEAKER))
    a.word(i_li(6, 0))
    a.call(FN_PROMPT)
    a.call(FN_WAIT_MESSAGE)
    a.call(FN_CHOICE)
    a.word(i_cmpwi(3, 0))
    a.branch("bne", "done")  # No (1) or cancelled (-1)
    a.branch("b", "spin")
    a.label("cpu")
    a.word(i_li(3, MSG_INTRO))
    a.call(show)
    a.label("spin")
    a.word(i_mr(3, 29))
    a.word(i_mr(4, 31))
    a.word(i_mem(LWZ, 5, 1, 0x10))
    a.call(wheel)
    a.label("done")
    a.word(i_mem(LWZ, 0, 1, 0x24))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x20))
    a.label("return")
    a.word(i_li(3, 0))  # the displaced instruction
    a.word(BLR)
    code = a.assemble()
    if len(code) > 0xE0:
        raise RuntimeError("landing cave overlaps its float table")
    return code + b"\0" * (0xE0 - len(code)) + struct.pack(">ff", 0.0, 8.0)


def build_all():
    caves = {name: addr for name, (addr, _) in CAVES.items()}
    code = {
        "init_count": build_init_count(caves["init_count"]),
        "init_icons": build_init_icons(caves["init_icons"]),
        "spin_width": build_const_branch(caves["spin_width"], 19, 90, RET_SPIN_WIDTH),
        "cpu_width": build_const_branch(caves["cpu_width"], 31, 90, RET_CPU_WIDTH),
        "slot": build_slot(caves["slot"]),
        "cpu_test": build_cpu_test(caves["cpu_test"]),
        "stop": build_stop(caves["stop"]),
        "show": build_show(caves["show"]),
        "stars": build_stars(caves["stars"]),
        "orbs": build_orbs(caves["orbs"]),
        "spin": build_spin(caves["spin"]),
        "wheel": build_wheel(caves["wheel"], caves["spin"], caves["show"], caves["stars"], caves["orbs"]),
        "landing": build_landing(caves["landing"], caves["show"], caves["wheel"]),
        "noop": struct.pack(">I", BLR),
    }
    for name, (addr, size) in CAVES.items():
        if len(code[name]) > size:
            raise RuntimeError(f"{name}: {len(code[name]):#x} bytes, too big for {size:#x}")
    return caves, code


# ---- DOL --------------------------------------------------------------------------------------

def patch_dol():
    dol = bytearray(DOL.read_bytes())
    section = struct.unpack_from(">I", dol, 0x48 + 4 * SECTION_SLOT)[0]
    if section != NEW_BASE:
        raise SystemExit("Run apply_mgtable_move_patch.py first: the old MgDataTbl is only free code space once it is relocated")
    caves, code = build_all()
    for name, (addr, size) in CAVES.items():
        position = dol_offset(dol, addr)
        dol[position:position + size] = code[name] + b"\0" * (size - len(code[name]))

    def branch_word(site, target):
        return struct.pack(">I", b_to(site, target))

    def hook(site, target, original, description):
        replace_bytes(dol, dol_offset(dol, site), struct.pack(">I", original), branch_word(site, target), description)

    hook(HOOK_INIT_COUNT, caves["init_count"], WORD_BGE[HOOK_INIT_COUNT], "Init slice count")
    hook(HOOK_INIT_ICONS, caves["init_icons"], WORD_BGE[HOOK_INIT_ICONS], "Init icon positions")
    hook(HOOK_SPIN_WIDTH, caves["spin_width"], WORD_BGE[HOOK_SPIN_WIDTH], "spin slice width")
    hook(HOOK_CPU_WIDTH, caves["cpu_width"], WORD_BGE[HOOK_CPU_WIDTH], "CPU stop slice width")
    hook(HOOK_SLOT, caves["slot"], WORD_BGE[HOOK_SLOT], "slot divisor")
    hook(HOOK_STOP, caves["stop"], WORD_STOP, "stop decision")
    replace_bytes(dol, dol_offset(dol, HOOK_COUNT), struct.pack(">I", WORD_COUNT), struct.pack(">I", WORD_NOP), "slice count")
    replace_bytes(
        dol, dol_offset(dol, HOOK_CPU_TEST), struct.pack(">I", WORD_CPU_TEST),
        struct.pack(">I", encode_branch(HOOK_CPU_TEST, caves["cpu_test"], link=True)), "CPU test",
    )
    replace_bytes(
        dol, dol_offset(dol, ICON_TABLE), struct.pack(">4I", *ICON_ORIGINAL), struct.pack(">4I", *ICONS),
        "kane icon table",
    )
    DOL.write_bytes(dol)
    used = {name: len(c) for name, c in code.items()}
    print("Wheel of Fortune DOL code written at", {n: hex(a) for n, a in caves.items()})
    print("sizes", {n: hex(s) for n, s in used.items()})
    return caves


# ---- REL --------------------------------------------------------------------------------------

def patch_rel(caves):
    path = REL_DIR / REL_NAME
    data = bytearray((path if path.exists() else REL_ORIG / REL_NAME).read_bytes())
    check_words(data, SITE_PASS, WORD_PASS, "48000001")
    check_words(data, SITE_LAND, WORD_LAND, "48000001")
    if add_calls(data, [(SITE_PASS, caves["noop"]), (SITE_LAND, caves["landing"])]):
        REL_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f"Hooked space 30 landing and passing ({REL_NAME})")
    else:
        print("Space 30 already hooked")


# ---- icon sprite -------------------------------------------------------------------------------

ICON_PNG = ASSETS / "wheel_super_shroom_84.png"


def build_icon_payload(template):
    """An 84x84 CMPR sprite (a copy of an existing icon with the bitmap replaced)."""
    from PIL import Image
    info = mpdata.parse_anm(template)["bmps"][0]
    if (info["w"], info["h"], info["fmt"], info["size"]) != (84, 84, 10, 3872):
        raise RuntimeError(f"Unexpected template sprite: {info}")
    icon = Image.open(ICON_PNG).convert("RGBA")
    canvas = Image.new("RGBA", (88, 88), (0, 0, 0, 0))
    canvas.paste(icon, (0, 0))
    bitmap = mpdata.encode_cmpr(canvas)
    if len(bitmap) != info["size"]:
        raise RuntimeError("Encoded icon has the wrong size")
    return template[:info["data_o"]] + bitmap


def patch_archives():
    for name in bt.BOARD_FILES:
        out = DATA_OUT / f"{name}.bin"
        source = out if out.exists() else DATA_ORIG / f"{name}.bin"
        data, offsets = mpdata.read_archive(source)
        while len(offsets) > NEW_ICON_FILE:  # already has the icon (and later files, e.g. the Castaway Bay icons): drop them
            data, offsets = drop_last_file(data, offsets)
        if len(offsets) != NEW_ICON_FILE:
            raise RuntimeError(f"{source}: {len(offsets)} files, expected {NEW_ICON_FILE} (run apply_battle_thumbs_patch.py first)")
        template = mpdata.read_file(data, offsets, 0x79)
        patched, _ = mpdata.append_files(data, offsets, [build_icon_payload(template)])
        DATA_OUT.mkdir(parents=True, exist_ok=True)
        out.write_bytes(patched)
    print(f"Added the Super 'Shroom icon as file {NEW_ICON_FILE} of {len(bt.BOARD_FILES)} board archives in {DATA_OUT}")


def drop_last_file(data, offsets):
    count = len(offsets) - 1
    body = data[4 + 4 * len(offsets):offsets[-1]]
    shift = 4
    new_offsets = [o - shift for o in offsets[:-1]]
    header = struct.pack(">I", count) + struct.pack(f">{count}I", *new_offsets)
    return header + body, new_offsets


def main():
    caves = patch_dol()
    patch_rel(caves)
    patch_archives()
    print("Now re-run apply_star_shuffle_bet_patch.py once (it owns message bank 49) if the text records are not in the build yet.")


if __name__ == "__main__":
    main()
