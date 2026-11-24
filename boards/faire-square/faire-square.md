# Faire Square (w03Dll) - notes for the next session

Nothing here has been run in Dolphin yet unless stated (the Wheel of Fortune and Luck Wheel rewards sections below have been, see their status lines). Board = `GwSystem.boardNo` 2 (assumed from the file name w03; not confirmed - the Whomp patch depends on it).

## Where things are
- REL: `src/build/GP6P01/w03Dll/asm/auto_00_00000000_text.s`. Listing columns: first = REL `.text` offset, second = REL file offset (`.text` offset + 0xDC). Symbols/splits: `src/config/GP6P01/rels/w03Dll/`.
- No C source for board RELs, only dtk assembly. Gameplay changes are idempotent Python scripts in `src/tools/apply_*_patch.py` that patch built files in `src/build/GP6P01/` (see "Build / deploy").
- Text: message bank 0x31 (49) in `messdata*.bin` is Faire Square (Luck Wheel, Swap Fest, Star Exchange, Star Shuffle). Bank 0x29 (41) is the shared toll-gate Whomp's text.
- Space data: `root/data/w03.bin` (day) and `w03n.bin` (night), file 0 (LZ). Both have identical type/flags. Dump with `cd src/tools && python -m tools.scripts.masu_dump w03` (format documented in the script).

## Spaces
Space ids are 1-based (`fn_80176FCC(id)` = flags at masu +0x14, `fn_80176F84(id)` = type at +0x10, stride 0x70). Flags and their handlers:

| flag | handler | meaning | space id |
|---|---|---|---|
| 0x1 | `fn_1_2718` (landing, via `fn_1_1CD4`) | **Luck Wheel** (3-reel slot machine, messages 0x310000-0x31000B; earlier notes called this Star Exchange) | 16 |
| 0x4 | `fn_1_5908` (landing) | Star Shuffle | 54 |
| 0x2 | `fn_1_8F70` (passing, via `fn_1_1C30`) | **Swap Fest** (messages 0x31000C-0x31001D; earlier notes called this Luck Wheel) | 25 |
| 0x10 | `fn_1_BDC8` (passing) | **Broom ride** (top left; see "Broom space" below; earlier notes wrongly said Swap Fest) | 20 |
| 0x8 | new cave code (passing, via `fn_1_1C30`) | Double or nothing (see below) | 28 |
| 0x20 | landing hook at the end of `fn_1_1CD4`; `fn_1_C5DC` (passing) is now a no-op | Wheel of Fortune (see below); its send-back outcome calls `fn_1_C5DC` | 30 |
| 0x40 | - | the start space (found with `fn_80179164(-1, 0x40)`) | 109 |

- **Return-to-start spaces: 28 and 30 (28 is now Double or Nothing, see below).** Path into Star Shuffle: 28 -> 29 -> 30 -> 31 -> 53 -> 54, so 30 is 3 spaces and 28 is 5 spaces before Star Shuffle. `fn_1_C5DC` picks variant 0 for flag 0x8 and 1 for 0x20, then writes the destination into `GwPlayer.masuId` (`sth r27, 0xc(r4)` at text 0xD05C). To change the destination, edit the `li r4, 0x40` before `bl fn_80179164` (text 0xC6DC) or move the 0x40 flag; to disable one, clear its flag in `w03.bin` and `w03n.bin`.
- **Space kind** (the u16 after the flags in the file record, masu +0x30, read by `fn_80177100`, shown as `extra` in `masu_dump.load`): 0 none, 1 blue, 2 red, 3 "?", 4 miracle, 5 duel, 6 DK (day) / Bowser (night), 7-9 other (9 = item shop at ids 7 and 52). Original DK/Bowser spaces: 34, 102. **Space 9 (8th real space after the start, 3rd after the shop at 7) was blue and is now DK/Bowser** via `src/tools/patches/apply_faire_square_dk_bowser_space_patch.py` (edits `root/data/w03.bin` and `w03n.bin`, file 0 re-stored as zlib; idempotent; `.bak_before_dk` copies sit next to them). The same script also made **space 106 a Miracle space** (kind 4; 3 spaces before the start, directly before the duel space 5). Backups of the files before each step are in `backups/`. Not yet run in Dolphin.
- Space type halfword: 1 blue, 2 red, 3 "?". Bit 0x4000 on id 38 marks the Whomp toll gate.
- Day/night: GwSystem (0x80283290) byte +0x10, bit 0x40 set = night.
- Star Shuffle is on the right side (3810, 588, 626); start is at (1, -106, 3805).

## Star Shuffle (`fn_1_5908`, `.text` 0x5908-0x8164)
Original behaviour: cost 1 Star always; day = 3 hats, win 2; night = 6 hats, win 3. Pays only on a correct pick. Key registers: r25 message variant, r26 hats (3 day / 6 night), r27 reward, r29 player. Key sites: prologue 0x5980/0x598C (`li r27,2/3`), Star check 0x59FC, intro text 0x31001F-0x310021, cost `li r4,-1` at 0x60F0 then `bl fn_8015CF64`, win reward 0x7AC0 (`fn_801816CC`) and popup `fn_80181DDC`.

**Patch: `src/tools/patches/apply_star_shuffle_bet_patch.py`** (night only):
- After "Sure", a human player gets a bet selector (Left/Right stick or D-pad, A confirms, 1..Stars owned, wraps). Bet is deducted, win pays 3 x bet.
- Day is unchanged. CPUs have no selector: they bet everything if in last place (3 players strictly ahead on Stars, then coins), otherwise 1.
- Hooks (module-0 relocations added to the REL via `battle_port.add_calls`): `.text` 0x5F48 (`mr r3,r26`) -> cave `0x80004040` (selector, ~420 bytes, ends before 0x800041E4); 0x60F0 (`li r4,-1`) -> cave `NEW_BASE+0x3340` (cost: `-(r27/3)` at night); CPU routine at `NEW_BASE+0x3390`; "%d" string at `NEW_BASE+0x3380`. `NEW_BASE` = 0x802F49A0 (relocated MgDataTbl section, tail space is nearly full).
- Text (bank 49): record 32 (intro) and 36 ("take your bet...") reworded in English only; new record 75 (message 0x31004B) is the selector prompt (English in every language file). Other languages still say "one Star" at night.
- Unverified: stick-up sign (if inverted only the D-pad feels right), prompt window position/width copied from "Choose a hat".

## Double or nothing (space 28)
**Patch: `src/tools/patches/apply_double_or_nothing_patch.py`** (run after `apply_star_shuffle_bet_patch.py`, which adds its text records):
- Human or CPU lands/passes on 28: "Double or nothing?" with Yes/No and no hint of the outcome. No (or B) does nothing. Yes rolls 1-10: 1-4 lose all coins, 5 lose a Star (nothing if none), 6 gain a Star, 7-10 double coins (game caps at 999).
- After the effect a line is shown: rolls 1-5 "Cheers for that good lad", 6 "Good for you pal", 7-10 "Good heart pal" (7-10 is my reading of "7"). English in every language file.
- Space 30 is now the Wheel of Fortune (next section).
- Hooks in `fn_1_1C30` (REL `.text`): 0x1C5C `andi. r0,r31,0x28` -> `0x20` (only 30 reaches `fn_1_C5DC`); 0x1CA4 `li r3,1` -> module-0 `bl` to the cave (the cave runs when flag 0x8 is set and returns r3 = 1). r29 = player, r31 = flags are live there.
- DOL caves: 0x80005218 (prompt, Yes/No, CPU answer), 0x80005318 (roll and result, 196 of 204 bytes), 0x80005418 (outcome line). Each region is 0xCC bytes of zero padding.
- Text (bank 49): record 76 (0x31004C) the question, 77-79 (0x31004D-0x31004F) the outcome lines. `edit_bank` accepts the older one- and two-record tails via `OLD_TAILS`.
- Calls used: `fn_8016B718` prompt, `fn_8016C52C` choice (0 Yes, 1 No, -1 cancel), `fn_80170720` CPU answer, `fn_8014CD78(10)` roll, `fn_8015C770` coins, `fn_8017E03C(p, amount, 1, 1)`, `fn_8015CE98`/`fn_8015CF64` Stars, `fn_80181DDC` popup + `fn_80182258` wait (Swap Fest sequence), `fn_8016B36C` + `fn_8016C7D8` for the outcome line.
- Unverified (not run in Dolphin): what `fn_80170720` makes CPUs answer; the Star popup sequence; positive amounts through `fn_8017E03C`; the speaker id 8 window (Star Shuffle's day host) for these messages. The 0-coin case now plays a 0-coin animation (the skip check was dropped for cave space).

## Wheel of Fortune (space 30)
**Status: tested in Dolphin by the user (2026-11-01) and reported to work well** after two fixes (see "Fixes after the first Dolphin test"). Seen in screenshots: the "Spin the wheel?" Yes/No window and the wheel with the rendered Super 'Shroom, Bowser and Star icons. The user did not itemise each outcome, so the Star popups (+2 / -1), the orb awards and the send-back were not individually confirmed in these notes.
**Patch: `src/tools/patches/apply_wheel_of_fortune_patch.py`** (run after `apply_mgtable_move_patch.py`, `apply_battle_thumbs_patch.py` and `apply_double_or_nothing_patch.py`; then `apply_star_shuffle_bet_patch.patch_messages()` if bank 49 lacks records 80-87):
- **Landing** on 30 (passing does nothing; `fn_1_1CD4` runs on every step of a move, so the landing cave also checks that the remaining-steps byte, GwPlayer +0xA, is still 1, because the game decrements it only after the handler returns) asks "Spin the wheel?" with Yes/No (message 0x310057, like Double or Nothing); No or B skips it. CPUs skip the question, hear the intro line and always spin. The wheel is the Warp Pipe Orb's pie roulette (the arrow spins over the pie), extended to 4 slices. The outcome is rolled in code first and the wheel is forced to land on it; the spin is automatic for everyone (nobody presses a button).

| Outcome | Odds | Effect | Icon (sprite id) |
|---|---|---|---|
| Jackpot | 20% | +2 Stars (popup) | gold Star, `board.bin` 0xA6 (0x500A6) |
| Item Windfall | 30% | every empty orb slot (max 3, `fn_8015D6B8`) gets Super 'Shroom (1), Sluggish (2) or Flutter (6); "pockets full" line if none free | rendered Super 'Shroom, new `board.bin` file 184 (0x500B8) |
| Fine | 30% | -1 Star with popup; "No Stars to fine" line if they have none | dark Star, 0xA7 |
| Send-back | 20% | `fn_1_C5DC` as before | Bowser head, 0xA8, **placeholder** (Kamek's orb model would not render; there is no 2D orb icon in the game, the HUD draws a plain coloured ball from `board.bin` 0x2E) |

- The slice order is shuffled by the game each spin. What happens is the icon the arrow actually lands on (`fn_801966E0`), so a visual/logic mismatch cannot give a wrong effect.
- **Roulette internals (P01 DOL, `auto_03_800EF6C8_text.s`)**: state object = `lbl_802DE7F8`+0x4C (+1 slice count, +2 user, +6 timeout, +8 angle in 1/16 degree while spinning, +0xA speed). The *arrow* rotates (sprite 4 of the group), the slices are fixed on screen; arrow bearing (clockwise from top) = angle. Warp Pipe only supported 2 and 3 slices: five switches (`0x80196A14`, `0x80196E30`, `0x80197120`, `0x80197AC4`, `0x80197B3C`) fell through to garbage for 4. Their `bge` words now branch into new handlers (width 90, 4 icon positions, slot = floor(((deg+45) mod 360)/90): the existing 4-quadrant divider sprite board 0x78 is an X, so slices are centred on top, right, bottom, left). Icon positions (y down): (0,-50), (50,0), (0,50), (-50,0).
- **Fixes after the first Dolphin test**: (1) the wheel drew only 3 slices because `fn_801963B8` does `li r28,3` at `0x80196450`, which discards its slice-count argument (it always lists the 3 opponents and never the user); that instruction is now a `nop` (Warp Pipe passes 3, so it is unchanged). (2) The landing cave first stands the player still the way Star Shuffle does, `fn_801565EC(p,0)` then `fn_8015BFB4(p,1,0.0,8.0,0x40000001)`, so the walking animation stops during the question and the spin.
- **Forcing the stop**: the game's own `fn_8019793C` (ComValue, flag `lbl_802DE7FE`, value `lbl_802DE804`) marks the roulette as forced; `0x801977D0` (`cmplwi r0,0` -> `bl`) makes a forced roulette take the automatic path even for a human, and `0x80197818` (`lha r0,flag` -> `b`) swaps the stop test: stop when `((angle>>4) + 208 - 90*slot + 30) mod 360 < 60`. The game clears the flag itself at the end. Warp Pipe never sets it, so it is unchanged. The spin physics (`+0.7`/frame to 18 deg/frame, then x0.92 per frame, quantised to 1/16) were modelled in Python; the model reproduces the game's own 3-slice stop logic exactly, and for 4 slices every (slice order, target) pair lands inside the target slice, at worst 19 degrees from its centre (half width 45), with the stop commanded by frame 40 (CPU timeout is 180).
- "Kane" mode (`lbl_802DE7FC` = 1, set after `fn_801963B8(player, 4, 0)`) makes slice icons come from the table at `0x80266314` (4 sprite ids indexed by choice value) instead of by character; the patch overwrites that table (Warp Pipe never uses it). Choice values are the outcome ids 0-3.
- **Code space**: the new code is in the old `MgDataTbl` at `0x80230000-0x8023068F` (dead once `apply_mgtable_move_patch.py` has relocated the table; the script refuses to run before that). The init-section caves are full. `0x80230000` init count, `0x80230020` icons (+ float table), `0xA0/0xB0` widths, `0xC0` slot, `0x100` CPU test, `0x120` stop, `0x1E0` show line, `0x220` Stars, `0x2A0` orbs, `0x340` spin, `0x3C0` the handler. `0x80230580` the landing cave, `0x80230680` a bare `blr`. REL hooks (module-0 calls): `.text` 0x1D3C (the `li r3,0` at the end of the landing handler `fn_1_1CD4`; r29 = player, r30 = flags, r31 = space) goes to the landing cave, which tests flag 0x20, asks (humans) or shows the intro (CPUs), then calls the wheel with the address of `fn_1_C5DC` (= LR + 0xA89C) for the send-back outcome; `.text` 0x1C70 (the passing handler's `bl fn_1_C5DC`) goes to the `blr`, so passing 30 no longer sends anyone back. The earlier passing hook of `fn_1_1C30` for Double or Nothing (0x1C5C, 0x1CA4) is untouched.
- Text (bank 49): records 80-87 (0x310050-0x310057: intro (shown to CPUs), jackpot, items, pockets full, fine, no stars, send-back, the "Spin the wheel?" question), English in every language file, owned by `apply_star_shuffle_bet_patch.WHEEL`.
- **Testing done without Dolphin**: the assembled cave bytes were run in a small PowerPC emulator (scratch scripts, not in the repo). Slot boundaries, the stop law against the physics model, the landing cave (human Yes / No / B, CPU, other spaces) and the whole handler (each outcome's call sequence, message ids, the send-back call target, 0 Stars, full pockets, 0/1/2 orbs, balanced stack, callee-saved registers) pass. This caught a real bug (`addi rD,r0,imm` is a load-immediate). The emulator does not model the game's functions, floats or sprites.
- **Confirmed in Dolphin**: the question window, the roulette starting from a landing handler, the 4-slice wheel after the slice-count fix (user: "works well"), the rendered 84x84 icon, and the player standing still during the question.
- **Not individually confirmed** (worth a glance when next testing): that the arrow always ends on the icon whose effect is applied, for every slot; the +2 / -1 Star popups; orbs added without the orb-space popup and the orb HUD refresh; the CPU path (intro line then spin); the send-back warp; the intro/result lines in the speaker id 8 window.
- **Known placeholder**: the Send-back slice shows a Bowser head until a Kamek icon exists (the Kamek orb model needs skeleton/weight handling that the Python renderer lacks; the render scripts were scratch work and are not in the repo, only `src/tools/assets/wheel_super_shroom_84.png`).

## Broom space (space 20, `fn_1_BDC8`, read from the assembly only)
- Passing handler for flag 0x10, `.text` 0xBDC8, 0x814 bytes. Rolls `fn_8014CD78(10)`: 0-3 (40%) -> destination space 42, 4-9 (60%) -> space 44 (the two words of `lbl_1_rodata_1C0` = 0x2A, 0x2C; both in the central plaza).
- Models, created in `fn_1_F4` from `w03.bin`/`w03n.bin` (dir 0xE7/0xE8): file 0x1B (`cyl155/157/158`, 15-16 KB, with a motion; probably the stand) stored at `lbl_1_bss_4D4`+0x8C, and file 0x1C (`houki`, `houki2`, `fook` = broom and hook, 23 KB, identical day/night, with a motion) at +0x90. The broom's flight path is most likely baked into its HSF motion in board coordinates; the handler drops the player when the motion time reaches `lbl_1_rodata_1D8` (space 42) or `_1DC` (space 44), then moves them there with `fn_80157AC8` + `fn_801550C8` (30 frames).
- Player motions `mariomot` 0x22, 0x11, 0x10, 0x17 (per character via `fn_8015C0C4`); sound 0x5CB; the sparkle effect from `effect.bin` file 2 (data 0x290002, shared) with callbacks `fn_1_FCF4` (0x418) and `fn_1_F744` (0x5B0, shared with the warp house `fn_1_C5DC`).
- Not to be confused with the warp house (`fn_1_C5DC`, models 0x1D-0x1F `warp_house`, door spaces 28/30 top right).

## Luck Wheel rewards (`fn_1_2718`)
**Patch: `src/tools/patches/apply_luck_wheel_rewards_patch.py`** (run after `apply_wheel_of_fortune_patch.py`). **Status: tested in Dolphin by the user (2026-11-01) and reported to work.** The user did not itemise each symbol, so individual outcomes (e.g. the full-orbs case, night, CPU players) are not separately confirmed in these notes.
- Three reels, each a strip of 8 stops (`lbl_1_data_6BC`), symbols 0-3; the results are the halfwords at `0xA8/0xAA/0xAC(r1)`. All equal = win. Regular prize: id 0 the whole pot, id 1 15, id 2 20, id 3 10 coins (`lbl_1_data_694`); night scales the coin amount.
- Extras on a match (on top of the regular prize): chest (0) +1 Star and +1 orb; mushroom (1) +20 coins and +1 orb; flower (2) +1 Star; coin (3) +1 orb. Orbs only below the max (3), random Super 'Shroom / Sluggish / Flutter. Symbol-to-picture mapping was given by the user, not read from sprites.
- Hook: REL `.text` 0x5520 (`li r3,1` before the closing line 0x31000A, match path only) -> module-0 call to the DOL cave `0x80230690` (rewards) which calls `0x80230720` (one-orb routine) and the Wheel of Fortune's Star routine `0x80230220`. Coins use `fn_8017E03C(p, 20, 1, 1)`.
- Confirmed working in Dolphin (user report): the extra awards, including the positive coin amount via `fn_8017E03C`, the orb awards and the Star popup before the closing line.

## Whomp toll gate (main DOL, not the REL)
The gate is generic main-DOL code `fn_80200524` (called from `fn_80214F54`), data-driven per board. It returns r28 = 1 when the player pays 10 coins and passes, 0 when they cannot or will not pay (the board then forks them the other way). Messages in bank 41: 0 offer, 1 "Good choice", 2 refusal, 3 "no coins" (+ 4-8 for the ride-type gate).

**Patch: `src/tools/patches/apply_whomp_rich_patch.py`** (only when `boardNo == 2`):
- **1st place** (nobody strictly ahead; ranking = Stars, then coins; ties on both count as 1st): treated as having no coins, hears new message 0x290009 "I HATE da rich! PTUH", goes the other way.
- **4th place** (3 players strictly ahead): skips the prompt, hears 0x29000A "I love a good underdog!", gains 5 coins instead of paying 10, and passes.
- 2nd/3rd place: unchanged. Team mode is not handled. Both new lines are English in every language file.
- Hooks (direct DOL edits): 0x80200680 (`bl fn_8015C770`) -> cave 0x80004654 (+ rank routine 0x80004754); 0x8020069C (message id) -> 0x80003F4C; 0x802006B4 (prompt start) -> 0x80004854; 0x80200748 (`li r4,-10`) -> 0x8000487C; 0x80200768 (message id) -> 0x800048A0. Flag word at `NEW_BASE+0x3388`: 1 = rich, 2 = underdog.
- Unverified: board number 2 = Faire Square; `fn_8017E03C` with a positive amount giving coins.

## Free DOL cave space
Caves live in TRK vector padding (`0x80003x18..x4E4`-style slots) and the tail of the table section. Owned: Bowser/DK/star-trap/random-bonus/cpu_landing scripts own their slots (see `apply_cpu_landing_patch.py` `CAVES`, `apply_star_trap_orb_patch.py` `REGIONS`). Used by the patches above: 0x80003F4C-0x80004018, 0x80004040-0x800041E4, 0x80004654-0x800046E4, 0x80004754-0x800047E4, 0x80004854-0x800048E4, and for Double or nothing 0x80005218, 0x80005318, 0x80005418 (each up to +0xCC). Check a candidate region is really zero before using it.

## Build / deploy
- Run order matters: the scripts chain on `build/GP6P01/main.dol` and `build/GP6P01/files/{dll,mess,data}`. Run `apply_star_shuffle_bet_patch.py` before `apply_double_or_nothing_patch.py` and `apply_whomp_rich_patch.py` (it imports helpers from it and reuses its spare words); `apply_wheel_of_fortune_patch.py` goes after those and after `apply_mgtable_move_patch.py` and `apply_battle_thumbs_patch.py` (it appends `board*.bin` file 184 after the thumbnails' 176-183). A fresh `ninja` build of the DOL drops every patch; re-run the scripts.
- Deploy: copy `build/GP6P01/main.dol` -> `root/&&systemdata/Start.dol`, `files/dll/*.rel` -> `root/dll/`, `files/mess/messdata*.bin` -> `root/mess/`, and for the wheel icon `files/data/board*.bin` -> `root/data/`. Then rebuild the ISO and test in Dolphin. Do not copy `messdata_eng.pre_random.bin`.
- Message editing: `apply_star_shuffle_bet_patch.edit_bank(source, replacements, label, bank, bank_records, append, known_tails)` rebuilds a bank and shifts later bank offsets. Text encoding: 0x10 space, 0xC2 `!`, 0xC3 `?`, 0x85 ellipsis, 0x82 comma, 0x5C apostrophe, `1F 01` numeric arg, `FF 00` end of page; record header `00 15 00 03` (or `...02`), padded to 4 bytes.
- Pitfall: heredocs that contain backslashes got mangled when writing Python files from the shell (`\xff\x00` became raw bytes). Use the Write/Edit tools for such files.

## Related
`plans/faire-square/README.md` has a shorter note on the spaces only. `plans/orbs`, `plans/bonus-stars` cover the Star helper functions (`fn_8015CE98` get Stars, `fn_8015CF64` add Stars, `fn_801816CC`, `fn_80181DDC`).
