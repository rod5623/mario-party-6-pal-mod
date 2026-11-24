"""Faire Square (w03Dll) space 28: "Double or nothing?".

Space 28 (flag 0x8) used to run fn_1_C5DC (send the player back to the start). It now asks
"Double or nothing?" (Yes/No, nothing else is revealed). On Yes a 1-10 roll decides:
  1-4  lose all coins        5  lose a Star (if they have one)
  6    gain a Star           7-10  double the coins (the game caps coins at 999)
Space 30 (flag 0x20) still runs fn_1_C5DC.

fn_1_1C30 (the passing handler, r29 = player, r31 = space flags) is changed in two places:
  * .text 0x1C5C  `andi. r0,r31,0x28` -> `andi. r0,r31,0x20`: only space 30 reaches fn_1_C5DC.
  * .text 0x1CA4  `li r3,1` -> bl to the cave below. The cave does the gamble when flag 0x8 is set
    and always returns r3 = 1 (the displaced instruction), so nothing else changes.
The question is message 0x31004C, a new record of bank 49 added by apply_star_shuffle_bet_patch.py.

Run after apply_star_shuffle_bet_patch.py. Idempotent.
"""
from tools.lib.paths import DOL
from tools.lib.dol import dol_offset
from tools.lib.ppc import (
    Asm, BLR, LBZ, LWZ, MFLR, MTLR, STW, STWU, i_add, i_addi, i_cmpwi, i_lis, i_mem, i_mr, i_mulli, i_x,
    ha, lo,
)
from tools.lib.paths import REL_DIR, REL_ORIG
from tools.patches.apply_star_shuffle_bet_patch import REL_NAME
from tools.lib.ppc import i_li, i_rlwinm
from tools.lib.ppc import i_mullw
from tools.lib.game import FN_COINS, FN_ADD_COINS
from tools.lib.dol import write_cave
from tools.lib.rel import add_calls, check_words, text_base

CAVE = 0x80005218  # zero padding in the init section, up to 0x800052E4
CAVE_END = 0x800052E4
GAMBLE = 0x80005318  # the roll and its result, called from the cave
GAMBLE_END = 0x800053E4
SHOW = 0x80005418  # picks and shows the outcome line
SHOW_END = 0x80005460
ROLL = 0x80005460  # the dice block roll
ROLL_END = 0x800054E4

SITE_MASK = 0x1C5C
WORD_MASK = "73E00028"  # andi. r0, r31, 0x28
WORD_MASK_NEW = "73E00020"  # andi. r0, r31, 0x20
SITE_RETURN = 0x1CA4
WORD_RETURN = "38600001"  # li r3, 1

FN_MESSAGE = 0x8016B36C  # fn_8016B36C(2, message, speaker)
FN_PROMPT = 0x8016B718  # fn_8016B718(2, message, speaker, 0) -> message window with choices
FN_WAIT_MESSAGE = 0x8016C7D8
FN_CHOICE = 0x8016C52C  # 0 = first option (Yes), 1 = No, -1 = cancelled
FN_CPU_ANSWER = 0x80170720
FN_DICE = 0x80184CFC  # fn_80184CFC(player, type, 0, -1, 1, 1, 0, 0): the turn dice block, waits for A, returns 1-10
FN_FRAMES = 0x8000E244  # wait r3 frames
FN_DICE_HIDE = 0x80187D14  # fn_80187D14(player): removes the dice block
FN_STARS = 0x8015CE98
FN_ADD_STARS = 0x8015CF64
FN_STAR_POPUP = 0x80181DDC  # returns a handle polled with fn_80182258
FN_POPUP_DONE = 0x80182258
FN_YIELD = 0x8000E2C4

GW_PLAYER = 0x80282E70
PLAYER_SIZE = 0x108
MESSAGE = 0x31004C  # bank 49 record 76
RESULT_LOSS = 0x4D  # records 77-79: "Cheers for that good lad" (roll 1-5), "Good for you pal" (6),
RESULT_STAR = 0x4E  # "Good heart pal" (7-10)
RESULT_COINS = 0x4F
SPEAKER = 8  # same host window Star Shuffle uses by day


def i_neg(rd, ra):
    return i_x(104, rd, ra, 0)


def build_cave(address):
    a = Asm(address)
    a.word(i_rlwinm(0, 31, 0, 28, 28) | 1)  # rlwinm. r0, r31, 0, 28, 28  (flag 0x8)
    a.branch("beq", "return")
    a.word(i_mem(STWU, 1, 1, -0x20))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x24))
    a.word(i_mem(STW, 30, 1, 0x18))

    a.word(i_li(3, 2))
    a.word(i_lis(4, MESSAGE >> 16))
    a.word(i_addi(4, 4, MESSAGE & 0xFFFF))
    a.word(i_li(5, SPEAKER))
    a.word(i_li(6, 0))
    a.call(FN_PROMPT)
    # CPU players (bit 0x20 of GwPlayer byte 0) answer on their own
    a.word(i_mulli(4, 29, PLAYER_SIZE))
    a.word(i_lis(5, ha(GW_PLAYER)))
    a.word(i_addi(5, 5, lo(GW_PLAYER)))
    a.word(i_add(5, 5, 4))
    a.word(i_mem(LBZ, 0, 5, 0))
    a.word(i_rlwinm(0, 0, 0, 26, 26) | 1)  # rlwinm. r0, r0, 0, 26, 26
    a.branch("beq", "human")
    a.call(FN_CPU_ANSWER)
    a.label("human")
    a.call(FN_WAIT_MESSAGE)
    a.call(FN_CHOICE)
    a.word(i_cmpwi(3, 0))
    a.branch("bne", "done")  # No (1) or cancelled (-1)

    a.call(GAMBLE)
    a.call(SHOW)  # r3 = the roll (0-9)
    a.label("done")
    a.word(i_mem(LWZ, 0, 1, 0x24))
    a.word(i_mem(LWZ, 30, 1, 0x18))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x20))
    a.label("return")
    a.word(i_li(3, 1))  # the displaced instruction
    a.word(BLR)
    return a.assemble()


def build_gamble(address):
    """Roll 1-10 for the player in r29 and apply the result."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x20))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x24))
    a.word(i_mem(STW, 30, 1, 0x18))
    a.call(ROLL)  # r3 = roll 0-9
    a.word(i_mem(STW, 3, 1, 0x10))
    a.word(i_cmpwi(3, 4))  # 0-3 lose all, 4 lose a Star, 5 gain a Star, 6-9 double
    a.branch("blt", "lose")
    a.branch("beq", "star_lose")
    a.word(i_cmpwi(3, 5))
    a.branch("beq", "star_gain")

    a.word(i_li(30, 1))  # double: add the coins you already have
    a.branch("b", "coins")
    a.label("lose")
    a.word(i_li(30, -1))  # lose all: add minus the coins you have
    a.label("coins")
    a.word(i_mr(3, 29))
    a.call(FN_COINS)
    a.word(i_mullw(4, 3, 30))
    a.word(i_mr(3, 29))
    a.word(i_li(5, 1))
    a.word(i_li(6, 1))
    a.call(FN_ADD_COINS)
    a.branch("b", "end")

    a.label("star_lose")
    a.word(i_mr(3, 29))
    a.call(FN_STARS)
    a.word(i_cmpwi(3, 0))
    a.branch("ble", "end")
    a.word(i_li(30, -1))
    a.branch("b", "stars")
    a.label("star_gain")
    a.word(i_li(30, 1))
    a.label("stars")
    a.word(i_mr(3, 29))
    a.word(i_mr(4, 30))
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
    a.word(i_mem(LWZ, 3, 1, 0x10))
    a.word(i_mem(LWZ, 0, 1, 0x24))
    a.word(i_mem(LWZ, 30, 1, 0x18))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x20))
    a.word(BLR)
    return a.assemble()


def build_show(address):
    """r3 = roll (0-9): show the outcome line."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x10))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x14))
    a.word(i_cmpwi(3, 5))
    a.word(i_li(4, RESULT_LOSS))
    a.branch("blt", "show")
    a.word(i_li(4, RESULT_STAR))
    a.branch("beq", "show")
    a.word(i_li(4, RESULT_COINS))
    a.label("show")
    a.word((15 << 26) | (4 << 21) | (4 << 16) | (MESSAGE >> 16))  # addis r4, r4, 0x31
    a.word(i_li(3, 2))
    a.word(i_li(5, SPEAKER))
    a.call(FN_MESSAGE)
    a.call(FN_WAIT_MESSAGE)
    a.word(i_mem(LWZ, 0, 1, 0x14))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x10))
    a.word(BLR)
    return a.assemble()


def build_roll(address):
    """Roll the turn dice block for the player in r29; returns the roll as 0-9."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x10))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x14))
    a.word(i_mr(3, 29))
    a.word(i_li(4, 0))  # normal dice type
    a.word(i_li(5, 0))
    a.word(i_li(6, -1))
    a.word(i_li(7, 1))
    a.word(i_li(8, 1))
    a.word(i_li(9, 0))
    a.word(i_li(10, 0))
    a.call(FN_DICE)
    a.word(i_cmpwi(3, 1))
    a.branch("bge", "ok")
    a.word(i_li(3, 1))  # no result: count it as a 1
    a.label("ok")
    a.word(i_addi(3, 3, -1))
    a.word(i_mem(STW, 3, 1, 0x8))
    a.word(i_li(3, 30))  # let the number show, then remove the block (as the DK bonus does)
    a.call(FN_FRAMES)
    a.word(i_mr(3, 29))
    a.call(FN_DICE_HIDE)
    a.word(i_mem(LWZ, 3, 1, 0x8))
    a.word(i_mem(LWZ, 0, 1, 0x14))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x10))
    a.word(BLR)
    return a.assemble()


def main():
    cave = build_cave(CAVE)
    gamble = build_gamble(GAMBLE)
    show = build_show(SHOW)
    roll = build_roll(ROLL)
    for start, end, code in ((CAVE, CAVE_END, cave), (GAMBLE, GAMBLE_END, gamble), (SHOW, SHOW_END, show), (ROLL, ROLL_END, roll)):
        if start + len(code) > end:
            raise RuntimeError(f"Code is {len(code)} bytes, too big for {start:#010x}-{end:#010x}")

    dol = bytearray(DOL.read_bytes())
    for start, end in ((CAVE, CAVE_END), (GAMBLE, GAMBLE_END), (SHOW, SHOW_END), (ROLL, ROLL_END)):
        position = dol_offset(dol, start)
        dol[position:position + end - start] = bytes(end - start)  # clear any earlier version
    write_cave(dol, CAVE, cave)
    write_cave(dol, GAMBLE, gamble)
    write_cave(dol, SHOW, show)
    write_cave(dol, ROLL, roll)
    DOL.write_bytes(dol)
    print(f"Cave: {len(cave)} + {len(gamble)} + {len(show)} + {len(roll)} bytes at {CAVE:#010x}, {GAMBLE:#010x}, {SHOW:#010x}, {ROLL:#010x}")

    path = REL_DIR / REL_NAME
    data = bytearray((path if path.exists() else REL_ORIG / REL_NAME).read_bytes())
    check_words(data, SITE_MASK, WORD_MASK, WORD_MASK_NEW)
    check_words(data, SITE_RETURN, WORD_RETURN, "48000001")
    position = text_base(data) + SITE_MASK
    data[position:position + 4] = bytes.fromhex(WORD_MASK_NEW)
    add_calls(data, [(SITE_RETURN, CAVE)])
    REL_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"Hooked space 28 ({REL_NAME})")


if __name__ == "__main__":
    main()
