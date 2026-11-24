"""Bowser space: 50% Bonus / 50% Mini-Game, with a Star penalty: python -m tools.patches.apply_bowser_minigame_patch

- 0x801BE69C: the Bonus roll compares against 0.5 (lbl_802E1B98) instead of 0.3.
- The Mini-Game penalty is random(3) + 1, an even split of all coins (1), all Orbs (2) and one
  Star (3) (0x801BEE70, 0x801BEE74). The Star penalty reuses the Orb-removal path and takes one
  Star from each loser who has one, in the first round only.
- If the roll picks the Star penalty and nobody has a Star, Bowser says so and the penalty
  becomes all coins (hook at 0x801BEE78).
- Announcements read lbl_80266B20, which has the extra Star slot (0x801BEEF0); its Star entry is
  set to the new fragment message.
- Code cave 0x80004918-0x800049E4 in the init section (zero padding nothing else uses). Hooks at
  0x801BF234, 0x801BF438 (coin/Star count), 0x801BF7E4, 0x801BFA1C (take) and 0x801BF5EC
  ("nobody has any" message).
- Message bank 0x3F (English): appends three records (Star fragment, nobody has a Star, swap to
  coins) after the records already there, reading the current output.

Writes main.dol, the .text, .data and init listings, and files/mess/messdata_eng.bin.
Runs after bowser_bonus / bowser_bonus_fix, which reset bank 0x3F: re-run this after either.
Idempotent; completes a partial earlier append.
"""
import struct

from tools.lib.paths import ASM_DATA, ASM_INIT, ASM_TEXT, DOL, MESS_OUTPUT, MESS_SOURCE
from tools.lib.dol import (
    dol_offset, encode_branch, patch_asm_instruction, patch_asm_word, patch_dol_instruction,
)
from tools.patches.apply_bowser_bonus_fix_patch import patch_text
from tools.patches.apply_dk_bonus_patch import assemble, branch, cmpwi, cond, li, mflr, mr, mtlr
from tools.lib.messages import append_records

# Penalty types stored in lbl_802DA8E0+8 by the Mini-Game roll: 1 = all coins,
# 2 = all Orbs, 3 = one Star (the Orb-removal path is reused for it).
STAR_PENALTY = 3
MESSAGE_BANK = 0x3F

# Zero padding in the init section that no other patch uses.
CAVE = 0x80004918
CAVE_END = 0x800049E4

FN_COIN_GET = 0x8015C770
FN_STAR_GET = 0x8015CE98
FN_STAR_ADD = 0x8015CF64
FN_ORB_REMOVE = 0x8015D8A4
FN_MESSAGE = 0x8016B36C
FN_MESSAGE_WAIT = 0x8016C7D8

PENALTY_NAMES = 0x80266B20  # lbl_80266B20: message ids shown for each penalty type
PENALTY_NAMES_STAR_SLOT = PENALTY_NAMES + 4 * STAR_PENALTY
PENALTY_NAMES_VANILLA = [0x003F000A, 0x003F000B, 0x003F000C]

STAR_FRAGMENT = (  # "The losers this time must <fragment>"
    b"\x00\x15\x00\x01hand\x10over\x10a\x10Star\x00\x00\x00\x00"
)
STAR_NOBODY = (
    b"\x00\x15\x00\x03    None\x10of\x10you\x10little\x10twerps\x10has\x10a\n"
    b"    Star\xc2\xc3\x10But\x10I\x10wanted\x10to\x10steal\n"
    b"    one\xc2\x10Grrrr\x85\x85\x85\xff\x00\x00"
)
STAR_SWAP = (  # shown at the roll when nobody has a Star; the penalty becomes coins
    b"\x00\x15\x00\x03    Nobody\x10has\x10a\x10Star\xc3\x10Hah\x82\x10then\x10I\n"
    b"    guess\x10I\\ll\x10take\x10your\x10coins\x10instead\xc2\xff\x00"
)
NEW_RECORDS = [record + b"\0" * (-len(record) % 4) for record in (STAR_FRAGMENT, STAR_NOBODY, STAR_SWAP)]

PATCHES = (
    # The Bonus roll is "random float < 0.3"; compare against 0.5 instead.
    # lbl_802E1BFC is shared with other code, so point this load at the 0.5 constant lbl_802E1B98.
    (
        0x801BE69C,
        bytes.fromhex("C0 02 B2 5C"),
        bytes.fromhex("C0 02 B1 F8"),
        "lfs f0, lbl_802E1BFC@sda21(r0)",
        "lfs f0, lbl_802E1B98@sda21(r0)",
    ),
    # The Mini-Game penalty is random(3) + 1: an even split between all coins (1),
    # all Orbs (2) and one Star (3). Vanilla was random(3) with 0 = half coins.
    (
        0x801BEE70,
        bytes.fromhex("38 60 00 02"),
        bytes.fromhex("38 60 00 03"),
        "li r3, 0x2",
        "li r3, 0x3",
    ),
    # Restores the random call removed by the earlier version of this patch.
    (
        0x801BEE74,
        bytes.fromhex("38 60 00 01"),
        bytes.fromhex("4B F8 DF 05"),
        "li r3, 0x1",
        "bl fn_8014CD78",
    ),
    # The announcement message is looked up by penalty type; read the table that
    # has the extra Star slot (lbl_80266B20, same first three entries as lbl_80266B14).
    (
        0x801BEEF0,
        bytes.fromhex("38 03 6B 14"),
        bytes.fromhex("38 03 6B 20"),
        "addi r0, r3, lbl_80266B14@l",
        "addi r0, r3, lbl_80266B20@l",
    ),
)


def bnelr():
    return "bnelr", 0x4C820020


def blelr():
    return "blelr", 0x4C810020


def cave_code(nobody_message, swap_message):
    return [
        # Coin / Star count for the "does any loser have something to take" checks.
        ("label", "amount"), cmpwi(25, STAR_PENALTY), cond("bne", "coins"),
        branch(FN_STAR_GET),
        ("label", "coins"), branch(FN_COIN_GET),
        # "Nobody has any <coins/Orbs/Stars>" message id.
        ("label", "nobody"), ("addi r4, r4, 0x10", 0x38840010), cmpwi(25, STAR_PENALTY), bnelr(),
        ("addi r4, r4, %#x" % (nobody_message - 0x10), 0x38840000 | nobody_message - 0x10),
        ("blr", 0x4E800020),
        # Replaces the Orb removal call (r3 = player, r31 = round): Star penalty takes
        # one Star in the first round only, if the player has one.
        ("label", "take"), cmpwi(25, STAR_PENALTY), cond("bne", "orb"),
        cmpwi(31, 0), bnelr(), mflr(24), mr(20, 3),
        branch(FN_STAR_GET, link=True), mtlr(24), cmpwi(3, 0), blelr(),
        mr(3, 20), li(4, -1), branch(FN_STAR_ADD),
        ("label", "orb"), branch(FN_ORB_REMOVE),
        # Replaces `mr r21, r3` after the penalty roll. If it picked the Star penalty and
        # no player has a Star, Bowser says so and the penalty becomes all coins.
        ("label", "roll"), ("addi r21, r3, 0x1", 0x3AA30001), cmpwi(21, STAR_PENALTY), bnelr(),
        ("stwu r1, -0x20(r1)", 0x9421FFE0), mflr(0),
        ("stw r0, 0x24(r1)", 0x90010024), ("stw r31, 0x1c(r1)", 0x93E1001C), li(31, 0),
        ("label", "scan"), mr(3, 31), branch(FN_STAR_GET, link=True), cmpwi(3, 0), cond("bne", "keep"),
        ("addi r31, r31, 0x1", 0x3BFF0001), cmpwi(31, 3), cond("ble", "scan"),
        li(3, 2), ("lis r4, 0x3f", 0x3C80003F),
        ("addi r4, r4, %#x" % swap_message, 0x38840000 | swap_message), li(5, 0xD),
        branch(FN_MESSAGE, link=True), branch(FN_MESSAGE_WAIT, link=True), li(21, 1),
        ("label", "keep"), ("lwz r31, 0x1c(r1)", 0x83E1001C), ("lwz r0, 0x24(r1)", 0x80010024),
        mtlr(0), ("addi r1, r1, 0x20", 0x38210020), ("blr", 0x4E800020),
    ]


def build_messages():
    source = MESS_OUTPUT if MESS_OUTPUT.exists() else MESS_SOURCE
    data = source.read_bytes()
    section = 4 + struct.unpack_from(">I", data, 4 + 4 * MESSAGE_BANK)[0]
    count = struct.unpack_from(">I", data, section)[0]
    offsets = [struct.unpack_from(">I", data, section + 4 + 4 * i)[0] for i in range(count)]
    next_section = 4 + struct.unpack_from(">I", data, 4 + 4 * (MESSAGE_BANK + 1))[0]
    bounds = [section + 4 + offset for offset in offsets] + [next_section]
    records = [data[bounds[i]:bounds[i + 1]] for i in range(count)]
    # Earlier runs may have appended only the first few of the records.
    present = max(
        (k for k in range(len(NEW_RECORDS) + 1) if k == 0 or records[count - k:] == NEW_RECORDS[:k]),
    )
    first = count - present
    if present == len(NEW_RECORDS):
        return data, first
    return append_records(data, {MESSAGE_BANK: (count, NEW_RECORDS[present:])}, "Bowser Mini-Game"), first


def patch_penalty_names(data_asm, message_id):
    marker = ".obj lbl_80266B20, global"
    start = data_asm.index(marker)
    end = data_asm.index(".endobj lbl_80266B20", start)
    lines = data_asm[start:end].splitlines(keepends=True)
    words = [i for i, line in enumerate(lines) if line.strip().startswith(".4byte")]
    if len(words) != 4:
        raise RuntimeError("Unexpected lbl_80266B20 layout")
    lines[words[STAR_PENALTY]] = lines[words[STAR_PENALTY]].split("0x")[0] + f"0x{message_id:08X}\n"
    return data_asm[:start] + "".join(lines) + data_asm[end:]


def main():
    text_asm = ASM_TEXT.read_bytes().decode("utf-8")
    data_asm = ASM_DATA.read_bytes().decode("utf-8")
    init_asm = ASM_INIT.read_bytes().decode("utf-8")
    dol = bytearray(DOL.read_bytes())

    messages, fragment_index = build_messages()
    nobody_index = fragment_index + 1
    swap_index = fragment_index + 2
    fragment_id = MESSAGE_BANK << 16 | fragment_index

    words, labels = assemble(CAVE, cave_code(nobody_index, swap_index), CAVE_END)
    for address in range(CAVE, CAVE_END, 4):
        word, mnemonic = {a: (w, t) for a, w, t in words}.get(address, (0, "invalid"))
        init_asm = patch_asm_word(init_asm, address, word, mnemonic, allowed=None)
        struct.pack_into(">I", dol, dol_offset(dol, address), word)

    def bl(address, target):
        return struct.pack(">I", encode_branch(address, target, link=True))

    hooks = []
    for address, vanilla_target in (
        (0x801BF234, FN_COIN_GET),
        (0x801BF438, FN_COIN_GET),
        (0x801BF7E4, FN_ORB_REMOVE),
        (0x801BFA1C, FN_ORB_REMOVE),
    ):
        target = labels["amount"] if vanilla_target == FN_COIN_GET else labels["take"]
        hooks.append((
            address, bl(address, vanilla_target), bl(address, target),
            f"bl fn_{vanilla_target:08X}", f"bl 0x{target:08X}",
        ))
    hooks.append((
        0x801BF5EC, bytes.fromhex("38 84 00 10"), bl(0x801BF5EC, labels["nobody"]),
        "addi r4, r4, 0x10", f"bl 0x{labels['nobody']:08X}",
    ))

    for address, original, patched, old_asm, new_asm in PATCHES + tuple(hooks):
        text_asm = patch_asm_instruction(
            text_asm, address, original, patched, old_asm, new_asm
        )
        patch_dol_instruction(dol, address, original, patched, f"instruction at {address:08X}")

    text_asm = patch_text(
        text_asm, dol, 0x801BEE78,
        [
            (bytes.fromhex("7C 75 1B 78"), "mr r21, r3"),
            (bytes.fromhex("3A A3 00 01"), "addi r21, r3, 0x1"),
        ],
        bl(0x801BEE78, labels["roll"]), f"bl 0x{labels['roll']:08X}",
    )

    data_asm = patch_penalty_names(data_asm, fragment_id)
    struct.pack_into(">I", dol, dol_offset(dol, PENALTY_NAMES_STAR_SLOT), fragment_id)

    ASM_TEXT.write_bytes(text_asm.encode("utf-8"))
    ASM_DATA.write_bytes(data_asm.encode("utf-8"))
    ASM_INIT.write_bytes(init_asm.encode("utf-8"))
    DOL.write_bytes(dol)
    MESS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    MESS_OUTPUT.write_bytes(messages)
    print("Patched Bowser space: 50% Bonus / 50% Mini-Game; Mini-Game is an even split of all coins, all Orbs or 1 Star")
    print(f"Built DOL: {DOL}")
    print(f"Built English message file: {MESS_OUTPUT}")


if __name__ == "__main__":
    main()
