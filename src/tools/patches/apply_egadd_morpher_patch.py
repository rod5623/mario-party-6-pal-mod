"""E. Gadd's Garage: Orb Morpher rework (night event on spaces 36/38, w02Dll fn_1_B334).

Vanilla: the machine takes ALL the player's orbs (fn_1_B570 mode 2) and pays their summed sell value in coins
(mode 4, "You get %d coin!"). CPUs always accept; with 0 orbs E. Gadd says "Come again when you have some Orbs!".

Now the reward depends on how many orbs went in (r26 in fn_1_B334 = orbs held on arrival; still all of them):
  * 1 orb:  every other player loses up to 7 coins (what they have) and the player gets the total;
  * 2 orbs: the same, plus +1 Star for the player (game popup);
  * 3+ orbs (team mode can hold 5): every other player who has a Star loses 1 and the player gets them all.
  No coins in the Star case. Lines first, then the coin / Star animations.

How:
  * .text 0xB4F4 `bl fn_1_B570` (mode 4, the coin payout, its only caller) -> module-0 call to CAVE_MORPH. The
    rest (machine motion, the closing line 0x30000B) is unchanged.
  * New DOL data section 17 at 0x802F8DA0 (0x1000 bytes; section 16 is full), OSSetArenaLo clamp raised to its end,
    the same way apply_castaway_spare_change_patch.py added section 16.
  * Calls: E. Gadd's show routine (apply_egadd_wheel_patch.CAVE_SHOW, bank 0x30, speaker 0xE), the Faire wheel's
    Star routine 0x80230220 (player, delta; popup + wait), FN_COINS / FN_ADD_COINS as the spare change guy's steal.
  * Text: bank 0x30 records that can no longer appear are reused (English in every language file): 8 (Shuffle-o-tron
    "No Orbs", unreachable after apply_egadd_shuffle_patch.py), 10 (the old "You get %d coin", shown only by mode 4)
    and 22 (Calamity "not enough coins", unreachable after apply_egadd_calamity_patch.py). Record 9 (the offer) is
    reworded in messdata_eng.bin only.

Run after apply_egadd_shuffle_patch.py (chained w02Dll.rel; records 8 and 22 must be unreachable). Idempotent.
Not run in Dolphin.
"""
import struct

from tools.patches import apply_castaway_spare_change_patch as spare
from tools.patches import apply_egadd_calamity_patch as cal
from tools.patches import apply_egadd_wheel_patch as egw
from tools.patches import apply_mgtable_move_patch as mg
from tools.patches import apply_wheel_of_fortune_patch as wheel
from tools.lib.paths import DOL
from tools.lib.dol import dol_offset
from tools.lib.ppc import epilogue, prologue
from tools.lib.game import FN_ADD_COINS, FN_COINS
from tools.lib.paths import MESS_NAMES, MESS_OUTPUT_DIR, MESS_SOURCE_DIR, REL_DIR
from tools.patches.apply_star_shuffle_bet_patch import edit_bank
from tools.lib.messages import encode, record
from tools.lib.ppc import i_li
from tools.lib.ppc import Asm, i_add, i_addi, i_cmpw, i_cmpwi, i_mr
from tools.lib.game import FN_STARS
from tools.lib.ppc import i_subf
from tools.lib.rel import add_calls, check_words, import_blocks, walk_relocs

REL_NAME = egw.REL_NAME
SITE_PAYOUT = 0xB4F4            # bl fn_1_B570 (mode 4); r3 = player, r26 = orbs held on arrival
PAYOUT_WORD = "4800007D"

SECTION = 17
CODE_BASE = spare.CODE_END      # 0x802F8DA0, right after section 16
CODE_SIZE = 0x1000
CODE_END = CODE_BASE + CODE_SIZE
CAVE_MORPH = CODE_BASE          # 0x200
USED_END = CAVE_MORPH + 0x200

STEAL = 7
PLAYERS = 4
CAVE_STARS = wheel.CAVES["stars"][0]   # (player, delta): Stars with the game's popup
SHOW = egw.CAVE_SHOW            # r3 = record in bank 0x30

BANK = egw.BANK
BANK_RECORDS = cal.BANK_RECORDS  # 34 (27 + the wheel's 7)
MSG_COINS, MSG_STAR, MSG_STARS = 8, 10, 22
INDENT = b"    "
LINES = {
    MSG_COINS: ("Whirr! The Orb Morpher drains", "7 coins from each of your rivals!"),
    MSG_STAR: ("And it spat out a Star", "for you, too!"),
    MSG_STARS: ("Whirr! Let's see which rivals", "have a Star to spare!"),
}
OFFER_OLD = "It can \ntransform Orbs into coins!"
OFFER_NEW = "Feed it \nyour Orbs to rob your rivals!"


def build_morph(address):
    """r3 = player, caller's r26 = orbs given (>= 1). Coins from everyone (1-2 orbs) + a Star (2), or Stars (3+)."""
    a = Asm(address)
    saved = (27, 28, 29, 30, 31)
    prologue(a, 0x30, saved)
    a.word(i_mr(31, 3))
    a.word(i_mr(30, 26))
    a.word(i_cmpwi(30, 3))
    a.branch("bge", "stars")
    # 1-2 orbs: everyone else pays up to STEAL coins
    a.word(i_li(3, MSG_COINS))
    a.call(SHOW)
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
    a.branch("ble", "bonus")
    a.word(i_mr(3, 31))
    a.word(i_mr(4, 29))
    a.word(i_li(5, 1))
    a.word(i_li(6, 1))
    a.call(FN_ADD_COINS)
    a.label("bonus")
    a.word(i_cmpwi(30, 2))
    a.branch("blt", "done")
    a.word(i_li(3, MSG_STAR))
    a.call(SHOW)
    a.word(i_mr(3, 31))
    a.word(i_li(4, 1))
    a.call(CAVE_STARS)
    a.branch("b", "done")
    # 3+ orbs: a Star from everyone else who has one
    a.label("stars")
    a.word(i_li(3, MSG_STARS))
    a.call(SHOW)
    a.word(i_li(29, 0))  # Stars taken
    a.word(i_li(28, 0))
    a.label("star_each")
    a.word(i_cmpw(28, 31))
    a.branch("beq", "star_next")
    a.word(i_mr(3, 28))
    a.call(FN_STARS)
    a.word(i_cmpwi(3, 0))
    a.branch("ble", "star_next")
    a.word(i_mr(3, 28))
    a.word(i_li(4, -1))
    a.call(CAVE_STARS)
    a.word(i_addi(29, 29, 1))
    a.label("star_next")
    a.word(i_addi(28, 28, 1))
    a.word(i_cmpwi(28, PLAYERS))
    a.branch("blt", "star_each")
    a.word(i_cmpwi(29, 0))
    a.branch("ble", "done")
    a.word(i_mr(3, 31))
    a.word(i_mr(4, 29))
    a.call(CAVE_STARS)
    a.label("done")
    epilogue(a, 0x30, saved)
    code = a.assemble()
    if len(code) > USED_END - CAVE_MORPH:
        raise RuntimeError(f"morph cave is {len(code):#x} bytes, too big")
    return code


def add_section(dol):
    """DOL data section 17 at CODE_BASE (zero-filled); the OSSetArenaLo clamp moves up to CODE_END."""
    if struct.unpack_from(">I", dol, 0x48 + 4 * spare.SECTION)[0] != spare.CODE_BASE:
        raise SystemExit("Run apply_castaway_spare_change_patch.py first: section 17 goes right after its section 16")
    offset_pos, addr_pos, size_pos = 4 * SECTION, 0x48 + 4 * SECTION, 0x90 + 4 * SECTION
    current = tuple(struct.unpack_from(">I", dol, p)[0] for p in (offset_pos, addr_pos, size_pos))
    if current[1:] != (CODE_BASE, CODE_SIZE):
        if any(current):
            raise RuntimeError(f"DOL section slot {SECTION} is already in use: {[hex(v) for v in current]}")
        while len(dol) % 0x20:
            dol.append(0)
        struct.pack_into(">I", dol, offset_pos, len(dol))
        struct.pack_into(">I", dol, addr_pos, CODE_BASE)
        struct.pack_into(">I", dol, size_pos, CODE_SIZE)
        dol.extend(b"\0" * CODE_SIZE)
        print(f"Added DOL section {SECTION}: {CODE_BASE:#010x}-{CODE_END:#010x}")
    at = dol_offset(dol, mg.ARENA_CAVE)
    hi, low = struct.unpack_from(">2I", dol, at)
    if hi >> 16 != 0x3C00 or low >> 16 != 0x6000:
        raise RuntimeError("OSSetArenaLo clamp not found: run apply_mgtable_move_patch.py first")
    if ((hi & 0xFFFF) << 16) | (low & 0xFFFF) < CODE_END:
        struct.pack_into(">2I", dol, at, 0x3C000000 | (CODE_END >> 16), 0x60000000 | (CODE_END & 0xFFFF))
        print(f"OSSetArenaLo now clamps ArenaLo to >= {CODE_END:#010x}")


def patch_dol():
    dol = bytearray(DOL.read_bytes())
    for address in (CAVE_STARS, SHOW):
        at = dol_offset(dol, address)
        if not any(dol[at:at + 16]):
            raise SystemExit(f"Run the Faire wheel and E. Gadd wheel scripts first: nothing at {address:#x}")
    add_section(dol)
    code = build_morph(CAVE_MORPH)
    at = dol_offset(dol, CAVE_MORPH)
    region = dol[at:at + USED_END - CAVE_MORPH]
    if any(region) and region[:len(code)] != code and not rel_hooked():
        raise SystemExit(f"{CAVE_MORPH:#x} is not free")
    dol[at:at + USED_END - CAVE_MORPH] = code.ljust(USED_END - CAVE_MORPH, b"\0")
    DOL.write_bytes(dol)
    print(f"Orb Morpher reward code at {CAVE_MORPH:#x} ({len(code):#x} bytes)")


def rel_hooked():
    data = bytearray((REL_DIR / REL_NAME).read_bytes())
    block = import_blocks(data)[0]
    return any(section == 1 and cursor == SITE_PAYOUT and addend == CAVE_MORPH
               for _, section, cursor, _, _, addend in walk_relocs(data, block))


def patch_rel():
    path = REL_DIR / REL_NAME
    if not path.exists():
        raise SystemExit("Run the earlier E. Gadd scripts first (they write the chained w02Dll.rel)")
    data = bytearray(path.read_bytes())
    check_words(data, SITE_PAYOUT, PAYOUT_WORD, "48000001")
    if add_calls(data, [(SITE_PAYOUT, CAVE_MORPH)]):
        path.write_bytes(data)
        print(f"Orb Morpher payout now calls {CAVE_MORPH:#x} ({REL_NAME})")
    else:
        print("Orb Morpher payout already hooked")


def line_record(lines):
    body = (b"\x0a" + INDENT).join(encode(line.replace("'", "\\")) for line in lines)
    return record("00150003", INDENT + body, bytes([0xFF, 0x00]))


def bank_record(data, index):
    return cal.bank_record(data, BANK, index)


def offer_record(original):
    old, new = ((b"\x0a" + INDENT).join(encode(part) for part in t.split("\n")) for t in (OFFER_OLD, OFFER_NEW))
    if old not in original:
        raise RuntimeError("Orb Morpher offer text not found")
    return original.replace(old, new, 1)


def patch_messages():
    for name in MESS_NAMES:
        current = MESS_OUTPUT_DIR / name
        if not current.exists():
            raise SystemExit(f"Run apply_egadd_wheel_patch.py first ({current} is missing)")
        replacements = {index: line_record(lines) for index, lines in LINES.items()}
        if name == "messdata_eng.bin":
            replacements[9] = offer_record(bank_record((MESS_SOURCE_DIR / name).read_bytes(), 9))
        edited = edit_bank(current.read_bytes(), replacements, name, bank=BANK, bank_records=BANK_RECORDS,
                           append=robots_tail(current.read_bytes()), known_tails=())
        current.write_bytes(edited)
    print(f"Orb Morpher lines in bank {BANK:#x} records {sorted(LINES)} (all languages), offer record 9 (English)")


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

