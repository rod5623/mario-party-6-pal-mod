"""Treat every minigame as unlocked.

GWMgUnlockGet (fn_8003CCBC) tests bit (id - 601) of GwCommon.mgUnlock. Minigame
Mode, the option menu, bank/mini modes and others use it to grey out minigames.
The patch makes it return 1 for every id, so minigames added to the table
(which have no unlock bit of their own) are selectable straight away.
Independent of the other patches; edits build/GP6P01/main.dol only.
"""
from tools.lib.paths import DOL
from tools.lib.dol import dol_offset

GET_UNLOCK = 0x8003CCBC
ORIGINAL = bytes.fromhex("9421FFF0")  # stwu r1,-0x10(r1)
PATCHED = bytes.fromhex("38600001") + bytes.fromhex("4E800020")  # li r3,1 ; blr


def main():
    dol = bytearray(DOL.read_bytes())
    offset = dol_offset(dol, GET_UNLOCK)
    current = bytes(dol[offset:offset + 4])
    if current == ORIGINAL:
        dol[offset:offset + 8] = PATCHED
    elif bytes(dol[offset:offset + 8]) != PATCHED:
        raise SystemExit(f"Unexpected GWMgUnlockGet prologue: {current.hex()}")
    DOL.write_bytes(dol)
    print("All minigames now report as unlocked")
    print(f"Built DOL: {DOL}")


if __name__ == "__main__":
    main()
