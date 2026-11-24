# Castaway Bay (w05Dll) - investigation notes

Investigation only: nothing here has been patched or run in Dolphin. Everything below was read from `masu_dump`, the REL assembly and message bank 0x33; items marked **unverified** are inferences. Method and patch conventions are the same as Faire Square, see `boards/faire-square/faire-square.md` (build/deploy, caves, message editing, `apply_*_patch.py` pattern); they are not repeated here. `boards/castaway bay/map-screenshot.png` is the overhead map.

## Where things are
- REL: `src/build/GP6P01/w05Dll/asm/auto_00_00000000_text.s` (~35k lines). Listing columns: first = REL `.text` offset, second = file offset (`.text` offset + 0xDC). `src/config/GP6P01/rels/w05Dll/splits.txt` only lists the default sections. No C source.
- Space data: `root/data/w05.bin` (day) and `w05n.bin` (night), file 0. **Day and night are identical** (type, flags, kind and links all match for all 99 spaces). Dump: `cd src/tools && python -m tools.scripts.masu_dump w05` (CLI prints id, pos, type, flags, links; the space kind is the `extra` field of `masu_dump.load()`).
- Text: message bank 0x33 (51, 51 records, 0x330000-0x330032) in `messdata*.bin`. Pristine English copy at `src/build/GP6P01/files/mess/messdata_eng.bin`. A decoder is in the session scratchpad only (`dumpbank.py`); the record header is `00150003` etc. as in the Faire note.
- `GwSystem.boardNo`: **unverified**. Faire Square (w03) is 2 ("third board"), so Castaway Bay (w05) is probably 4. Check before writing any boardNo-gated DOL patch (see `FAIRE_SQUARE` in `apply_whomp_rich_patch.py`).

## Layout (positions -> screenshot)
Position x grows to the right of the screenshot and z grows downwards (checked against the pier loop at z about 4241 and the left island at x about -3400). y is height.
- **Right ruins island** (flat, y 96): ids 3-13, 30-38, 80-84, 88-89, 97-98, x 1300-4200, z 900-3150.
- **Top-right tower island** (y about 806): ids 1, 2, 5, 40, 77, 82, x 2300-3100, z -600..100.
- **Top cliff island** (y 300-1150): ids 39, 41-56, 67, 68, 74-76, 90, 91, 93, x -1900..1650, z -1600..-150.
- **Left jungle island** (y 6-250): ids 57-65, 79, 86, 87, x -3400..-1400, z 270..3200.
- **Bottom pier loop** (y -99..230, z up to 4241): ids 15-29, 66, 72, 85, 99, x -3200..-200.
- **Sea nodes** (y 96, x 780-1900, z 1460-2320): ids 92 (start), 94, 95, 30, 36, 98. These sit between the islands where the two boats are in the screenshot, so they are probably the boat waypoints (**unverified**).
- **Correction:** id 92 (flag 0x40) is NOT the player start; `fn_1_9528` (Rowdy River Rafting) scans for it, so it is the raft ride's anchor. The real start is unconfirmed (candidates: the right end of the pier chain 14 -> 78 -> 66 -> 16 -> 20 -> 19, where 19 forks to 85 or 21).
- Types 0x2000 (ids 4, 7, 14, 69, 70, 79, 88-91, 93, 96-99) with no links and kind 0 look like hidden markers/waypoints; type 0x8000 on 78 and 0x20 on 40 and 71 likewise. **Unverified.**

## Space kinds (`extra`)
1 blue: 45 spaces; 2 red: 8, 11, 24, 53, 56, 61, 77, 80; 3 "?": 12, 17, 36, 54, 60, 83; 4 miracle: 6; 5 duel: 76; 6 DK/Bowser (day/night): 9; 7: 30 (the boat space, flag 0x10); 8: 68, 72, 74; 9 item shop: 2, 27; 0 (no kind): the rest (markers, 18, 19, 22, 34, 46, 49, 57, 66, 67, 75, 92-95...). Meaning of 8 is unknown here (Faire Square's note lists 7-9 as "other").

## Flags and handlers
`fn_1_20F8` is registered with `fn_80179A1C` (`lbl_802DE700`, called by `fn_80176EA0` once the player has arrived: the real landing events). `fn_1_2238` is registered with `fn_80179A0C` (`lbl_802DE704`, called by `fn_80176C44` from the movement loop on EVERY step with the space just entered; r30 = player, r31 = space). (Faire Square's notes call the equivalents the other way round.) Flag 0x1 (ids 24, 32) is explicitly skipped by both (those spaces have their own handling elsewhere, **not yet found**). Mask bit = 31 - rlwinm field.

| flag | ids | handler | what it does (messages in bank 0x33) |
|---|---|---|---|
| 0x20 | 60 | landing `fn_1_E4A0` (0xE4A0, 0x1118 bytes) | **Ukiki "Coin Catch"** offer, msgs 24-29 ("Free coins? Sweet!" / "No..."). Calls `fn_8017E03C` (coins). |
| 0x8 | 12 | landing `fn_1_12D14` or `fn_1_13C30` (0x12D14 / 0x13C30), chosen by the day/night bit (`GwSystem+0x10` bit 0x40) | One is the **Mushroom Spirit** (msgs 30-39: pay respects, "Ask for the spirit's favor?", prize: orb / coins / nothing), the other the **Goomba Spirit** (msgs 31, 32, 40-46: swaps everyone's position, judgement). Which is day vs night is **unverified** (`12D14` = msgs 30-39, `13C30` = 31, 32, 40-46). |
| 0x2000 | 17, 36, 54, 83 | landing `fn_1_160D8` (0x160D8) | No bank 0x33 messages; uses roulette/camera style helpers (`fn_8016A288/A3B0`) and `fn_1_35F0`. Probably a "?" -> event/random-warp style handler (**unverified**). |
| 0x10 | 30 | passing `fn_1_42B4` (0x42B4) | Reads a byte through `lbl_1_bss_4`: 0 -> `fn_1_433C` (**DK's Riverboat**: buy a Star for 20 coins, "take you back to the start", msgs 1-11), 1 (or other) -> `fn_1_5900` (**Bowser's Battle Yacht**: Shadow Star, msgs 12-17, "send you back to the Start Space"). It is the per-ship event; the ships swap when someone stops on them (msg 49). |
| 0x400 | 67 | passing `fn_1_8FC0` (0x8FC0) | Stands the player still first (`fn_801565EC`), no bank 0x33 messages (uses banks 0x1B/shared). Unknown; position (876, 706, -984) on the top cliff island (**unverified**, maybe a gate or the pipe at the top of the screenshot). |
| 0x2 | 46 | passing `fn_1_9528` (0x9528, 0x1B50 bytes) | **Rowdy River Rafting** (msgs 19-22: rent a raft for 10 coins, "view board"), runs the raft ride (`fn_1_C398` = Bowser cannon, msg 23) with the 0x40 start scan; also uses `fn_1_B078`, `fn_1_7AF8`, `fn_1_D390`. |
| 0x800 / 0x1000 | 94 / 95 | `fn_1_2324` (0x2324) | Small (0x148) helper that tests these bits and calls `fn_80174694`/`fn_80176F28`; probably the ship path/anchor lookup (**unverified**). |
| 0x80 / 0x100 / 0x200 | 56 / 55 / 53 | no landing/passing handler | Used by a mask scan at `.text` 0xCE60 (`fn_80176FCC & r0`), likely ship or raft dock markers (**unverified**). |
| 0x40 | 92 | - | start |

Also: `fn_1_1FB8` shows msg 48 "Move the ship"; `fn_1_35F0` shows msgs 49-50 (ship swap and "lose a Star or coins" warnings). `fn_1_21D8` calls `fn_1_3308` and `fn_1_3540` (event-handler registrations, unexamined).

## Message bank 0x33 index
0-11 DK's Riverboat (Star for 20 coins; 6-11 is the alternate wording); 12-18 Bowser's Battle Yacht; 19-23 Rowdy River Rafting and the cannon; 24-29 Ukiki Coin Catch; 30-39 Mushroom Spirit (and result lines 37 orb, 38 nothing, 39 "%d coin"); 40-46 Goomba Spirit position swap; 47-50 ship help text. English only decoded; other language files have the same bank layout.

## Candidate patch points (analogues of the Faire Square work)
- New events can reuse the Faire Square trick: relocate a `bl` at the end of `fn_1_20F8` (landing) or `fn_1_2238` (passing) to a DOL cave (module-0 call through `battle_port.add_calls`), free a flag bit and tag a space in `w05.bin` and `w05n.bin`. Free flag bits: 0x4000, 0x8000 (unused in the table), and any space with flag 0x0.
- Kind edits (blue -> DK/Bowser/miracle) only need the kind halfword in both board files (see `apply_faire_square_dk_bowser_space_patch.py`).
- "Return to start" already exists via the two ship events (ids 30, DK/Bowser text); `fn_80179164(-1, 0x40)` finds id 92.
- Free caves and the `NEW_BASE` region are shared with the Faire Square patches (DOL-wide, not per board). Check the Faire note's "Free DOL cave space" list before choosing any address.
- `apply_all.py` currently has Faire-specific scripts that gate on boardNo 2; new Castaway Bay scripts must gate on its boardNo.

## Open questions for the next session
1. Confirm `boardNo` for Castaway Bay (4?).
2. Which of `fn_1_12D14` / `fn_1_13C30` is day and which is night (they read the day/night bit but the table is identical).
3. What flag 0x1 (ids 24, 32; red space 24) does, what `fn_1_160D8` (0x2000) does, and what `fn_1_8FC0` (0x400, id 67) does.
4. How the two ships move and swap (`lbl_1_bss_4` byte, ids 30/94/95, flags 0x80-0x200).
5. Confirm the ship/space-to-screenshot mapping by looking at the ship code or in Dolphin.
6. Choose the modifications (e.g. new events on blue spaces, changes to the Ukiki, Spirit or ship events).

## Wheel o' Fortune scaffolding (`src/tools/patches/apply_castaway_wheel_patch.py`, not run in Dolphin)
- Fires when any player enters **space 20** (from 16, pier right end, before the fork at 19) on every pass, automatically: hold the player, "Time for the Wheel o' Fortune!", 4-slice wheel (25% each), then a placeholder line for the slice the arrow landed on. Outcomes are stubs; slice icons are Faire Square's (gold Star, Super 'Shroom, dark Star, Bowser).
- Trigger: flag 0x4000 on space 20 in `w05.bin`/`w05n.bin` (backups `backups/w05*.bin.bak_before_castaway_wheel`). Hook: w05Dll `.text` 0x2300 (`li r3,0`, common exit of `fn_1_2238`) -> module-0 call to the DOL cave `0x802307E0` (message routine `0x802307A0`, floats at `0x80230910`) in the dead old MgDataTbl. Text: bank 0x33 records 51-55, speaker 0xF (the Spirits', placeholder).
- Reuses Faire's spin routine (`0x80230340`) and DOL roulette support, so it needs `wheel_of_fortune` and `luck_wheel_rewards` first; it is the last step in `apply_all.py`.
- **Floating wheel model (built, not run in Dolphin):** a custom HSF (`src/tools/lib/hsf_build.py` -> `assets/castaway_wheel.hsf`: a thin double-sided disc, radius 40, 128x128 CMPR pie texture gold/green/purple/red) appended to `capsule.bin` as entry 86 = data number `0x140056` (after the Star Trap orb's entry 85, so `star_trap_orb` must run first). Created at board init: the last call of `fn_1_F4` (`.text` 0x1D34, `bl fn_8017461C`) is retargeted to cave `0x80230A60`, which runs `0x80230940` (model create `fn_801687F4(0x140056,0,0)`, layer 3 `fn_80168F60`, position `fn_80169064` from the table at `0x80230AC0`, then an object-manager callback `0x802309E0` via `fn_8003AB3C(lbl_802DE5C8, 0x104, 0, 0, -1, cb)`, the same way the board and the orb spaces do) and then makes the original call. The callback turns the model about the vertical axis 2 degrees per frame with `fn_80169328` and deletes itself when `fn_8014A544` (exit request) is nonzero. Position (-919, 251, 4241) = above space 20 (the second blue space), 225 above the pad (constants `WHEEL_POS`, `SPIN_STEP` in the script).
- HSF layout notes: the format is documented by `mp6-repo/.../hsfload.c` and `hsfformat.h` (sections, sizes: material 0x3C, attribute 0x84, object 0x144, bitmap 0x20, face 0x30; no skeleton so normals are s8 triples; bitmap data must start 32-byte aligned). `hsf_build.check()` re-does the loader's offset checks. The orb-space model for reference is `0x140021` (created by `fn_8019A6F0`, hidden with attr 0x40000001 until needed; ours is left visible).
- **Shared with E. Gadd's Garage:** `apply_egadd_wheel_patch.py` reuses the spin cave `0x80230B00` and the random orb routine `0x80231040`, and builds its own copies of the other caves through the (now parameterised) builders here. Changing those two caves changes both boards.
- Not done: real outcomes and icons; whether the walk animation resumes after the wheel (unverified); the model size, height and look are untested (tune `RADIUS`/`HALF_THICKNESS` in `hsf_build.py` and `WHEEL_POS`).

## Wheel outcomes (`apply_castaway_wheel_patch.py`, not run in Dolphin; the cave code was run in a unicorn PowerPC emulator with stubbed game calls)
Slices (equal odds for now, the roll is `FN_RANDOM(4)` in the pass cave; the wheel is forced to land on it): 0 random orb (Luck Wheel's one-orb routine `0x80230720`: Super 'Shroom / Sluggish / Flutter; "pockets full" line when the player holds the maximum; to be replaced by an orb list), 1 +5 coins, 2 -10 coins (clamped to the coins held; "no coins to fine" line at 0), 3 teleport.
- **Teleport** (`CAVE_TELEPORT 0x80230E00`): scans spaces 1..`fn_80176F28()`, keeps `fn_80177100(id)` in 3 ("?"), 4 miracle, 5 duel, 6 DK/Bowser except the current space (in Castaway Bay: 6, 9, 12, 17, 60, 76, 83; spaces 36 and 54 are excluded via `TELEPORT_EXCLUDED`), rolls `fn_8014CD78(count)`, then plays sound 0x5C1, gets the destination with `fn_80177378`, moves the player with `fn_8015BAD0`, writes `GwPlayer.masuId` (+0xC) and zeroes the steps byte (+0xA), waits 20 frames. The move loop (`fn_80154A60..`) re-reads masuId after the passing callback and, with 0 steps left, ends the move; the landing dispatcher `fn_80176A0C` then runs the destination's event (kind 3 -> `fn_80176EA0` -> the board's `fn_1_20F8`: Spirits on 12, Ukiki on 60, the 0x2000 cutscene on 17/36/54/83). Unverified: that these events behave when the player arrives by warp, that the camera follows, and that the instant relocation looks acceptable (no vanish/appear effect yet, unlike Faire's `fn_1_C5DC`).
- **Icons**: `make_castaway_wheel_icons.py` draws `assets/castaway_wheel_icon_{orb,plus5,minus10,warp}.png`; added as files 185-188 of every `board*.bin` (sprite ids 0x500B9-0x500BC). `CAVE_SPIN 0x80230B00` copies them into the shared Kane table (`0x80266314`) before the spin and puts Faire's ids back afterwards, so Faire Square is unaffected. `apply_wheel_of_fortune_patch.patch_archives` now drops any later files before re-adding its icon, so re-running it after this patch works.
- Text: bank 0x33 records 51-57 (intro, four outcome lines, pockets full, no coins).
- Cave map (dead MgDataTbl): show `0x802307A0`, pass `0x802307E0`, model `0x80230940`, turn callback `0x802309E0`, init hook `0x80230A60`, data `0x80230AC0`, spin `0x80230B00`, outcome `0x80230BE0`, teleport `0x80230E00`, icon ids `0x80231000`; all end before `0x80232744`.

### Orb slice pool
The orb slice gives one orb drawn evenly from Klepto (13), Mushroom (0), Thwomp (23), Warp Pipe (5), Podoboo (20) and Sluggish 'Shroom (2) (`ORB_POOL`, cave `CAVE_RANDOM_ORB 0x80231040`, which calls `fn_8015D6FC(player, id)`; the table of ids is at +0x50). The "pockets full" check before it is unchanged. The Faire Square wheel and Luck Wheel keep their own pool (Super 'Shroom / Sluggish / Flutter). Not run in Dolphin; whether placed-orb types (Klepto, Thwomp, Podoboo) behave when given directly like this is unverified.

### Change: slice 1 is now "lose a Star" (was +5 coins)
Slice 1 takes one Star with the game's popup (`fn_8015CE98` to check, the Faire wheel's Star routine `0x80230220` with -1; line "Ouch! You lose a Star!"; "No Stars to lose, lucky you!" when the player has none, record 58). Its wheel icon is Faire Square's dark Star (sprite `0x500A7`, the old "lose a Star" image), so only three new icons are added (files 185-187: orb, -10 coins, warp swirl; `castaway_wheel_icon_plus5.png` was removed). Bank 0x33 records are now 51-58. The "+5 coins" entries above describe the earlier version. Not run in Dolphin.

## Boo's house by day (`src/tools/patches/apply_boo_day_orbs_patch.py`, tested in Dolphin: works)
Boo's house is shared DOL code (`fn_801B16A8`, messages in bank 0x3B), so this applies to every board with a Boo house, not just Castaway Bay. Vanilla: by day (`GwSystem+0x10` bit 0x40 clear) Boo only says "Daytime is totally lame... Come back later" (record 0) and the event ends. The night menu (coins x5 / Star x40) is untouched.
- **Now by day:** "Want me to launch some orbs?" Yes/No (CPUs skip it: 5 orbs if they have 20 coins, else 3). Yes opens a menu: **3 orbs free**, or **5 orbs + 1 random orb in your pocket for 20 coins**. Under 20 coins: refusal line, menu again. The spare orb is one of Super 'Shroom / Sluggish / Flutter (the Faire Square Wheel of Fortune / Luck Wheel pool, routine `CAVE_ORB` 0x80230720 from `apply_luck_wheel_rewards_patch.py`, not the Castaway wheel pool). Pockets full: the 5 orbs launch, no spare orb. No or B: "maybe later".
- **Launcher:** a relocated copy of the Final Five Character Spaces routine `fn_802026F8` (the original is unchanged). Its fixed count of 10 (`cmpwi 0xA` at 0x80202824, 0x80202844, 0x80202A68) became `cmpw rX,r16`, with r16 = 3 or 5; the Final Five host character calls (`fn_801ECBC0`/`fn_801ECC84`) and host model calls (`fn_80168ED4`) are removed from the copy, and a dummy host block stands in for the host's data. The routine groups spaces as empty / holding another player's orb / holding the player's own, and draws from the first non-empty group, so empty spaces fill first and existing orbs are overwritten only afterwards (replacement itself, in `fn_801C4304`, inferred, not traced).
- **Hook:** DOL 0x801B1734 (`li r3,2`, start of the daytime message) -> `b 0x802311A0`; the cave ends with the displaced `bl fn_8000E144` and `b 0x801B3E7C` (the function epilogue). Runs in `fn_801B16A8`'s frame (r26 = event data, player = `0(r26)`).
- **Caves** (dead old MgDataTbl, after the wheel caves): show 0x80231100, launch wrapper 0x80231140, day 0x802311A0, dummy host block 0x80231360, launcher copy 0x80231400 (ends 0x80231860). The spare orb calls `CAVE_ORB`, which checks for a free slot itself.
- **Text:** bank 0x3B records 18-24 (ask, menu, no coins, launch, spare orb, pockets full, decline), English in every language file; speaker 0xA.
- Runs after `luck_wheel_rewards`, `castaway_wheel` and `final_five_odds` in `apply_all.py`.


## Broom space (space 26, `src/tools/patches/apply_castaway_broom_patch.py`, not run in Dolphin)
Faire Square's broom ride (w03Dll `fn_1_BDC8`, space 20 there; see `boards/faire-square/faire-square.md` "Broom space") brought to the bottom-left pier, option (c): the take-off is Faire's, the destination is ours.
- Space 26 is now kind 3 (green "?", it was blue) with flag 0x8000 in `w05.bin`/`w05n.bin`. **Status: the ride was tested in Dolphin by the user (2026-11-02, first version with random destinations): "seems to work".**
- Landing on it opens a choice window with only the three options, no question line (bank 0x33 record 59, speaker 0xF; the first menu version had "Where shall the broom take you?" above them): **Fans -> space 48** (blue, first space after the ladder on the top cliff), **Glory -> space 36** (the "?" by the boats on the ruins island; after the drop the cave calls the board's landing handler `fn_1_20F8(player, 36)`, found as the hook's return address - 0xC8, so its flag-0x2000 event `fn_1_160D8` runs), **Heart -> space 56** (red, stepping stones). Spots from `broom-spots.png`. B shows the menu again. CPUs pick at random, no text. Not yet run in Dolphin: the 3-option menu, the CPU pick, and Glory's event after a broom arrival (only the board event runs, not the main DOL's generic "?" landing steps).
- Ride: the player faces the front, the broom and its stand (Faire models w03 files 0x1B/0x1C, appended as w05/w05n files 46/47, created at board init moved by space 26 - Faire space 20 = (-359, -1025, 4802)) play their motions; jump at broom frame 148, hang from the hook `fook` from 166, carried until `CUT_FRAME` 226 along Faire's baked path (it heads +x/+z from the pier, i.e. towards the camera; unverified how that looks). Then three sparkles, the player hides, the broom fades out (30 frames), the player reappears 300 above the destination and drops onto it (`mbPlayerMoveMain`, 30 frames) with three more sparkles; `masuId` = destination, turn ends.
- Hooks: w05Dll `.text` 0x21BC (`li r3,1`, exit of the landing handler `fn_1_20F8`) -> `0x80232590`; `.text` 0x1D18 (`bl mbOpeningViewSet` in `fn_1_F4`) -> `0x80231EB0` (makes the call, then creates the models). The script re-points calls that a re-run of `mgtable_move` moved.
- Caves (dead MgDataTbl after Boo's house): `0x80231860` Faire's sparkle particle callback `fn_1_F744` copied out of w03Dll (relocations rewritten; the REL's ADDR16 relocation offsets point at the instruction's low halfword), `0x80231E10` its rodata, `0x80231EB0` init, `0x80231F80` ride, `0x80232590` landing (menu / CPU pick / Glory event), `0x80232690` data (offset, model ids, floats, "fook", destinations); ends `0x802326F0`. (The first, random-destination layout had landing at 0x80231EB0 and init at 0x80231F10; the script re-points hooks from it.) `apply_castaway_wheel_patch.py` accepts the menu record after its own records 51-58, so the wheel and broom scripts both re-run cleanly.
- Tested only in a unicorn emulator with every game function stubbed (scratch scripts, not in the repo): landing with/without the flag, the ride's call sequence and arguments, masuId, stack and callee-saved registers, init by day and night. The copied `fn_1_F744` was checked word by word against the w03 listing (15 calls, 48 rodata references).
- Unverified / to look at in Dolphin: the broom's flight direction and height from the pier (tune `CUT_FRAME`, or rotate the models later); the camera during the ride and after the jump to the destination; whether the broom is visible parked at frame 0 before the first ride (Faire leaves it alpha 0 after a ride, so it is invisible afterwards, as in Faire); memory for the two extra models; the board's generic "?" behaviour on landing.
- Interactions: the Castaway wheel's teleport slice picks kind 3-6 spaces, so it can now send a player to space 26; the arrival runs the landing handler, so a broom ride may follow (not tested). Add 26 to `TELEPORT_EXCLUDED` in `apply_castaway_wheel_patch.py` if that is unwanted.

## Spare change guy (space 100, `src/tools/patches/apply_castaway_spare_change_patch.py`, not run in Dolphin)
A beggar on the top cliff, where `spare-change-guy-location.png` points. Passing him (any player): "Spare change?" Yes / No. No or B: "So greedy." Yes: pay 5 coins (fewer than 5: "You're broke too? Never mind."), then one of five outcomes at equal odds (`fn_8014CD78(5)`):
- 0: an orb from Boo-away (31) / Mushroom (0) / Super 'Shroom (1), or a "pockets full" line;
- 1: 20 coins back;
- 2: "Got a bit more? Spare change?". Yes pays again and re-rolls; No: "So greedy.";
- 3: nothing, "Thanks, sucker!";
- 4: each other player pays the passer up to 5 coins (whatever they have).

CPUs answer Yes whenever they hold at least 5 coins, also in the outcome 2 loop (`mbComChoiceUpSet` 0x80170720 / `DownSet` 0x80170780). There is no speaker face (speaker -1, as vanilla uses at 0x8019A328).

**How "pass, never land" works.** The move loop `fn_801548D8` decrements the steps only when `fn_801771E4(id)` says the space's kind counts (tables `lbl_80265408` party / `lbl_80265460` story). Kind 0 never counts in either mode, is not drawn (`fn_8017512C`, sprite -1) and can never end a move. The raft (46) and Boo (67) nodes work the same way: kind 0 plus a flag handled by the board's pass callback `fn_1_2238`. The shop (kind 9) is uncounted in party mode only.
- **Space 100** is appended at (-1.5, 373.5, -164), halfway between 55 and 54, in both `w05.bin` and `w05n.bin`. It has type 0, kind 0, flag 0x10000 and one link, to 54. Space 55 now links to 100. Existing ids are unchanged.
- The path chooser skips spaces with `type & 0xA020` or with flags in `lbl_802DE8D4`; this board sets 0x1840 via `fn_801EF39C`. So 0x10000 is safe.
- The space table holds up to 255 spaces (0x7000 bytes per map), with at most 5 links per space. Backups: `backups/w05*.bin.bak_before_spare_change`.

**The guy** is a flat card that always faces the camera.
- It is built by `hsf_build.build_card`: a quad with object flag 1, which is `HSF_MATERIAL_BBOARD`; `hsfdraw.c` cancels the view rotation for such objects.
- Texture: 128x256 CMPR with 1-bit alpha; the default alpha compare drops clear pixels. It comes from `src/tools/assets/spare_change_guy.png` (the user's art, RGBA, transparent background). The image is scaled to fit and stands on the bottom edge.
- Until that file exists, a generated stand-in is used: `assets/spare_change_guy_placeholder.png`, a brown coat and hat.
- Current art (2026-11-03): a cartoon footballer in a red kit, supplied by the user. Their image had a painted checkerboard (RGB, no alpha), so it was cut out by flood-filling neutral greys and whites from the edges (the checker, the white sticker border and its shadow), stopping at the dark outline, then cropped (215x496, so 111x256 on the card).
- The card is file 48 of `w05.bin`/`w05n.bin` (data `0xEB0030` by day, `0xEC0030` by night). It is created at board init with layer 3, at `GUY_POS` (-60, 385, -225), on the ledge just behind the path. The first try, (-60, 350, -320), was not visible in the user's first Dolphin screenshot; it was probably behind the rock rim.
- Size: `GUY_WIDTH` x `GUY_HEIGHT` = 130 x 260 board units (was 100 x 200, about Waluigi's height; made 30% bigger for the footballer art). Tune all of these constants in the script.
- **Seen in Dolphin (user screenshot, 2026-11-02):** at (-60, 385, -225) the card shows, faces the camera, is cut out cleanly and stands on the ledge between spaces 55 and 54. At 65 x 130 it was smaller than Waluigi, so it was scaled up 1.5x.
- Re-running the script with new art replaces file 48.

**Hooks**
- Pass: w05Dll `.text` 0x2300 now calls `CAVE_PASS`. That cave calls the wheel's pass cave 0x802307E0 first, then tests flag 0x10000 on r31.
  - The REL had three relocations at 0x2300. Two pointed to 0x802F523C, the wheel's address moved by an `mgtable_move` re-run. The last one (correct) won.
  - All three now point to `CAVE_PASS`. The wheel script no longer adds its call when this chain is present.
- Init: `.text` 0x1C2C (`bl fn_801EF39C`, r3 = 0x1840) now calls `CAVE_INIT`, which makes that call and then creates the card. The wheel (0x1D34) and broom (0x1D18) init hooks are untouched.

**Code** lives in a new DOL data section 16 at 0x802F7DA0-0x802F8DA0. The dead MgDataTbl had only 0x54 bytes left. `OSSetArenaLo`'s clamp (`ARENA_CAVE` 0x80004D18) is raised to 0x802F8DA0, and `apply_mgtable_move_patch.py` now leaves a raised clamp alone.

| Cave | Address | Size |
|---|---|---|
| show | 0x802F7DA0 | |
| ask (Yes/No + CPU answer) | 0x802F7DE0 | |
| pass | 0x802F7E80 | |
| init | 0x802F7EE0 | |
| event | 0x802F7F60 | 0x20C |
| data (position, hold floats, orb pool) | 0x802F8260 | |

About 0xB20 bytes of the section are still free.

**Text:** bank 0x33 records 60-68. The outcome lines are the user's wording, spelled exactly as given (keep it that way):

| Record | Line |
|---|---|
| 60 | "Spare change?" (options: "Here, have 5 coins" / "No") |
| 61 | "So greedy." |
| 62 | "Found this in me back pockih" (orb) |
| 63 | "Your pockets are full? / Never mind, then." |
| 64 | "Guess what I got for you bud" (+20) |
| 65 | "Got a bit more for me mate?" (asks again; same options) |
| 66 | "Cheers for that good lad" (nothing) |
| 67 | "Lets tax the good lads HAHA" (everyone pays) |
| 68 | "You're broke too? Never mind." |

Lines after a newline are indented like the vanilla records. `OLD_TAILS` holds the two earlier versions so a re-run replaces them. The wheel and broom scripts accept these records on a re-run; re-run this script after either of them.

**Testing so far:** unicorn emulator only, with every game call stubbed. It ran No, B, Yes while broke, each outcome, the ask-again loop (Yes twice, No, and Yes while broke), the steal clamping (8/10/3/0 coins), a CPU with and without coins, a space without the flag (wheel only), and init. Stack and r14-r31 were checked.

**Unverified in Dolphin:**
- that walking 55 -> 100 -> 54 costs one step and looks right;
- that the custom HSF card loads, shows, faces the camera and cuts out cleanly (the wheel's custom HSF is also untested in-game);
- the card's position, height and ground contact;
- the Yes/No window with no face;
- the coin animations for four players in a row in outcome 4;
- memory for the extra 4 KB section.

## Bridge troll (space 39, `src/tools/patches/apply_castaway_troll_patch.py`, not run in Dolphin)
A green "?" action space on the bridge between the top cliff and the tower island, with a troll standing by it. Space 39 (1981, 716, -694) is the last blue space of the bridge (route: Boo's house 67, blue 42, blue 41, then 39; `action-space-troll-bridge.png`). It is now kind 3 with flag 0x20000 in `w05.bin`/`w05n.bin` (backups `backups/w05*.bin.bak_before_troll`).
- **Only when landed on:** only kind 3 spaces reach the landing handler `fn_1_20F8`, which runs after the move ends. The pass handler is not hooked for this flag, so walking over 39 does nothing.
- **Event** (human or CPU, no choice, equal odds, the line first, then the effect): 0 "pay the toll there good lad": 15 coins, or one Star (game popup) if under 15, or all their coins if no Star either; 1 "Those look delish man": all orbs removed (`fn_8015D8A4(player, 0)` repeated until it returns -1); 2 "i dont like messers on my bridge": back to the start, `fn_80179164(-1, 0x40)` = the flag-0x40 space (id 92, the same lookup the raft uses), moved like the wheel's teleport (position, `masuId`, steps 0); 3 "keep doing what you're doing there pal": nothing. **Unverified:** that 92 is where the ship events send you and a sensible start (it is a sea node linked to space 3).
- **Card (now the tax man):** `hsf_build.build_card`, 156 x 312 (20% bigger than the spare change guy, 130 x 260), file 49 of the w05 archives, art `assets/taxman.png` (cut out of `taxman.jpeg` by flood-filling the near-white background from the edges). It replaced the troll art (`troll-example.jpeg`, was 390 x 780); the constant names still say TROLL. Position `TROLL_POS` (2020, 735, -780): at -650 (first guess) he stood on the green space in Dolphin, so he was moved back (-830 was slightly off the bridge, so -780) (-z, away from the camera) to stand behind it on the deck; tune in Dolphin.
- **Hooks (chained, run this script last):** `.text` 0x21BC -> `CAVE_LAND` 0x802F82A0 (tests flag 0x20000, runs the event, then JUMPS to the broom's landing cave so it still sees `fn_1_20F8`'s return address); `.text` 0x1C2C -> `CAVE_INIT` 0x802F8300 (calls the spare change guy's init cave, then creates the troll). Event cave 0x802F8380 (0x1B4 bytes), data 0x802F87A0, all in DOL section 16. The wheel, broom and spare change scripts accept the troll's file, records and hooks on a re-run (and put their own hook back; re-run this one after them).
- **Text:** bank 0x33 records 69-72. The wheel's teleport slice may send a player to 39 (it is kind 3 and not excluded); the arrival runs the landing handler, so the troll then plays.
- **Tested:** unicorn emulator with game calls stubbed: all four outcomes, 20/15/14 coins, with and without a Star, 0 coins, 0/2/3 orbs, CPU, the landing cave with and without the flag (broom reached with the original LR, stack and r14-r31 intact). Full Castaway chain run twice (wheel, boo, broom, spare change, troll) without errors. **Unverified in Dolphin:** the card's position, size and cut-out, the toll/orb/warp visuals, the warp destination, and that nothing in the broom/wheel/spare change behaviour changed.
