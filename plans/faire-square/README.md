# Faire Square (w03Dll) notes

Board = `GwSystem.boardNo` 2 (assumed from w03; not confirmed). REL: `src/build/GP6P01/w03Dll/asm/auto_00_00000000_text.s`
(offsets below are REL `.text` offsets; file offset = +0xDC). Space data: `root/data/w03.bin` file 0 (night: `w03n.bin`),
dump with `python -m tools.scripts.masu_dump w03` (run from `src/tools`). Space ids are 1-based.

## Space flags (masu +0x14, `fn_80176FCC(id)`) and who handles them
| flag | handler | meaning |
|---|---|---|
| 0x1  | `fn_1_2718` (on landing, from `fn_1_1CD4`) | Luck Wheel (id 16) |
| 0x4  | `fn_1_5908` (on landing) | Star Shuffle (id 54) |
| 0x2  | `fn_1_8F70` (passing, `fn_1_1C30`) | Swap Fest (id 25) |
| 0x10 | `fn_1_BDC8` (passing) | Broom ride to space 42 or 44 (id 20; see `boards/faire-square/faire-square.md`) |
| 0x8, 0x20 | `fn_1_C5DC` (passing) | **send the player back to the start** (originally). Now: id 28 is Double or Nothing, id 30 is the Wheel of Fortune (landing only); `fn_1_C5DC` remains the wheel's send-back outcome. See `boards/faire-square/faire-square.md`. |
| 0x40 | - | the start space (id 109); `fn_1_C5DC` finds it with `fn_80179164(-1, 0x40)` |
Type halfword (masu +0x10, `fn_80176F84`): 1 blue, 2 red, 3 "?"; bit 0x4000 on id 38 marks the Whomp toll gate (handled in the main DOL, `fn_80214F54` -> `fn_80200524`).

## The two return-to-start spaces (right side of the map)
Path into the Star Shuffle (id 54): 28 -> 29 -> 30 -> 31 -> 53 -> 54.
* **id 30**, flags 0x20, type 2 (red), pos (2515, 913, -231): **3 spaces** before Star Shuffle.
* **id 28**, flags 0x08, type 1 (blue), pos (2137, 913, -873): **5 spaces** before Star Shuffle.
Both run `fn_1_C5DC(player, space)` from `fn_1_1C30` (the pass handler registered with `fn_80179A1C` in `fn_1_F4`).
`fn_1_C5DC` picks variant `r29 = 0` for flag 0x8 and `1` for flag 0x20 (float table `lbl_1_data_840`),
then teleports with animation and writes the destination into `GwPlayer.masuId` (`sth r27, 0xc(r4)` at text 0xD138)
where r27 = the flag-0x40 space. To change where they send you, change the `li r4, 0x40` before `bl fn_80179164`
(text 0xC7B8) or move the 0x40 flag in the space data; to disable one, clear its flag in `w03.bin`/`w03n.bin`.
