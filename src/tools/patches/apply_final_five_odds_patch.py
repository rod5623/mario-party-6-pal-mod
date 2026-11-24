"""Final Five event odds and rewards: python -m tools.patches.apply_final_five_odds_patch

- Event weights lbl_8026994C (Blue/Red x3, coin bonus, Character Spaces, Bowser Revolution):
  3/3/3/1 becomes 0/1/1/1, so Blue/Red x3 is off and the other three are 1/3 each.
- The coin bonus is 100 instead of 40 (0x802026C0, fn_80202408; the coin-shower visual still
  shows 40 coins).
- 10 Character Spaces instead of 7 (0x80202824, 0x80202844, 0x80202A68 in fn_802026F8).
- Message bank 0x2E (English) records 0x12-0x15, 0x1C, 0x1D, 0x20 and 0x21: the amounts in the text, each
  edit fitting in its record. Edits the current message output, so other patches' text is kept.

Writes main.dol, the .text and .data listings, and files/mess/messdata_eng.bin. No
prerequisites. Idempotent; upgrades the earlier 5-Character-Space version.
"""
import struct

from tools.lib.paths import ASM_TEXT, BUILD, DOL, MESS_OUTPUT, MESS_SOURCE
from tools.lib.dol import dol_offset, patch_asm_instruction, patch_dol_instruction

ASM_DATA_80259D80 = BUILD / "asm" / "auto_07_80259D80_data.s"

# Final Five turns event weights (lbl_8026994C, one word per outcome, 3/3/3/1 originally).
# Order: Blue/Red x3, coin bonus, Character Spaces, Bowser Revolution.
TABLE_ADDRESS = 0x8026994C
OBJECT_NAME = "lbl_8026994C"
OLD_WEIGHTS = (3, 3, 3, 1)
PREVIOUS_WEIGHTS = (0, 3, 3, 1)  # earlier version of this patch
NEW_WEIGHTS = (0, 1, 1, 1)  # Blue/Red disabled; coins, Character Spaces and Revolution are 1/3 each

COIN_BONUS = 100
CHARACTER_SPACES = 10
PREVIOUS_CHARACTER_SPACES = 5  # earlier version of this patch (already in older asm listings / DOLs)
CHARACTER_SPACES_WORD = "ten"  # the Europe English text spells the count out ("five")

# (address, original word, patched word, original asm, patched asm)
CODE_PATCHES = (
    # fn_80202408: coin amount passed to fn_8017DE30 (r28 stays 40 for the coin-shower visual count).
    (0x802026C0, 0x7F84E378, 0x38800000 | COIN_BONUS, "mr r4, r28", f"li r4, 0x{COIN_BONUS:X}"),
    # fn_802026F8: Character Space count and the minimum candidate list padding.
    (0x80202824, 0x2C1C0007, 0x2C1C0000 | CHARACTER_SPACES, "cmpwi r28, 0x7", f"cmpwi r28, 0x{CHARACTER_SPACES:X}"),
    (0x80202844, 0x2C1C0007, 0x2C1C0000 | CHARACTER_SPACES, "cmpwi r28, 0x7", f"cmpwi r28, 0x{CHARACTER_SPACES:X}"),
    (0x80202A68, 0x2C1E0007, 0x2C1E0000 | CHARACTER_SPACES, "cmpwi r30, 0x7", f"cmpwi r30, 0x{CHARACTER_SPACES:X}"),
)

# Message bank 0x2E (English) text edits: (record index, old bytes, new bytes).
MESSAGE_BANK = 0x2E
MESSAGE_EDITS = (
    (0x12, b"40=coin", f"{COIN_BONUS}=coin".encode()),
    (0x13, b"40=coin", f"{COIN_BONUS}=coin".encode()),
    (0x1C, b"\x1040\x10coins", f"\x10{COIN_BONUS}\x10coins".encode()),
    (0x1D, b"\x1040\x10coins", f"\x10{COIN_BONUS}\x10coins".encode()),
    (0x14, b"five\x10", f"{CHARACTER_SPACES_WORD}\x10".encode()),
    (0x15, b"five\x10", f"{CHARACTER_SPACES_WORD}\x10".encode()),
    (0x20, b"five\x10more", f"{CHARACTER_SPACES_WORD}\x10more".encode()),
    (0x21, b"\x1e\x055\x1e\x08\x10more\n    ", f"\x1e\x05{CHARACTER_SPACES}\x1e\x08\x10more\n   ".encode()),
)


def previous_word(old):
    """The instruction as the earlier (5 Character Spaces) version wrote it; coin patch has none."""
    if (old >> 16) in (0x2C1C, 0x2C1E):
        return (old & 0xFFFF0000) | PREVIOUS_CHARACTER_SPACES
    return old


def patch_dol(dol):
    offset = dol_offset(dol, TABLE_ADDRESS)
    current = struct.unpack(">4I", dol[offset:offset + 16])
    if current not in (OLD_WEIGHTS, PREVIOUS_WEIGHTS, NEW_WEIGHTS):
        raise SystemExit(f"Unexpected Final Five weights in DOL: {current}")
    dol[offset:offset + 16] = struct.pack(">4I", *NEW_WEIGHTS)
    for address, old, new, _, _ in CODE_PATCHES:
        for source in (old, previous_word(old)):
            try:
                patch_dol_instruction(dol, address, struct.pack(">I", source), struct.pack(">I", new), f"instruction at {address:08X}")
                break
            except (RuntimeError, SystemExit):
                if source == previous_word(old):
                    raise


def patch_data_asm(text):
    lines = text.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.startswith(f".obj {OBJECT_NAME},"))
    for k, weight in enumerate(NEW_WEIGHTS):
        lines[start + 1 + k] = f"\t.4byte 0x{weight:08X}\n"
    return "".join(lines)


def patch_text_asm(text):
    for address, old, new, old_asm, new_asm in CODE_PATCHES:
        try:
            text = patch_asm_instruction(text, address, struct.pack(">I", old), struct.pack(">I", new), old_asm, new_asm)
        except RuntimeError:
            previous = previous_word(old)
            if previous == old:
                raise
            text = patch_asm_instruction(text, address, struct.pack(">I", previous), struct.pack(">I", new),
                                         old_asm.replace("0x7", f"0x{PREVIOUS_CHARACTER_SPACES:X}"), new_asm)
    return text


def patch_messages(source):
    data = bytearray(source)
    directory = 4 + struct.unpack_from(">I", data, 4 + 4 * MESSAGE_BANK)[0]
    for index, old, new in MESSAGE_EDITS:
        start = directory + 4 + struct.unpack_from(">I", data, directory + 4 + 4 * index)[0]
        end = directory + 4 + struct.unpack_from(">I", data, directory + 4 + 4 * (index + 1))[0]
        record = bytes(data[start:end])
        if old in record:
            patched = record.replace(old, new, 1)
        elif new in record:
            continue
        else:
            raise RuntimeError(f"Final Five message {index:#x} did not match the expected text")
        body = patched.rstrip(b"\0")
        if len(body) + 1 > len(record):
            raise RuntimeError(f"Final Five message {index:#x} does not fit its record")
        data[start:end] = body.ljust(len(record), b"\0")
    return data


def main():
    dol = bytearray(DOL.read_bytes())
    patch_dol(dol)
    data_asm = ASM_DATA_80259D80.read_bytes().decode("utf-8")
    ASM_DATA_80259D80.write_bytes(patch_data_asm(data_asm).encode("utf-8"))
    text_asm = ASM_TEXT.read_bytes().decode("utf-8")
    ASM_TEXT.write_bytes(patch_text_asm(text_asm).encode("utf-8"))
    DOL.write_bytes(dol)

    # Build on the existing output so earlier message patches are kept.
    message_source = MESS_OUTPUT if MESS_OUTPUT.exists() else MESS_SOURCE
    MESS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    MESS_OUTPUT.write_bytes(patch_messages(message_source.read_bytes()))

    print(f"Final Five weights (Blue/Red, coins, Character Spaces, Revolution) = {NEW_WEIGHTS}")
    print(f"Coin bonus = {COIN_BONUS}, Character Spaces = {CHARACTER_SPACES}")
    print(f"Built DOL: {DOL}")
    print(f"English message data: {MESS_OUTPUT}")


if __name__ == "__main__":
    main()
