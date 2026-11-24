"""Castaway Bay: the spare change guy, a pass-through event on the top cliff (no space you can stop on).

A new space 100 sits between spaces 55 and 54 (the bottom row of the top cliff island, where
boards/castaway bay/spare-change-guy-location.png points). It is kind 0, like the raft (46) and Boo (67) nodes:
the move loop (fn_801548D8) only counts a step when fn_801771E4(kind) says so, and kind 0 never counts, is never
drawn and can never be where a move ends. So walking 55 -> 100 -> 54 costs one step, as 55 -> 54 did.

Passing it (any player): "Spare change?" Yes / No. No (or B): "So greedy." Yes: pay 5 coins (a player with
fewer gets "You're broke too?"), then one of five outcomes, equal odds:
  0 an orb from ORB_POOL (Boo-away, Mushroom, Super 'Shroom), or a "pockets full" line;
  1 20 coins back;
  2 "Got a bit more?" Yes / No again: Yes pays and rolls again, No is "So greedy.";
  3 nothing, "Thanks, sucker!";
  4 every other player pays the passer up to 5 coins.
CPUs answer Yes whenever they hold at least 5 coins (the window still shows; mbComChoiceUpSet/DownSet).

The guy is a flat card that always faces the camera (hsf_build.build_card, object flag HSF_MATERIAL_BBOARD),
textured with assets/spare_change_guy.png (RGBA, transparent background; the user's art) or, until that exists,
a generated placeholder (assets/spare_change_guy_placeholder.png). It is file 48 of w05.bin / w05n.bin, after the
broom's 46/47, created at board init.

What was built:
  * DOL data section 16 (CODE_BASE.., CODE_SIZE bytes, zero-filled) for the code: the dead old MgDataTbl is
    full. OSSetArenaLo's clamp (apply_mgtable_move_patch.py, ARENA_CAVE) is raised to the section's end.
  * w05Dll .text 0x2300 (the wheel's hook at the exit of the pass handler fn_1_2238) now calls CAVE_PASS, which
    calls the wheel's pass cave first and then tests flag 0x10000 on the space (r31). The wheel script leaves
    this chain alone on a re-run.
  * w05Dll .text 0x1C2C (`bl fn_801EF39C`, r3 = 0x1840, in the board init fn_1_F4) now calls CAVE_INIT, which
    makes that call and then creates the card (data dir 0xEB by day, 0xEC by night).
  * root/data/w05.bin and w05n.bin: space 100 appended (type 0, kind 0, flag 0x10000, links to 54), space 55
    links to 100 instead of 54, card model as file 48. Backups: backups/w05*.bin.bak_before_spare_change.
  * Text: bank 0x33 records 60-68 (after the wheel's 51-58 and the broom menu's 59), English in every language
    file, no speaker face (-1).

Run after castaway_wheel, boo_day_orbs and castaway_broom. Idempotent. Nothing here has been run in Dolphin.
"""
import shutil
import struct

from tools.patches import apply_boo_day_orbs_patch as boo
from tools.patches import apply_castaway_broom_patch as broom
from tools.patches import apply_castaway_wheel_patch as cw
from tools.patches import apply_mgtable_move_patch as mg
from tools.patches import apply_wheel_of_fortune_patch as wheel
from tools.lib import hsf_build
from tools.lib import mpdata
from tools.lib.paths import DOL
from tools.lib.dol import dol_offset
from tools.lib.game import FN_ADD_COINS, FN_COINS
from tools.lib.paths import MESS_NAMES, MESS_OUTPUT_DIR, MESS_SOURCE_DIR, REL_DIR, REL_ORIG
from tools.patches.apply_star_shuffle_bet_patch import edit_bank
from tools.lib.messages import encode, record
from tools.lib.ppc import i_li, i_rlwinm
from tools.lib.ppc import (
    Asm, LBZ, i_add, i_addi, i_cmpw, i_cmpwi, i_lis, i_mem, i_mr, i_mulli, i_ori, i_slwi, ha, lo,
)
from tools.lib.boards import load_spaces, replace_file0
from tools.lib.game import (
    FN_CHOICE, FN_MESSAGE, FN_ORB_ADD, FN_ORB_COUNT, FN_ORB_MAX, FN_PLAYER_HOLD, FN_PLAYER_MOTION,
    FN_PROMPT, FN_RANDOM, FN_WAIT_MESSAGE, GW_PLAYER, PLAYER_SIZE,
)
from tools.lib.minigames import NEW_BASE, NEW_END, OLD_BASE, SECTION_SLOT
from tools.lib.paths import BACKUPS, GAME_DATA
from tools.lib.ppc import LFS, epilogue, i_addis, i_extsh, i_lbzx, i_subf, prologue
from tools.lib.rel import check_words

REL_NAME = "w05Dll.rel"
BOARDS = ("w05", "w05n")
from tools.lib.paths import TOOLS
ART = TOOLS / "assets" / "spare_change_guy.png"
PLACEHOLDER = TOOLS / "assets" / "spare_change_guy_placeholder.png"

# the new space
SPACE = 100                   # appended: every existing id stays the same
FROM_SPACE, TO_SPACE = 55, 54  # 55 -> 100 -> 54 (was 55 -> 54)
SPACE_POS = (-1.5, 373.5, -164.0)  # halfway between 55 (-184, 406, -154) and 54 (181, 341, -174)
SPACE_FLAG = 0x10000          # unused by the board data, w05Dll and the path mask (fn_801EF39C(0x1840))
VANILLA_SPACES = 99

# the card
CARD_FILE = 48                # after the broom's 46/47
BOARD_FILES = broom.BOARD_FILES + 2
CARD_W, CARD_H = 128, 256     # texture, power-of-two sides
GUY_WIDTH, GUY_HEIGHT = 130.0, 260.0  # board units (65 x 130, then 100 x 200, looked small in Dolphin)
GUY_POS = (-60.0, 385.0, -225.0)     # on the ledge just behind the path (z -320 was behind the rock rim); tune in Dolphin
DIR_DAY, DIR_NIGHT = broom.DIR_DAY, broom.DIR_NIGHT

# outcomes
COST = 5
PAYBACK = 20
STEAL = 5                     # at most this many coins from each other player
ORB_POOL = (31, 0, 1)         # Boo-away, Mushroom, Super 'Shroom (plans/orbs/README.md)
OUTCOMES = 5
PLAYERS = 4

# code: DOL data section 16, right after section 15 (the relocated MgDataTbl and the battle ports)
SECTION = 16
CODE_BASE = NEW_END        # 0x802F7DA0
CODE_SIZE = 0x1000
CODE_END = CODE_BASE + CODE_SIZE
CAVE_SHOW = CODE_BASE + 0x000   # r3 = record: show and wait (0x40)
CAVE_ASK = CODE_BASE + 0x040    # r3 = player, r4 = record: Yes/No, CPU answers -> 0 Yes (0xA0)
CAVE_PASS = CODE_BASE + 0x0E0   # the .text 0x2300 hook (0x60)
CAVE_INIT = CODE_BASE + 0x140   # the .text 0x1C2C hook (0x80)
CAVE_EVENT = CODE_BASE + 0x1C0  # r3 = player: the whole event (0x300)
CAVE_DATA = CODE_BASE + 0x4C0   # card position, hold floats, orb pool (0x20)
USED_END = CAVE_DATA + 0x20
D_POS, D_ZERO, D_EIGHT, D_POOL = 0x00, 0x0C, 0x10, 0x14

SITE_PASS = cw.SITE_HOOK      # 0x2300
SITE_INIT = 0x1C2C            # bl fn_801EF39C in fn_1_F4
FN_PATH_MASK = 0x801EF39C     # path chooser: skip spaces with these flags (or-ed in)
FN_FLAGS = 0x80176FCC
FN_OBJ_CREATE = broom.FN_OBJ_CREATE
FN_OBJ_LAYER = cw.FN_MODEL_LAYER
FN_OBJ_POS = broom.FN_OBJ_POS
FN_COM_YES, FN_COM_NO = 0x80170720, 0x80170780  # mbComChoiceUpSet / DownSet
GW_SYSTEM = broom.GW_SYSTEM

# text: bank 0x33 after the broom's menu
BANK = cw.BANK
BANK_RECORDS = broom.BANK_RECORDS + len(broom.RECORDS)  # 60
MSG_BASE = cw.MSG_BASE
SPEAKER = -1                  # no face


def say(text):
    """A plain line; lines after a newline are indented like the first, as in the vanilla records."""
    lines = text.replace(".", "\x85").replace("'", "\\").split("\n")
    return record("00150003", b"\n".join(boo.INDENT + encode(line) for line in lines), bytes([0xFF, 0x00]))


def say_unindented(text):
    """The earlier versions: lines after a newline were not indented."""
    return boo.line(text.replace(".", "\x85"))


def ask(question):
    return boo.menu(question.replace(".", "\x85"), [f"Here, have {COST} coins", "No"])


def texts(line):
    return [  # the outcome lines are the user's wording, spelled exactly as given
        ask("Spare change?"),
        line("So greedy."),
        line("Found this in me back pockih"),
        line("Your pockets are full?\nNever mind, then."),
        line("Guess what I got for you bud"),
        ask("Got a bit more for me mate?"),
        line("Cheers for that good lad"),
        line("Lets tax the good lads HAHA"),
        line("You're broke too? Never mind."),
    ]


TEXT = texts(say)
MSG_ASK, MSG_GREEDY, MSG_ORB, MSG_FULL, MSG_BACK, MSG_MORE, MSG_SUCKER, MSG_STEAL, MSG_BROKE = range(
    BANK_RECORDS, BANK_RECORDS + len(TEXT))
RECORDS = TEXT
OLD_TAILS = (
    [  # the first wording (placeholder lines)
        ask("Spare change?"), say_unindented("So greedy."), say_unindented("Bless you! Here, take this orb!"),
        say_unindented("Your pockets are full?\nNever mind, then."), say_unindented(f"Lucky day! Have {PAYBACK} coins back!"),
        ask("Got a bit more? Spare change?"), say_unindented("Thanks, sucker!"),
        say_unindented("Everybody chip in for\nmy friend here!"), say_unindented("You're broke too? Never mind."),
    ],
    texts(say_unindented),  # the user's wording, before the indent fix
)


# ---- code -------------------------------------------------------------------

def gw_player(a, reg, player):
    """reg = &GwPlayer[player]."""
    a.word(i_mulli(4, player, PLAYER_SIZE))
    a.word(i_lis(reg, ha(GW_PLAYER)))
    a.word(i_addi(reg, reg, lo(GW_PLAYER)))
    a.word(i_add(reg, reg, 4))


def fits(code, size, name):
    if len(code) > size:
        raise RuntimeError(f"{name} is {len(code):#x} bytes, more than {size:#x}")
    return code


def build_show(address, msg_base=MSG_BASE, speaker=SPEAKER, limit=CAVE_ASK - CAVE_SHOW):
    """r3 = record index in bank msg_base >> 16 (0x33 here): show it with no face and wait."""
    a = Asm(address)
    prologue(a, 0x10, ())
    a.word(i_addis(4, 3, msg_base >> 16))
    a.word(i_li(3, 2))
    a.word(i_li(5, speaker))
    a.call(FN_MESSAGE)
    a.call(FN_WAIT_MESSAGE)
    epilogue(a, 0x10, ())
    return fits(a.assemble(), limit, "show")


def build_ask(address, msg_base=MSG_BASE, speaker=SPEAKER, limit=CAVE_PASS - CAVE_ASK):
    """r3 = player, r4 = record: a Yes/No window; a CPU says Yes when it holds at least COST coins.
    Returns 0 for Yes, 1 No, -1 cancelled."""
    a = Asm(address)
    saved = (30, 31)
    prologue(a, 0x20, saved)
    a.word(i_mr(31, 3))
    a.word(i_mr(30, 4))
    a.word(i_li(3, 2))
    a.word(i_addis(4, 30, msg_base >> 16))
    a.word(i_li(5, speaker))
    a.word(i_li(6, 0))
    a.call(FN_PROMPT)
    gw_player(a, 5, 31)
    a.word(i_mem(LBZ, 0, 5, 0))
    a.word(i_rlwinm(0, 0, 0, 26, 26) | 1)  # CPU (GwPlayer byte 0, bit 0x20)
    a.branch("beq", "wait")
    a.word(i_mr(3, 31))
    a.call(FN_COINS)
    a.word(i_cmpwi(3, COST))
    a.branch("blt", "cpu_no")
    a.call(FN_COM_YES)
    a.branch("b", "wait")
    a.label("cpu_no")
    a.call(FN_COM_NO)
    a.label("wait")
    a.call(FN_WAIT_MESSAGE)
    a.call(FN_CHOICE)
    epilogue(a, 0x20, saved)
    return fits(a.assemble(), limit, "ask")


def build_pass(address, wheel_pass, event):
    """Replaces the wheel's call at the exit of fn_1_2238 (r30 = player, r31 = space just entered): the wheel's
    cave first (it keeps r30/r31 and returns 0), then the spare change guy on flag SPACE_FLAG."""
    a = Asm(address)
    prologue(a, 0x10, ())
    a.call(wheel_pass)
    a.word(i_mr(3, 31))
    a.call(FN_FLAGS)
    a.word(i_rlwinm(0, 3, 0, 15, 15) | 1)  # rlwinm. r0, r3, 0, 15, 15  (flag 0x10000)
    a.branch("beq", "return")
    a.word(i_mr(3, 30))
    a.call(event)
    a.label("return")
    a.word(i_li(3, 0))  # the displaced instruction: fn_1_2238 returns 0 (the step still counts as usual)
    epilogue(a, 0x10, ())
    return fits(a.assemble(), CAVE_INIT - CAVE_PASS, "pass")


def build_init(address):
    """Replaces `bl fn_801EF39C` in fn_1_F4 (r3 = 0x1840 is still in place): make that call, then create the card."""
    a = Asm(address)
    saved = (31,)
    prologue(a, 0x20, saved)
    a.call(FN_PATH_MASK)
    a.word(i_lis(3, ha(GW_SYSTEM)))
    a.word(i_addi(3, 3, lo(GW_SYSTEM)))
    a.word(i_mem(LBZ, 0, 3, 0x10))
    a.word(i_rlwinm(0, 0, 0, 25, 25) | 1)  # night bit 0x40
    a.word(i_li(3, DIR_DAY))
    a.branch("beq", "day")
    a.word(i_li(3, DIR_NIGHT))
    a.label("day")
    a.word(i_slwi(3, 3, 16))
    a.word(i_ori(3, 3, CARD_FILE))
    a.word(i_li(4, 0))
    a.word(i_li(5, 0))
    a.call(FN_OBJ_CREATE)
    a.word(i_extsh(31, 3))
    a.word(i_mr(3, 31))
    a.word(i_li(4, 3))
    a.call(FN_OBJ_LAYER)
    a.word(i_mr(3, 31))
    a.word(i_lis(4, ha(CAVE_DATA)))
    a.word(i_addi(4, 4, lo(CAVE_DATA + D_POS)))
    a.call(FN_OBJ_POS)
    epilogue(a, 0x20, saved)
    return fits(a.assemble(), CAVE_EVENT - CAVE_INIT, "init")


EVENT_MSGS = (MSG_ASK, MSG_GREEDY, MSG_ORB, MSG_FULL, MSG_BACK, MSG_MORE, MSG_SUCKER, MSG_STEAL, MSG_BROKE)


def build_event(address, show, ask_cave, data=CAVE_DATA, msgs=EVENT_MSGS, limit=CAVE_DATA - CAVE_EVENT, pool=ORB_POOL):
    """r3 = player: hold them, ask, pay, roll, apply; release them. data: the block build_data() makes (hold
    floats at +D_ZERO/+D_EIGHT, orb pool at +D_POOL); msgs: the 9 record ids in EVENT_MSGS order."""
    MSG_ASK, MSG_GREEDY, MSG_ORB, MSG_FULL, MSG_BACK, MSG_MORE, MSG_SUCKER, MSG_STEAL, MSG_BROKE = msgs
    CAVE_DATA = data
    a = Asm(address)
    saved = (27, 28, 29, 30, 31)
    frame = 0x30
    prologue(a, frame, saved)
    a.word(i_mr(31, 3))
    # hold the player and stop the walk animation, as the wheel does
    a.word(i_mr(3, 31))
    a.word(i_li(4, 0))
    a.call(FN_PLAYER_HOLD)
    a.word(i_mr(3, 31))
    a.word(i_li(4, 1))
    a.word(i_lis(5, ha(CAVE_DATA)))
    a.word(i_mem(LFS, 1, 5, lo(CAVE_DATA + D_ZERO)))
    a.word(i_mem(LFS, 2, 5, lo(CAVE_DATA + D_EIGHT)))
    a.word(i_lis(5, 0x4000))
    a.word(i_addi(5, 5, 1))
    a.call(FN_PLAYER_MOTION)
    a.word(i_mr(3, 31))
    a.word(i_li(4, MSG_ASK))
    a.call(ask_cave)
    a.word(i_cmpwi(3, 0))
    a.branch("bne", "greedy")
    # Yes: pay, then roll
    a.label("pay")
    a.word(i_mr(3, 31))
    a.call(FN_COINS)
    a.word(i_cmpwi(3, COST))
    a.branch("bge", "paid")
    a.word(i_li(3, MSG_BROKE))
    a.call(show)
    a.branch("b", "done")
    a.label("paid")
    a.word(i_mr(3, 31))
    a.word(i_li(4, -COST))
    a.word(i_li(5, 1))
    a.word(i_li(6, 1))
    a.call(FN_ADD_COINS)
    a.word(i_li(3, OUTCOMES))
    a.call(FN_RANDOM)
    a.word(i_mr(30, 3))
    # 0: an orb, if there is room
    a.word(i_cmpwi(30, 0))
    a.branch("bne", "payback")
    a.word(i_mr(3, 31))
    a.call(FN_ORB_MAX)
    a.word(i_mr(29, 3))
    a.word(i_mr(3, 31))
    a.call(FN_ORB_COUNT)
    a.word(i_cmpw(3, 29))
    a.branch("blt", "room")
    a.word(i_li(3, MSG_FULL))
    a.call(show)
    a.branch("b", "done")
    a.label("room")
    a.word(i_li(3, MSG_ORB))
    a.call(show)
    a.word(i_li(3, len(pool)))
    a.call(FN_RANDOM)
    a.word(i_lis(4, ha(CAVE_DATA + D_POOL)))
    a.word(i_addi(4, 4, lo(CAVE_DATA + D_POOL)))
    a.word(i_lbzx(4, 4, 3))
    a.word(i_mr(3, 31))
    a.call(FN_ORB_ADD)
    a.branch("b", "done")
    # 1: coins back
    a.label("payback")
    a.word(i_cmpwi(30, 1))
    a.branch("bne", "more")
    a.word(i_li(3, MSG_BACK))
    a.call(show)
    a.word(i_mr(3, 31))
    a.word(i_li(4, PAYBACK))
    a.word(i_li(5, 1))
    a.word(i_li(6, 1))
    a.call(FN_ADD_COINS)
    a.branch("b", "done")
    # 2: asks again
    a.label("more")
    a.word(i_cmpwi(30, 2))
    a.branch("bne", "sucker")
    a.word(i_mr(3, 31))
    a.word(i_li(4, MSG_MORE))
    a.call(ask_cave)
    a.word(i_cmpwi(3, 0))
    a.branch("beq", "pay")
    a.branch("b", "greedy")
    # 3: nothing
    a.label("sucker")
    a.word(i_cmpwi(30, 3))
    a.branch("bne", "steal")
    a.word(i_li(3, MSG_SUCKER))
    a.call(show)
    a.branch("b", "done")
    # 4: everyone else pays the passer up to STEAL coins
    a.label("steal")
    a.word(i_li(3, MSG_STEAL))
    a.call(show)
    a.word(i_li(29, 0))  # total
    a.word(i_li(28, 0))  # player index
    a.label("each")
    a.word(i_cmpw(28, 31))
    a.branch("beq", "next")
    a.word(i_mr(3, 28))
    a.call(FN_COINS)
    a.word(i_mr(27, 3))
    a.word(i_cmpwi(27, STEAL))
    a.branch("ble", "capped")
    a.word(i_li(27, STEAL))
    a.label("capped")
    a.word(i_cmpwi(27, 0))
    a.branch("ble", "next")
    a.word(i_mr(3, 28))
    a.word(i_li(4, 0))
    a.word(i_subf(4, 27, 4))  # r4 = -r27
    a.word(i_li(5, 1))
    a.word(i_li(6, 1))
    a.call(FN_ADD_COINS)
    a.word(i_add(29, 29, 27))
    a.label("next")
    a.word(i_addi(28, 28, 1))
    a.word(i_cmpwi(28, PLAYERS))
    a.branch("blt", "each")
    a.word(i_cmpwi(29, 0))
    a.branch("ble", "done")
    a.word(i_mr(3, 31))
    a.word(i_mr(4, 29))
    a.word(i_li(5, 1))
    a.word(i_li(6, 1))
    a.call(FN_ADD_COINS)
    a.branch("b", "done")
    # No / cancelled
    a.label("greedy")
    a.word(i_li(3, MSG_GREEDY))
    a.call(show)
    a.label("done")
    a.word(i_mr(3, 31))
    a.word(i_li(4, 1))
    a.call(FN_PLAYER_HOLD)
    epilogue(a, frame, saved)
    return fits(a.assemble(), limit, "event")


def build_data(pos=GUY_POS, pool=ORB_POOL):
    data = struct.pack(">3fff", *pos, 0.0, 8.0) + bytes(pool)
    return fits(data.ljust(0x20, b"\0"), 0x20, "data")


def pieces():
    return {
        CAVE_SHOW: build_show(CAVE_SHOW),
        CAVE_ASK: build_ask(CAVE_ASK),
        CAVE_PASS: build_pass(CAVE_PASS, cw.CAVE_PASS, CAVE_EVENT),
        CAVE_INIT: build_init(CAVE_INIT),
        CAVE_EVENT: build_event(CAVE_EVENT, CAVE_SHOW, CAVE_ASK),
        CAVE_DATA: build_data(),
    }


# ---- DOL --------------------------------------------------------------------

def add_section(dol):
    """DOL data section SECTION at CODE_BASE (zero-filled); the arena clamp moves up to CODE_END."""
    if struct.unpack_from(">I", dol, 0x48 + 4 * SECTION_SLOT)[0] != NEW_BASE:
        raise SystemExit("Run apply_mgtable_move_patch.py first: section 16 goes right after its section")
    offset_pos, addr_pos, size_pos = 4 * SECTION, 0x48 + 4 * SECTION, 0x90 + 4 * SECTION
    current = tuple(struct.unpack_from(">I", dol, p)[0] for p in (offset_pos, addr_pos, size_pos))
    if current[1:] == (CODE_BASE, CODE_SIZE):
        pass
    elif any(current):
        raise RuntimeError(f"DOL section slot {SECTION} is already in use: {[hex(v) for v in current]}")
    else:
        while len(dol) % 0x20:
            dol.append(0)
        struct.pack_into(">I", dol, offset_pos, len(dol))
        struct.pack_into(">I", dol, addr_pos, CODE_BASE)
        struct.pack_into(">I", dol, size_pos, CODE_SIZE)
        dol.extend(b"\0" * CODE_SIZE)
        print(f"Added DOL section {SECTION}: {CODE_BASE:#010x}-{CODE_END:#010x}")
    # OSSetArenaLo clamp: lis r0, hi / ori r0, r0, lo at the start of mg.ARENA_CAVE
    at = dol_offset(dol, mg.ARENA_CAVE)
    hi, low = struct.unpack_from(">2I", dol, at)
    if hi >> 16 != 0x3C00 or low >> 16 != 0x6000:
        raise RuntimeError("OSSetArenaLo clamp not found: run apply_mgtable_move_patch.py first")
    clamp = ((hi & 0xFFFF) << 16) | (low & 0xFFFF)
    if clamp < CODE_END:
        struct.pack_into(">2I", dol, at, 0x3C000000 | (CODE_END >> 16), 0x60000000 | (CODE_END & 0xFFFF))
        print(f"OSSetArenaLo now clamps ArenaLo to >= {CODE_END:#010x}")


def patch_dol():
    dol = bytearray(DOL.read_bytes())
    add_section(dol)
    for address, code in pieces().items():
        position = dol_offset(dol, address)
        dol[position:position + len(code)] = code
    DOL.write_bytes(dol)
    print(f"Spare change code at {CODE_BASE:#x}-{USED_END:#x} (event {len(pieces()[CAVE_EVENT]):#x} bytes)")


# ---- REL --------------------------------------------------------------------

def patch_rel():
    path = REL_DIR / REL_NAME
    data = bytearray((path if path.exists() else REL_ORIG / REL_NAME).read_bytes())
    if not path.exists():
        raise SystemExit("Run apply_castaway_wheel_patch.py first: the pass hook chains onto its cave")
    check_words(data, SITE_PASS, "48000001")
    # the wheel's call, and stale copies of it that a re-run of apply_mgtable_move_patch.py moved into its table
    # (the wheel re-run then added another; the loader applies them in order, so the last one won)
    wheel_moved = NEW_BASE + (cw.CAVE_PASS - OLD_BASE)
    changed = broom.point_call(data, SITE_PASS, CAVE_PASS, (cw.CAVE_PASS, wheel_moved))
    from tools.patches import apply_castaway_troll_patch as troll
    changed += broom.point_call(data, SITE_INIT, CAVE_INIT, (FN_PATH_MASK,), earlier=(troll.CAVE_INIT,))
    if changed:
        path.write_bytes(data)
        print(f"Hooked the pass handler (wheel, then spare change) and the board init ({REL_NAME})")
    else:
        print("Pass handler and board init already hooked")


# ---- board data -------------------------------------------------------------

def placeholder():
    """An original stand-in figure (long brown coat, hat, bag) until the user's art is in ART."""
    from PIL import Image, ImageDraw
    s = 4
    img = Image.new("RGBA", (CARD_W * s, CARD_H * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def box(x0, y0, x1, y1):
        return (x0 * s, y0 * s, x1 * s, y1 * s)

    ink = (40, 30, 25, 255)
    d.rectangle(box(48, 222, 60, 246), fill=(30, 30, 35, 255))                              # legs
    d.rectangle(box(68, 222, 80, 246), fill=(30, 30, 35, 255))
    d.ellipse(box(40, 240, 62, 252), fill=ink)                                              # shoes
    d.ellipse(box(66, 240, 88, 252), fill=ink)
    d.polygon([(34 * s, 92 * s), (94 * s, 92 * s), (100 * s, 226 * s), (28 * s, 226 * s)],
              fill=(150, 110, 70, 255), outline=ink, width=2 * s)                           # coat
    d.line([(64 * s, 96 * s), (64 * s, 224 * s)], fill=ink, width=2 * s)
    for y in (140, 160, 180, 200):
        d.ellipse(box(68, y, 74, y + 6), fill=(220, 220, 220, 255))                         # buttons
    d.rectangle(box(40, 190, 52, 202), fill=(190, 160, 90, 255))                            # patches
    d.rectangle(box(80, 120, 90, 132), fill=(190, 160, 90, 255))
    d.rectangle(box(20, 96, 34, 180), fill=(150, 110, 70, 255), outline=ink, width=2 * s)   # arms
    d.rectangle(box(94, 96, 108, 180), fill=(150, 110, 70, 255), outline=ink, width=2 * s)
    d.ellipse(box(8, 176, 40, 214), fill=(120, 170, 220, 255), outline=ink, width=2 * s)    # bag
    d.ellipse(box(38, 40, 90, 96), fill=(240, 200, 170, 255), outline=ink, width=2 * s)     # face
    d.ellipse(box(48, 60, 58, 68), fill=ink)                                                # sleepy eyes
    d.ellipse(box(70, 60, 80, 68), fill=ink)
    d.line([(56 * s, 84 * s), (72 * s, 84 * s)], fill=ink, width=2 * s)
    d.rectangle(box(26, 36, 102, 44), fill=(120, 90, 60, 255), outline=ink, width=2 * s)    # hat brim
    d.rectangle(box(40, 12, 88, 38), fill=(120, 90, 60, 255), outline=ink, width=2 * s)     # hat
    return img.resize((CARD_W, CARD_H), Image.LANCZOS)


def card_image():
    from PIL import Image
    if ART.exists():
        art = Image.open(ART).convert("RGBA")
        art.thumbnail((CARD_W, CARD_H), Image.LANCZOS)
        image = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
        image.paste(art, ((CARD_W - art.width) // 2, CARD_H - art.height))  # feet on the bottom edge
        return image, ART
    if not PLACEHOLDER.exists():
        placeholder().save(PLACEHOLDER)
    return Image.open(PLACEHOLDER).convert("RGBA"), PLACEHOLDER


def card_model():
    image, source = card_image()
    blob = hsf_build.build_card(image, GUY_WIDTH, GUY_HEIGHT, name="sparechange")
    hsf_build.check(blob)
    return blob, source


def space_records(blob):
    """[(offset, length)] of each space record in a decoded space file."""
    pos, out = 4, []
    for _ in range(struct.unpack_from(">I", blob, 0)[0]):
        links = struct.unpack_from(">H", blob, pos + 44)[0]
        out.append((pos, 46 + 2 * links))
        pos += 46 + 2 * links
    return out


def patch_spaces(blob):
    """Append SPACE and re-link FROM_SPACE through it; returns the new blob, or None if already done."""
    records = space_records(blob)
    count = len(records)
    from_at, from_len = records[FROM_SPACE - 1]
    link = struct.unpack_from(">H", blob, from_at + 46)[0] + 1
    if count == SPACE:
        at, _ = records[SPACE - 1]
        flags, kind, links = struct.unpack_from(">IHH", blob, at + 38)
        target = struct.unpack_from(">H", blob, at + 46)[0] + 1
        if (flags, kind, links, target, link) != (SPACE_FLAG, 0, 1, TO_SPACE, SPACE):
            raise RuntimeError(f"space {SPACE} exists but is not the spare change space")
        return None
    if count != VANILLA_SPACES or from_len != 48 or link != TO_SPACE:
        raise RuntimeError(f"{count} spaces, space {FROM_SPACE} links {link}: not the expected board")
    out = bytearray(blob)
    struct.pack_into(">H", out, from_at + 46, SPACE - 1)  # links are 0-based
    rot_scale = blob[from_at + 12:from_at + 36]           # rotation and scale of space 55
    out += struct.pack(">3f", *SPACE_POS) + rot_scale + struct.pack(">HIHHH", 0, SPACE_FLAG, 0, 1, TO_SPACE - 1)
    struct.pack_into(">I", out, 0, SPACE)
    return bytes(out)


def patch_board(board, model):
    path = GAME_DATA / f"{board}.bin"
    data, offsets = mpdata.read_archive(path)
    if len(offsets) not in (BOARD_FILES, BOARD_FILES + 1, BOARD_FILES + 2):  # + 2: the troll's card is file 49
        raise SystemExit(f"{board}: {len(offsets)} files: run apply_castaway_broom_patch.py first (expected {BOARD_FILES})")
    blob, start, end = load_spaces(data, offsets)
    spaces = patch_spaces(bytes(blob))
    current = mpdata.read_file(data, offsets, CARD_FILE) if len(offsets) > CARD_FILE else None
    if spaces is None and current == model:
        print(f"{board}: space {SPACE} and the card (file {CARD_FILE}) already in place")
        return
    BACKUPS.mkdir(parents=True, exist_ok=True)
    backup = BACKUPS / f"{board}.bin.bak_before_spare_change"
    if not backup.exists():
        shutil.copy2(path, backup)
    if spaces is not None:
        data, offsets = replace_file0(data, offsets, start, end, spaces)
    if current != model:
        while len(offsets) > CARD_FILE:  # new art: replace the card (and the troll's file after it: re-run the troll script)
            data, offsets = wheel.drop_last_file(data, offsets)
        data, offsets = mpdata.append_files(data, offsets, [model])
    path.write_bytes(data)
    print(f"{board}: space {SPACE} (between {FROM_SPACE} and {TO_SPACE}, flag {SPACE_FLAG:#x}); card is file {CARD_FILE}")


# ---- text -------------------------------------------------------------------

def patch_messages():
    MESS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    from tools.patches import apply_castaway_troll_patch as troll
    tails = OLD_TAILS + tuple(tail + troll.RECORDS for tail in (RECORDS, *OLD_TAILS))
    for name in MESS_NAMES:
        chained = MESS_OUTPUT_DIR / name
        source = chained if chained.exists() else MESS_SOURCE_DIR / name
        edited = edit_bank(source.read_bytes(), {}, name, bank=BANK, bank_records=BANK_RECORDS, append=RECORDS, known_tails=tails)
        (MESS_OUTPUT_DIR / name).write_bytes(edited)
    print(f"Added records {MSG_ASK}-{MSG_BROKE} to bank {BANK:#x}")


def main():
    patch_dol()
    patch_rel()
    model, source = card_model()
    print(f"Card texture: {source}")
    for board in BOARDS:
        patch_board(board, model)
    patch_messages()


if __name__ == "__main__":
    main()
