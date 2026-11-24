"""DK space: 50% DK Bonus / 50% DK Mini-Game: python -m tools.patches.apply_dk_split_patch

The DK Bonus roll is "random float < 0.3". The load at 0x801BC278 now reads the 0.5 constant
lbl_802E1B98 instead of lbl_802E1BFC (which other code shares, so it is left alone).
Writes main.dol and the .text listing (ASM_TEXT). No prerequisites; independent of dk_bonus.
Idempotent.
"""
from tools.lib.paths import ASM_TEXT, DOL
from tools.lib.dol import patch_asm_instruction, patch_dol_instruction

PATCHES = (
    # The DK Bonus roll is "random float < 0.3"; compare against 0.5 instead.
    # lbl_802E1BFC is shared with other code, so point this load at the 0.5 constant lbl_802E1B98.
    (
        0x801BC278,
        bytes.fromhex("C0 02 B2 5C"),
        bytes.fromhex("C0 02 B1 F8"),
        "lfs f0, lbl_802E1BFC@sda21(r0)",
        "lfs f0, lbl_802E1B98@sda21(r0)",
    ),
)


def main():
    text_asm = ASM_TEXT.read_bytes().decode("utf-8")
    dol = bytearray(DOL.read_bytes())
    for address, original, patched, old_asm, new_asm in PATCHES:
        text_asm = patch_asm_instruction(
            text_asm, address, original, patched, old_asm, new_asm
        )
        patch_dol_instruction(dol, address, original, patched, f"instruction at {address:08X}")

    ASM_TEXT.write_bytes(text_asm.encode("utf-8"))
    DOL.write_bytes(dol)
    print("Patched DK space: 50% Bonus / 50% Mini-Game")
    print(f"Built DOL: {DOL}")


if __name__ == "__main__":
    main()
