# Bonus stars: customizing existing awards and adding new ones (GP6P01)

Status: research only. Everything below is from reading disassembly; nothing has been run in Dolphin. Items marked "inferred" or "open" are not confirmed.

## Implementation status
- **Build pipeline proven:** `src/tools/lib/rebuild_mdpresult.py` assembles the four `mdpresultdll` asm listings, runs `dtk elf fixup`, and relinks via ninja (ninja alone does not see asm edits). Unmodified asm gives a REL with the original SHA-1.
- **Random 3 of 4 (built, not yet run in Dolphin):** `src/tools/patches/apply_random_bonus_patch.py`. Pool = Mini-game, Orb, Action, Coin (revived).
  - `fn_1_17BF8` calls new `fn_1_bonus_run` (partial Fisher-Yates over `fn_8003FD50` = `frandmod`), which runs `fn_1_1245C` for each pick.
  - Instead of widening the message table, ids >= 3 are remapped to column 0 of their own 3-column table; the real id is kept in `lbl_1_bss_14E4` for `fn_1_122F0`, which now reads its stat offset from `lbl_1_rodata_FF8` (0x0A, 0x0C, 0x0E, 0x08).
  - Two table sets per award (`lbl_1_rodata_1000`): "first" carries the Bonus Star opening text, "plain" does not. Nine new English records appended to bank 0x0E (ids 66-74).
  - Not done: other five languages (they have no records 66-90), option and tutorial text.
- **Pool is now 6 (built, untested):** adds Boss Space Star (award 4: entry +0x24 Bowser + +0x26 DK, via a second-offset table `lbl_1_rodata_FF8+8`) and Distance Star (award 5).
  - Distance counter: `GwPlayer+0x106` (padding) is incremented where `moveNum` is decremented (DOL 0x80154BE8 and 0x801A0808, caves at 0x80003F18) and cleared in the board init (0x8014C024). `fn_1_56C` copies it (summed over both members in tag mode) into REL bss `lbl_1_bss_14EC[entry]`; stat offset 0xFF in the award table means "read that array". The results entry itself is untouched.
  - Counts steps that decrement `moveNum`; warps/teleports are not counted. Only the DOL binary is patched (the DOL asm listing is not updated). `tools/patches/apply_random_bonus_patch.py` rebuilds from `asm_pre_random/` each run (English messages: only bank 0x0E, built from the original and spliced into the current file) and deploys REL, messages and Start.dol to `root/`.
- **Heart Star (built, untested):** Action (2) and Boss (4) are merged. Award 4 is now the Heart Star: entry +0x0E (? spaces) + 0x20 (Duel) + 0x22 (Miracle) + 0x24 (Bowser) + 0x26 (DK), summed. `fn_1_122F0` adds up to four extra offsets per award from `lbl_1_rodata_stat_extra` (8 awards x 4 bytes, 0 ends the list); the second row of `lbl_1_rodata_FF8` is now unused. Award 2 is no longer drawn: the pool is 0, 1, 3, 4, 5, 6 (3 of 6). The Boss records (bank 0x0E 75-82) were reworded to Heart Star; colour 3 (red).
  - Colours: text colour code `1E nn` sets palette index nn-1. Vanilla uses 2, 3, 5, 6, 7; the Coin Star now uses 1 (untested, unknown shade). Boss uses 3 (red), Distance uses 2 (blue).

- **Mini-game Star counts wins (built, untested):** award 0 reads entry +0x0A, now filled from `GwPlayer+0x2A`, which counts minigames won. See the "Mini-game Star counts wins" section in `src/README.md`.
  - Counted in resultDll `fn_1_37D8` (`tools/patches/apply_minigame_wins_patch.py`).
  - Reset by the `stw` at DOL `0x8014C00C`.
  - `fn_1_dist_ins` now inserts the stat for awards 0, 5 and 6, reading the offset from `lbl_1_rodata_FF8`.
  - New bank 0x0E records 107-111: the tag first intro and four winner-name pages.
  - The free `GwPlayer` space left is the single byte at +0x0B.

- **Unlucky Star (built, untested):** award 7, pool 0, 1, 3, 4, 5, 6, 7 (3 of 7).
  - The stat is `GwPlayer+0x104` (coins + 30 x Stars lost to bad luck), counted by `tools/patches/apply_unlucky_patch.py`. See the "Unlucky Star" section in `src/README.md`.
  - `fn_1_56C` copies it (summed per team) into `lbl_1_bss_unl[entry]`; stat offset 0xFE means "read that array".
  - Bank 0x0E records 112-123.
  - Free GwPlayer space left: +0x0B (1 byte) and `starGraph[51]` (+0x9C, 2 bytes).

## Where the logic lives
- **Ceremony REL:** `orig/GP6P01/files/dll/mdpresultdll.rel` (257,812 bytes), the Party Mode results overlay.
  - Listing: `build/GP6P01/mdpresultdll/asm/auto_00_00000000_text.s`
  - Symbols: `config/GP6P01/rels/mdpresultdll/symbols.txt`, all generic `fn_1_XXXX` / `lbl_1_*`.
  - Overlay table: `include/ovl_table.h` line 93.
- **Not involved:** `partyresultdll.rel`, `storyresultdll.rel` (156-byte stubs); `resultDll.rel` (minigame result screen, but it feeds one counter); `mdsingdll` (solo mode, not read).
- **DOL:** only the stat counters (see Stat tracking). Listing `build/GP6P01/asm/auto_03_800EF6C8_text.s`.
- **Option flag:** `GwSystem.bonusStarF` = bit 7 of byte 0x02 of `lbl_80283290` (`include/game/gamework.h` line 78), from `GwCommon.confBonusStar` (bit 0 of byte 0x42C of `lbl_80283550`, line 152). The option menu sets it in `mdpartydll` (~lines 778-780 of its text listing). Where the DOL copies it into `bonusStarF` at game start was not located (open).
- Message id = `(dir<<16)|index` (`include/messdir_enum.h`). Dir 0x0E = PARTY_RESULTS, 0x0D = PARTY_SETTING.
- Real P01 addresses: `GwPlayerConf` `lbl_80282E48`, `GwPlayer` `lbl_80282E70` (stride 0x108), `GwSystem` `lbl_80283290`, `GwCommon` `lbl_80283550`. The names in `config/GP6P01/symbols.txt` still sit at old E01 addresses.

## The three awards today
There is no enum; the award index is a bare 0, 1 or 2.

| Idx | Star | Results-entry stat | Source `GwPlayer` field |
|---|---|---|---|
| 0 | Mini-game Star | +0x0A | `coinTotalMg` (+0x1E) |
| 1 | Orb Star | +0x0C | `capsuleUseNum` (+0x34) |
| 2 | Action Star ("?" spaces) | +0x0E | `hatenaMasuNum` (+0x17) |

- **Coin Star is cut content.** Text exists (bank 0x0E records 15-18 and 35-36) but nothing references it. The tutorial (bank 0x2A records 66-69, "three bonuses in all") lists only the three awards above.
- `coinMax` (+0x22) is tracked (`GWPlayerCoinSet`, `src/game/gamework.c` line 296) but the results code never reads it; probably the original Coin Star source. The results code uses current coins only (entry +0x08 / +0x12).

## Flow
1. `fn_1_17BF8` (listing line 25933) runs the whole sequence. If `lbl_1_bss_1278+4` (copy of `bonusStarF`) is nonzero it calls `fn_1_1245C(0)`, `(1)`, `(2)` in order (~line 26133). Afterwards it calls `fn_1_13FD0` (Dice Block tie-break, if tied) and `fn_1_165CC` (winner announcement).
2. `fn_1_56C` (line 400) builds the results table `lbl_1_bss_10D4`: 4 entries x 0x2A bytes (0xA8 total), one per player or per team in tag mode (stats summed). Reads `GwSystem`: +0x08 board, +0x05 turnMax, bit 7 of +0x02 `bonusStarF`, bit 6 of +0x00 `tagF`; and `lbl_1_bss_1278` (+0 board, +2 turnMax, +4 bonus flag, +6 tag flag).
3. `fn_1_122F0(awardIdx, uint8* outMask)` (line 19905) reads `ent[i] + 0x0A + 2*awardIdx` for 4 players (2 teams in tag mode), takes the maximum, sets a mask bit for every entrant equal to it. Maximum 0 = no winners. No tie-break and no priority between awards.
4. `fn_1_1245C(awardIdx)` (line 20011) awards. Party mode: if the winner count is neither 0 nor 4, each winner gets `ent+0x06 += 1` (~0x130E8-0x13124); 4 winners ("Everyone wins") gives nothing. Tag mode: only if exactly one team wins (~0x13964-0x139B0).
5. The bonus star goes only into the results table, not back into `GwPlayer`. It does affect the final ranking and the star bank (`fn_1_10374`, line 17780).
6. Final ranking `fn_1_176E0` (line 25579): sort by stars (+6) then coins (+8); remaining ties go to the Dice Block (`fn_1_13FD0`, line 21871; messages 24-26).
7. Sounds: 0x496, 0x497, 0x498 (0x498 for 0 or 4 winners, 0x497 otherwise; the tag-path branch was not fully decoded).

### Results-entry layout (s16 offsets, 0x2A stride)
| Off | Meaning | Off | Meaning |
|---|---|---|---|
| 0x00 / 0x02 | player index | 0x1A | Red (+0x15) |
| 0x04 | rank | 0x1C | Orb space (+0x16) |
| 0x06 | final stars (+ partner's in tag) | 0x1E | "?" spaces (+0x17) |
| 0x08 | coins | 0x20 | Duel (+0x1A) |
| 0x0A | minigame coins | 0x22 | Miracle (+0x19) |
| 0x0C | orbs used | 0x24 | Bowser (+0x18) |
| 0x0E | "?" spaces | 0x26 | DK (+0x1B) |
| 0x10-0x16 | stars, coins, minigame coins, orbs used (stat pages) | 0x28 | handicap (`GwPlayer+3`) |
| 0x18 | Blue (+0x14) | | |

The table is full. Offsets 0x10-0x26 form the per-page stat block, and the 0x2A stride is used completely, so a new stat needs a new field or reuse of an existing one.

## Stat tracking (DOL)
`GW_PLAYER` is in `include/game/gamework.h` line 16. Per-player counters are s8, saturating at 99:

| Off | Field | Space |
|---|---|---|
| 0x14 | `plusMasuNum` | Blue |
| 0x15 | `minusMasuNum` | Red |
| 0x16 | `capsuleMasuNum` | Orb space |
| 0x17 | `hatenaMasuNum` | "?" (Action Star stat) |
| 0x18 | `koopaMasuNum` | Bowser |
| 0x19 | `miracleMasuNum` | Miracle |
| 0x1A | `kettouMasuNum` | Duel |
| 0x1B | `donkeyMasuNum` | DK |

- **Increment hook:** `fn_801765AC(playerNo, masuId)` (line 156531) calls `fn_80177100(masuId)` (line 157365, space-type getter) and switches: Blue and Red types 0/1 and 2; "?" type 3; Miracle 4; Duel 5; type 6 is DK if `GwSystem+0x10` bit 6 is 0, otherwise Bowser. In non-party modes only types 3 and 6 count. If `fn_80179ADC` returns nonzero the special-space path through `fn_801D44B8` (line 261278) increments `+0x16` (~0x801D478C, 0x801D47A8).
- **Pass-over orbs:** that increment is on the landing path only (`r6`/`r28` = 0). Orbs whose type (`fn_801C8EDC`, table `0x80266BDC` + 0x1E) is 2 (ids 20-25: Bob-omb, Thwomp, Podoboo, Tweester, Zap, Koopa Troopa) are skipped on landing and trigger from the pass-over path (`r28` != 0, called per step from `fn_801764A8`, including the final step), which returns at `0x801D4668` without reaching the counter. The Trap Merchant patch counts them with a hook at `0x801D4668` (cave `0x80004018`). The two paths accept opposite orb types, so no orb is counted twice. Not yet tested in Dolphin.
- **Reset:** `fn_80179DFC(playerNo)` (line 160776), called from board init `fn_8014BE04` (line 107921, ~0x8014BF64), which also zeroes +0x1E, +0x20, +0x22, +0x24, +0x26, +0x28, +0x34.
- **Orbs used (+0x34):** `fn_80154100` (line 117247, 0x801541F8-0x80154200), only when `capsuleUse` (+0x12) is not -1.
- **Minigame coins (+0x1E):** `resultDll` `fn_1_37D8` (line 3863), capped at 9999 (0x270F).
- **Coins (+0x1C) and max coins (+0x22):** `GWPlayerCoinSet` (`src/game/gamework.c` line 296). Stars (+0x30): `GWPlayerStarSet` (line 318).
- **Free space for new counters:** `GwPlayer` is exactly 0x108 bytes with 2 pad bytes at 0x106. Possibly dead: `coinTotal` (+0x20; but `mbPlayerCoinAdd` `fn_8015C844` line 126841 writes it, so verify), `coinBattle` (+0x24), `mgCoin` (+0x26), `mgCoinBonus` (+0x28), `mgScore` (+0x2C), `starGraph` / `coinGraph` (52 shorts each). Not checked for other readers: `GwSystem.boardWork` (32 bytes at 0x14), `GwSystem.flag[8][16]` (0x23E), GwSystem pad at 0x2BE.

## Messages, display and graphics
- **File:** `files/mess/messdata_eng.bin`, 75 banks; layout as in the orbs README. Bank 0x0E = PARTY_RESULTS (66 records, base 0x6EDC, size 0x12B8); bank 0x0D = PARTY_SETTING (records 32-33 are the "Bonus Stars will be handed out / No Bonus Stars" option text); bank 0x2A = BOARD_TUTORIAL (records 65-69 explain bonuses).
- **Bank 0x0E records:** 0-4 intro and counts; 5 Mini-game intro; 6 single-winner name; 7-10 two/three winners (Mini-game); 11-14 everyone/nobody; 15-18 Coin Star (unused); 19-22 Action Star; 23 "The winner is..."; 24-26 tie-break; 27-28 final results; 29-41 tag-mode awards (29 intro, 30 names, 31-34 tie/none, 35-36 Coin, 37-38 Action, 39-41 tie and winners); 42-53, 61-65 stat pages; 55-60 Orb Star.
- **Per-award message table:** `lbl_1_rodata_4A8` (`auto_03_00000000_rodata.s` line 824), 0xC0 bytes = 48 words = 16 rows x 3 columns. `fn_1_1245C` copies it to the stack and indexes `word[award + 3*row]`.
  - Party rows 0-9: 0 intro (`0E0005`, `0E0037`, `0E0013`); 1 name page `0E0006` x3; 2 two-winner intros (7, 0x38, 0x14); 3 two-winner names (8); 4 three-winner intros (9, 0x39, 0x15); 5 three-winner names (0xA); 6 everyone (0xB); 7 nobody (0xC, 0xD, 0xC); 8 nobody qualifies (0xE, 0x3A, 0x16); 9 repeat of 7.
  - Tag rows 10-15: team intros (0x1D, 0x3B, 0x25); names (0x1E); tie (0x1F); neither wins (0x20, 0x21, 0x20); none qualify (0x22, 0x3C, 0x26); repeat of neither-wins.
- **Text codes:** header `00 15 00 0N`, `0x10` space, `0x0A` newline, `0x85` "...", `0x82` ",", `0xC2` "!", `0xC3` "?", `=` for "-", `\` for apostrophe, `1E 03/06/05/07` start colour (Mini-game / Orb / Action / names), `1E 08` end colour, `1F n` player or team name, `19 n` number, `FF 00` page end.
- **Stat pages:** `lbl_1_data_3B4` (`auto_04_00000000_data.s` line 266, 0x240 bytes): six 12-pair sets of (stat id, `0x000E00xx`); page counts in `lbl_1_data_3A8` (12,12,12,12,12,10). Page code `fn_1_1C5D4` (line 30985, solo) and `fn_1_1DDF8` (line 32610, tag); which set is used when was not traced (open). Message 0x30 ("Orb Space") is unreferenced; stat page 6 pairs msg 0x3D ("Character Space") with a counter mapped to the Orb-space counter (uncertain).
- **Graphics:** sprite ids `0x00A0xxxx` live in `data/mdpresult.bin` (dir 0xA0 in P01; the Europe table has 261 entries versus 249 in `include/datadir_table.h`, so that header's indices are wrong for P01). Id tables `lbl_1_data_C0` (39 ids), `lbl_1_data_620`, `lbl_1_data_7A8`. No per-star icon or animation exists: the ceremony is text, colour-coded names and character animations. Winner display `fn_1_AC6C` (line 11806) / `fn_1_B3D4` (line 12307). Tag team-name lookup `fn_1_46C` (line 324) with byte-pair table `lbl_1_rodata_84`.

## Customizing existing awards
- **Change which stat decides an award (cheapest).** In `fn_1_122F0` the stat field is `0x0A + 2*idx`. Re-point an award to any other field of the entry: Red (0x1A), Blue (0x18), Orb space (0x1C), Duel (0x20), Miracle (0x22), Bowser (0x24), DK (0x26) or end coins (0x08). For example Action Star -> Bowser spaces. Then reword the matching text in bank 0x0E (and the tutorial/option text).
- **Change the award value** (e.g. 2 stars): edit the `+= 1` in `fn_1_1245C` (party ~0x130E8-0x13124, tag ~0x13964-0x139B0).
- **Change tie rules:** edit the winner-count checks in `fn_1_1245C` (0 and 4 in party mode, exactly 1 in tag mode).
- **Reorder or drop awards:** edit the three `li r3,N / bl fn_1_1245C` calls in `fn_1_17BF8`.
- **Rewording:** bank 0x0E records, in all six language files.

## Adding new awards
1. Add a 4th `li r3,3 / bl fn_1_1245C` in `fn_1_17BF8`. This needs code room, so use a code cave or relink the REL from edited asm.
2. Make `fn_1_122F0` read a per-award field offset, for example from a small table indexed by award.
3. Extend the message table `lbl_1_rodata_4A8` from 3 to 4 columns. `fn_1_1245C` indexes `award + 3*row`, so the stride constant and the stack copy size both change; the table must be relocated or the function patched to use a new table.
4. Append message records (intro, names, 2/3 winners, nobody, tag variants) to bank 0x0E in all six languages, using `build_messages` from `tools/patches/apply_dk_bonus_patch.py` lines 228-281. Revive the unused Coin Star records 15-18 and 35-36 first.
5. Update the option text (bank 0x0D 32-33) and tutorial (bank 0x2A 65-69), and the star-count wording ("three bonuses in all").
6. If a new counter is needed (not just a rename), add the increment in `fn_801765AC`, the reset in `fn_80179DFC`, and storage (see free space above), then copy it into the results table in `fn_1_56C`.
7. Check ceremony length and pacing.

Awards that need no new counter: Blue Star, Red Star, Orb-space Star, Duel Star, Miracle Star, Bowser Star, DK Star, and Coin Star using end-of-game coins (entry +0x08) or the unused `coinMax`.

## Limits
- Results entry full (0x2A stride); `GwPlayer` full (2 pad bytes).
- Award index and message-table columns hardcoded to 3.
- No tie-break, no priority; 4-way ties give nothing.
- Counters saturate at 99.
- No per-star graphic; a new award reuses the text layout.

## Patch technique
- Same DOL technique as the other patches (see the orbs README and `tools/apply_*.py`): patch `build/GP6P01/main.dol` and the matching asm listing, idempotent, caves in `.init` (see the orbs README for the free-cave list and caveats).
- **REL patching is new here.** No script patches a REL binary directly. Edit the REL asm listing and let `ninja` relink (the `m699Dll` fix works this way, but the repo notes its generated object is not automatically rebuilt by the current Ninja graph, so confirm the build graph handles `mdpresultdll`). Because the REL is relinked from asm, code can be appended to the text asm instead of hunting for caves.
- Message helpers: `MESS_SOURCE` = `orig/.../messdata_eng.bin`, `MESS_OUTPUT` = `build/GP6P01/files/mess/messdata_eng.bin`; edits in place if the record fits, otherwise rebuild the bank and shift later offsets; chained patches read `MESS_OUTPUT` when it exists.

## Risks and open questions
- Whether `mdpresultdll` changes survive the Ninja build and match the REL relocation layout (first thing to test: a no-op edit).
- Stat-page set selection (`fn_1_1C5D4` / `fn_1_1DDF8`), tag-mode sound branch, and where `bonusStarF` is set are untraced.
- Safe storage for new counters is unverified; check readers of each candidate field first.
- Mapping of "Character Space" stat page is uncertain.
- Other-language files need the same appends.

## Roadmap
1. No-op REL edit to prove the build and replace pipeline works.
2. Re-point one award to a different existing stat and reword the text (smallest real change).
3. Revive the Coin Star as a 4th award.
4. Add awards backed by existing counters (Red, Bowser, Duel, ...).
5. Add new counters and awards that need them.

## Dolphin test checklist
- Bonus Stars option on and off; party mode and tag mode.
- Each award with 0 winners, 1 winner, 2 winners, 3 winners and 4 winners.
- Final standings include the extra stars; Dice Block tie-break still works.
- Stat pages still show correct values; no crash on a 4th ceremony step.
- Check all six languages and the tutorial text.
