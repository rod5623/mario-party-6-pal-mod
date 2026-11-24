"""Minigame type odds: python -m tools.patches.apply_minigame_odds_patch

- 18% Battle on any roll (vanilla 10%, and only after a 4-Player roll): 0x801EFCC0 (the
  4-Player check becomes a nop) and 0x801EFCCC (the compare).
- Otherwise the type comes from the weight table lbl_80269154: 4-Player / 1v3 / 2v2 =
  80 / 10 / 10 (vanilla 60 / 10 / 30).
- Space colours are ignored (0x801F0650: fn_8018E858 reports "no colour"), so the type is always
  rolled from the table.

Writes main.dol and the .text and .data listings. No prerequisites. Idempotent; upgrades the
earlier weights and Battle chance (PREVIOUS_WEIGHTS, PREVIOUS_BATTLE_CHANCES).
"""
import struct

from tools.lib.paths import ASM_TEXT, DOL
from tools.lib.dol import (
    dol_offset, patch_asm_instruction, patch_dol_instruction, patch_word_table, replace_bytes,
)
from tools.patches.apply_miracle_odds_patch import ASM_DATA_80259D80

# Minigame type weights, indexed by type: 4-Player, 1v3, 2v2 (they sum to 100).
WEIGHT_TABLE = 0x80269154
ORIGINAL_WEIGHTS = [60, 10, 30]
NEW_WEIGHTS = [80, 10, 10]
# Earlier versions of this patch; they are upgraded in place.
PREVIOUS_WEIGHTS = [[20, 0, 80]]
# Battle chance out of 100 (original game: 10).
BATTLE_CHANCE = 18
# Earlier battle chances; they are rolled back to the original compare before re-patching.
PREVIOUS_BATTLE_CHANCES = [20]
# The table object has three more words that fn_801F0618 does not read; they stay untouched.
UNUSED_WEIGHTS = [30, 40, 30]

INSTRUCTION_PATCHES = (
    # fn_801F0618 reads each player's space colour via fn_8018E858. Report "no colour" for everyone
    # so the type is always rolled from the weight table instead of the squares players are on.
    (
        0x801F0650,
        bytes.fromhex("4B F9 E2 09"),
        bytes.fromhex("38 60 00 00"),
        "bl fn_8018E858",
        "li r3, 0x0",
    ),
    # Battle roll: stop requiring that the type rolled was 4-Player.
    (
        0x801EFCC0,
        bytes.fromhex("40 82 00 E4"),
        bytes.fromhex("60 00 00 00"),
        "bne .L_801EFDA4",
        "nop",
    ),
    # Battle roll: random(100) < 10 becomes random(100) < BATTLE_CHANCE.
    (
        0x801EFCCC,
        bytes.fromhex("28 03 00 0A"),
        b"\x28\x03\x00" + bytes([BATTLE_CHANCE]),
        "cmplwi r3, 0xa",
        f"cmplwi r3, {BATTLE_CHANCE:#x}",
    ),
)
BATTLE_COMPARE = 0x801EFCCC


def roll_back_battle_chance(text_asm, dol):
    for chance in PREVIOUS_BATTLE_CHANCES:
        previous = b"\x28\x03\x00" + bytes([chance])
        original = bytes.fromhex("28 03 00 0A")
        offset = dol_offset(dol, BATTLE_COMPARE)
        if bytes(dol[offset:offset + 4]) == previous:
            text_asm = patch_asm_instruction(
                text_asm, BATTLE_COMPARE, previous, original,
                f"cmplwi r3, {chance:#x}", "cmplwi r3, 0xa",
            )
            dol[offset:offset + 4] = original
    return text_asm


def main():
    text_asm = ASM_TEXT.read_bytes().decode("utf-8")
    data_asm = ASM_DATA_80259D80.read_bytes().decode("utf-8")
    dol = bytearray(DOL.read_bytes())
    text_asm = roll_back_battle_chance(text_asm, dol)

    for address, original, patched, old_asm, new_asm in INSTRUCTION_PATCHES:
        text_asm = patch_asm_instruction(
            text_asm, address, original, patched, old_asm, new_asm
        )
        patch_dol_instruction(dol, address, original, patched, f"instruction at {address:08X}")

    offset = dol_offset(dol, WEIGHT_TABLE)
    current = list(struct.unpack_from(">3I", dol, offset))
    source = current if current in PREVIOUS_WEIGHTS else ORIGINAL_WEIGHTS
    data_asm = patch_word_table(
        data_asm,
        ".obj lbl_80269154,",
        ".endobj lbl_80269154",
        source + UNUSED_WEIGHTS,
        NEW_WEIGHTS + UNUSED_WEIGHTS,
    )
    replace_bytes(
        dol,
        offset,
        struct.pack(">3I", *source),
        struct.pack(">3I", *NEW_WEIGHTS),
        "minigame weight table",
    )

    ASM_TEXT.write_bytes(text_asm.encode("utf-8"))
    ASM_DATA_80259D80.write_bytes(data_asm.encode("utf-8"))
    DOL.write_bytes(dol)
    print(
        f"Patched minigame odds: {BATTLE_CHANCE}% Battle (any roll); otherwise "
        "80% 4-Player / 10% 2v2 / 10% 1v3, ignoring space colours"
    )
    print(f"Built DOL: {DOL}")


if __name__ == "__main__":
    main()
