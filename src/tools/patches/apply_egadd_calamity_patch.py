"""E. Gadd's Garage: Calamity Launcher rework (space 43, w02Dll fn_1_13708).

  * Prices: 1-3 orbs free, 4 orbs 10 coins, 5 orbs 20 coins, for every rank. The table lbl_1_data_C64 (w02Dll
    .data +0xC64, 4 rank rows x 5 words) gets 0,0,0,10,20 in each row. The handler's own checks then do the
    rest: the "not enough coins" exit (coins < price[0]) never fires, Set 4/5 are greyed out below 10/20 coins.
  * No coin animation for a free launch: the pay call `bl mbCoinAddDispExec(player, -price, 1, 1)` at .text
    0x13EE4 is retargeted to a 3-word DOL cave (cmpwi r4,0 / beqlr / b mbCoinAddDispExec).
  * CPUs always buy 3 orbs (fewer only when fewer target spaces are free, the largest option the menu enables):
    the first CPU instruction (.text 0x13DA0) branches to 0x13E2C, rewritten as
    li r3,2 / cmpwi r26,3 / bge +8 / addi r3,r26,-1 / nop, followed by the existing
    bl mbComChoiceListDownSet (r26 = number of valid target spaces). The old budget code is skipped.
  * Targets are vanilla (empty spaces, then rivals' orbs, then the launcher's own). An earlier version merged
    the last two groups (.text 0x14040 / 0x140FC); a re-run puts the vanilla words back.
  * Menu text: bank 0x30 record 20 in messdata_eng.bin only ("Set 1-3 Free"; messdata.bin is Japanese, the
    other languages keep their text and show x0).

Run after apply_egadd_wheel_patch.py (it adds bank 0x30 records 27-33 and owns DOL section 16 up to 0x802F8D70).
Idempotent. Not run in Dolphin.
"""
import struct

from tools.patches import apply_castaway_spare_change_patch as spare
from tools.patches import apply_egadd_wheel_patch as egw
from tools.lib.paths import DOL
from tools.lib.dol import dol_offset
from tools.lib.paths import MESS_OUTPUT_DIR, MESS_SOURCE_DIR, REL_DIR
from tools.patches.apply_star_shuffle_bet_patch import edit_bank
from tools.lib.messages import encode
from tools.lib.messages import _bounds
from tools.lib.rel import check_words, retarget_call, text_base

REL_NAME = egw.REL_NAME
DATA_SECTION = 5
PRICE_OFFSET = 0xC64            # lbl_1_data_C64 in .data
VANILLA_PRICES = (10, 30, 60, 100, 150, 10, 25, 50, 80, 120, 10, 20, 40, 60, 90, 5, 15, 30, 50, 75)
PRICES = (0, 0, 0, 10, 20) * 4

FN_COIN_ADD_DISP = 0x8017E03C   # mbCoinAddDispExec(player, amount, 1, 1)
SITE_PAY = 0x13EE4
CAVE_PAY = 0x802F8D70           # section 16, right after the E. Gadd wheel's data
CAVE_END = CAVE_PAY + 0xC
assert egw.USED_END <= CAVE_PAY and CAVE_END <= spare.CODE_END

SITE_CPU = 0x13DA0              # mr r3,r27: the first instruction of the CPU-only block
SITE_CHOICE = 0x13E2C           # ... up to the kept bl mbComChoiceListDownSet at 0x13E40
CPU_OLD = {SITE_CPU: "7F63DB78", 0x13E2C: "7C1ED000", 0x13E30: "4180FFD8", 0x13E34: "2C130000",
           0x13E38: "41800010", 0x13E3C: "7E639B78"}
CPU_NEW = {
    SITE_CPU: 0x48000000 | (SITE_CHOICE - SITE_CPU),  # b 0x13E2C
    0x13E2C: 0x38600002,  # li r3, 2          ("Set 3")
    0x13E30: 0x2C1A0003,  # cmpwi r26, 3      (valid target spaces)
    0x13E34: 0x40800008,  # bge +8
    0x13E38: 0x387AFFFF,  # addi r3, r26, -1  (fewer spaces: the largest enabled option)
    0x13E3C: 0x60000000,  # nop
}

# Targets stay vanilla: (a) empty spaces, then (b) rivals' orbs, then (c) the launcher's own, each group shuffled.
# An earlier version merged (b) and (c) with TARGET_NEW; patch_rel() restores TARGET_OLD.
TARGET_OLD = {0x14040: "40820018",   # bne .L_14058: skip the space when the orb is the launcher's own
              0x140FC: "4080010C"}   # bge .L_14208: the own-orbs pass runs only while fewer than 5 targets
TARGET_NEW = {0x14040: 0x60000000,   # (earlier version) nop: (b) took every occupied valid space
              0x140FC: 0x4800010C}   # (earlier version) b .L_14208: skipped the own-orbs pass

BANK = egw.BANK
BANK_RECORDS = egw.BANK_RECORDS + len(egw.RECORDS)  # 34
MENU_RECORD = 20
MESS_FILES = ("messdata_eng.bin",)
OLD_TEXT = ("The number of Orbs you can", "launch depends on how many", "coins you have!")
NEW_TEXT = ("Launch up to 3 Orbs for free!", "Any more than that will", "cost you!")


def build_cave():
    branch = (FN_COIN_ADD_DISP - (CAVE_PAY + 8)) & 0x03FFFFFC
    return struct.pack(">III", 0x2C040000, 0x4D820020, 0x48000000 | branch)  # cmpwi r4,0 / beqlr / b


def patch_dol():
    dol = bytearray(DOL.read_bytes())
    if struct.unpack_from(">I", dol, 0x48 + 4 * spare.SECTION)[0] != spare.CODE_BASE:
        raise SystemExit("Run apply_castaway_spare_change_patch.py first: its DOL section 16 holds this code")
    code = build_cave()
    at = dol_offset(dol, CAVE_PAY)
    if dol[at:at + len(code)] not in (bytes(len(code)), code):
        raise SystemExit(f"{CAVE_PAY:#x} is not free")
    dol[at:at + len(code)] = code
    DOL.write_bytes(dol)
    print(f"Calamity pay cave at {CAVE_PAY:#x}")


def data_offset(rel):
    table = struct.unpack_from(">I", rel, 0x10)[0]
    offset = struct.unpack_from(">I", rel, table + 8 * DATA_SECTION)[0] & ~1
    if not offset:
        raise RuntimeError("w02Dll has no .data section")
    return offset


def patch_rel():
    path = REL_DIR / REL_NAME
    if not path.exists():
        raise SystemExit("Run apply_egadd_wheel_patch.py first (it writes the chained w02Dll.rel)")
    data = bytearray(path.read_bytes())
    # prices
    at = data_offset(data) + PRICE_OFFSET
    current = struct.unpack_from(">20I", data, at)
    if current not in (VANILLA_PRICES, PRICES):
        raise RuntimeError(f"Unexpected Calamity price table {current}")
    struct.pack_into(">20I", data, at, *PRICES)
    # CPU choice
    text = text_base(data)
    for offset, word in CPU_NEW.items():
        check_words(data, offset, CPU_OLD[offset], f"{word:08X}")
        struct.pack_into(">I", data, text + offset, word)
    for offset, word in TARGET_OLD.items():  # undo the earlier target merge
        check_words(data, offset, word, f"{TARGET_NEW[offset]:08X}")
        struct.pack_into(">I", data, text + offset, int(word, 16))
    # pay call
    check_words(data, SITE_PAY, "48000001")
    retarget_call(data, SITE_PAY, FN_COIN_ADD_DISP, CAVE_PAY)
    path.write_bytes(data)
    print(f"Calamity prices, CPU choice and pay call patched ({REL_NAME})")


def menu_record(original):
    new = original
    for old, text in zip(OLD_TEXT, NEW_TEXT):
        if encode(old) not in new:
            raise RuntimeError(f"Calamity menu: {old!r} not found")
        new = new.replace(encode(old), encode(text), 1)
    for n in (1, 2, 3):
        price = encode(f"Set {n} ") + bytes([0x0E, 0x13, ord("x"), 0x1F, n + 1])
        if price not in new:
            raise RuntimeError(f"Calamity menu: Set {n} price not found")
        new = new.replace(price, encode(f"Set {n} Free"), 1)
    new = new.rstrip(b"\0")
    return new + b"\0" * (4 - len(new) % 4)


def bank_record(data, bank, index):
    _, start, end = _bounds(data, bank)
    count = struct.unpack_from(">I", data, start)[0]
    bounds = [start + 4 + struct.unpack_from(">I", data, start + 4 + 4 * i)[0] for i in range(count)] + [end]
    return bytes(data[bounds[index]:bounds[index + 1]])


def patch_messages():
    for name in MESS_FILES:
        current = MESS_OUTPUT_DIR / name
        if not current.exists():
            raise SystemExit(f"Run apply_egadd_wheel_patch.py first ({current} is missing)")
        new = menu_record(bank_record((MESS_SOURCE_DIR / name).read_bytes(), BANK, MENU_RECORD))
        edited = edit_bank(current.read_bytes(), {MENU_RECORD: new}, name, bank=BANK, bank_records=BANK_RECORDS,
                           append=robots_tail(current.read_bytes()), known_tails=())
        current.write_bytes(edited)
    print(f"Calamity menu (bank {BANK:#x} record {MENU_RECORD}) reworded in {', '.join(MESS_FILES)}")


def robots_tail(data):
    """The robots' records (apply_egadd_robots_patch.py) after the bank's first 34, kept in place."""
    from tools.patches import apply_egadd_robots_patch as robots
    return robots.RECORDS if robots.bank_count(data) == robots.BANK_RECORDS + len(robots.RECORDS) else []


def main():
    patch_dol()
    patch_rel()
    patch_messages()


if __name__ == "__main__":
    main()

