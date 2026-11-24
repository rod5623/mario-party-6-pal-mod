"""Whomp toll gate (Faire Square): the player in 1st place is refused and sent the other way.

The toll gate is fn_80200524 in the main DOL. It returns r28 = 1 when the player pays the 10 coins
and passes, 0 when they cannot or will not pay (the board then forks them down the other path).
It asks for the player's coins with `bl fn_8015C770` (0x80200680) and, with under 10, shows
"Yous gots no coins" (message 0x290003, `addi r4,r4,3` at 0x8020069C) and returns 0. Two hooks:
  * 0x80200680: cave A calls fn_8015C770; on Faire Square, if nobody is ahead of the player
    (Stars, then coins: the game's own ranking order) it sets a flag and reports 0 coins.
  * 0x8020069C: cave B uses message 0x290009 (new record appended to bank 41) instead of
    0x290003 when the flag is set, and clears the flag.
Everyone else, and every other board, behaves exactly as before. The new line is English in all
language files. Idempotent.
"""
import struct

from tools.lib.paths import DOL
from tools.lib.dol import dol_offset, encode_branch
from tools.lib.minigames import NEW_BASE
from tools.lib.ppc import (
    Asm, BLR, LBZ, LWZ, MFLR, MTLR, STW, STWU, i_add, i_addi, i_cmpwi, i_lis, i_mem, i_mr, i_mulli, i_x,
    ha, lo,
)
from tools.patches import apply_star_shuffle_bet_patch as ss
from tools.lib.ppc import b_to, i_li
from tools.lib.dol import write_cave
from tools.lib.messages import INDENT, encode, record
from tools.lib.paths import MESS_NAMES, MESS_OUTPUT_DIR, MESS_SOURCE_DIR

HOOK_COINS = 0x80200680  # bl fn_8015C770
FN_COINS = 0x8015C770
OLD_CAVE_COINS = 0x80003F74  # first version of this patch
HOOK_MESSAGE = 0x8020069C  # addi r4, r4, 3
WORD_MESSAGE = 0x38840003
HOOK_PROMPT = 0x802006B4  # li r3, 0x3a0: start of the "pay 10 coins?" prompt
WORD_PROMPT = 0x386003A0
PAY_PATH = 0x80200744  # the paid-toll path (deduct, "Good choice", walk through)
PROMPT_BODY = 0x802006B8
HOOK_AMOUNT = 0x80200748  # li r4, -10
WORD_AMOUNT = 0x3880FFF6
HOOK_PAID_MESSAGE = 0x80200768  # addi r4, r4, 1 ("Good choice, mac")
WORD_PAID_MESSAGE = 0x38840001

# Zero padding between TRK vector slots, unused by the other patches
CAVE_MESSAGE = 0x80003F4C  # ends before 0x80004018
CAVE_COINS = 0x80004654  # 0x90 bytes
CAVE_RANK = 0x80004754  # 0x90 bytes
CAVE_PROMPT = 0x80004854  # 0x90 bytes: prompt, amount and paid-message hooks
CAVE_AMOUNT = CAVE_PROMPT + 0x28
CAVE_PAID_MESSAGE = CAVE_PROMPT + 0x4C
FLAG = NEW_BASE + 0x3388  # spare word after the "%d" string of the Star Shuffle patch: 1 rich, 2 underdog

GW_SYSTEM = 0x80283290
GW_PLAYER = 0x80282E70
PLAYER_SIZE = 0x108
FAIRE_SQUARE = 2  # GwSystem.boardNo (w03Dll is the third board)
LHA = 42
RICH_MESSAGE = 9  # new record indices in bank 41
UNDERDOG_MESSAGE = 10
UNDERDOG_COINS = 5

BANK = 41
BANK_RECORDS = 9


def build_message(address):
    """0x8020069C: pick the "no coins" line, or the rich-hater's line when the flag is 1."""
    a = Asm(address)
    a.word(i_lis(5, ha(FLAG)))
    a.word(i_mem(LWZ, 6, 5, lo(FLAG)))
    a.word(i_cmpwi(6, 1))
    a.branch("bne", "normal")
    a.word(i_li(6, 0))
    a.word(i_mem(STW, 6, 5, lo(FLAG)))
    a.word(i_addi(4, 4, RICH_MESSAGE))
    a.word(BLR)
    a.label("normal")
    a.word(i_addi(4, 4, 3))  # the displaced instruction
    a.word(BLR)
    return a.assemble()


def build_rank(address):
    """r12 = number of players ahead of r31 (more Stars, or equal Stars and more coins). Keeps r3."""
    a = Asm(address)
    a.word(i_mulli(4, 31, PLAYER_SIZE))
    a.word(i_lis(5, ha(GW_PLAYER)))
    a.word(i_addi(5, 5, lo(GW_PLAYER)))
    a.word(i_add(11, 4, 5))
    a.word(i_mem(LHA, 6, 11, 0x30))  # my Stars
    a.word(i_mem(LHA, 7, 11, 0x1C))  # my coins
    a.word(i_li(8, 4))
    a.word(i_li(12, 0))
    a.word(i_mr(4, 5))
    a.label("next")
    a.word(i_mem(LHA, 9, 4, 0x30))
    a.word(i_x(0, 0, 9, 6))  # cmpw r9, r6
    a.branch("bgt", "ahead")
    a.branch("blt", "skip")
    a.word(i_mem(LHA, 10, 4, 0x1C))
    a.word(i_x(0, 0, 10, 7))  # cmpw r10, r7
    a.branch("ble", "skip")
    a.label("ahead")
    a.word(i_addi(12, 12, 1))
    a.label("skip")
    a.word(i_addi(4, 4, PLAYER_SIZE))
    a.word(i_addi(8, 8, -1))
    a.word(i_cmpwi(8, 0))
    a.branch("bgt", "next")
    a.word(BLR)
    return a.assemble()


def build_coins(address):
    """0x80200680: fn_8015C770 plus the Faire Square rules for 1st and 4th place."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x10))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x14))
    a.call(FN_COINS)
    a.word(i_lis(4, ha(GW_SYSTEM + 8)))
    a.word(i_mem(LBZ, 5, 4, lo(GW_SYSTEM + 8)))
    a.word((21 << 26) | (5 << 21) | (5 << 16) | (0 << 11) | (27 << 6) | (31 << 1))  # clrlwi r5,r5,27
    a.word(i_cmpwi(5, FAIRE_SQUARE))
    a.branch("bne", "out")
    a.call(CAVE_RANK)
    a.word(i_cmpwi(12, 0))
    a.branch("bne", "not_first")
    a.word(i_li(5, 1))  # 1st place: turned away, as if they had no coins
    a.word(i_li(3, 0))
    a.branch("b", "flag")
    a.label("not_first")
    a.word(i_cmpwi(12, 3))
    a.branch("bne", "out")
    a.word(i_li(5, 2))  # last place: waved through (the prompt hook skips the payment)
    a.word(i_li(3, 10))
    a.label("flag")
    a.word(i_lis(4, ha(FLAG)))
    a.word(i_mem(STW, 5, 4, lo(FLAG)))
    a.label("out")
    a.word(i_mem(LWZ, 0, 1, 0x14))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x10))
    a.word(BLR)
    return a.assemble()


def build_prompt(address):
    """0x802006B4: underdog => skip the prompt and take the paid path."""
    a = Asm(address)
    a.word(i_lis(5, ha(FLAG)))
    a.word(i_mem(LWZ, 6, 5, lo(FLAG)))
    a.word(i_cmpwi(6, 2))
    a.branch("bne", "prompt")
    a.word(b_to(address + 16, PAY_PATH))
    a.label("prompt")
    a.word(i_li(3, 0x3A0))  # the displaced instruction
    a.word(b_to(address + 24, PROMPT_BODY))
    return a.assemble()


def build_amount(address):
    """0x80200748: the underdog is paid 5 coins instead of paying 10."""
    a = Asm(address)
    a.word(i_lis(12, ha(FLAG)))
    a.word(i_mem(LWZ, 11, 12, lo(FLAG)))
    a.word(i_cmpwi(11, 2))
    a.branch("bne", "toll")
    a.word(i_li(4, UNDERDOG_COINS))
    a.word(BLR)
    a.label("toll")
    a.word(i_li(4, -10))  # the displaced instruction
    a.word(BLR)
    return a.assemble()


def build_paid_message(address):
    """0x80200768: the underdog hears the underdog line (then the flag is cleared)."""
    a = Asm(address)
    a.word(i_lis(12, ha(FLAG)))
    a.word(i_mem(LWZ, 11, 12, lo(FLAG)))
    a.word(i_cmpwi(11, 2))
    a.branch("bne", "toll")
    a.word(i_li(11, 0))
    a.word(i_mem(STW, 11, 12, lo(FLAG)))
    a.word(i_addi(4, 4, UNDERDOG_MESSAGE))
    a.word(BLR)
    a.label("toll")
    a.word(i_addi(4, 4, 1))  # the displaced instruction
    a.word(BLR)
    return a.assemble()


RICH_LINE = record("00150002", INDENT + encode("I HATE da rich! PTUH"), b"\xff\x00")
UNDERDOG_LINE = record("00150002", INDENT + encode("I love a good underdog!"), b"\xff\x00")
OLD_TAILS = [  # earlier versions of the appended records
    [record(
        "00150002",
        INDENT + encode("I HATE da rich! *PTUH*\n") + INDENT + encode("Yous can go dat way, mac!"),
        b"\xff\x00",
    )],
]


def patch_messages():
    MESS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in MESS_NAMES:
        chained = MESS_OUTPUT_DIR / name
        source = chained if chained.exists() else MESS_SOURCE_DIR / name
        data = ss.edit_bank(
            source.read_bytes(), {}, name, BANK, BANK_RECORDS, [RICH_LINE, UNDERDOG_LINE], OLD_TAILS
        )
        (MESS_OUTPUT_DIR / name).write_bytes(data)
    print(f"Appended messages {0x290000 + RICH_MESSAGE:#x}, {0x290000 + UNDERDOG_MESSAGE:#x} to bank {BANK}")


HOOKS = (  # (address, original word, cave address, link)
    (HOOK_COINS, None, CAVE_COINS, True),
    (HOOK_MESSAGE, WORD_MESSAGE, CAVE_MESSAGE, True),
    (HOOK_PROMPT, WORD_PROMPT, CAVE_PROMPT, False),
    (HOOK_AMOUNT, WORD_AMOUNT, CAVE_AMOUNT, True),
    (HOOK_PAID_MESSAGE, WORD_PAID_MESSAGE, CAVE_PAID_MESSAGE, True),
)


def main():
    caves = (
        (CAVE_MESSAGE, 0x80004018, build_message(CAVE_MESSAGE)),
        (CAVE_COINS, CAVE_COINS + 0x90, build_coins(CAVE_COINS)),
        (CAVE_RANK, CAVE_RANK + 0x90, build_rank(CAVE_RANK)),
        (CAVE_PROMPT, CAVE_AMOUNT, build_prompt(CAVE_PROMPT)),
        (CAVE_AMOUNT, CAVE_PAID_MESSAGE, build_amount(CAVE_AMOUNT)),
        (CAVE_PAID_MESSAGE, CAVE_PROMPT + 0x90, build_paid_message(CAVE_PAID_MESSAGE)),
    )
    for start, end, code in caves:
        if start + len(code) > end:
            raise RuntimeError(f"Cave at {start:#x} is {len(code)} bytes, room for {end - start}")

    dol = bytearray(DOL.read_bytes())
    for address, original, cave, link in HOOKS:
        original = encode_branch(address, FN_COINS, link=True) if original is None else original
        hooked = encode_branch(address, cave, link=link)
        current = struct.unpack_from(">I", dol, dol_offset(dol, address))[0]
        if current not in (original, hooked, encode_branch(address, OLD_CAVE_COINS, link=True)):
            raise RuntimeError(f"Unexpected word at {address:#x}: {current:#010x}")
    # The caves belong to this patch: clear an earlier version before writing
    for start, end, code in caves:
        position = dol_offset(dol, start)
        dol[position:position + (end - start)] = bytes(end - start)
        write_cave(dol, start, code)
    for address, _, cave, link in HOOKS:
        struct.pack_into(">I", dol, dol_offset(dol, address), encode_branch(address, cave, link=link))
    DOL.write_bytes(dol)
    print("Hooked the Whomp toll gate")

    patch_messages()


if __name__ == "__main__":
    main()
