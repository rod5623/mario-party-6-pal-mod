"""Shorten the time limit of selected 1v3 minigames.

Each game starts a shared countdown object with `li r4, N` before calling fn_8006F370; N is in
1/50 s ticks (1500 = 30 s, assumed PAL 50 Hz). Only that immediate is changed, so the HUD and
the game-over test stay in sync.

Stage Fright (m630) has no `li r4` countdown. Its .data header (lbl_1_data_0) starts with the time
limit in whole seconds as a big-endian halfword (0x001E = 30); the DOL minigame init
(fn_80071464..fn_80071500) copies it to lbl_802A3C38 and starts the countdown with seconds * 50
(`mulli r4, r0, 0x32`). 0 or 0x12C means no countdown.

Run after apply_mgtable_move_patch.py (m628 already carries its relocation edits in
build/GP6P01/files/dll). Writes patched RELs to build/GP6P01/files/dll/.
"""
from tools.lib.paths import ROOT, BUILD
from tools.lib.dol import replace_bytes

REL_DIR = BUILD / "files" / "dll"
REL_ORIG = ROOT / "orig" / "GP6P01" / "files" / "dll"
TICKS_PER_SECOND = 50
ORIGINAL_TICKS = 1500

# rel name, file offset of `li r4, 1500`, new seconds
GAMES = [
    ("m628DLL.rel", 0x11CDC, 25),  # Surge and Destroy
    ("m632dll.rel", 0x1A00, 12),   # Crate and Peril
    ("m633dll.rel", 0x8E8, 20),    # Ray of Fright
]

# rel name, file offset of the data-header seconds halfword (REL section 5), original, new seconds
HEADER_GAMES = [
    ("m630dll.rel", 0x8F08, 30, 20),  # Stage Fright
]


def li_r4(value):
    return bytes([0x38, 0x80]) + value.to_bytes(2, "big")


def patch(name, offset, original, patched, seconds):
    path = REL_DIR / name
    data = bytearray((path if path.exists() else REL_ORIG / name).read_bytes())
    before = bytes(data)
    replace_bytes(data, offset, original, patched, f"{name} time limit")
    if bytes(data) != before:
        REL_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f"{name}: time limit -> {seconds} s")
    else:
        print(f"{name}: already {seconds} s")


def main():
    for name, offset, seconds in GAMES:
        patch(name, offset, li_r4(ORIGINAL_TICKS), li_r4(seconds * TICKS_PER_SECOND), seconds)
    for name, offset, old, seconds in HEADER_GAMES:
        patch(name, offset, old.to_bytes(2, "big"), seconds.to_bytes(2, "big"), seconds)


if __name__ == "__main__":
    main()
