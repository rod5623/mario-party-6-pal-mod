"""Bowser Bonus wheel: python -m tools.patches.apply_bowser_bonus_fix_patch

Wheel slots (faces 5, 10, 20, 30, Star): 5 = all coins, 10 = Bowser gives 100 coins,
20 = 1 Star, 30 = 30 coins, Star = 2 Stars (1 if the player has only one).

- Result table lbl_80266B00 = NEW_RESULTS; face table lbl_802DD648 (.sdata) is set back to the
  five vanilla faces. Every earlier state of both tables (RESULT_STATES, FACE_STATES) is accepted.
- Helpers in the init-section cave: Star count at 0x80003628 (STAR_HELPER), message choice at
  0x80003670 (MESSAGE_HELPER), coin change at 0x800036A0 (GIVE_HELPER). Words that older
  versions used (OLD_CAVE_WORDS, 0x80003614-0x80003624 and 0x800036A4-0x800036DC) are zeroed.
- Hooks at 0x801BEBA0, 0x801BEC68, 0x801BEC7C and 0x801BECFC, among others, call the helpers.
- Message bank 0x3F (English): record 1 loses its last page, record 0x0A becomes "Gimme ALL
  your coins!", and record 0x15 (the generous message) is added, inside the bank's original
  size. Also applies bowser_bonus's record 5 wording. Only this bank is spliced in (write_bank).

Writes main.dol, the .text, .data, .sdata and init listings, and files/mess/messdata_eng.bin.
No prerequisites; if bowser_bonus is also used, this runs after it (the STEPS order). Re-running
it resets bank 0x3F, so re-run bowser_minigame afterwards. Idempotent.
"""
import struct

from tools.lib.messages import write_bank

from tools.lib.paths import ASM_DATA, ASM_INIT, ASM_SDATA, ASM_TEXT, DOL, MESS_OUTPUT, MESS_SOURCE
from tools.patches.apply_bowser_bonus_patch import BOWSER_MESSAGE_BANK, patch_message
from tools.lib.dol import dol_offset, encode_branch, patch_asm_instruction, patch_asm_word, patch_word_table

STAR_HELPER = 0x80003628
MESSAGE_HELPER = 0x80003670
GIVE_HELPER = 0x800036A0

# Code-cave words written by earlier versions of these patches that are no longer used.
OLD_CAVE_WORDS = list(range(0x80003614, 0x80003628, 4)) + list(range(0x800036A4, 0x800036E0, 4))

# Wheel slots (the wheel always has the faces 5, 10, 20, 30, Star):
#   0 (5)    all coins          3 (30)   30 coins
#   1 (10)   give 100 coins     4 (Star) 2 Stars (1 if the player has only 1)
#   2 (20)   1 Star
NEW_RESULTS = [999, 100, 0xFFFFFFFF, 30, 0xFFFFFFFE]
RESULT_STATES = (
    [5, 10, 20, 30, 0xFFFFFFFF],
    [999, 0xFFFFFFFE, 20, 30, 0xFFFFFFFF],
    [999, 0xFFFFFFFE, 30, 0xFFFFFFFF, 0xFFFFFFFF],
    [999, 0xFFFFFFFD, 0xFFFFFFFF, 30, 0xFFFFFFFE],
    NEW_RESULTS,
)
ORIGINAL_FACES = bytes.fromhex("00 01 02 03 04 FF 00 00")
FACE_STATES = (
    bytes.fromhex("00 01 03 04 FF 00 00 00"),
    bytes.fromhex("00 04 03 04 FF 00 00 00"),
)

ALL_COINS_MESSAGE = 0x0A
GENEROUS_MESSAGE = 0x15


def star_helper():
    # Returns r4 = Stars to take: -2 for the Star face (slot 4) if the player
    # has at least two Stars, otherwise -1.
    base = STAR_HELPER
    return (
        (0x2C190004, "cmpwi r25, 0x4"),
        (0x4082003C, "bne .L_80003668"),
        (0x9421FFE0, "stwu r1, -0x20(r1)"),
        (0x7C0802A6, "mflr r0"),
        (0x90010024, "stw r0, 0x24(r1)"),
        (0x90610008, "stw r3, 0x8(r1)"),
        (encode_branch(base + 0x18, 0x8015CE98, link=True), "bl fn_8015CE98"),
        (0x2C030002, "cmpwi r3, 0x2"),
        (0x80610008, "lwz r3, 0x8(r1)"),
        (0x80010024, "lwz r0, 0x24(r1)"),
        (0x7C0803A6, "mtlr r0"),
        (0x38210020, "addi r1, r1, 0x20"),
        (0x3880FFFE, "li r4, -0x2"),
        (0x4C800020, "bgelr"),
        (0x3880FFFF, "li r4, -0x1"),
        (0x4E800020, "blr"),
        (0x3880FFFF, "li r4, -0x1"),
        (0x4E800020, "blr"),
    )


def message_helper():
    # Replaces the coin message call: slot 0 shows the "all your coins" message,
    # slot 1 the generous message, other slots keep "Fork over N coins".
    base = MESSAGE_HELPER
    return (
        (0x2C190000, "cmpwi r25, 0x0"),
        (0x40820010, "bne .L_80003684"),
        (0x3C80003F, "lis r4, 0x3f"),
        (0x38840000 | ALL_COINS_MESSAGE, f"addi r4, r4, {ALL_COINS_MESSAGE:#x}"),
        (encode_branch(base + 0x10, 0x8016B36C), "b fn_8016B36C"),
        (0x2C190001, "cmpwi r25, 0x1"),
        (0x40820010, "bne .L_80003698"),
        (0x3C80003F, "lis r4, 0x3f"),
        (0x38840000 | GENEROUS_MESSAGE, f"addi r4, r4, {GENEROUS_MESSAGE:#x}"),
        (encode_branch(base + 0x24, 0x8016B36C), "b fn_8016B36C"),
        (encode_branch(base + 0x28, 0x8016B36C), "b fn_8016B36C"),
    )


def give_helper():
    # Replaces the coin change call: slot 1 gives 100 coins instead of taking some.
    base = GIVE_HELPER
    return (
        (0x2C190001, "cmpwi r25, 0x1"),
        (0x4082000C, "bne .L_800036B0"),
        (0x38800064, "li r4, 0x64"),
        (0x38A00064, "li r5, 0x64"),
        (encode_branch(base + 0x10, 0x8017DE30), "b fn_8017DE30"),
    )


def build_messages():
    data = bytearray(patch_message(MESS_SOURCE.read_bytes()))
    base = 4 + struct.unpack_from(">I", data, 4 + 4 * 0x3F)[0]
    end = 4 + struct.unpack_from(">I", data, 4 + 4 * 0x40)[0]
    count = struct.unpack_from(">I", data, base)[0]
    if count != 21:
        raise RuntimeError(f"Unexpected Bowser message count: {count}")
    table = base + 4
    offsets = [struct.unpack_from(">I", data, table + 4 * i)[0] for i in range(count)]
    bounds = [table + offset for offset in offsets] + [end]
    records = [bytes(data[bounds[i]:bounds[i + 1]]) for i in range(count)]

    def pad(record):
        return record + b"\0" * (-len(record) % 4)

    # The last page of the "no coins" message is cut to make room for a new record.
    marker = b"\n    Oooh\x82\x10I\\m"
    records[1] = pad(records[1][:records[1].index(marker)] + b"\0")
    records[ALL_COINS_MESSAGE] = pad(
        b"\x00\x15\x00\x03    Gimme\x10ALL\x10your\x10coins\xc2\xff\0"
    )
    if len(records[ALL_COINS_MESSAGE]) > bounds[ALL_COINS_MESSAGE + 1] - bounds[ALL_COINS_MESSAGE]:
        raise RuntimeError("All-coins message does not fit")
    records.append(pad(
        b"\x00\x15\x00\x03    Wow\x10pal\x82\x10my\x10scratcher\x10\n"
        b"    paid\x10off\x85\x10I\x10feel\x10generous\xc2\xff\0"
    ))

    table_size = 4 + 4 * len(records)
    position = table_size
    new_offsets = []
    for record in records:
        new_offsets.append(position - 4)
        position += len(record)
    if position > end - base:
        raise RuntimeError("Bowser messages do not fit in their original block")
    block = struct.pack(">I", len(records)) + struct.pack(f">{len(records)}I", *new_offsets)
    block += b"".join(records)
    block += b"\0" * (end - base - len(block))
    data[base:end] = block
    return data


def patch_text(text, dol, address, candidates, patched, new_asm):
    # candidates are (bytes, asm) pairs for every earlier form of this instruction.
    for original, old_asm in candidates:
        try:
            text = patch_asm_instruction(text, address, original, patched, old_asm, new_asm)
            break
        except RuntimeError:
            continue
    else:
        raise RuntimeError(f"Unexpected assembly at {address:08X}")
    offset = dol_offset(dol, address)
    current = bytes(dol[offset:offset + 4])
    if current not in [original for original, _ in candidates] + [patched]:
        raise RuntimeError(f"Unexpected DOL bytes at {address:08X}: {current.hex(' ')}")
    dol[offset:offset + 4] = patched
    return text


def main():
    text_asm = ASM_TEXT.read_bytes().decode("utf-8")
    data_asm = ASM_DATA.read_bytes().decode("utf-8")
    sdata_asm = ASM_SDATA.read_bytes().decode("utf-8")
    init_asm = ASM_INIT.read_bytes().decode("utf-8")
    dol = bytearray(DOL.read_bytes())

    for address in OLD_CAVE_WORDS:
        init_asm = patch_asm_word(init_asm, address, 0, "invalid", allowed=None)
        offset = dol_offset(dol, address)
        dol[offset:offset + 4] = b"\0\0\0\0"
    for base, words in (
        (STAR_HELPER, star_helper()),
        (MESSAGE_HELPER, message_helper()),
        (GIVE_HELPER, give_helper()),
    ):
        for index, (word, mnemonic) in enumerate(words):
            address = base + 4 * index
            init_asm = patch_asm_word(init_asm, address, word, mnemonic, allowed=None)
            offset = dol_offset(dol, address)
            dol[offset:offset + 4] = struct.pack(">I", word)

    def bl(address, target):
        return struct.pack(">I", encode_branch(address, target, link=True))

    text_asm = patch_text(
        text_asm, dol, 0x801BEBA0,
        [(bytes.fromhex("38 60 00 04"), "li r3, 0x4")],
        bytes.fromhex("38 60 00 05"), "li r3, 0x5",
    )
    text_asm = patch_text(
        text_asm, dol, 0x801BEC68,
        [(bl(0x801BEC68, 0x80003670), "bl 0x80003670")],
        bytes.fromhex("4B F3 38 89"), "bl fn_800F24F0",
    )
    text_asm = patch_text(
        text_asm, dol, 0x801BEC7C,
        [
            (bytes.fromhex("4B FA C6 F1"), "bl fn_8016B36C"),
            (bl(0x801BEC7C, 0x80003614), "bl 0x80003614"),
        ],
        bl(0x801BEC7C, MESSAGE_HELPER), f"bl 0x{MESSAGE_HELPER:08X}",
    )
    text_asm = patch_text(
        text_asm, dol, 0x801BECFC,
        [(bytes.fromhex("4B FB F1 35"), "bl fn_8017DE30")],
        bl(0x801BECFC, GIVE_HELPER), f"bl 0x{GIVE_HELPER:08X}",
    )
    text_asm = patch_text(
        text_asm, dol, 0x801BED1C,
        [(struct.pack(">I", encode_branch(0x801BED1C, 0x800036C0)), "b 0x800036C0")],
        bytes.fromhex("38 60 00 02"), "li r3, 0x2",
    )

    for state in RESULT_STATES:
        try:
            data_asm = patch_word_table(
                data_asm, ".obj lbl_80266B00, global", ".endobj lbl_80266B00", state, NEW_RESULTS
            )
            break
        except RuntimeError:
            continue
    else:
        raise RuntimeError("Unexpected Bowser Bonus result table")
    result_offset = dol_offset(dol, 0x80266B00)
    dol[result_offset:result_offset + 20] = struct.pack(">5I", *NEW_RESULTS)

    face_offset = dol_offset(dol, 0x802DD648)
    current_faces = bytes(dol[face_offset:face_offset + 8])
    if current_faces not in (ORIGINAL_FACES, *FACE_STATES):
        raise RuntimeError(f"Unexpected Bowser Bonus faces: {current_faces.hex(' ')}")
    dol[face_offset:face_offset + 8] = ORIGINAL_FACES
    for state in ([0x00010304, 0xFF000000], [0x00040304, 0xFF000000], [0x00010203, 0x04FF0000]):
        try:
            sdata_asm = patch_word_table(
                sdata_asm,
                ".obj lbl_802DD648, global",
                ".endobj lbl_802DD648",
                state,
                [0x00010203, 0x04FF0000],
            )
            break
        except RuntimeError:
            continue
    else:
        raise RuntimeError("Unexpected Bowser Bonus face table")

    messages = build_messages()
    ASM_TEXT.write_bytes(text_asm.encode("utf-8"))
    ASM_DATA.write_bytes(data_asm.encode("utf-8"))
    ASM_SDATA.write_bytes(sdata_asm.encode("utf-8"))
    ASM_INIT.write_bytes(init_asm.encode("utf-8"))
    DOL.write_bytes(dol)
    write_bank(MESS_OUTPUT, MESS_SOURCE, messages, BOWSER_MESSAGE_BANK)
    print("Patched Bowser Bonus: 5=all coins, 10=+100 coins, 20=1 Star, 30=30 coins, Star=2 Stars")


if __name__ == "__main__":
    main()
