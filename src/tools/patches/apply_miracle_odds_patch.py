"""Round of Miracles outcome odds: python -m tools.patches.apply_miracle_odds_patch

The three outcome pools (one per game-progress tier) at 0x802666A0, 0x80266720 and 0x802667A0,
32 words each and -1 terminated, all get the same 20-entry pool: 5% 20 coins, 25% coins swap,
10% 1 Star, 10% 2 Stars, 25% Stars swap, 25% coins and Stars swap.

Writes main.dol and the .data listing (auto_07_80259D80_data.s, object lbl_80266687). The pools
are overwritten without checking their current contents. No prerequisites. Idempotent.
"""
import re
import struct

from tools.lib.paths import BUILD, DOL
from tools.lib.dol import dol_offset

ASM_DATA_80259D80 = BUILD / "asm" / "auto_07_80259D80_data.s"

# Round of Miracles outcome pools (one per game-progress tier), 32 words each, -1 terminated.
# Outcome IDs: 0 = 20 coins ->, 1 = coins <->, 2 = 1 Star ->, 3 = 2 Stars ->,
# 4 = Stars <->, 5 = coins and Stars <->.
POOL_ADDRESSES = (0x802666A0, 0x80266720, 0x802667A0)
POOL_WORDS = 32
# 20 entries: 5% 20 coins, 25% coins <->, 10% 1 Star, 10% 2 Stars, 25% Stars <->, 25% both <->.
NEW_POOL = [1, 4, 5, 1, 4, 5, 2, 3, 1, 4, 5, 0, 1, 4, 5, 3, 2, 1, 4, 5]
NEW_WORDS = NEW_POOL + [-1] + [0] * (POOL_WORDS - len(NEW_POOL) - 1)
NEW_BYTES = struct.pack(">32i", *NEW_WORDS)

# The generated asm stores this region as one unaligned object starting here.
OBJECT_NAME = "lbl_80266687"
OBJECT_ADDRESS = 0x80266687


def patch_dol(dol):
    for address in POOL_ADDRESSES:
        offset = dol_offset(dol, address)
        dol[offset:offset + len(NEW_BYTES)] = NEW_BYTES


def patch_asm(text):
    lines = text.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.startswith(f".obj {OBJECT_NAME},"))
    end = next(i for i in range(start, len(lines)) if lines[i].startswith(f".endobj {OBJECT_NAME}"))

    data_lines = [i for i in range(start + 1, end) if re.match(r"\t\.(4byte|byte) 0x", lines[i])]
    data = bytearray()
    for i in data_lines:
        value = int(lines[i].split()[1], 16)
        data += value.to_bytes(4 if ".4byte" in lines[i] else 1, "big")

    for address in POOL_ADDRESSES:
        offset = address - OBJECT_ADDRESS
        data[offset:offset + len(NEW_BYTES)] = NEW_BYTES

    position = 0
    for i in data_lines:
        if ".4byte" in lines[i]:
            lines[i] = f"\t.4byte 0x{int.from_bytes(data[position:position + 4], 'big'):08X}\n"
            position += 4
        else:
            lines[i] = f"\t.byte 0x{data[position]:02X}\n"
            position += 1
    return "".join(lines)


def main():
    dol = bytearray(DOL.read_bytes())
    patch_dol(dol)
    asm = ASM_DATA_80259D80.read_bytes().decode("utf-8")
    ASM_DATA_80259D80.write_bytes(patch_asm(asm).encode("utf-8"))
    DOL.write_bytes(dol)
    print("Patched Round of Miracles: 5% 20 coins, 25% coins swap, 10% 1 Star, 10% 2 Stars, 25% Stars swap, 25% coins+Stars swap (all tiers)")
    print(f"Built DOL: {DOL}")


if __name__ == "__main__":
    main()
