"""Run every apply_*_patch.py in a dependency-safe order.

    python tools/apply_all.py                # all patches, stop at the first failure
    python tools/apply_all.py --list         # print the order and exit
    python tools/apply_all.py --from NAME    # resume at a step (e.g. mgtable_move)
    python tools/apply_all.py --only NAME... # run just these steps, in the table order
    python tools/apply_all.py --ninja        # first rebuild build/GP6P01/main.dol from asm
    python tools/apply_all.py --test-aids    # also run battle_always and duel_test_aid

Each step is tools/patches/apply_<NAME>_patch.py (test aids: tools/patches/test_aids/),
run as `python -m tools.patches.apply_<NAME>_patch` from src/. This does NOT copy anything
into root/ except what apply_random_bonus_patch.py deploys itself; copy the outputs
afterwards (tools/README.md, Deploying).

Why this order (see the groups below):
  A. Scripts that own one bank of messdata_eng.bin and splice only that bank into the
     current file (tools/lib/messages.py): dk_bonus (0x3E), bowser_bonus + bowser_bonus_fix
     (0x3F), random_bonus (0x0E). They no longer overwrite each other and are re-runnable.
  B. Scripts that chain onto the existing message files. bowser_minigame appends to bank
     0x3F, so it must follow bowser_bonus/bowser_bonus_fix (re-running those resets 0x3F).
  C. DOL tweaks that do not touch messages.
  D. mgtable_move relocates the minigame table. It edits the binary DOL only, so no
     ninja rebuild may follow it, and it must come after everything that edits the table.
  E. Patches that need the relocated table, in their documented dependency order.
  random_bonus runs ninja (via rebuild_mdpresult), so it sits before the DOL-only
  tweaks in C/D/E. minigame_wins also runs ninja (it rebuilds resultDll from asm) and
  writes build/GP6P01/files/dll/resultDll.rel from scratch, so it must precede
  mgtable_move, which retargets that REL (minigame_wins also retargets it itself when
  re-run alone after mgtable_move). random_bonus resets its counter (GwPlayer+0x2A).
"""
import argparse
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent

STEPS = [
    # A. single-bank message writers
    "dk_split",
    "dk_bonus",
    "bowser_bonus",
    "bowser_bonus_fix",
    "random_bonus",  # runs ninja, so it precedes the DOL-only patches below
    "minigame_wins",  # rebuilds resultDll (ninja); writes files/dll/resultDll.rel, so before mgtable_move
    # B. message writers that chain
    "bowser_minigame",
    "final_five_odds",
    "star_trap_orb",
    # (star_shuffle_bet, whomp_rich, double_or_nothing chain messages too, but put
    # caves in the relocated table section, so they run right after mgtable_move)
    # C. independent DOL tweaks
    "dunk_bros",  # edits the table, so before mgtable_move
    "miracle_odds",
    "minigame_odds",
    "unlock_all",
    "music_volume",
    "sfx",  # voice clips + quieter SFX: rebuilds files/sound/MP6_SND.msm from the retail file (about 2 min); touches nothing else
    "cpu_landing",
    # D. relocate the minigame table
    "mgtable_move",
    # E. need the relocated table
    "star_shuffle_bet",  # caves at NEW_BASE + 0x3340..; also chains bank 49 messages
    "whomp_rich",  # caves in the relocated section; imports star_shuffle_bet
    "double_or_nothing",  # needs star_shuffle_bet's bank 49 record
    "whatgoesup_battle",
    "cpu_handicap",  # hooks m604/m648 RELs written by mgtable_move and whatgoesup_battle
    "battle_ports",
    "battle_thumbs",
    "daft_rafts_duel",
    "lift_leapers_duel",
    "closecall",  # new 4P minigame: table entry 88 (after 82-87), jbtestdll.rel, saf/instpic files, banks 5 and 65
    "1v3_time_limit",
    "minigame_exclusion",
    "wheel_of_fortune",
    "luck_wheel_rewards",
    # board files in decompiling/root/data (independent)
    "faire_square_dk_bowser_space",
    "castaway_wheel",  # DOL caves after luck_wheel_rewards; also writes root/data/w05*.bin (backups in backups/)
    "boo_day_orbs",  # Boo's house by day; DOL caves after castaway_wheel (uses its random orb routine) and final_five_odds
    "castaway_broom",  # Castaway space 26 broom ride; DOL caves after boo_day_orbs; also writes root/data/w05*.bin (backups in backups/)
    "castaway_spare_change",  # after castaway_broom: chains the wheel's pass hook, bank 0x33 records and w05 files after the broom's; adds DOL section 16; writes root/data/w05*.bin
    "castaway_troll",  # last of the Castaway scripts: Castaway space 39 troll; chains the broom landing cave and the spare change init, adds w05 file 49 and bank 0x33 records 69-72; writes root/data/w05*.bin
    "egadd_wheel",  # E. Gadd's Garage space 7 wheel: DOL section 16 after the troll, reuses the Castaway wheel's spin/orb caves; w02Dll.rel, bank 0x30 records 27-33; writes root/data/w02*.bin
    "egadd_calamity",  # Calamity Launcher rework: chains w02Dll.rel after egadd_wheel (prices, CPU choice, pay call), DOL cave 0x802F8D70, bank 0x30 record 20 (eng); needs the wheel's 34-record bank
    "egadd_shuffle",  # Shuffle-o-tron gives n+1 orbs below 3 and works with 0 orbs: chains w02Dll.rel after egadd_calamity, DOL leaf at 0x802F8D80
    "egadd_morpher",  # Orb Morpher rewards by orb count: adds DOL section 17 (0x802F8DA0, arena clamp raised), chains w02Dll.rel after egadd_shuffle, reuses bank 0x30 records 8/10/22 (all languages) + 9 (eng)
    "egadd_robots",  # two robot cards + the spare change event (nodes 114/115): chains the wheel's pass/init hooks, DOL section 17 after egadd_morpher, bank 0x30 records 34-42, w02 file 58 and spaces (root/data)
    "egadd_miracle_space",  # E. Gadd's Garage space 27 (turntable, below the hub) blue -> Miracle; writes root/data/w02*.bin only
    "unlucky",  # Unlucky Star counter: DOL section 17 after egadd_robots; hooks the coin/Star setters (reset + award in random_bonus)
]
TEST_AIDS = ["battle_always", "duel_test_aid", "closecall_always"]  # appended last when requested


def run(cmd, cwd):
    print(f"\n>>> {' '.join(str(c) for c in cmd)}", flush=True)
    subprocess.run([str(c) for c in cmd], cwd=cwd, check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--from", dest="start")
    ap.add_argument("--only", nargs="+")
    ap.add_argument("--ninja", action="store_true")
    ap.add_argument("--test-aids", action="store_true")
    args = ap.parse_args()

    steps = STEPS + (TEST_AIDS if args.test_aids else [])
    for name in (args.only or []) + ([args.start] if args.start else []):
        if name not in steps:
            sys.exit(f"unknown step {name!r}; use --list")
    if args.only:
        steps = [s for s in steps if s in args.only]
    if args.start:
        steps = steps[steps.index(args.start):]

    if args.list:
        for s in steps:
            print(s)
        return 0

    if args.ninja:
        run([ROOT / "tools/bin/ninja.exe", "build/GP6P01/main.dol"], ROOT)
    for name in steps:
        package = "patches.test_aids" if name in TEST_AIDS else "patches"
        script = TOOLS / package.replace(".", "/") / f"apply_{name}_patch.py"
        if not script.exists():
            sys.exit(f"missing {script}")
        try:
            # run as a module from src/, so the patches' `tools.lib...` imports resolve
            run([sys.executable, "-m", f"tools.{package}.apply_{name}_patch"], ROOT)
        except subprocess.CalledProcessError as e:
            sys.exit(f"\nFAILED at step {name!r} (exit {e.returncode}). Fix it, then resume with: "
                     f"python tools/apply_all.py --from {name}")
    print("\nAll patches applied. Next: copy the build outputs into root/ (see tools/README.md, Deploying).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
