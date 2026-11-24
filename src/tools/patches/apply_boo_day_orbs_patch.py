"""Boo's house by DAY: "Want me to launch some orbs?" (every board with a Boo house, e.g. Castaway Bay).

Vanilla: the Boo event (fn_801B16A8, shared DOL code) says "Daytime is totally lame... Come back later" (bank
0x3B record 0) when the night bit (GwSystem+0x10 bit 0x40) is clear and ends. Now, by day:
  * "Want me to launch some orbs?" Yes / No (CPUs skip the question);
  * Yes: 3 orbs for free, or 5 orbs plus 1 random orb for your pocket for 20 coins. B cancels like No. Fewer
    than 20 coins: a refusal line and the menu again. Pockets full: the launch happens but no spare orb.
  * The orbs are launched by a relocated copy of the Final Five "Character Spaces" routine fn_802026F8, with
    its fixed count of 10 replaced by r16 (3 or 5), and without the Final Five host character (fn_801ECBC0 /
    fn_801ECC84) or the host model show/hide calls (fn_80168ED4); a dummy argument block stands in for the
    host's model table. fn_802026F8 itself is untouched, so the Final Five event is unchanged.

Hook: DOL 0x801B1734 (`li r3,2`, the start of the daytime message) becomes `b CAVE_DAY`; the cave ends with
the displaced `bl fn_8000E144` and `b .L_801B3E7C` (the function epilogue), exactly like the original branch.
The cave runs inside fn_801B16A8's frame (r26 = event data, player = 0(r26)) and may use r16-r31, which the
prologue saved.

Code space: the dead old MgDataTbl after the Castaway Bay wheel caves (0x802310A0..0x80232744). Run after
luck_wheel_rewards (needs its one-orb routine, CAVE_ORB: the Faire Square wheel pool), castaway_wheel and final_five_odds. Idempotent.
Text: bank 0x3B (Boo) records 18-25, English text in every language file.
Nothing here has been run in Dolphin. Unverified: that the Final Five routine's camera calls behave from a
board Boo event, and the menu markup (copied from the Faire Square "Double or nothing?" record).
"""
import struct

from tools.patches import apply_castaway_wheel_patch as cb
from tools.patches import apply_luck_wheel_rewards_patch as luck
from tools.lib.paths import DOL
from tools.lib.dol import dol_offset, encode_branch
from tools.lib.game import FN_ADD_COINS, FN_COINS
from tools.lib.minigames import NEW_BASE, SECTION_SLOT
from tools.lib.paths import MESS_NAMES, MESS_OUTPUT_DIR, MESS_SOURCE_DIR
from tools.patches.apply_star_shuffle_bet_patch import edit_bank
from tools.lib.messages import encode, record
from tools.lib.ppc import i_li, i_rlwinm
from tools.lib.ppc import Asm, LBZ, LWZ, i_add, i_addi, i_cmpw, i_cmpwi, i_lis, i_mem, i_mr, i_mulli, ha, lo
from tools.lib.game import (
    FN_CHOICE, FN_MESSAGE, FN_ORB_COUNT, FN_ORB_MAX, FN_PROMPT, FN_WAIT_MESSAGE, GW_PLAYER, PLAYER_SIZE,
)
from tools.lib.ppc import epilogue, i_addis, prologue

HOOK = 0x801B1734            # `li r3,2` in the daytime branch of fn_801B16A8
HOOK_WORD = 0x38600002
EXIT = 0x801B3E7C            # .L_801B3E7C, the epilogue of fn_801B16A8
FN_EVENT_END = 0x8000E144    # the call the daytime branch makes before the epilogue

LAUNCHER = 0x802026F8        # fn_802026F8: Final Five Character Spaces; r3 player, r4 host data, r5 host character
LAUNCHER_END = 0x80202B58
FREE_ORBS = 3
PAID_ORBS = 5
PAID_COST = 20

CAVE_SHOW = 0x80231100       # r3 = record index in bank 0x3B (0x40 bytes)
CAVE_LAUNCH = 0x80231140     # r3 player, r4 count (0x60 bytes)
CAVE_DAY = 0x802311A0        # the hook target (0x1C0 bytes)
CAVE_DATA = 0x80231360       # dummy host block (0x80 bytes)
CAVE_COPY = 0x80231400       # the relocated launcher (0x460 bytes)
CAVES_END = CAVE_COPY + (LAUNCHER_END - LAUNCHER)
DEAD_END = 0x80232744

BANK = 0x3B
BANK_RECORDS = 18
MSG_BASE = 0x3B0000
MSG_ASK, MSG_MENU, MSG_NO_COINS, MSG_LAUNCH, MSG_GOT, MSG_FULL, MSG_DECLINE = range(18, 25)
SPEAKER = 0xA                # Boo (as in the vanilla daytime line)

INDENT = b"    "
CHOICE = bytes([0x20] * 6 + [0x0F])  # option marker, as in the Faire Square "Double or nothing?" record


def line(text):
    return record("00150003", INDENT + encode(text.replace("'", "\\")), bytes([0xFF, 0x00]))


def menu(question, options):
    body = INDENT + encode(question + "\n")
    body += b"".join(CHOICE + encode(option + ("\n" if i < len(options) - 1 else "")) for i, option in enumerate(options))
    return record("00150003", body, bytes([0]))


RECORDS = [
    menu("Want me to launch some orbs?", ["Yes", "No"]),
    menu("Hee hee, how many orbs?", [f"{FREE_ORBS} orbs for free", f"{PAID_ORBS} orbs and 1 orb for you, {PAID_COST} coins"]),
    line(f"You don't have {PAID_COST} coins to take! Teeheehee!"),
    line("Here they come! Teeheehee!"),
    line("And a spare orb for your pocket! Teehee!"),
    line("Your pockets are full, no spare orb! Teehee!"),
    line("Boo hoo, maybe later then! Teeheehee!"),
]


def build_show(address):
    """r3 = record index in bank 0x3B: show it and wait."""
    a = Asm(address)
    prologue(a, 0x10, ())
    a.word(i_addis(4, 3, MSG_BASE >> 16))
    a.word(i_li(3, 2))
    a.word(i_li(5, SPEAKER))
    a.call(FN_MESSAGE)
    a.call(FN_WAIT_MESSAGE)
    epilogue(a, 0x10, ())
    return a.assemble()


def build_launch(address, copy, data):
    """r3 = player, r4 = count: run the relocated Final Five routine with r16 = count."""
    a = Asm(address)
    saved = (16,)
    prologue(a, 0x60, saved)
    a.word(i_mr(16, 4))
    a.word(i_lis(4, ha(data)))
    a.word(i_addi(4, 4, lo(data)))
    a.word(i_li(5, 0))
    a.call(copy)
    epilogue(a, 0x60, saved)
    code = a.assemble()
    if len(code) > CAVE_DAY - CAVE_LAUNCH:
        raise RuntimeError("launch wrapper overlaps the day cave")
    return code


def build_day(address, show, launch):
    """Runs inside fn_801B16A8: r26 = event data. Ends with the displaced call and a jump to the epilogue."""
    a = Asm(address)
    a.word(i_mem(LWZ, 31, 26, 0))  # player
    a.word(i_mulli(4, 31, PLAYER_SIZE))
    a.word(i_lis(5, ha(GW_PLAYER)))
    a.word(i_addi(5, 5, lo(GW_PLAYER)))
    a.word(i_add(5, 5, 4))
    a.word(i_mem(LBZ, 0, 5, 0))
    a.word(i_rlwinm(0, 0, 0, 26, 26) | 1)  # rlwinm. r0, r0, 0, 26, 26 (CPU)
    a.branch("bne", "cpu")
    # human: Yes/No, then the menu
    a.word(i_li(3, 2))
    a.word(i_addis(4, 0, MSG_BASE >> 16))
    a.word(i_addi(4, 4, MSG_ASK))
    a.word(i_li(5, SPEAKER))
    a.word(i_li(6, 0))
    a.call(FN_PROMPT)
    a.call(FN_WAIT_MESSAGE)
    a.call(FN_CHOICE)
    a.word(i_cmpwi(3, 0))
    a.branch("bne", "decline")
    a.label("menu")
    a.word(i_li(3, 2))
    a.word(i_addis(4, 0, MSG_BASE >> 16))
    a.word(i_addi(4, 4, MSG_MENU))
    a.word(i_li(5, SPEAKER))
    a.word(i_li(6, 0))
    a.call(FN_PROMPT)
    a.call(FN_WAIT_MESSAGE)
    a.call(FN_CHOICE)
    a.word(i_cmpwi(3, 0))
    a.branch("beq", "free")
    a.word(i_cmpwi(3, 1))
    a.branch("bne", "decline")  # cancelled
    a.word(i_mr(3, 31))
    a.call(FN_COINS)
    a.word(i_cmpwi(3, PAID_COST))
    a.branch("bge", "paid")
    a.word(i_li(3, MSG_NO_COINS))
    a.call(show)
    a.branch("b", "menu")
    a.label("cpu")
    a.word(i_mr(3, 31))
    a.call(FN_COINS)
    a.word(i_cmpwi(3, PAID_COST))
    a.branch("bge", "paid")
    a.label("free")
    a.word(i_li(30, 0))
    a.word(i_li(29, FREE_ORBS))
    a.branch("b", "go")
    a.label("paid")
    a.word(i_mr(3, 31))
    a.word(i_li(4, -PAID_COST))
    a.word(i_li(5, 1))
    a.word(i_li(6, 1))
    a.call(FN_ADD_COINS)
    a.word(i_li(30, 1))
    a.word(i_li(29, PAID_ORBS))
    a.label("go")
    a.word(i_li(3, MSG_LAUNCH))
    a.call(show)
    a.word(i_mr(3, 31))
    a.word(i_mr(4, 29))
    a.call(launch)
    a.word(i_cmpwi(30, 0))
    a.branch("beq", "out")
    # the spare orb, only with a free slot
    a.word(i_mr(3, 31))
    a.call(FN_ORB_MAX)
    a.word(i_mr(29, 3))
    a.word(i_mr(3, 31))
    a.call(FN_ORB_COUNT)
    a.word(i_cmpw(3, 29))
    a.branch("blt", "room")
    a.word(i_li(3, MSG_FULL))
    a.call(show)
    a.branch("b", "out")
    a.label("room")
    a.word(i_li(3, MSG_GOT))
    a.call(show)
    a.word(i_mr(3, 31))
    a.call(luck.CAVE_ORB)  # Faire Square wheel pool: Super 'Shroom / Sluggish / Flutter
    a.branch("b", "out")
    a.label("decline")
    a.word(i_li(3, MSG_DECLINE))
    a.call(show)
    a.label("out")
    a.call(FN_EVENT_END)  # the displaced call
    a.word(0)  # `b EXIT`, filled in below (the exit is outside the cave's label set)
    code = bytearray(a.assemble())
    end = address + len(code) - 4
    struct.pack_into(">I", code, len(code) - 4, encode_branch(end, EXIT))
    if len(code) > CAVE_DATA - CAVE_DAY:
        raise RuntimeError(f"day cave is {len(code):#x} bytes, too big")
    return bytes(code)


def build_data(data):
    """Dummy Final Five host block: +0x40 -> a zero s16 table (+0x60), +0x4C = 0 (single model flag)."""
    block = bytearray(0x80)
    struct.pack_into(">I", block, 0x40, data + 0x60)
    return bytes(block)


NOP = 0x60000000
# (address, expected opcode check, replacement) for the copy; `cmpwi rX,N` sites become `cmpw rX,r16`
CALL_SITES_NOP = (0x80202734, 0x80202774, 0x80202798, 0x802027AC, 0x80202AB4, 0x80202AD8, 0x80202AEC)
CALL_SITE_ONE = 0x80202744  # bl fn_801ECC84 -> li r3,1
COUNT_SITES = {0x80202824: 28, 0x80202844: 28, 0x80202A68: 30}  # address: register compared with the count


def sext(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def build_copy(dol, address):
    start = dol_offset(dol, LAUNCHER)
    length = LAUNCHER_END - LAUNCHER
    words = list(struct.unpack(f">{length // 4}I", dol[start:start + length]))
    for i, word in enumerate(words):
        old = LAUNCHER + 4 * i
        new = address + 4 * i
        opcode = word >> 26
        if opcode == 18 and not word & 2:
            target = old + sext(word & 0x03FFFFFC, 26)
            if not LAUNCHER <= target < LAUNCHER_END:
                words[i] = encode_branch(new, target, bool(word & 1))
        elif opcode == 16 and not word & 2:
            target = old + sext(word & 0xFFFC, 16)
            if not LAUNCHER <= target < LAUNCHER_END:
                raise RuntimeError(f"conditional branch at {old:#x} leaves the routine")
    for site in CALL_SITES_NOP:
        i = (site - LAUNCHER) // 4
        if words[i] >> 26 != 18 or not words[i] & 1:
            raise RuntimeError(f"expected a bl at {site:#x}, found {words[i]:#010x}")
        words[i] = NOP
    i = (CALL_SITE_ONE - LAUNCHER) // 4
    if words[i] >> 26 != 18 or not words[i] & 1:
        raise RuntimeError(f"expected a bl at {CALL_SITE_ONE:#x}")
    words[i] = i_li(3, 1)
    for site, reg in COUNT_SITES.items():
        i = (site - LAUNCHER) // 4
        if words[i] & 0xFFE00000 != 0x2C000000:  # cmpwi cr0, rA, imm
            raise RuntimeError(f"expected a cmpwi at {site:#x}, found {words[i]:#010x}")
        if (words[i] >> 16) & 0x1F != reg:
            raise RuntimeError(f"cmpwi at {site:#x} compares r{(words[i] >> 16) & 0x1F}, expected r{reg}")
        words[i] = i_cmpw(reg, 16)
    return b"".join(struct.pack(">I", w) for w in words)


def patch_dol():
    dol = bytearray(DOL.read_bytes())
    if struct.unpack_from(">I", dol, 0x48 + 4 * SECTION_SLOT)[0] != NEW_BASE:
        raise SystemExit("Run apply_mgtable_move_patch.py first: the old MgDataTbl is only free code space once it is relocated")
    if CAVES_END > DEAD_END or CAVE_SHOW < cb.OUTCOME_END:
        raise RuntimeError("Boo caves overlap the Castaway Bay wheel code or run past the dead MgDataTbl")
    at = dol_offset(dol, luck.CAVE_ORB)
    if not any(dol[at:at + 16]):
        raise SystemExit("Run apply_luck_wheel_rewards_patch.py first: its one-orb routine is missing")
    pieces = {
        CAVE_SHOW: build_show(CAVE_SHOW),
        CAVE_LAUNCH: build_launch(CAVE_LAUNCH, CAVE_COPY, CAVE_DATA),
        CAVE_DAY: build_day(CAVE_DAY, CAVE_SHOW, CAVE_LAUNCH),
        CAVE_DATA: build_data(CAVE_DATA),
        CAVE_COPY: build_copy(dol, CAVE_COPY),
    }
    for address, code in pieces.items():
        position = dol_offset(dol, address)
        dol[position:position + len(code)] = code
    hook = struct.pack(">I", encode_branch(HOOK, CAVE_DAY))
    position = dol_offset(dol, HOOK)
    current = bytes(dol[position:position + 4])
    if current not in (struct.pack(">I", HOOK_WORD), hook):
        raise RuntimeError(f"Unexpected word at {HOOK:#x}: {current.hex()}")
    dol[position:position + 4] = hook
    DOL.write_bytes(dol)
    print(f"Boo day orbs: show {CAVE_SHOW:#x}, launch {CAVE_LAUNCH:#x}, day {CAVE_DAY:#x}, copy {CAVE_COPY:#x} (ends {CAVES_END:#x})")


def patch_messages():
    MESS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in MESS_NAMES:
        chained = MESS_OUTPUT_DIR / name
        source = chained if chained.exists() else MESS_SOURCE_DIR / name
        edited = edit_bank(source.read_bytes(), {}, name, bank=BANK, bank_records=BANK_RECORDS, append=RECORDS, known_tails=())
        (MESS_OUTPUT_DIR / name).write_bytes(edited)
    print(f"Added records {BANK_RECORDS}-{BANK_RECORDS + len(RECORDS) - 1} to bank {BANK:#x}")


def main():
    patch_dol()
    patch_messages()


if __name__ == "__main__":
    main()
