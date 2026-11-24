"""Star Shuffle (Faire Square, w03Dll): choose how many Stars to bet at night.

At night the player picks a bet from 1 to the number of Stars they own (left lowers, right raises on
the stick or D-pad, A to confirm) and a win pays 3 x the bet. Daytime is unchanged (bet 1, win 2).

fn_1_5908 keeps the reward in r27 (day 2, night 3) and takes a hard-coded 1 Star at .text
0x60F0 (`li r4,-1` before fn_8015CF64). Two module-0 relocations hook it (see battle_port.py):
  * .text 0x5F48 (`mr r3,r26`, right after the player answers "Sure"): night + human player runs
    the selector, then r27 = 3 * bet. Day: falls straight through (bet 1, r27 unchanged).
    CPU: no selector; bets 1, or every Star when in last place (build_cpu).
  * .text 0x60F0 (`li r4,-1`): night => r4 = -(r27 / 3) = -bet, day => -1.
The selector lives in a DOL cave. It shows the same kind of small prompt window as "Choose a hat"
(message 0x31004B, one new record appended to bank 49) and refreshes its number in place.

Message text: record 0x310020 (intro) and 0x310024 ("I need to take a Star...") no longer assume a
single Star. Only the English file gets the reworded text; the new prompt record is English in
every language file.

Run after the other patches (it chains onto the files already in build/). Idempotent.
"""
import struct

from tools.lib.paths import DOL
from tools.lib.dol import dol_offset, encode_branch
from tools.lib.minigames import NEW_BASE
from tools.lib.ppc import (
    Asm, BLR, LBZ, LWZ, MFLR, MTLR, STW, STWU, i_add, i_addi, i_cmpwi, i_lis, i_mem, i_mr, i_mulli, i_x,
    ha, lo,
)
from tools.lib.ppc import i_li, i_rlwinm, i_extsb, i_extsh
from tools.lib.messages import encode, record, INDENT
from tools.lib import messages
from tools.lib.paths import REL_DIR, REL_ORIG, MESS_SOURCE_DIR, MESS_OUTPUT_DIR, MESS_NAMES
from tools.lib.dol import write_cave
from tools.lib.rel import add_calls, check_words

REL_NAME = "w03Dll.rel"


# REL hook sites (.text offsets) and the instruction words they replace
SITE_SELECT = 0x5F48
WORD_SELECT = "7F43D378"  # mr r3, r26
SITE_COST = 0x60F0
WORD_COST = "3880FFFF"  # li r4, -1
SITES_PAYOUT = (0x7AC4, 0x7AD0)  # mr r4, r27 before fn_801816CC / fn_80181DDC
WORD_PAYOUT = "7F64DB78"

CAVE_SELECT = 0x80004040  # zero padding in the init section, up to 0x800041E4
CAVE_SELECT_END = 0x800041E4
CAVE_COST = NEW_BASE + 0x3340  # free tail of the relocated table section
CAVE_PAYOUT = NEW_BASE + 0x3360  # night: 3 x bet, day: r27
BET = NEW_BASE + 0x338C  # the night bet, read by the cost and payout hooks
CAVE_SHOW = 0x80004454  # zero padding in the init section, up to 0x800044E4
CAVE_SHOW_END = 0x800044E4
CAVE_FMT = NEW_BASE + 0x3380  # "%d"
CAVE_CPU = NEW_BASE + 0x3390
LHA = 42

FN_STAR_COUNT = 0x8015CE98  # fn_8015CE98(player) -> Stars
FN_FRAME = 0x8000E2C4
FN_PAD_STK_X = 0x8020497C
FN_SPRINTF = 0x800F24F0
FN_MSG_ARG = 0x8016C660
FN_PROMPT = 0x8016B7A4
FN_PROMPT_POS = 0x8016BCA0
FN_PROMPT_CLOSE = 0x8016BA18

GW_PLAYER = 0x80282E70
PLAYER_SIZE = 0x108
BTN_DOWN = 0x802DD8E8  # HuPad pressed-button halfwords, indexed by pad
PROMPT_MESSAGE = 0x31004B  # new record appended to bank 49

NIGHT_HATS = 6  # r26 in fn_1_5908: 6 hats at night, 3 by day
NIGHT_REWARD = 3  # r27 keeps this value: the win animation loops over r27 objects
FIRST_REPEAT = 15  # frames before a held direction starts repeating
REPEAT = 4


def i_slwi1(ra, rs):
    return i_rlwinm(ra, rs, 1, 0, 30)


def build_select(address):
    a = Asm(address)
    a.word(i_cmpwi(26, NIGHT_HATS))
    a.branch("bne", "done")
    a.word(i_lis(4, ha(BET)))
    a.word(i_li(0, 1))
    a.word(i_mem(STW, 0, 4, lo(BET)))  # default bet: 1
    # CPU players (bit 0x20 of GwPlayer byte 0) skip the selector (see build_cpu)
    a.word(i_mulli(3, 29, PLAYER_SIZE))
    a.word(i_lis(4, ha(GW_PLAYER)))
    a.word(i_addi(4, 4, lo(GW_PLAYER)))
    a.word(i_add(12, 3, 4))  # r12 = &GwPlayer[player]
    a.word(i_mem(LBZ, 3, 12, 0))
    a.word(i_rlwinm(3, 3, 0, 26, 26))
    a.word(i_cmpwi(3, 0))
    a.branch("bne", "cpu")
    a.word(i_mem(LBZ, 3, 12, 4))
    a.word(i_extsb(27, 3))  # r27 = the player's pad (r27 is rewritten at the end)

    a.word(i_mem(STWU, 1, 1, -0x40))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x44))
    a.word(i_mem(STW, 31, 1, 0x3C))
    a.word(i_mem(STW, 30, 1, 0x38))
    a.word(i_mem(STW, 28, 1, 0x34))

    a.word(i_mr(3, 29))
    a.call(FN_STAR_COUNT)
    a.word(i_mr(30, 3))  # r30 = most the player can bet
    a.word(i_li(31, 1))  # r31 = bet
    a.word(i_li(0, 0))
    a.word(i_mem(STW, 0, 1, 0x10))  # last direction
    a.word(i_mem(STW, 0, 1, 0x14))  # repeat timer

    a.label("show")  # the number is read when a window opens, so every change opens a new one
    a.word(i_mr(3, 31))
    a.call(CAVE_SHOW)
    a.word(i_mr(28, 3))  # r28 = prompt window

    a.label("loop")
    a.call(FN_FRAME)
    a.word(i_mr(3, 27))
    a.call(FN_PAD_STK_X)
    a.word(i_extsb(3, 3))
    a.word(i_mem(STW, 3, 1, 0x18))
    a.word(i_lis(4, ha(BTN_DOWN)))
    a.word(i_addi(4, 4, lo(BTN_DOWN)))
    a.word(i_slwi1(0, 27))
    a.word(i_x(279, 5, 4, 0))  # lhzx r5, r4, r0
    a.word(i_rlwinm(0, 5, 0, 23, 23))  # A
    a.word(i_cmpwi(0, 0))
    a.branch("bne", "confirm")
    a.word(i_rlwinm(0, 5, 0, 30, 30))  # D-pad right raises
    a.word(i_cmpwi(0, 0))
    a.branch("bne", "up")
    a.word(i_rlwinm(0, 5, 0, 31, 31))  # D-pad left lowers
    a.word(i_cmpwi(0, 0))
    a.branch("bne", "down")
    a.word(i_mem(LWZ, 3, 1, 0x18))
    a.word(i_cmpwi(3, 8))
    a.branch("bgt", "up")
    a.word(i_cmpwi(3, -8))
    a.branch("blt", "down")
    a.word(i_li(0, 0))  # neutral: re-arm
    a.word(i_mem(STW, 0, 1, 0x10))
    a.word(i_mem(STW, 0, 1, 0x14))
    a.branch("b", "loop")

    a.label("up")
    a.word(i_li(6, 1))
    a.branch("b", "step")
    a.label("down")
    a.word(i_li(6, -1))
    a.label("step")
    a.word(i_mem(LWZ, 0, 1, 0x10))
    a.word(i_x(0, 0, 0, 6))  # cmpw r0, r6
    a.branch("bne", "first")
    a.word(i_mem(LWZ, 4, 1, 0x14))
    a.word(i_addi(4, 4, -1))
    a.word(i_mem(STW, 4, 1, 0x14))
    a.word(i_cmpwi(4, 0))
    a.branch("bgt", "loop")
    a.word(i_li(4, REPEAT))
    a.branch("b", "fire")
    a.label("first")
    a.word(i_li(4, FIRST_REPEAT))
    a.label("fire")
    a.word(i_mem(STW, 6, 1, 0x10))
    a.word(i_mem(STW, 4, 1, 0x14))
    a.word(i_add(31, 31, 6))
    a.word(i_cmpwi(31, 1))  # wrap around the ends
    a.branch("bge", "not_low")
    a.word(i_mr(31, 30))
    a.label("not_low")
    a.word(i_x(0, 0, 31, 30))  # cmpw r31, r30
    a.branch("ble", "wrapped")
    a.word(i_li(31, 1))
    a.label("wrapped")
    a.word(i_extsh(3, 28))
    a.call(FN_PROMPT_CLOSE)
    a.branch("b", "show")

    a.label("confirm")
    a.word(i_extsh(3, 28))
    a.call(FN_PROMPT_CLOSE)
    a.word(i_lis(4, ha(BET)))
    a.word(i_mem(STW, 31, 4, lo(BET)))
    a.word(i_mem(LWZ, 0, 1, 0x44))
    a.word(i_mem(LWZ, 31, 1, 0x3C))
    a.word(i_mem(LWZ, 30, 1, 0x38))
    a.word(i_mem(LWZ, 28, 1, 0x34))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x40))
    a.word(i_li(27, NIGHT_REWARD))  # r27 held the pad
    a.label("done")
    a.word(i_mr(3, 26))  # the displaced instruction
    a.word(BLR)
    a.label("cpu")
    code = a.assemble()
    return code + struct.pack(">I", encode_branch(a.labels["cpu"], CAVE_CPU))  # r12 = &GwPlayer[player]


def build_show(address):
    """r3 = bet: format it, open the prompt window and return the window."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x20))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x24))
    a.word(i_mem(STW, 31, 1, 0x1C))
    a.word(i_mr(31, 3))
    a.word(i_lis(3, 0x31))
    a.word(i_addi(3, 3, PROMPT_MESSAGE & 0xFFFF))
    a.call(FN_PROMPT)
    a.word(i_mem(STW, 3, 1, 0x18))
    a.word(i_extsh(3, 3))
    a.word(i_li(4, 0xE4))
    a.word(i_li(5, 0x14A))
    a.call(FN_PROMPT_POS)
    a.word(i_addi(3, 1, 8))
    a.word(i_lis(4, ha(CAVE_FMT)))
    a.word(i_addi(4, 4, lo(CAVE_FMT)))
    a.word(i_mr(5, 31))
    a.call(FN_SPRINTF)
    a.word(i_addi(3, 1, 8))
    a.word(i_li(4, 0))
    a.call(FN_MSG_ARG)
    a.word(i_mem(LWZ, 31, 1, 0x1C))
    a.word(i_mem(LWZ, 3, 1, 0x18))
    a.word(i_mem(LWZ, 0, 1, 0x24))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x20))
    a.word(BLR)
    return a.assemble()


def build_payout(address):
    a = Asm(address)
    a.word(i_cmpwi(26, NIGHT_HATS))
    a.branch("bne", "day")
    a.word(i_lis(4, ha(BET)))
    a.word(i_mem(LWZ, 4, 4, lo(BET)))
    a.word(i_mulli(4, 4, NIGHT_REWARD))
    a.word(BLR)
    a.label("day")
    a.word(i_mr(4, 27))  # the displaced instruction
    a.word(BLR)
    return a.assemble()


def build_cpu(address):
    """CPU bet: everything when in last place (3 players strictly ahead on Stars, then coins), else 1."""
    a = Asm(address)
    a.word(i_mem(LHA, 6, 12, 0x30))  # my Stars
    a.word(i_mem(LHA, 7, 12, 0x1C))  # my coins
    a.word(i_lis(4, ha(GW_PLAYER)))
    a.word(i_addi(4, 4, lo(GW_PLAYER)))
    a.word(i_li(8, 0))  # players ahead of me
    a.word(i_li(9, 4))
    a.label("next")
    a.word(i_mem(LHA, 10, 4, 0x30))
    a.word(i_x(0, 0, 10, 6))  # cmpw r10, r6
    a.branch("bgt", "ahead")
    a.branch("blt", "skip")
    a.word(i_mem(LHA, 11, 4, 0x1C))
    a.word(i_x(0, 0, 11, 7))  # cmpw r11, r7
    a.branch("ble", "skip")
    a.label("ahead")
    a.word(i_addi(8, 8, 1))
    a.label("skip")
    a.word(i_addi(4, 4, PLAYER_SIZE))
    a.word(i_addi(9, 9, -1))
    a.word(i_cmpwi(9, 0))
    a.branch("bgt", "next")
    a.word(i_cmpwi(8, 3))
    a.branch("blt", "done")
    a.word(i_lis(4, ha(BET)))
    a.word(i_mem(STW, 6, 4, lo(BET)))  # last place: bet every Star
    a.label("done")
    a.word(i_mr(3, 26))  # the displaced instruction
    a.word(BLR)
    return a.assemble()


def build_cost(address):
    a = Asm(address)
    a.word(i_cmpwi(26, NIGHT_HATS))
    a.branch("bne", "day")
    a.word(i_lis(4, ha(BET)))
    a.word(i_mem(LWZ, 4, 4, lo(BET)))
    a.word(i_x(104, 4, 4, 0))  # neg r4, r4
    a.word(BLR)
    a.label("day")
    a.word(i_li(4, -1))  # the displaced instruction
    a.word(BLR)
    return a.assemble()


# ---- messages ---------------------------------------------------------------

BANK = 49
BANK_RECORDS = 75


INTRO = record(
    "00150003",
    INDENT + encode("In this magical and mysterious\n") + INDENT
    + encode("game, you can transform your\n") + INDENT + encode("Stars into <N> times as many!"),
    b"\xff\x00",
)
TAKE = record(
    "00150003",
    INDENT + encode("I need to take your bet") + b"\x85",
    b"\xff\x00",
)
PROMPT = record(
    "000c0002",
    b"\x0e\x01" + encode(" Stars <N>\n") + b"\x0e\x03" + encode(" Confirm"),
    b"\x00",
)
REPLACEMENTS = {32: INTRO, 36: TAKE}  # English only
# Record 76 (0x31004C) is the Faire Square space 28 question, see apply_double_or_nothing_patch.py
CHOICE = bytes([0x20] * 6 + [0x0F])  # option marker, as in record 33 (Star Shuffle "Sure / Not interested")
DOUBLE = record(
    "00150003",
    INDENT + encode("Double or nothing?" + chr(10)) + CHOICE + encode("Yes" + chr(10)) + CHOICE + encode("No"),
    bytes([0]),
)
# Records 77-79 (0x31004D-0x31004F): the space 28 outcome lines (loss, Star gain, coins doubled)
RESULTS = [
    record("00150003", INDENT + encode(text), bytes([0xFF, 0x00]))
    for text in ("Cheers for that good lad", "Good for you pal", "Good heart pal")
]
# Records 80-86 (0x310050-0x310056): the space 30 Wheel of Fortune, see apply_wheel_of_fortune_patch.py
WHEEL = [
    record("00150003", INDENT + encode(text), bytes([0xFF, 0x00]))
    for text in (
        "Spin the Wheel of Fortune!", "Jackpot! Two Stars for you!", "Free orbs for the lucky!",
        "Pockets full, no orbs!", "A fine! Pay one Star!", "No Stars to fine, lucky!",
        "Back to the start you go!",
    )
]
WHEEL_V1 = list(WHEEL)  # records 80-86 as first released
# Record 87 (0x310057): the landing question
WHEEL.append(record(
    "00150003",
    INDENT + encode("Spin the wheel?" + chr(10)) + CHOICE + encode("Yes" + chr(10)) + CHOICE + encode("No"),
    bytes([0]),
))
APPEND = [PROMPT, DOUBLE, *RESULTS, *WHEEL]
OLD_DOUBLE = record("00150003", INDENT + encode("Double or nothing?"), bytes([0xFF, 0]))  # no Yes/No
OLD_PROMPT = record(
    "000c0002",
    b"\x0e\x01" + encode(" Stars <N>\n") + b"\x0e\x03" + encode(" Up Down A"),
    b"\x00",
)
OLD_TAILS = tuple(
    [prompt, *rest]
    for prompt in (PROMPT, OLD_PROMPT)
    for rest in ([], [OLD_DOUBLE], [OLD_DOUBLE, *RESULTS], [DOUBLE], [DOUBLE, *RESULTS], [DOUBLE, *RESULTS, *WHEEL_V1], [DOUBLE, *RESULTS, *WHEEL])
)


def edit_bank(source, replacements, label, bank=BANK, bank_records=BANK_RECORDS, append=None, known_tails=OLD_TAILS):
    """lib.messages.edit_bank with this patch's bank, records and old tails as defaults."""
    return messages.edit_bank(source, replacements, label, bank, bank_records,
                              APPEND if append is None else append, known_tails)


def patch_messages():
    MESS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in MESS_NAMES:
        chained = MESS_OUTPUT_DIR / name
        source = chained if chained.exists() else MESS_SOURCE_DIR / name
        replacements = REPLACEMENTS if name == "messdata_eng.bin" else {}
        (MESS_OUTPUT_DIR / name).write_bytes(edit_bank(source.read_bytes(), replacements, name))
    print(f"Patched bank {BANK} in {MESS_OUTPUT_DIR}")


# ---- main -------------------------------------------------------------------

def main():
    select = build_select(CAVE_SELECT)
    if CAVE_SELECT + len(select) > CAVE_SELECT_END:
        raise RuntimeError(f"Selector is {len(select)} bytes, too big for the cave")
    show = build_show(CAVE_SHOW)
    if CAVE_SHOW + len(show) > CAVE_SHOW_END:
        raise RuntimeError(f"Show routine is {len(show)} bytes, too big for the cave")
    cost = build_cost(CAVE_COST)
    payout = build_payout(CAVE_PAYOUT)
    cpu = build_cpu(CAVE_CPU)
    if CAVE_CPU + len(cpu) > NEW_BASE + 0x3400:
        raise RuntimeError("CPU routine overruns the table section")
    fmt = b"%d\0\0\0\0\0\0"

    dol = bytearray(DOL.read_bytes())
    # These regions belong to this patch: clear any earlier version before writing
    for address, size in (
        (CAVE_SELECT, CAVE_SELECT_END - CAVE_SELECT), (CAVE_SHOW, CAVE_SHOW_END - CAVE_SHOW),
        (CAVE_COST, 0x20), (CAVE_PAYOUT, 0x20), (CAVE_CPU, 0x70),
    ):
        position = dol_offset(dol, address)
        dol[position:position + size] = bytes(size)
    write_cave(dol, CAVE_SELECT, select)
    write_cave(dol, CAVE_SHOW, show)
    write_cave(dol, CAVE_COST, cost)
    write_cave(dol, CAVE_PAYOUT, payout)
    write_cave(dol, CAVE_FMT, fmt)
    write_cave(dol, CAVE_CPU, cpu)
    DOL.write_bytes(dol)
    print(f"Selector cave: {len(select)} bytes at {CAVE_SELECT:#010x}")

    path = REL_DIR / REL_NAME
    data = bytearray((path if path.exists() else REL_ORIG / REL_NAME).read_bytes())
    check_words(data, SITE_SELECT, WORD_SELECT, "48000001")
    check_words(data, SITE_COST, WORD_COST, "48000001")
    for site in SITES_PAYOUT:
        check_words(data, site, WORD_PAYOUT, "48000001")
    calls = [(SITE_SELECT, CAVE_SELECT), (SITE_COST, CAVE_COST)] + [(site, CAVE_PAYOUT) for site in SITES_PAYOUT]
    if add_calls(data, calls):
        REL_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f"Hooked Star Shuffle ({REL_NAME})")
    else:
        print("Star Shuffle already hooked")

    patch_messages()


if __name__ == "__main__":
    main()
