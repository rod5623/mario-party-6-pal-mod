# Star Trap Orb: a Piranha-style hit orb that steals a Star (GP6P01)

Status: implemented in `src/tools/patches/apply_star_trap_orb_patch.py` (see the Star Trap Orb section of `src/README.md`); applied and built, not yet tested in Dolphin. Differences from this design: the orb icon is the Soluna sun model from the Mario Party 6 DX mod, appended to `capsule.bin` as entry 85 (`0x140055`) by the same script;  the HUD status panel is shown with `fn_80186258` (no `fn_8016E1D0`); caves are at `0x80003830`, `0x80003918`, `0x80003A18`, `0x80003B18`; the `mbCapListRead` hook adds the orb to the six main board lists with a weight equal to the average of the weights already there (`STAR_TRAP_ODDS`). `fn_80181DDC` does handle a positive count. Addresses and register names come from the GP6P01 disassembly (`build/GP6P01/asm/auto_03_800EF6C8_text.s`). Read `README.md` in this folder first for the orb tables and patch technique.

## Behaviour
- A player places the orb on a space (same as any hit orb).
- When another player **lands** on it, the Piranha-style bite plays. If the victim has at least 1 Star, they lose 1 Star and the owner gains 1 Star. If they have none, nothing is taken and a "no Star" message is shown.
- It does not fire on pass; hit orbs (usage mode 1) fire only on landing (`mbev_MasuCapStop` 0x801768F4 -> `mbev_CapCall` 0x801D44B8, `use=0, pass=0`).
- It reuses the Piranha handler `fn_801A3BC8` and its kill function (`0x801A4A70`, a bare `blr`) for the whole animation. The coin logic inside the handler is switched to Star logic when the orb ID is the new ID.
- Computer players never buy or place it (no AI chance row; the AI jump table covers IDs 0-31 and the chance table has no row for it). They can still be victims.

## Why this approach
The Piranha handler keys all its control flow on one register, `r27`, the amount. For a coin steal `r27 = (coins+1)/2`; the bite animation, messages and owner reward all test `r27 != 0`. If `r27` becomes `min(1, stars)`, the animation and flow stay valid, and only the five places that touch coins need a Star variant. The cost is that those five sites live in shared vanilla code, so each gets a branch on orb ID.

## Orb ID and data rows

### ID
Use **ID 14** (debug name HANUKE, currently unused).
- It sits in the hit-orb range (10-17), and `mbCapMasuCapsuleSet` (0x801CA380) only refuses to place 30, 43 and IDs above 41, so it can be placed.
- The random-scatter set `lbl_80268130` indexes `(id-10) mod 8` and holds 10,11,12,13,25,15,16,17, so slot 14 is never scattered (index 4 is Paratroopa, 25). That is fine; the orb is only obtained via the shop or an orb space.
- IDs 8, 9, 18, 19 and 26-29 would also work; 14 is the neatest fit for a hit orb.
- The ID is also written into placed-orb values (`id | owner<<8`) and into the byte at `[r31+8]` of the handler block, which is what the hooks test.

### `capsuleData` row 14 at `0x80266E0C` (`0x80266BDC + 14*0x28`)
Start from the Piranha row (orb 12, `0x80266DBC`) and change:

| Off | Value |
|---|---|
| +0x00 model | any hit-orb model from `capsule.bin` entries 0-37 (a different one from Piranha's helps tell them apart). Must be non-zero or `mbCapValidCheck` rejects the row. |
| +0x04 frame | same as Piranha (category 1 frame) |
| +0x08 description | `(0x37<<16) \| N` with N a new record appended to bank 55 (from index 59) |
| +0x0C name | `(0x38<<16) \| M` with M a new record appended to bank 56 (from index 37) |
| +0x10 category | 1 (hit) |
| +0x14 colour | same as Piranha |
| +0x18 price | your choice (Stars are strong; suggest about 30) |
| +0x1C rarity | a class byte 'A'-'E' (e.g. 'D' or 'E' for rare) |
| +0x1E use mode | 1 (throw/place) |
| +0x20 name pointer | optional debug string, or leave as the Piranha pointer |
| +0x24 list flag | same as Piranha |

### Dispatch row 14 at `0x80268688` (`0x80268500 + 14*0x1C`)
Copy the Piranha row (orb 12, `0x80268650`) verbatim: `+0x00` handler `fn_801A3BC8`, `+0x04` kill `0x801A4A70`, `+0x08` 0, `+0x0C/+0x10` as orb 12, `+0x14` character file `0x170000` (capsulechar2, the placed-orb characters), `+0x18` 0. The placed model and bite animation therefore look like the Piranha Plant; a different look needs a new character file.

### Making it obtainable
The orb must be in the board's orb list; a rarity byte alone does not make it appear (the shop and orb-space draws come from `lbl_802DA940`).
- **Option A (recommended, no repack tool needed):** hook `mbCapListRead` (0x801C7EDC). After it copies a board's list into `lbl_802DA940` (33 entries x 16 bytes, id -1 terminates), find the terminator and, if fewer than 33 entries, append a 16-byte entry for ID 14. Copy the Piranha entry for that board (change byte 0 to 14, scale the weights down) so the weight groups at +7/+10, which were not traced, stay valid. Skip boards 6-8 (they only hold orbs 2 and 7, so a new orb would change that design) unless you want it there.
- **Option B:** repack `capsule.bin` entries 74-84. This needs a tool that inflates the zlib entries, edits them and rebuilds the offset table; no such tool exists yet.

## The five hook sites in `fn_801A3BC8`
Common mechanism for every site that is a single `bl X` with its arguments already set: replace it with `bl <cave_n>`. The cave runs `lwz r12, 8(r31)` and `cmpwi r12, 14`. If it is not the star orb it does `b X`, which tail-calls the original function so the original return address (the instruction after the hook) is preserved. For the star orb it does the Star work and returns. `r12` is volatile and not an argument register, so loading it does not disturb the arguments. `r31` (the block) and `r27` (the amount) are callee-saved in this function and available in the caves.

| # | Address | Original | Star variant |
|---|---|---|---|
| 1 | 0x801A4720 | `bl fn_8015C770` (victim coins, in r3; the following code computes `r27 = (n+1)/2`) | Return `min(1, fn_8015CE98(victim))`. Then `(1+1)/2 = 1` and `(0+1)/2 = 0`, so `r27` is 1 with a Star and 0 without. The cave needs `mflr`/`bl`/`mtlr` since it must post-process the result. |
| 2 | 0x801A4878 | `bl fn_8017E03C` with `r3=victim, r4=-r27, r5=0, r6=1` (coin loss) | If `r27 == 0` do nothing. Otherwise `fn_80181DDC(victim, -1)`, wait until `fn_80182258(victim) == 1` (yield with `fn_8000E2C4` in between, as in the Bowser patch at 0x801BED78-0x801BEDA8), then `fn_8015CF64(victim, -1)`. The vanilla call is harmless with 0 coins; the star cave must guard `r27 == 0` itself. |
| 3 | 0x801A4970 | `bl fn_801E705C` (coin popup for the victim), already skipped when `r27 == 0` | Return immediately for the star orb; the star popup is shown at site 2. |
| 4 | 0x801A498C and 0x801A49A4 | `bl fn_8016B36C(2, 0x360004 / 0x360005, -1)` (two sites: has-coins message and none message) | Show the star messages instead. The message ids are `(0x36<<16) \| 4/5` loaded into `r4` by the instructions just before each `bl`, so the cave can overwrite `r4` for the star orb before tail-calling `fn_8016B36C`. New records are appended to bank 0x36 (see Text). |
| 5 | 0x801A4A1C | `bl fn_801E26E8` with `r3=effectObj [r31+0xBE4], r4=owner [r31+4], r5=r27, r6=1` (coins fly to owner) | If the owner is in 0-3: `fn_8015CF64(owner, +1)`, then refresh the HUD (`fn_8016E1D0(0, 1, -1)` and `fn_80186258(owner)`, as the DK patch does). Optionally show a `+1` popup with `fn_80181DDC(owner, +1)`. |

Notes on the table:
- Sites 3, 4 and 5 are only reached when `r27 != 0` (site 3 and the reward block at 0x801A49B4 are guarded by `cmpwi r27, 0`), except the "none" message at 0x801A49A4.
- Site 4 is two call sites for one logical change.
- The owner's character camera and "happy" motion at 0x801A49B4-0x801A4A08 stay unchanged.

## Star functions to call
- `fn_8015CE98(player)`: team-aware Star count (maps to the team leader in team mode).
- `fn_8015CF64(player, delta)`: team-aware Star add; plays the Star SE (`fn_8016FE84(8)`), clamps at 0, then calls `fn_8003CF28` (set, clamps 0..999).
- `fn_80181DDC(player, n)`: signed Star popup above the player; `fn_80182258(player)` returns 1 when it finishes. Bowser only calls it with -1; whether a positive `n` renders correctly is unverified. If it does not, skip the owner popup and rely on the SE.
- `fn_8016E1D0(0, 1, -1)` and `fn_80186258(player)`: HUD refresh after a Star change (copy the DK patch's usage).

## Code cave
The existing patches use `.init` caves inside the TRK interrupt-vector table, which nobody has proved unused at runtime. Prefer the debug-orb handler area, `0x801D7C40-0x801D8E9B` (about 0x1258 bytes, orbs 50-52, cost 1, rarity 'Z', no shop entries).
- Before using it, confirm nothing references those handlers, then point the dispatch rows of orbs 50-52 at `mbev_CapNull` (`0x801D7C10-0x801D7C3F`, keep intact).
- The five caves are small (roughly 10-30 instructions each), so even the smaller `.init` runs would hold them. The unused-cave list is in `README.md`.
- Use `assemble()`, `branch`, `cond` and friends from `tools/patches/apply_dk_bonus_patch.py` (lines 113-145) and `encode_branch` from `tools/patches/apply_bowser_bonus_patch.py`.

## Text
- **Orb name:** append a record to bank 56 (CAPSULE_EX98) at index 37, header `00 07 00 01`, e.g. "Star Trap Orb".
- **Orb description:** append a record to bank 55 (CAPSULE_EX99) at index 59, header `00 15 00 03`, a one-or-two page description ending `FF 00`.
- **Event messages:** the handler shows `0x360004` (coins stolen) and `0x360005` (none to take) from bank 0x36 = 54 (CAPSULE_EX02, 21 records). Append two records (index 21 and 22) for "A Star was taken!" and "You don't have a Star to take!", and use `(0x36<<16) \| 21` / `\| 22` in the star branch of site 4.
- Control codes: 0x10 space, 0x0A newline, 0xC2 `!`, 0xC3 `?`, 0x5C apostrophe, `1E nn` colour, `FF 00` page end. Copy a vanilla Piranha record (bank 54 records 4 and 5) as the template for header and colour codes.
- Use `build_messages` from `tools/patches/apply_dk_bonus_patch.py` (lines 228-281): it appends records and shifts every later bank offset. Each language file must receive the same appends, or non-English players see wrong text. Chain on `build/GP6P01/files/mess/messdata_eng.bin` so earlier patches survive.
- Shipping with no custom event text is possible (the star popups and SE carry the meaning), but the orb name and description records are required.

## Patch script outline: `tools/patches/apply_star_trap_orb_patch.py`
1. Patch both `build/GP6P01/main.dol` (via `dol_offset`) and the matching asm listings (`auto_03_800EF6C8_text.s`, `auto_07_80259D80_data.s`, and the cave listing) so Ninja rebuilds stay in sync. Check original bytes first and stay idempotent.
2. Write `capsuleData` row 14 and dispatch row 14.
3. Assemble the five caves and the `mbCapListRead` append hook; install the branches at the six `bl` sites.
4. Append the message records in all six language files.
5. Run after the Bowser and DK patches (it does not touch the same code but chains the message file).
6. Update the main `README.md` with a section like the existing patches.

## Risks and open questions
- **Orb ID byte:** `[r31+8]` is the orb ID in the trap path; confirm the same layout for the land path's block from `mbev_CapCall`, since the whole design depends on it.
- **Space clearing:** whether a hit orb is cleared from its space after triggering was not found in the Piranha path. The star orb inherits whatever Piranha does; test that it does not trigger repeatedly or never disappear.
- **Owner immunity:** the trap path skips same player and same team via `fn_801E6BA4`; confirm the hit path does the same, so owners cannot rob themselves.
- **Popup behaviour:** `fn_80181DDC` with a positive value.
- **Cave space** unproven at runtime (see above).
- **Pipeline:** the main README still lists ordinary mods and the rebuilt DOL as untested in Dolphin, so run a smoke test of the build before trusting new patches.
- **Balance:** a Star is worth far more than coins; consider a high price and a low rarity, and consider whether a victim at 0 Stars should still consume the orb (it does, as Piranha does with 0 coins).

## Test checklist
- Orb Hut lists the orb at the chosen price on each board you added it to, with the right name and description; a new board list entry does not overflow the 33-entry buffer.
- Place it; another player lands on it with 0 Stars (message, nothing changes), 1 Star, and several Stars.
- The owner gains exactly 1 Star; the HUD updates for both players; final standings are correct.
- Same-player and same-team landing (owner immunity); team mode Star counts.
- Piranha (orb 12), Goomba and Spiny still steal coins as before.
- The orb vanishes after triggering; save and load mid-game with the orb placed.
- All six languages show the text; computer players can be victims and never place it.
