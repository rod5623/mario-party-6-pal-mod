"""Battle-type copies of more 4P minigames (see battle_port.py for the recipe).

Run after apply_mgtable_move_patch.py and apply_whatgoesup_battle_patch.py.
Each game below gets a new table entry (type 3) that shares the 4P overlay.
Edits build/GP6P01/main.dol and the patched REL copies in build/GP6P01/files/dll/.
"""

from tools.lib.paths import BUILD, DOL, ROOT
from tools.lib.game import FN_PRACTICE_CHECK
from tools.lib import battle_port as bp
from tools.lib.dol import write_cave
from tools.lib.rel import add_calls, check_words, retarget_call, text_base

REL_DIR = BUILD / "files" / "dll"
REL_ORIG = ROOT / "orig" / "GP6P01" / "files" / "dll"

LHA_R0_4_R30 = 0xA81E0004


class Game:
    def __init__(self, name, rel, src_index, new_index):
        self.name, self.rel, self.src_index, self.new_index = name, rel, src_index, new_index

    def patch_rel(self, data, wrapper_address):  # pragma: no cover - overridden
        raise NotImplementedError


# ---- m615 Note to Self -------------------------------------------------------
# Counter: REL bss_1C[4], higher is better. fn_1_99D0 (0x99D0) writes it to
# GwPlayer[i]+0x2C only when fn_8006A7B0(0x30002) says decathlon (call at 0x9B74).
# Forcing that for type 3 also skips fn_80072388 (winner banner). Both the
# "+0x28 = 10" and the decathlon paths join at 0x9BE4 (lha r0,4(r30)); the rank
# wrapper runs there, so +0x28 ends up holding dense ranks for all four players.
class NoteToSelf(Game):
    def __init__(self):
        super().__init__("m615 Note to Self", "m615DLL.rel", 14, 83)

    def patch_rel(self, data, wrapper_address):
        check_words(data, 0x9B74, "48000001")
        check_words(data, 0x9BE4, "A81E0004", "48000001")
        changed = retarget_call(data, 0x9B74, FN_PRACTICE_CHECK, bp.CAVE_FORCE)
        added = add_calls(data, [(0x9BE4, wrapper_address)])
        return changed or added

    def wrapper(self):
        return 0, [LHA_R0_4_R30]


# ---- m614 Cannonball Fun -----------------------------------------------------
# Counter: per-player work struct +0x17C (first to 5 wins, hits scored). No
# decathlon branch exists, so the result code (fn_1_656C) is hooked directly:
# at 0x7770 `bl fn_80072388` (winner banner) is redirected to a hook that reads
# the four work structs (pointers at 0x34(r1)), copies each count to
# GwPlayer[work+4]+0x2C and runs rank_core. +0x28 is overwritten for all four
# players, replacing the "+0x28 = 10" winner write just before.
FN_WINNER_SET = 0x80072388


class CannonballFun(Game):
    def __init__(self):
        super().__init__("m614 Cannonball Fun", "m614DLL.rel", 13, 84)

    def patch_rel(self, data, hook_address):
        check_words(data, 0x7770, "48000001")
        return retarget_call(data, 0x7770, FN_WINNER_SET, hook_address)

    def hook(self, address):
        return bp.build_workstruct_hook(address, 0x34, 4, 0x17C, FN_WINNER_SET)


# ---- m603 Freeze Frame -------------------------------------------------------
# Counter: score object (REL bss_10, pointer kept in callee-saved r24 inside
# fn_1_7C4), player i's score is an s32 at obj + 0x24 + i*0x1C, higher wins.
# The winner is decided in fn_1_62DC (0x87C) and the scores are final from then.
# The REL already skips its "+0x28 = 10" write for a type-3 entry. Hook: the
# `bl fn_8004944C` at 0x92C (a fade call with r3-r5 = 1, 6, 0x3C) is redirected
# to a hook that ranks the four scores and then tail-calls fn_8004944C.
FN_FADE = 0x8004944C


class FreezeFrame(Game):
    def __init__(self):
        super().__init__("m603 Freeze Frame", "m603DLL.rel", 2, 85)

    def patch_rel(self, data, hook_address):
        check_words(data, 0x92C, "48000001")
        return retarget_call(data, 0x92C, FN_FADE, hook_address)

    def hook(self, address):
        return bp.build_object_hook(address, 24, 0x24, 0x1C, FN_FADE)


GAMES = [NoteToSelf(), CannonballFun(), FreezeFrame()]
CAVE_ADDRESS = {
    "m615 Note to Self": bp.CAVE_WRAPPERS,
    "m614 Cannonball Fun": bp.CAVE_WRAPPERS + 0x60,
    "m603 Freeze Frame": bp.NEW_BASE + 0x2F00,  # free tail of the relocated table section
}


# ---- instDll: allow table indices above 81 ------------------------------------
# The instruction-screen overlay (shown before every board minigame) reads
# GwSystem.mgNo and replaces anything >= 0x52 (the vanilla table size) with 0,
# i.e. Smashdance: `cmplwi r3, 0x52` at REL .text 0x128. Raise the limit to 0x60.
INSTDLL = "instDll.rel"
INSTDLL_LIMIT_OFFSET = 0x128


def patch_instdll():
    path = REL_DIR / INSTDLL
    data = bytearray((path if path.exists() else REL_ORIG / INSTDLL).read_bytes())
    position = text_base(data) + INSTDLL_LIMIT_OFFSET
    current = bytes(data[position:position + 4])
    if current == bytes.fromhex("28030052"):
        data[position:position + 4] = bytes.fromhex("28030060")
        REL_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print("instDll: minigame index limit raised from 82 to 96")
    elif current != bytes.fromhex("28030060"):
        raise RuntimeError(f"Unexpected instDll limit instruction: {current.hex()}")
    else:
        print("instDll limit already raised")


def main():
    patch_instdll()
    dol = bytearray(DOL.read_bytes())
    bp.install_core(dol)
    for game in GAMES:
        address = CAVE_ADDRESS[game.name]
        if hasattr(game, "hook"):
            write_cave(dol, address, game.hook(address))
        else:
            direction, replaced = game.wrapper()
            write_cave(dol, address, bp.build_wrapper(address, direction, replaced))
        bp.add_table_entry(dol, game.src_index, game.new_index)
    DOL.write_bytes(dol)
    for game in GAMES:
        address = CAVE_ADDRESS[game.name]
        path = REL_DIR / game.rel
        data = bytearray((path if path.exists() else REL_ORIG / game.rel).read_bytes())
        if game.patch_rel(data, address):
            REL_DIR.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            print(f"Hooked {game.name} ({game.rel})")
        else:
            print(f"{game.name} already hooked")


if __name__ == "__main__":
    main()
