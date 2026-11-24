"""Bowser Bonus outcomes (first version): python -m tools.patches.apply_bowser_bonus_patch

Superseded by apply_bowser_bonus_fix_patch.py: if the fix is already in the DOL (0x8000362C
holds its bne), this script does nothing. Otherwise it applies the older outcomes: all coins,
two Stars, 30 coins, one Star.

- 0x801BEBA0: the face roll uses 4 faces instead of 5 (li r3,5 -> li r3,4).
- 0x801BEC7C and 0x801BEDA4 call helpers in the init-section cave 0x80003614-0x8000363C.
- Result table lbl_80266B00 and face table lbl_802DD648 (.sdata) are rewritten.
- Message bank 0x3F (BOWSER_MESSAGE_BANK), record 5: "Hand over one of your Stars" becomes
  "Hand over a Star or two". Only this bank is spliced into the current output (write_bank).

Writes main.dol, the .text, .data, .sdata and init listings, and files/mess/messdata_eng.bin.
No prerequisites. Re-running it resets bank 0x3F, so re-run bowser_minigame afterwards.
"""
import struct

from tools.lib.messages import write_bank
from tools.lib.dol import (
    encode_branch, dol_offset, replace_bytes, patch_dol_instruction, patch_asm_instruction,
    patch_asm_word, patch_word_table,
)
from tools.lib.paths import ASM_TEXT, ASM_DATA, ASM_SDATA, ASM_INIT, DOL, MESS_SOURCE, MESS_OUTPUT


BOWSER_MESSAGE_BANK = 0x3F  # only this bank is written, so other patches' text in the file is kept


def patch_message(source):
    data = bytearray(source)
    directory_offset = struct.unpack_from(">I", data, 4 + 4 * 0x3F)[0]
    directory = 4 + directory_offset
    count = struct.unpack_from(">I", data, directory)[0]
    if count <= 6:
        raise RuntimeError(f"Unexpected Bowser message count: {count}")

    start = directory + 4 + struct.unpack_from(">I", data, directory + 4 + 4 * 5)[0]
    end = directory + 4 + struct.unpack_from(">I", data, directory + 4 + 4 * 6)[0]
    record = bytes(data[start:end])
    old_phrase = b"\x10Hand\x0A\x20\x20\x20\x20over\x10one\x10of\x10your\x10Stars"
    new_phrase = b"\x10Hand\x0A\x20\x20\x20\x20over\x10a\x10Star\x10or\x10two"
    if old_phrase in record:
        patched = record.replace(old_phrase, new_phrase, 1)
    elif new_phrase in record:
        return data
    else:
        raise RuntimeError("Bowser Bonus Star message did not match the expected English text")
    if len(patched) > len(record):
        raise RuntimeError("Updated Star message does not fit its original message record")

    data[start:end] = patched.ljust(len(record), b"\0")
    return data


def main():
    text_asm = ASM_TEXT.read_bytes().decode("utf-8")
    data_asm = ASM_DATA.read_bytes().decode("utf-8")
    sdata_asm = ASM_SDATA.read_bytes().decode("utf-8")
    init_asm = ASM_INIT.read_bytes().decode("utf-8")
    dol = bytearray(DOL.read_bytes())

    # apply_bowser_bonus_fix_patch.py supersedes this patch's selector and helpers.
    fix_offset = dol_offset(dol, 0x8000362C)
    if struct.unpack_from(">I", dol, fix_offset)[0] == 0x4082003C:
        print("Bowser Bonus fix patch already applied; nothing to do")
        return

    helper_words = (
        (0x80003614, 0x2C190000, "cmpwi r25, 0x0"),
        (0x80003618, 0x4082000C, "bne .L_80003624"),
        (0x8000361C, 0x3C80003F, "lis r4, 0x3f"),
        (0x80003620, 0x3884000B, "addi r4, r4, 0xb"),
        (0x80003624, encode_branch(0x80003624, 0x8016B36C), "b fn_8016B36C"),
        (0x80003628, 0x2C190001, "cmpwi r25, 0x1"),
        (0x8000362C, 0x4082000C, "bne .L_80003638"),
        (0x80003630, 0x3880FFFE, "li r4, -0x2"),
        (0x80003634, 0x4E800020, "blr"),
        (0x80003638, 0x3880FFFF, "li r4, -0x1"),
        (0x8000363C, 0x4E800020, "blr"),
    )
    for address, word, mnemonic in helper_words:
        init_asm = patch_asm_word(init_asm, address, word, mnemonic)
        patch_dol_instruction(
            dol,
            address,
            b"\0\0\0\0",
            struct.pack(">I", word),
            f"Bowser helper at {address:08X}",
        )

    text_patches = (
        (
            0x801BEBA0,
            bytes.fromhex("38 60 00 05"),
            bytes.fromhex("38 60 00 04"),
            "li r3, 0x5",
            "li r3, 0x4",
        ),
        (
            0x801BEC7C,
            bytes.fromhex("4B FA C6 F1"),
            struct.pack(">I", encode_branch(0x801BEC7C, 0x80003614, link=True)),
            "bl fn_8016B36C",
            "bl 0x80003614",
        ),
        (
            0x801BEDA4,
            bytes.fromhex("38 80 FF FF"),
            struct.pack(">I", encode_branch(0x801BEDA4, 0x80003628, link=True)),
            "li r4, -0x1",
            "bl 0x80003628",
        ),
    )
    for address, original, patched, old_asm, new_asm in text_patches:
        text_asm = patch_asm_instruction(
            text_asm, address, original, patched, old_asm, new_asm
        )
        patch_dol_instruction(dol, address, original, patched, f"instruction at {address:08X}")

    old_results = [5, 10, 20, 30, 0xFFFFFFFF]
    new_results = [999, 0xFFFFFFFE, 20, 30, 0xFFFFFFFF]
    data_asm = patch_word_table(
        data_asm,
        ".obj lbl_80266B00, global",
        ".endobj lbl_80266B00",
        old_results,
        new_results,
    )
    replace_bytes(
        dol,
        dol_offset(dol, 0x80266B00),
        struct.pack(">5I", *old_results),
        struct.pack(">5I", *new_results),
        "Bowser Bonus result table",
    )

    old_choices = bytes.fromhex("00 01 02 03 04 FF 00 00")
    new_choices = bytes.fromhex("00 01 03 04 FF 00 00 00")
    replace_bytes(
        dol,
        dol_offset(dol, 0x802DD648),
        old_choices,
        new_choices,
        "Bowser Bonus selector choices",
    )
    sdata_asm = patch_word_table(
        sdata_asm,
        ".obj lbl_802DD648, global",
        ".endobj lbl_802DD648",
        [0x00010203, 0x04FF0000],
        [0x00010304, 0xFF000000],
    )

    message_data = patch_message(MESS_SOURCE.read_bytes())

    ASM_TEXT.write_bytes(text_asm.encode("utf-8"))
    ASM_DATA.write_bytes(data_asm.encode("utf-8"))
    ASM_SDATA.write_bytes(sdata_asm.encode("utf-8"))
    ASM_INIT.write_bytes(init_asm.encode("utf-8"))
    DOL.write_bytes(dol)
    write_bank(MESS_OUTPUT, MESS_SOURCE, message_data, BOWSER_MESSAGE_BANK)
    print("Patched Bowser Bonus outcomes: all coins, two Stars, 30 coins, one Star")
    print(f"Built DOL: {DOL}")
    print(f"English message data: {MESS_OUTPUT}")


if __name__ == "__main__":
    main()
