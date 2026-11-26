# Board tables: what a 7th party board needs

This is a map of every place found in the PAL game (GP6P01) that hard-codes the set of boards,
and what a new party board would need from each one. It is the research behind board 11 (Pagoda
Peak). For the step-by-step recipe for the next board, see [adding-a-board.md](adding-a-board.md).

The machine-readable version is `tools/lib/board_tables.py`. To print every table and code site
from your files and check them against vanilla, run this from `src/`:

```powershell
python -m tools.scripts.board_tables_dump
```

All addresses are PAL. Function names in brackets are US (E01) decomp names for the same code.

## Board numbers

- `GwSystem.boardNo` is a 5-bit field at `0x80283298` (`GwSystem` = `0x80283290`, +8, `& 0x1F`).
- Numbers 0–10 are all used (`GW_BOARD_NO`, `include/game/gamework_enum.h`):

  | Number | Board |
  |---|---|
  | 0–5 | w01–w06 |
  | 6–8 | s01–s03 (solo mode) |
  | 9 | w10 |
  | 10 | w11 |

  **A new party board is 11.**
- Each board REL's prolog sets the number with `li r3,N` at `.text+0xCC`, then calls
  `mbObjectSetup` (`fn_8014A554`). That function stores it in `GwSystem` and keeps no other copy.
  `fn_8014BE04` also sets it when a game starts from `mdpartydll` or `mdsingdll`.
- **The readers.** A scan of every asm listing for reads of `GwSystem+8` (DOL and all RELs) found
  16 DOL functions plus code in `mdpartydll`, `mdpresultdll`, `resultDll`, `mdsingdll` and each
  board REL's init:
  - The DOL readers are the boardNo-indexed tables below, plus `boardNo == 3` checks in
    `fn_801BBDC0` and `fn_801BE24C`, and code that only runs in solo mode.
  - `resultDll` bounds-checks (`cmplwi 5`).
  - The board RELs store the value and never use it.

## Disc files and data directories

- New files reach the disc with `tools/scripts/build_iso.py`.
- **Overlay table** `0x8022D404`: 131 entries of `{char *path, 0}`, then a terminator.
  - It is referenced once, at `0x80005A10`. Moving it means copying the table and changing that
    one `lis`/`addi` pair.
  - Two slots are 156-byte stub RELs that nothing loads (no `li 0x70`/`0x79` call and no
    table row): `0x70` partyresultdll and `0x79` storyresultdll. Re-pointing one slot's path
    string gives a board overlay without moving the table. (jbtestdll, slot 5, is already Close
    Call.)
- **Data dirs** `0x8021BEF0`: 261 entries of `{char *path, -1}`, then a terminator.
  - `HuDataInit` counts them at start-up and calls `OSPanic` if a listed file is missing.
  - The board archives are dirs 227–241 (w01 227, w01n 228 … w11 241).
  - The list is alphabetical, but a new `w07`/`w07n` must be appended at 261/262: inserting would
    renumber waluigi…yoshimot (242–260).
  - The table is referenced 3 times by its own address (lis/addi at `0x80007688`, `0x800084A4`,
    `0x80008BC4`), **and 7 more times through a base register**: `data.c` keeps `0x8021AD88` (its string
    pool) in a register and adds `0x1168` (`0x80007A9C`, `0x80008090`, `0x80008238`, `0x80008854`,
    `0x80008FF4`, `0x80009458`, `0x80009B6C`). Grepping for the label finds only the first 3: missing the
    others panicked at boot (`dvd.c:205` File Open Error). When moving any table, also grep for its
    offset from nearby labels.
  - **Done (step `pagoda_board`):** the table is copied into DOL section 19 (`0x802FA1C0`) with
    dir 261 = `data/w07.bin` (Pagoda Peak's archive), and the 3 references point at the copy. The
    vanilla table stays in place unused, so `board_tables_dump` still reports it as 261 entries.
    HuDataInit counts the dirs (`DataDirMax`) and writes each file's disc entry into the table, so
    nothing else is sized to 261. One archive serves day and night: `mbObjDirSet(dir, dir)`, and
    the engine's day/night remap (`fn_80168258` and its copies) only swaps a matching dir.
- **Board RELs choose their own data.** `w01Dll` loads dirs 227/228 through about 77 `lis`
  immediates and 28 data words, and its message bank 0x2F through 23 `lis`. No DOL table maps a
  board to its archive. A cloned REL keeps using the original board's archives until those are
  rewritten.

## Tables indexed by board number (main.dol)

| Table | Address | Entries | Lookup | What happens with board 11 | Refs |
|---|---|---|---|---|---|
| Board music (`boardMusData`) | `0x802651F8` | 11 × `{board, day, night, flag}`, ends -1 | searched | no music; needs a row, so the table must move | 14 |
| Orb lists (`mbCapListRead`) | `0x80267D20` | 11 × `{board, capsule file 0x14004A+n}`, ends -1 | searched | **loads file -1**; needs a row | 1 |
| Camera (`mbCameraInit`) | `0x8021A2E0` | 11 × `{board, 5 floats}` | searched, falls back to entry 0 | fine: every entry is the same | – |
| Orb throw (`CapEffThrowCreate`) | `0x802679B4` | 11 words | clamped to 0..10 | fine | – |
| Pause logo (`logoFileTbl`) | `0x8021A828` | 11 board.bin sprite ids | **unchecked** | reads the floats after the table | 2 |
| Opening name card (`telopFileTbl`) | `0x8021AAF0` | 27, board names at `boardNo+16` | **unchecked** | index 27, past the end | 3 |
| Welcome message (`welcomeMesTbl`) | `0x80265D20` | **6** message ids (0x2C0000–5) | **unchecked** | index 11, past the end | 1 |

"Refs" counts `lis`/`addi` pairs on the table's own label. The real number is a minimum, because
`dtk` merges some tables into a bigger label that code reaches as base + offset (the sound group
table is one example).

## Tables indexed by overlay number (main.dol)

| Table | Address | Entries | What a new board overlay needs |
|---|---|---|---|
| Sound groups (`sndGrpTable`) | `0x8022B810` | 121 × 0x14, ends -1 | a row (boards use groups 22–27). Without one it falls back to MG601's group, so board sounds are wrong. Referenced as `lbl_8022B758+0xB8` in `HuAudDllSndGrpSet` (`0x800413EC`) and 4 times in `instDll`. |
| Footsteps (`stepTbl`) | `0x8022ED58` | 112 × `{ovl, type}`, ends -1 | optional; there is a default |
| Win voice (`charman.c`) | `cmpwi` at `0x80059000` / `0x8005900C` | range `0x7B`–`0x82` | outside the range the win voice plays on the board (cosmetic) |
| Win length (`charman.c`) | `cmpwi` at `0x80061784` | w01 only | nothing |

## Save data (GwCommon, 0x80283550, 0x5D0 bytes)

- **The arrays.** `charPlayNum[11][14]` (+0x54), `boardPlayNum[11]` (+0x188),
  `boardMaxStar[11][14]` (+0x19E) and `boardMaxCoin[11][14]` (+0x2D2). The only spare bytes are
  `unk5C8[8]`.
- **Who writes them.** Only `mdpresultdll` writes records, and only through two functions:
  - `GWBoardPlayNumAdd(board, 1)` (`fn_8003CB20`, called at `.text 0x1048C`). With board 11 it
    writes `boardPlayNum[11]`, which is `boardMaxStar[0][0]`.
  - `GWCharPlayNumInc(char, board)` (`fn_8003CC14`, 3 calls). With board 11 it writes
    `charPlayNum[11][c]`, which is **`boardPlayNum[c]`, the play counts of every board**.

  The max-star and max-coin setters are never called.
- **Who reads them.** The options records screen (`optionDll`) loops over boards 0–5 only, so a
  board 11 record would never be shown.
- **Spare bit.** `map7Unlock` (+0x428, bit 6) is written at start-up but never read. It could act
  as the new board's unlock flag.
- **Plan:** don't change the save format. In `mdpresultdll` `fn_1_56C` (`.text 0x590`), map
  board 11 to another number when it is copied into its work struct, or skip both record calls.

## Party menu and results (RELs)

- **`mdpartydll`, board select** (mapped 2026-11-25 for Pagoda Peak's step 2d; addresses are `.text` /
  `.data` / `.bss` offsets in the vanilla REL, as in `build/GP6P01/mdpartydll/asm/`). The REL runs the whole
  party menu (players, board, rules), so most of its tables are shared between screens, and **every
  per-board slot is already full**.
  - **Cursor:** the halfword at `lbl_1_bss_9F4+4`. Only `fn_1_188BC` moves it: left subtracts 1 and adds 6
    below 0, right adds 1 and subtracts 6 at 6 (`.text 0x18960`-`0x18AFC`). Readers: `fn_1_918`, `fn_1_EBE0`,
    `fn_1_16840`, `fn_1_1722C`, `fn_1_18010`, `fn_1_19510`, `fn_1_19C30`, `fn_1_305E0`, `fn_1_39E00` (found by
    the label; a reader through a register loaded far earlier would be missed).
  - **Launch and bookkeeping:** `party_board_dlls` (rodata +0x7C) maps the 6 cursor positions to overlays
    `0x7B`-`0x80`, copied to the stack in `fn_1_129C` and `fn_1_2DF8C` (both hooked by `clone_board`).
    `fn_1_918` writes the cursor into `GwSystem+8` (low 5 bits, the board number) and `GwCommon+0x42E`
    (`lastBoard`); `fn_1_305E0` sets the cursor back from `boardNo` after a game.
  - **Loader** `fn_1_2E380` (and `fn_1_E78C`, which reloads): 32 sprite animations from the data numbers at
    `lbl_1_data_1C` into `lbl_1_bss_93C` (0x80 bytes, full); 41 texture animations from `lbl_1_data_800` into
    `lbl_1_bss_800` (0xA4, full); **25 copies** of one 3D model (`mdparty` file `0x50`; `0x4F + language` in
    other languages) in `lbl_1_bss_288` (records of 0x38: model id, then 4 `Hu3DAnim` ids at +2..+8; 0x578,
    full), each with 4 texture slots. A data number listed in `lbl_1_data_BC8` is per language: file + language
    - 1 (`GwCommon+6` bits), 5 languages. All `mdparty` files are dir `0x9F`.
  - **Model copies:** 0-10 other screens, **11-16 the 6 board icons**, 17-20 the player icons (character faces
    `0x57`-`0x61`, CPU `0x51`), 21-24 the rule options (turns etc.).
  - **Per board i (0-5), the parts a 7th board needs:**
    - Icon: model copy 11 + i, its 4 texture slots set to texture animation 12 + i = `mdparty` file `0x63` + i
      (512x256 RGB5A3, 2 banks: the board's octagon by day and by night); slots 1 and 3 use bank 1
      (`fn_1_19510`, `fn_1_D19C`/`fn_1_D244`). A locked board (`lbl_1_data_C66[i]` != 1) shows texture 40
      (`0x9F00BD`) on slots 2-3.
    - Half-disc picture behind the menu: sprite animations 3 + 2i (day) and 4 + 2i (night) = files `0x06` + 2i
      and `0x07` + 2i (256x256), set on the `lbl_1_bss_8` object's model (`fn_1_EBE0` `.text 0xFBE8`,
      `fn_1_19C30` `0x1A4B8`). Animations 1-2 (files `0x04`/`0x05`) are the sun and moon shown otherwise.
    - Name banner: sprite group 1 (6 members, member count in `lbl_1_data_9C`), member i = sprite
      `lbl_1_data_C0` entry 1 + i (rows of 0x20: group, member, animation, priority, **bank**, then position,
      scale), animation 15 + i = files `0x32` + 5i + language - 1 (248x48, "Towering Treetop" on a wooden
      plank). `fn_1_188BC` shows member = cursor and hides the rest. Group 2 is the arrows (file `0x2B`).
    - Description: message `0x20009` + cursor (bank 2 records 9-14; `fn_1_39E00`, `.text 0x3A16C`,
      `0x3A5D0`). **Bank 2 records 15-17 are empty**, so cursor 6 already lands on a free record (15). Bank 2
      records 0-8 are the 9 board names (6 party, 3 solo).
    - Unlock: `lbl_1_data_C66` has 7 halfwords; `fn_1_354` sets 0-4 to 1, 5 (Clockwork Castle) from
      `GWBankFlagGet(0x33)`, and never sets 6. `lbl_1_data_E5E` (6 halfwords, read in many functions, e.g.
      a sound when moving) is not identified yet.
    - Positions: `lbl_1_data_8A4` (vec3 rows, shared with the other screens: rows 13-66 belong to them):
      row 1 + i where icon i rests (x -200 to 200 step 80, y 325 / 225 alternating: two staggered rows) and
      row 7 + i where it moves when selected (y 275). The arrows are at x +-340 (rows 37-40).
  - **Loops and bounds on 6:** `cmpwi 6` in `fn_1_19510` (twice), `fn_1_188BC` (wrap and the icon loop),
    `fn_1_19C30`; the functions indexing model 11 + i (`fn_1_184C8`, `fn_1_187E8`, `fn_1_18F9C`,
    `fn_1_19208`, `fn_1_1A618`) still need their bounds checked. The loaders loop `cmpwi 0x19` (models),
    `0x29` (texture animations), `0x20` (sprite animations), `0x3A` (sprites), `0x11` (sprite groups).
  - **Built on this map:** `apply_party_pages_patch.py` (pages of six; Pagoda Peak on page 2).
  - **Not in `mdpartydll`:** MP7's board select art. MP7 `mdparty7.bin` 147-151 are its mode-select sprites
    (not boards); MP7 `board.bin` 77-82 are round board emblems with Japanese names (Pagoda Peak is 78). An MP6
    octagon and half-disc picture for Pagoda Peak have to be made, e.g. from a Dolphin screenshot of its map.
- **`mdpresultdll`, party results.** Two tables have only 6 boards: `result_counts` (data +0x3A8,
  s16) and `result_sprites` (data +0x3B4, 0x60 bytes each).
- **Messages.** Board text is one bank per board: W01–W06 are banks 0x2F–0x34. The loader reads
  the bank count from the file (`HuWinMesDataPtrGet`, `window.c`), so a new bank can be appended
  with `tools.lib.messages`. **Done (step `pagoda_board`):** Pagoda Peak's text is bank 0x4B, after
  the 75 vanilla banks (`set_bank`); `splice_bank` keeps it when an earlier bank owner re-runs.

## This mod's own assumptions

- `apply_whomp_rich_patch.py` gates on boardNo 2 (Faire Square).
- Star Trap appends itself to any orb list with at least 5 entries, so a new board's list gets it.
- Everything else the mod does is scoped by the board's own REL, archive or message bank.

## Room in the DOL

- All 11 data section slots are used in the build (15–17 by this mod), but **text slots 2–6 are
  free**. The DOL loader copies text and data sections the same way, so moved tables can go in a
  new section in a text slot.
- A new section must start at `0x802F9DA0` and raise the arena clamp at `0x80004D18`, the same
  way as the existing ones (patching guide, section 4).

## Clone board (confirmed in game, 2026-11-24)

Step `clone_board` (`tools/patches/apply_clone_board_patch.py`) runs board 11 from
`dll/w07dll.rel` as a copy of **Snowflake Lake** (w04, board 3), using an alias instead of moving
tables.

- **The alias.** Every read in `board_tables.BOARD_NO_READS` (9 in the DOL, 7 in `mdpartydll`, 1 in
  `mdpresultdll`) goes through a stub that turns 11 into 3. So board 11 uses Snowflake Lake's music,
  orb list, pause logo, name card, welcome text and capsule events.
- **Results and records.** Board 11's results and records count under Snowflake Lake, so the save
  arrays stay in range.
- **The board file.** `w07dll.rel` is `w04Dll.rel` with `li r3,11`. It uses w04's archives and
  message bank.
- **Overlay and sound.** Overlay slot 0x70 points to it, and its sound-group lookup maps 0x70 to
  0x7E.
- **Code.** DOL section 18, in text slot 2 at `0x802F9DA0`.
- **Launching it.** Page 2 of the board select (`party_pages`) launches overlay 0x70. Before page 2
  existed, the test aid `clone_board_menu` pointed Snowflake Lake's icon at it.
- **How to tell it apart.** The clone looks the same as Snowflake Lake. Dolphin's OSReport log
  shows `DLLStart 112` instead of 126.
- **Why Snowflake Lake rather than w01.** The mod doesn't touch it, its icon is the one the test
  borrows, and the DOL's `boardNo == 3` events are its own.

**Pagoda Peak presentation** (step `pagoda_peak`): board 11 has its own music (MP7 track 12 as
track 111), logo (pause logo and name card, `board*.bin` file 189) and welcome text (0x2C0013),
all taken from the user's Mario Party 7 disc. Confirmed in game (2026-11-24): name card, welcome
text, music and pause logo. The board music, pause logo, name card and welcome
tables moved into section 18 with a board-11 entry. Those five reads no longer alias, and
everything else still borrows Snowflake Lake's.

**Pagoda Peak's own slots** (step `pagoda_board`, 2026-11-25): its archive `w07.bin` (dir 261), message
bank 0x4B, its own orb list (row {11, `0x140057`} in the orb list table moved to section 19; the
list is `capsule.bin` entry 87) and its results label (bank 6 of `mdpresult.bin` files 89–93, picked
by a stub on mdpresultdll's `HuSprBankSet` call). The results tables (`result_counts`,
`result_sprites`) are the same for boards 0–4, so the alias to 3 shows the right categories; the save
records still count under Snowflake Lake (the user's choice).

**Orb list rows** (`capsule.bin` 0x4A-0x54 and entry 87): 16 bytes, an orb id (0xFF ends the list), 3 prices,
then 12 signed weights (read with `extsb`, so at most 127), 4 per use, indexed by the player's rank (0-3, a
2-bit field at `GwPlayer` +9): columns 0-3 the orb spaces in the first half of the game and 4-7 in the
second half (`mbCapMasuNextGet`, `fn_801CAEE4`), columns 8-11 the shop (`CapShopNextGet`, `fn_801CB5A4`,
which halves the weight of an orb the player already holds and offers each orb once per visit). A 0
weight means never in that situation. MP7's rows use the columns differently.

The 7th icon is page 2 of the board select (`party_pages`, see "Party menu and results" above), and
board 11 runs its own C board REL. To add another board after Pagoda Peak, follow
[adding-a-board.md](adding-a-board.md).

Open question: whether anything indexes by overlay number with a table sized `DLL_MAX`. Slots 0x70 and
0x79 avoid that; a board on a new overlay number past the table would not.
