"""Make the CPU one difficulty level weaker in What Goes Up (m604) and Sunday Drivers (m648).

Both games read GwPlayerConf[i].comDif (lbl_80282E48 + i*0xA + 4) only where a CPU
player is set up:
  m604  .text 0xF744, 0xF81C, 0x12144, 0x1221C   lha r5,0x4(r5) -> passed to the CPU
        controller constructors (fn_1_A68 / fn_1_11EC)
  m648  .text 0xB0F4                              lha r0,0x4(r3) -> stored at obj+0x34
Each lha becomes a bl to a DOL hook that does the same load, then subtracts 1 unless
the level is already 0. So Very Hard plays like Hard, Hard like Normal, Normal like
Easy, and Easy is unchanged. Human players never reach these sites. It applies
everywhere these games are played (party, Minigame Mode, Free Play), including the
Battle copy of m604.

The hooks live in zero padding after the TRK vector handlers at 0x80004500
(0x8000456C-0x800045E4 is free; no other patch uses it).

Run after apply_mgtable_move_patch.py and apply_whatgoesup_battle_patch.py: it edits
their build/GP6P01/files/dll/m604DLL.rel and m648DLL.rel in place, adding module-0
relocations. Safe to re-run. Edits build/GP6P01/main.dol and those two RELs.
"""
import struct

from tools.lib.paths import BUILD, DOL
from tools.lib.dol import dol_offset

HOOK_R5 = 0x80004570
HOOK_R0 = 0x80004590
CAVE_END = 0x800045E4

R_PPC_REL24 = 10
R_DOLPHIN_SECTION = 202
R_DOLPHIN_END = 203
DOL_TEXT_SECTION = 4  # section byte the RELs use for DOL .text targets
BL_PLACEHOLDER = bytes.fromhex("48000001")  # bl, displacement filled by the relocation

# REL -> [(.text offset, original instruction, hook)]
SITES = {
    "m604DLL.rel": [
        (0xF744, bytes.fromhex("A8A50004"), HOOK_R5),
        (0xF81C, bytes.fromhex("A8A50004"), HOOK_R5),
        (0x12144, bytes.fromhex("A8A50004"), HOOK_R5),
        (0x1221C, bytes.fromhex("A8A50004"), HOOK_R5),
    ],
    "m648DLL.rel": [
        (0xB0F4, bytes.fromhex("A8030004"), HOOK_R0),
    ],
}


def build_hook(rd, ra):
    """lha rd,4(ra); cmpwi rd,0; beqlr; addic rd,rd,-1; blr"""
    words = [
        (42 << 26) | (rd << 21) | (ra << 16) | 4,  # lha
        (11 << 26) | (rd << 16),  # cmpwi rd,0
        0x4D820020,  # beqlr
        (12 << 26) | (rd << 21) | (rd << 16) | 0xFFFF,  # addic (addi would read r0 as 0)
        0x4E800020,  # blr
    ]
    return b"".join(struct.pack(">I", w) for w in words)


HOOKS = {HOOK_R5: build_hook(5, 5), HOOK_R0: build_hook(0, 3)}


def patch_dol():
    dol = bytearray(DOL.read_bytes())
    for address, code in HOOKS.items():
        assert address + len(code) <= CAVE_END
        position = dol_offset(dol, address)
        current = bytes(dol[position:position + len(code)])
        if current not in (b"\0" * len(code), code):
            raise SystemExit(f"Code cave {address:#010x} is not free")
        dol[position:position + len(code)] = code
        print(f"Wrote {len(code)} bytes at {address:#010x}")
    DOL.write_bytes(dol)


def patch_rel(name, sites):
    path = BUILD / "files" / "dll" / name
    if not path.exists():
        raise SystemExit(f"{path} missing; run apply_mgtable_move_patch.py first")
    rel = bytearray(path.read_bytes())
    section_table = struct.unpack_from(">I", rel, 0x10)[0]
    text = struct.unpack_from(">I", rel, section_table + 8)[0] & ~1
    imp_offset, imp_size = struct.unpack_from(">II", rel, 0x28)
    imports = [struct.unpack_from(">II", rel, imp_offset + 8 * i) for i in range(imp_size // 8)]
    if max(imports, key=lambda m: m[1])[0] != 0:
        raise SystemExit(f"{name}: module-0 relocations are not the last table")
    if struct.unpack_from(">HBBI", rel, len(rel) - 8)[1] != R_DOLPHIN_END:
        raise SystemExit(f"{name}: does not end with an END relocation")

    current = [bytes(rel[text + s:text + s + 4]) for s, _, _ in sites]
    if all(c == BL_PLACEHOLDER for c in current):
        print(f"{name} already hooked")
        return
    for (site, original, _), c in zip(sites, current):
        if c != original:
            raise SystemExit(f"{name}: unexpected instruction {c.hex()} at .text {site:#x}")

    records = struct.pack(">HBBI", 0, R_DOLPHIN_SECTION, 1, 0)
    previous = 0
    for site, _, hook in sorted(sites):
        rel[text + site:text + site + 4] = BL_PLACEHOLDER
        records += struct.pack(">HBBI", site - previous, R_PPC_REL24, DOL_TEXT_SECTION, hook)
        previous = site
    rel[len(rel) - 8:len(rel) - 8] = records
    path.write_bytes(rel)
    print(f"Hooked {len(sites)} difficulty read(s) in {name}")


def main():
    patch_dol()
    for name, sites in SITES.items():
        patch_rel(name, sites)
    print("CPU handicap applied: m604 and m648 CPUs play one level lower (Easy unchanged)")


if __name__ == "__main__":
    main()
