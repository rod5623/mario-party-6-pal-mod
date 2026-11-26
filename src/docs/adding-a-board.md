# Adding a party board

How to add a new party board to the board select without replacing one of MP6's six. Pagoda Peak
(board 11, ported from Mario Party 7) is the worked example: every step below names the Pagoda Peak
script that did it, so read that script's docstring next to this page.

Read first: [patching-guide.md](patching-guide.md) (caves, sections, message banks, archives) and
[board-tables.md](board-tables.md) (every table and code site that hard-codes the set of boards).
The Pagoda Peak handoff, with its research record and engine facts, is
[plans/pagoda-peak/README.md](../../plans/pagoda-peak/README.md).

Paths are relative to `src/`. Addresses are PAL (GP6P01).

## 1. What a board is made of

| Piece | Where the game finds it | Pagoda Peak (board 11) | The next board |
|---|---|---|---|
| Board number | `GwSystem+8`, 5 bits, set by the board REL's `mbObjectSetup(n, ...)` | 11 | 12 (up to 31 fit) |
| Board REL | overlay table `0x8022D404`, slot = the board select's DLL table entry | slot `0x70` → `dll/w07dll.rel` | slot `0x79` (the last unused stub); then the table has to move (one reference, `0x80005A10`) |
| Sound group | `HuAudDllSndGrpSet` by overlay number | stub maps `0x70` → `0x7E` (Snowflake Lake's group 25) | another case in that stub |
| Archive | data dir table (moved to section 19) | dir 261, `data/w07.bin`, day and night alike | dir 262, e.g. `data/w08.bin` (see section 2: the table has no room left in place) |
| Text | one message bank | bank `0x4B` | bank `0x4C` |
| Music | board music table (moved to section 18) | `MP6_Str.pdt` track 111 | track 112 |
| Pause logo and name card | `logoFileTbl`, `telopFileTbl` (moved to section 18) | `board*.bin` file 189 | file 190 |
| Welcome line | `welcomeMesTbl` (moved to section 18) | bank `0x2C` record 19 | record 20 |
| Orb list | orb list table (moved to section 19) | row `{11, 0x140057}`: `capsule.bin` entry 87 | a row `{12, ...}`; `capsule.bin` entries from 89 |
| Board select | `party_pages` `EXTRA_BOARDS` | page 2 slot 0; `mdparty.bin` files 254 (empty slot), 255-257 | page 2 slot 1; files 258-260 |
| Select banner | that slot's banner files, one bank per page | slot 0's files `0x32`-`0x36`, bank 1 | slot 1's files `0x37`-`0x3B`, bank 1 |
| Select description | bank 2 record `15 + e` (e = index in `EXTRA_BOARDS`) | record 15 | record 16 (records 15-17 are empty in vanilla; a fourth extra board needs records appended) |
| Results label | bank of `mdpresult.bin` files 89-93 | bank 6, picked by a stub on `HuSprBankSet` | bank 7, and the stub needs a second case |
| Everything else indexed by board | the `clone_board` alias (11 → 3) | Snowflake Lake's entry, including save records | an alias too (section 2) |

## 2. What already scales and what is fixed to board 11

Some of the board-11 work was written for any number of extra boards. Some was written for one board,
and has to be generalised before a board 12 goes in. Do that first, as its own change, and check that
Pagoda Peak still plays the same.

**Ready for more boards:**
- **The board select** (`apply_party_pages_patch.py`). Add an `ExtraBoard` row to `EXTRA_BOARDS`.
  Pages, the cursor walk, the launch, "play again" and the description already handle any count.
  Mind the memory: every extra board's three pictures load when the party menu opens. Keep them C8,
  as `tools/pagoda/select_art.py` explains.
- **Message banks.** `messages.set_bank` appends one bank after the existing ones, so a step that runs
  after `pagoda_board` can add bank `0x4C`.
- **Disc files.** `tools/scripts/build_iso.py` keeps any new file in `root/`.
- **Text slots for new DOL sections.** Slots 4-6 are free. The next section starts at `0x802FB1A0`
  (the end of section 19) in text slot 4, and raises the arena clamp the same way.

**Fixed to one board, to generalise:**
- **The board-number alias** (`apply_clone_board_patch.py`). Each stub is
  `cmplwi cr7,rd,11; bnelr cr7; li rd,3`. The simplest change that covers every future board is
  `bltlr` instead of `bnelr`: every board from 11 up borrows Snowflake Lake's entries and save records.
  `party_pages` already writes the extra board's overlay into DLL table entry `ALIAS` (3), which fits
  that choice. A board that needs a different donor needs a lookup in the stub instead.
- **Overlay slot and sound group** (`OVERLAY_SLOT`, `SOUND_STUB`, `clone_board`). One slot, one case.
  `0x79` (`storyresultdll`, a 156-byte stub nothing loads) is the only other free slot.
- **Section 18 tables** (`apply_pagoda_peak_patch.py`). The music, pause logo, name card and welcome
  tables are sized for board 11 (`NEW_BOARD_NO + 1`) and packed back to back, with 0x140 bytes free after
  them (`0x802FA060`-`0x802FA1A0`). Board 12 needs one more entry in each, so they have to move again,
  into the new section.
- **Section 19** (`apply_pagoda_board_patch.py`). The data dir table ends at `0x802FA9F8` and the orb
  list table starts at `0x802FAA00`, so dir 262 doesn't fit in place. **Don't move anything else in
  section 19:** the Cannon orb's hook words (`0x802FAAA0`-`0x802FAAA8`) are hard-coded in
  `src/REL/w07Dll/pagoda.h`. Copy the data dir table into the new section instead and re-point the same
  10 sites (3 `lis`/`addi` pairs, 7 base-register reads; the list is in the docstring). The orb list
  table has room for 3 more rows before the label stub at `0x802FAA80`.
- **The results label stub** (`LABEL_STUB`). It picks bank 6 for board 11 and has no room for another
  case. Put a longer stub in the new section and re-point the `mdpresultdll` hook to it.
- **`mdparty.bin`.** `pagoda_board` rebuilds it from the original every run ("no other step writes
  it"). A second board would wipe Pagoda Peak's pictures, or the other way round. Move the writing into
  one shared step that loops over `EXTRA_BOARDS`, with each board's art coming from its own module.
- **The REL build.** `tools/pagoda/build_pagoda_rel.py` hard-codes `src/REL/w07Dll/` and `w07dll`.
  Take the source folder and module name as parameters. `pagoda_board` installs the result
  (`install_rel`) over the clone REL that `clone_board` writes, and a new board's step can do the same.
- **`board_tables.NEW_BOARD_NO`** is a single number. Replace it with the list of extra board numbers
  (or read them from `EXTRA_BOARDS`).

## 3. Steps, in order

Each step below is one patch script (or a section of one) with its own Dolphin test. Make the board
reachable and stable first, then add content.

1. **Slot.** Board number, overlay slot, sound group and alias (`clone_board`). Start with a clone of
   an existing board's REL with only `li r3,N` changed (`.text+0xCC`, before `mbObjectSetup`). That
   proves the slot before any new code exists. Check Dolphin's log for `DLLStart <overlay>`.
2. **Board select.** An `EXTRA_BOARDS` row, the icon, half-disc pictures, banner bank and description
   (`party_pages`; the art is `tools/pagoda/select_art.py`). Test: launch, "play again" and backing out
   of the rules screen.
3. **Presentation.** Music, logo and welcome line (`pagoda_peak`). Music is appended to
   `MP6_Str.pdt` with `tools.audio.pdt`. MP7's PDT format is the same. Pagoda Peak's logo is a
   256x240 C8 sprite; MP6 shows the same sprite as the pause logo and the opening name card.
4. **Archive and text.** The data dir, the board's archive and its message bank (`pagoda_board`).
   Keep one list of the archive's files (`FILES`), a header of `FILE_*` defines that matches it, and a
   test that checks both (`tests/test_pagoda_files.py`). Store every file zlib-compressed
   (`mpdata.pack_file`).
5. **Spaces.** File 0 of the archive is the space table: 46-byte records, LZ type 1, the same in MP6
   and MP7 (`tools/pagoda/spaces.py` has what each field means and what to fix). Dump any board's table
   with `python -m tools.scripts.masu_dump w05`. Exactly one colour-0 node has type `0x8000` (the start).
   Colours 1-6 count as spaces in party mode. MP7's colour 11 doesn't exist in MP6.
6. **Board REL in C** (section 4 below): the skeleton first, then the Star, then one event per file.
7. **Orb list and results label** (`pagoda_board`).
8. **Board-only orbs** (optional; Pagoda Peak's Cannon). Orb ids with an EMPTY row in the orb data
   table (`0x80266BDC`) are free. The orb's event stubs jump through hook words that the board REL sets
   at init and clears at kill and in `_epilog`, so the orb does nothing on other boards.

Then add each new step to `STEPS` in `tools/apply_all.py`, after `pagoda_board`, with a comment
saying why it goes there. Add it to the dependency table in `tools/README.md` and test it with
`--only` from a fresh build, as AGENTS.md says.

## 4. The board REL in C

`src/REL/w07Dll/` is the template. `board.c` is the skeleton every MP6 party board REL shares:

- `_prolog` sets `GwSystem.partyF` and calls `mbObjectSetup(BOARD_NO, BoardInit, BoardKill)`.
- `BoardInit`, in this order: sound group, `mbObjDirSet(dir, dir)` (one archive for day and night),
  `mbMasuInit(spaces)`, masu layer 1 if the board has one, `mbCapThrowColCreate`, the map model,
  `mbScrollInit` (view-board area mesh), `mbLightFuncSet`, `mbev_ShopExInit`, the opening hooks and
  cameras, each event's init, `mbev_MasuHatenaSet`, a frame object that deletes itself on
  `mbExitCheck`, then `HuDataDirClose`.
- `BoardKill` unhooks children before it frees them, then kills each event and the map.
- `_epilog` clears any hook word the REL put in the DOL.

The board sells its own Star: no MP6 board leaves that to the engine (`star.c`).

Build: `python -m tools.pagoda.build_pagoda_rel` (mwcc with `p01_names.h`, then `dtk rel make`
against `build/GP6P01/main.elf`; module id 1, like every board REL). It never runs ninja, so it's
safe after `mgtable_move`. Grep `build/GP6P01/include/p01_names.h` for a function's real name before
you declare it.

Engine facts that cost a test round each (details in the Pagoda Peak plan, "Key facts"):

- **Close the board archive after every model made mid-game** (`HuDataDirClose`). Reading one file
  loads the whole archive into the DVD heap until it's closed, and a later event runs out of memory.
- **`mbSinRad` and `mbCosRad` take radians.** MP7's matching functions take degrees.
- **The PAL `HU3D_MODEL` layout doesn't match the decomp's `hu3d.h`.** Read models through raw
  offsets, as `pagoda.h` does. `Hu3DData` is `lbl_802DDAA8` in PAL.
- **The move-end hook** gets `(player, masuId)`. Return 0 to count the step. The move stops when
  `GwPlayer.moveNum` reaches 0.
- **The "?" hook** returns 1 when no event ran.
- **An event that moves a player outside a move** turns `mbPlayerColSnapPlayerSet` off around it.
  To run a space's event: turn phase `GwSystem+0x36` = 7, then `mbev_MasuStop(player, masu)`.
- **The board's saved state** is `GwSystem.boardWork`. Document which bits you use.
- **Extra player motions** go in each `<char>mot.bin` after file 125. Close them with
  `CharMotionDataClose`. Pagoda Peak's take files 126-129 (`pagoda_board`
  `write_char_motions`, which accepts only 126 or 130 files). A second board's motions go after those,
  and that check has to allow them.

## 5. Porting from another Mario Party

`tools/lib/mp7.py` reads the user's Mario Party 7 disc (`src/orig/GP7P01/` or `GP7P01.iso`).
MP6 and MP7 share the archive format, the HSF models, ANM sprites, the space record, the PDT music
format and the text codes, so most data copies over with small fixes:

- **Text:** `tools/pagoda/mp7_text.py` rewrites the record header and drops MP7-only icons.
- **Code:** MP7's board RELs can't run in MP6 (Route A was ruled out; see Experiment 2 in the plan).
  Read them and rewrite them in C. `python -m tools.scripts.mp7_rel_dis w02dll 0x100c4` disassembles
  an MP7 function with each call shown as its MP6 match. `mp7_rel_coverage` lists the MP7 calls with no
  MP6 match.
- **Motion numbers differ** between the games. MP6's slot → animation table is `.rodata 0x8021A3E8`.
- **Particles:** MP7's particle records use their own layout. Rebuild effects on MP6's `Hu3DParticle`.

Another game's disc would need its own reader like `mp7.py`, and its formats checked one by one.

## 6. Testing and deploying

- Run the chain with `python tools/apply_all.py --from <first board step>`, then copy the outputs into
  `root/` (the deploy table in `tools/README.md`, plus the new board's archive and REL) and run
  `python -m tools.scripts.build_iso`. The DOL panics at start-up if a data dir it lists is missing
  from the disc, so the new archive has to go in together with the DOL.
- After each new build, boot it and make a fresh Dolphin save state. A save state holds the old code
  in RAM.
- Each step's test should cover: page 1 unchanged and every vanilla board still launching itself;
  the new board from the board select; a full game through to the results; "play again"; the save
  records of the other boards unchanged.
- Only what the user has confirmed in Dolphin counts as working. Keep each script's status note
  current.
