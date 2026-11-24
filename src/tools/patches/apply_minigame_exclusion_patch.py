"""Keep chosen minigames out of the party-mode pool.

The core picker fn_801F19B8 rejects a table entry if (flag & MG_FLAG_MIC) in its
first pass (0x801F1AF8) and again when topping up from the history ring
(0x801F1C48). Both masks are widened to MG_FLAG_MIC | MG_FLAG_PARTY_EXCLUDE, a
new flag (1 << 12, unused by the game), which is then set on the entries listed
in excluded_minigames.txt. Menus (Minigame Mode, Free Play) never test that bit.

Requires apply_mgtable_move_patch.py (the flag lives in the relocated table).
Run it after apply_battle_ports_patch.py so every entry exists. Safe to re-run:
the flag is cleared on all entries and re-applied from the list each time.
Edits build/GP6P01/main.dol only.
"""
import struct

from tools.lib.paths import DOL
from tools.lib.dol import dol_offset, replace_bytes
from tools.lib.minigames import ENTRY_SIZE, NEW_BASE
from tools.lib.paths import TOOLS

CONFIG = TOOLS / "excluded_minigames.txt"
MG_FLAG_PARTY_EXCLUDE = 1 << 12
MG_FLAG_MIC = 1 << 9
OVL_BASE = 595  # table ovl field = minigame number - 595 (m601 -> 6, m646 -> 51)

# Picker mask sites: rlwinm r0,r0,0,22,22 -> andi. r0,r0,MIC|EXCLUDE
MASK_SITES = (0x801F1AF8, 0x801F1C48)
MASK_ORIGINAL = bytes.fromhex("540005AC")
MASK_PATCHED = struct.pack(">I", 0x70000000 | (MG_FLAG_MIC | MG_FLAG_PARTY_EXCLUDE))

# Entries needed per pick (fn_801F19B8 count) for each type, to warn about tiny pools.
PICK_COUNT = {0: 1, 3: 3, 6: 3}


def parse_config():
    rules = []
    for number, line in enumerate(CONFIG.read_text(encoding="utf-8").splitlines(), 1):
        text = line.split("#", 1)[0].strip().lower()
        if not text:
            continue
        name, _, mg_type = text.partition(":")
        if not (name.startswith("m") and name[1:].isdigit()):
            raise SystemExit(f"{CONFIG.name}:{number}: expected 'm604' or 'm604:3', got {line!r}")
        if mg_type and not mg_type.isdigit():
            raise SystemExit(f"{CONFIG.name}:{number}: bad type in {line!r}")
        rules.append((name, int(name[1:]) - OVL_BASE, int(mg_type) if mg_type else None))
    return rules


def main():
    dol = bytearray(DOL.read_bytes())
    if struct.unpack_from(">I", dol, 0x48 + 4 * 15)[0] != NEW_BASE:
        raise SystemExit("Relocated table not found; run apply_mgtable_move_patch.py first")

    for address in MASK_SITES:
        replace_bytes(dol, dol_offset(dol, address), MASK_ORIGINAL, MASK_PATCHED,
                      f"picker flag mask at {address:08X}")

    base = dol_offset(dol, NEW_BASE)
    entries = []
    while struct.unpack_from(">H", dol, base + len(entries) * ENTRY_SIZE)[0] != 0xFFFF:
        entries.append(base + len(entries) * ENTRY_SIZE)

    for position in entries:
        flag = struct.unpack_from(">H", dol, position + 4)[0]
        struct.pack_into(">H", dol, position + 4, flag & ~MG_FLAG_PARTY_EXCLUDE)

    excluded = set()
    for name, ovl, mg_type in parse_config():
        hits = [i for i, p in enumerate(entries)
                if struct.unpack_from(">H", dol, p)[0] == ovl
                and (mg_type is None or dol[p + 2] == mg_type)]
        if not hits:
            raise SystemExit(f"No table entry matches {name}" + (f":{mg_type}" if mg_type is not None else ""))
        excluded.update(hits)

    for index in sorted(excluded):
        position = entries[index]
        flag = struct.unpack_from(">H", dol, position + 4)[0]
        struct.pack_into(">H", dol, position + 4, flag | MG_FLAG_PARTY_EXCLUDE)
        print(f"  excluded entry {index}: m{struct.unpack_from('>H', dol, position)[0] + OVL_BASE} type {dol[position + 2]}")

    for mg_type, needed in PICK_COUNT.items():
        total = sum(1 for p in entries if dol[p + 2] == mg_type)
        left = sum(1 for i, p in enumerate(entries) if dol[p + 2] == mg_type and i not in excluded)
        if total and left < needed:
            print(f"WARNING: only {left} of {total} type-{mg_type} entries left (a pick needs {needed})")

    DOL.write_bytes(dol)
    print(f"Party pool exclusion applied: {len(excluded)} of {len(entries)} entries excluded")
    print(f"Built DOL: {DOL}")


if __name__ == "__main__":
    main()
