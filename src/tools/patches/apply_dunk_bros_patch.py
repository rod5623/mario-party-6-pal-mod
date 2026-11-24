"""Dunk Bros (m699) becomes a normal 2v2 minigame: python -m tools.patches.apply_dunk_bros_patch

Its MgDataTbl entry (index 81 of the vanilla table at 0x8022FF44): type 5 (last) becomes 2
(2v2), and the flags MG_FLAG_RARE (0x0080) become MG_FLAG_4P (0x0010). Without that the result
goes through the Rare path and the normal 2v2 coins aren't given.

Writes main.dol and build/GP6P01/asm/auto_07_8021AC00_data.s. No prerequisites. It edits the
vanilla table, so it must run before mgtable_move (the STEPS order). Idempotent.
"""
from tools.lib.paths import BUILD, DOL
from tools.lib.dol import dol_offset, replace_bytes

ASM_DATA_ALL = BUILD / "asm" / "auto_07_8021AC00_data.s"

# MgDataTbl entry for m699 ("BASKET", Dunk Bros). Entry layout: u16 ovl, u8 type, pad, u16 flag.
# It is 82nd in the table (index 81, stride 0x7C), so its type byte is at base + 81 * 0x7C + 2.
TABLE_BASE = 0x8022FF44
ENTRY_SIZE = 0x7C
M699_INDEX = 81
TYPE_ADDRESS = TABLE_BASE + M699_INDEX * ENTRY_SIZE + 2
MG_TYPE_LAST = 5
MG_TYPE_2VS2 = 2

# The first two data words of the entry: ovl 0x0057, type, pad, and flags.
# Normal minigames include MG_FLAG_4P (0x0010); Dunk Bros. originally had only
# MG_FLAG_RARE (0x0080), which sends post-game processing through the special
# Rare path and does not award the normal 2v2 coins.
OLD_WORDS = (
    "\t.4byte 0x00570500\n\t.4byte 0x0080FF00\n",
    "\t.4byte 0x00570200\n\t.4byte 0x0080FF00\n",
    "\t.4byte 0x00570200\n\t.4byte 0x0000FF00\n",
)
NEW_WORD = "\t.4byte 0x00570200\n\t.4byte 0x0010FF00\n"


def main():
    dol = bytearray(DOL.read_bytes())
    offset = dol_offset(dol, TYPE_ADDRESS)
    if dol[offset - 2:offset] != bytes.fromhex("0057"):
        raise SystemExit("m699 entry (ovl 0x57) not found at the expected MgDataTbl address")
    if dol[offset] == MG_TYPE_LAST:
        replace_bytes(dol, offset, bytes([MG_TYPE_LAST]), bytes([MG_TYPE_2VS2]), "m699 type")
    elif dol[offset] != MG_TYPE_2VS2:
        raise SystemExit(f"Unexpected m699 type byte: {dol[offset]:#x}")
    current_flags = bytes(dol[offset + 2:offset + 4])
    if current_flags in (bytes.fromhex("0080"), bytes.fromhex("0000")):
        replace_bytes(
            dol,
            offset + 2,
            current_flags,
            bytes.fromhex("0010"),
            "m699 rare flag",
        )
    elif dol[offset + 2:offset + 4] != bytes.fromhex("0010"):
        raise SystemExit(
            f"Unexpected m699 flag bytes: {dol[offset + 2:offset + 4].hex()}"
        )

    text = ASM_DATA_ALL.read_bytes().decode("utf-8")
    old_word = next((word for word in OLD_WORDS if word in text), None)
    if old_word is not None:
        text = text.replace(old_word, NEW_WORD, 1)
    elif NEW_WORD not in text:
        raise SystemExit("m699 MgDataTbl entry not found in data asm")

    ASM_DATA_ALL.write_bytes(text.encode("utf-8"))
    DOL.write_bytes(dol)
    print("Dunk Bros (m699) is now a normal 2v2 game with standard ranking and coin rewards")
    print(f"Built DOL: {DOL}")


if __name__ == "__main__":
    main()
