"""Testing aid: make every board minigame roll a Battle.

The Battle roll in the board minigame function (fn_801EF728) is
`random(100) < chance` (0x801EFCCC, `cmplwi r3, chance`). The odds patch sets
the chance to 18. This sets it to 100, so it always passes. The richest player
still needs at least 10 coins (fn_8015CC14 >= 10 at 0x801EFCD4), otherwise the
normal 4P/1v3/2v2 roll is used.

    python -m tools.patches.test_aids.apply_battle_always_patch        # 100% Battle
    python -m tools.patches.test_aids.apply_battle_always_patch --off  # back to the odds patch value (18%)

Edits build/GP6P01/main.dol only; run after apply_minigame_odds_patch.py.
"""
import sys

from tools.lib.paths import DOL
from tools.lib.dol import dol_offset

BATTLE_COMPARE = 0x801EFCCC
CHANCE_ODDS_PATCH = 18
CHANCE_ALWAYS = 100


def compare(chance):
    return bytes([0x28, 0x03, 0x00, chance])


def main():
    off = "--off" in sys.argv[1:]
    dol = bytearray(DOL.read_bytes())
    position = dol_offset(dol, BATTLE_COMPARE)
    current = bytes(dol[position:position + 4])
    known = {compare(CHANCE_ODDS_PATCH), compare(CHANCE_ALWAYS), compare(10)}
    if current not in known:
        raise SystemExit(f"Unexpected Battle compare: {current.hex()}")
    target = compare(CHANCE_ODDS_PATCH if off else CHANCE_ALWAYS)
    dol[position:position + 4] = target
    DOL.write_bytes(dol)
    print(f"Battle chance is now {target[3]}%")


if __name__ == "__main__":
    main()
