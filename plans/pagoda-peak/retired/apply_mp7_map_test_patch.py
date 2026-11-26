"""Experiment: the clone board (board 11) draws Mario Party 7's Pagoda Peak map model instead of Snowflake Lake's.

Both games use HSF version HSFV037. MP7 data/w02.bin (Pagoda Peak) file 6 is its map model (785 KB);
MP6 w04Dll loads Snowflake Lake's map as file 3 of w04.bin / w04n.bin (day / night) at .text 0x210:
`ori r3, r26, 3` before mbObjCreate (the base r26 is 0xE90000 or 0xEA0000).
  * MP7 file 6 is appended to w04.bin and w04n.bin as file 41 (after the 41 vanilla files), in
    root/data and build/GP6P01/files/data. The real Snowflake Lake never loads file 41.
  * In w07dll.rel (apply_clone_board_patch.py), .text 0x210 becomes `ori r3, r26, 41`.
Everything else is still Snowflake Lake's: the spaces (file 0), objects and events, so players stand
on Snowflake Lake's space positions over Pagoda Peak's scenery. The question is whether the model
loads and draws.

    python -m tools.patches.test_aids.apply_mp7_map_test_patch        # on
    python -m tools.patches.test_aids.apply_mp7_map_test_patch --off  # back to Snowflake Lake's map

Run after apply_clone_board_patch.py (re-running that step also turns the REL change off). The
originals are backed up to backups/w04*.bin.bak_before_mp7_map_test before the first edit.

Result in Dolphin (2026-11-24): the MP7 model loads and draws unchanged. Pagoda Peak's scenery
shows, with the players and Snowflake Lake's objects on Snowflake Lake's space positions.
"""
import shutil
import struct
import sys

from tools.lib import mp7, mpdata
from tools.lib.paths import BACKUPS, DATA_ORIG, DATA_OUT, GAME_DATA, REL_DIR
from tools.lib.rel import check_words, text_base
from tools.patches.apply_pagoda_peak_patch import drop_last_file

MP7_ARCHIVE, MP7_MODEL = "files/data/w02.bin", 6
ARCHIVES = ("w04", "w04n")
VANILLA_FILES = 41
NEW_FILE = VANILLA_FILES              # file 41
REL_NAME = "w07dll.rel"
SITE = 0x210
ORIGINAL = 0x63430003                 # ori r3, r26, 3
PATCHED = 0x63430000 | NEW_FILE       # ori r3, r26, 41


def mp7_model():
    data = mp7.read(MP7_ARCHIVE)
    count = struct.unpack_from(">I", data, 0)[0]
    model = mpdata.read_file(data, list(struct.unpack_from(f">{count}I", data, 4)), MP7_MODEL)
    if not model.startswith(b"HSFV037"):
        raise RuntimeError(f"MP7 w02.bin file {MP7_MODEL} is not an HSFV037 model")
    return model


def patch_archive(name, model):
    """Write root/data and build/.../data <name>.bin with `model` as file 41 (None: vanilla 41 files)."""
    game = GAME_DATA / f"{name}.bin"
    source = game if game.exists() else DATA_ORIG / f"{name}.bin"
    backup = BACKUPS / f"{name}.bin.bak_before_mp7_map_test"
    if game.exists() and not backup.exists():
        BACKUPS.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(game, backup)
    data, offsets = mpdata.read_archive(source)
    while len(offsets) > VANILLA_FILES:
        data, offsets = drop_last_file(data, offsets)
    if len(offsets) != VANILLA_FILES:
        raise SystemExit(f"{source}: {len(offsets)} files, expected {VANILLA_FILES}")
    if model is not None:
        data, offsets = mpdata.append_files(data, offsets, [model])
    for out in (game, DATA_OUT / f"{name}.bin"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)


def main():
    off = "--off" in sys.argv[1:]
    path = REL_DIR / REL_NAME
    if not path.exists():
        raise SystemExit(f"{path} is missing: run apply_clone_board_patch.py first")
    rel = bytearray(path.read_bytes())
    check_words(rel, SITE, f"{ORIGINAL:08X}", f"{PATCHED:08X}")
    struct.pack_into(">I", rel, text_base(rel) + SITE, ORIGINAL if off else PATCHED)
    path.write_bytes(rel)
    model = None if off else mp7_model()
    for name in ARCHIVES:
        patch_archive(name, model)
    if off:
        print("Clone board map: Snowflake Lake's again (w04*.bin back to 41 files)")
    else:
        print(f"Clone board map: MP7 Pagoda Peak model ({len(model)} bytes) as file {NEW_FILE} of "
              f"{', '.join(ARCHIVES)}; {REL_NAME} .text {SITE:#x} -> ori r3,r26,{NEW_FILE}")


if __name__ == "__main__":
    main()
