"""RETIRED (2026-11-26): the step pagoda_board now builds and installs the REL and the motions. Kept for the record.

Experiment: board 11 runs Pagoda Peak's own board code, a REL written in C (Route B), instead of Snowflake Lake's.

The REL (src/REL/w07Dll/*.c, built by tools/pagoda/build_pagoda_rel.py) is installed as files/dll/w07dll.rel.
It reads Pagoda Peak's own archive, w07.bin (data dir 261), and message bank 0x4B, which the step
pagoda_board builds (with the DOL's moved data dir table): the spaces with MP7's flags, masu layer 1, the
map, Snowflake Lake's shopkeeper and every event's models (pagoda.h FILE_*), and MP7 bank 0x14's text. What each event does is in its C file's header:
  * star.c: Master Koopa sells the Star at the summit (space 54) for 10, 20, 30, then 40 coins; the cloud
    flies the player back to the start and the move carries on.
  * gong.c (spaces 19, 38), rocket.c (23), kungfu.c (65), blaze.c (41), dragon.c (44): the "?" spaces.
  * bowser.c: Bowser Time every 3 turns (a bridge breaks for a turn, or the stomp); gaps.c: the bamboo and
    the branch.
This aid also adds MP7's fanning and chest motions (<char>.bin 0x82, 0x83, 0x89, 0x8B) as files 126-129 of
each MP6 <char>mot.bin, for Blazing Rock (backed up to backups/<char>mot.bin.bak_before_pagoda_stub).

    python -m tools.patches.test_aids.apply_pagoda_stub_patch        # build and install
    python -m tools.patches.test_aids.apply_pagoda_stub_patch --off  # back to the Snowflake Lake clone

Outputs: build/GP6P01/files/dll/w07dll.rel (copy it to root/dll/), and the 11 <char>mot.bin in both
root/data and build/GP6P01/files/data. Needs clone_board and pagoda_board (build/GP6P01/files/data/w07.bin).
--off rebuilds the clone (as clone_board does: Snowflake Lake's code on Snowflake Lake's vanilla archives)
and removes the characters' motions 126-129; bank 0x4B stays (unused by the clone).

History: until 2026-11-25 the board borrowed Snowflake Lake's w04.bin / w04n.bin (files 41-81 appended by
this aid and the retired aids mp7_map_test and mp7_spaces_test, kept in plans/pagoda-peak/retired/), and this
aid appended the text to Snowflake Lake's bank 0x32 as records 26-82 (pagoda_board strips them).

Status:
  * v1 and v2 confirmed in Dolphin (2026-11-25): no crash, Stars can be bought at the summit, and the
    "you lack coins" line shows. The price going up hasn't been checked yet.
  * The summit confirmed in Dolphin (2026-11-25): the house and platform, the price sign, and Master Koopa
    coming out, animating and selling the Star.
  * Spaces with MP7's flags and the bottle rocket confirmed in Dolphin (2026-11-25).
  * Gong of Fate confirmed in Dolphin (2026-11-25), with Master Koopa's cloud (MP7 0x26, file 54).
  * The dragon, Kung Fu Falls (with its Star prize) and Blazing Rock confirmed in Dolphin (2026-11-25), after
    the fixes: the move carrying on from the start, no sinking after the gong, the flames, the Star loss.
  * Bowser Time (both events), the cloud flight back down and the bamboo/branch leaps confirmed in Dolphin
    (2026-11-25). Not yet tested: a player reaching a broken bridge (hop back, move ends) and its repair.
"""
import shutil
import struct
import sys

from tools.lib import mp7, mpdata
from tools.lib.paths import BACKUPS, DATA_ORIG, DATA_OUT, GAME_DATA, REL_DIR
from tools.pagoda.build_pagoda_rel import build
from tools.patches.apply_pagoda_peak_patch import drop_last_file
from tools.patches import apply_clone_board_patch as clone
from tools.patches import apply_pagoda_board_patch as board

CHARS = ("mario", "luigi", "peach", "yoshi", "wario", "daisy", "waluigi", "kinopio", "teresa", "minikoopa",
         "kinopiko")
CHAR_MOTS = 126                               # files in every MP6 <char>mot.bin
MP7_CHAR_MOTS = (0x82, 0x83, 0x89, 0x8B)      # MP7 <char>.bin: fan slow, fan fast, hold chest, carry chest


def mp7_char_motions(char):
    data = mp7.read(f"files/data/{char}.bin")
    count = struct.unpack_from(">I", data, 0)[0]
    offsets = list(struct.unpack_from(f">{count}I", data, 4))
    return [mpdata.read_file(data, offsets, i) for i in MP7_CHAR_MOTS]


def patch_char_motions(on):
    """Append (or drop) MP7's four motions as files 126-129 of every <char>mot.bin, in root/data and build."""
    for char in CHARS:
        name = f"{char}mot.bin"
        game = GAME_DATA / name
        source = game if game.exists() else DATA_ORIG / name
        data, offsets = mpdata.read_archive(source)
        if len(offsets) < CHAR_MOTS:
            raise SystemExit(f"{source}: {len(offsets)} files, expected at least {CHAR_MOTS}")
        backup = BACKUPS / f"{name}.bak_before_pagoda_stub"
        if game.exists() and not backup.exists():
            BACKUPS.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(game, backup)
        while len(offsets) > CHAR_MOTS:
            data, offsets = drop_last_file(data, offsets)
        if on:
            data, offsets = mpdata.append_files(data, offsets, mp7_char_motions(char))
        for out in (game, DATA_OUT / name):
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)


def main():
    if "--off" in sys.argv[1:]:
        clone.write_clone_rel()
        patch_char_motions(False)
        print("Board 11: the Snowflake Lake clone again; MP7 motions removed")
        return
    if not (DATA_OUT / board.ARCHIVE).exists():
        raise SystemExit(f"{DATA_OUT / board.ARCHIVE} is missing: run apply_pagoda_board_patch.py first")
    patch_char_motions(True)
    built = build()
    out = REL_DIR / clone.REL_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(built, out)
    print(f"Board 11: Pagoda Peak REL installed as {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
