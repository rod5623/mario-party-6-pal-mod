"""Move MgDataTbl out of its fixed spot in the DOL so it can grow.

Proof-of-concept step: the table is copied byte-for-byte into a new DOL data
section placed at the vanilla ArenaLo, every reference is retargeted, and
OSSetArenaLo is clamped so the heap starts after the new section. No entries
are added yet. See decompiling/plans/minigame-pools/README.md.

Run this LAST, after every other apply_*_patch.py (Dunk Bros edits the table,
and ninja rebuilds main.dol from asm and would drop this patch).
It rewrites build/GP6P01/main.dol and writes patched copies of every REL that
references the table into build/GP6P01/files/dll/.
"""
import re
import struct

from tools.lib.paths import BUILD, DOL, ROOT
from tools.lib.dol import dol_offset, encode_branch, replace_bytes
from tools.lib.ppc import ha, lo
from tools.lib.minigames import OLD_BASE, ENTRY_SIZE, NEW_BASE, NEW_SIZE, NEW_END, SECTION_SLOT


ARENA_FN = 0x800994B0  # OSSetArenaLo: stw r3, __OSArenaLo; blr
ARENA_CAVE = 0x80004D18  # zero padding in the init section, unused by other patches
STW_ARENA = bytes.fromhex("906D84B0")

DOL_ASM = [
    BUILD / "asm" / "auto_03_80005920_text.s",
    BUILD / "asm" / "auto_03_800EF6C8_text.s",
]
REL_SRC = ROOT / "orig" / "GP6P01" / "files" / "dll"
REL_OUT = BUILD / "files" / "dll"

REF_RE = re.compile(
    r"/\* ([0-9A-F]{8}) [0-9A-F]{8}\s+[0-9A-F ]+\*/\s+(lis|addi)\s.*lbl_8022FF44@(ha|l)\b"
)


def table_size(dol):
    base = dol_offset(dol, OLD_BASE)
    count = 0
    while struct.unpack_from(">H", dol, base + count * ENTRY_SIZE)[0] != 0xFFFF:
        count += 1
        if count > 1000:
            raise RuntimeError("MgDataTbl terminator not found")
    return count, (count + 1) * ENTRY_SIZE


def add_section(dol):
    """Append the relocated table as DOL data section SECTION_SLOT."""
    offset_pos = 4 * SECTION_SLOT
    addr_pos = 0x48 + 4 * SECTION_SLOT
    size_pos = 0x90 + 4 * SECTION_SLOT
    current = struct.unpack_from(">3I", dol, offset_pos)[0], struct.unpack_from(">I", dol, addr_pos)[0], struct.unpack_from(">I", dol, size_pos)[0]
    if current[1] == NEW_BASE:
        if current[2] != NEW_SIZE:
            raise RuntimeError(f"Section {SECTION_SLOT} exists with unexpected size {current[2]:#x}")
        print("DOL section already present; table contents left as they are")
        return
    if any(current):
        raise RuntimeError(f"DOL section slot {SECTION_SLOT} is already in use: {current}")

    count, size = table_size(dol)
    if size > NEW_SIZE:
        raise RuntimeError("Table does not fit the new section")
    table = bytes(dol[dol_offset(dol, OLD_BASE):dol_offset(dol, OLD_BASE) + size])
    while len(dol) % 0x20:
        dol.append(0)
    file_offset = len(dol)
    dol.extend(table + b"\0" * (NEW_SIZE - size))
    struct.pack_into(">I", dol, offset_pos, file_offset)
    struct.pack_into(">I", dol, addr_pos, NEW_BASE)
    struct.pack_into(">I", dol, size_pos, NEW_SIZE)
    print(f"Added DOL section {SECTION_SLOT}: {NEW_BASE:#010x}-{NEW_END:#010x}, {count} entries copied")


def retarget_dol_references(dol):
    refs = []
    for path in DOL_ASM:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = REF_RE.search(line)
            if match:
                refs.append((int(match.group(1), 16), match.group(2), match.group(3)))
    if not refs:
        raise RuntimeError("No lbl_8022FF44 references found in the asm listings")

    for address, mnemonic, part in refs:
        if (mnemonic, part) not in (("lis", "ha"), ("addi", "l")):
            raise RuntimeError(f"Unexpected reference form at {address:08X}: {mnemonic} @{part}")
        position = dol_offset(dol, address) + 2
        old = ha(OLD_BASE) if part == "ha" else lo(OLD_BASE)
        new = ha(NEW_BASE) if part == "ha" else lo(NEW_BASE)
        replace_bytes(dol, position, struct.pack(">H", old), struct.pack(">H", new), f"table reference at {address:08X}")
    print(f"Retargeted {len(refs)} DOL instruction operands")


def patch_arena_clamp(dol):
    """OSSetArenaLo(x) -> store max(x, NEW_END)."""
    cave = [
        0x3C000000 | (NEW_END >> 16),  # lis r0, hi
        0x60000000 | (NEW_END & 0xFFFF),  # ori r0, r0, lo
        0x7C030040,  # cmplw r3, r0
        0x40800008,  # bge +8
        0x7C030378,  # mr r3, r0
        struct.unpack(">I", STW_ARENA)[0],  # stw r3, __OSArenaLo
        0x4E800020,  # blr
    ]
    cave_bytes = b"".join(struct.pack(">I", word) for word in cave)
    cave_position = dol_offset(dol, ARENA_CAVE)
    current = bytes(dol[cave_position:cave_position + len(cave_bytes)])
    hi, low = struct.unpack_from(">2I", current)
    raised = current[8:] == cave_bytes[8:] and hi >> 16 == 0x3C00 and low >> 16 == 0x6000 \
        and ((hi & 0xFFFF) << 16 | (low & 0xFFFF)) > NEW_END  # a later section (apply_castaway_spare_change_patch.py)
    if raised:
        print("OSSetArenaLo clamp already raised past this section; left as it is")
    elif current not in (b"\0" * len(cave_bytes), cave_bytes):
        raise RuntimeError("Arena clamp code cave is not free")
    else:
        dol[cave_position:cave_position + len(cave_bytes)] = cave_bytes
    branch = struct.pack(">I", encode_branch(ARENA_FN, ARENA_CAVE))
    replace_bytes(dol, dol_offset(dol, ARENA_FN), STW_ARENA, branch, "OSSetArenaLo")
    if not raised:
        print(f"OSSetArenaLo now clamps ArenaLo to >= {NEW_END:#010x}")


def patch_rel(data):
    """Retarget module-0 relocations whose addend lies in the old table.

    Returns the number of patched relocations.
    """
    rel_offset, imp_offset, imp_size = struct.unpack_from(">3I", data, 0x24)
    old_end = OLD_BASE + 83 * ENTRY_SIZE
    patched = 0
    for index in range(imp_size // 8):
        module_id, reloc_offset = struct.unpack_from(">II", data, imp_offset + 8 * index)
        if module_id != 0:
            continue
        position = reloc_offset
        while True:
            _, kind, _, addend = struct.unpack_from(">HBBI", data, position)
            if kind == 203:  # R_DOLPHIN_END
                break
            if kind not in (201, 202, 204) and OLD_BASE <= addend < old_end:
                struct.pack_into(">I", data, position + 4, NEW_BASE + (addend - OLD_BASE))
                patched += 1
            position += 8
    return patched


def patch_rels():
    REL_OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for source in sorted(REL_SRC.glob("*.rel")):
        built = REL_OUT / source.name
        data = bytearray((built if built.exists() else source).read_bytes())
        count = patch_rel(data)
        if count:
            built.write_bytes(data)
            total += count
            print(f"  {source.name}: {count} relocations")
    print(f"Patched {total} REL relocations; copy {REL_OUT} over the extracted files\\dll")


def main():
    dol = bytearray(DOL.read_bytes())
    add_section(dol)
    retarget_dol_references(dol)
    patch_arena_clamp(dol)
    DOL.write_bytes(dol)
    patch_rels()
    print(f"Built DOL: {DOL}")


if __name__ == "__main__":
    main()
