# Mario Party 6 (PAL) gameplay mod

A set of gameplay changes for **Mario Party 6, European version (GP6P01)**, built on top of a
decomp-toolkit split of the game. The changes are applied by Python patch scripts to the
game's `main.dol`, its REL overlays, message files and board data.

**No game files are included.** You need your own copy of the PAL disc and must dump it
yourself (see below). The US version (GP6E01) is not supported by the patches.

## What it changes

- **Bowser and DK spaces:** new Bowser Bonus and Bowser Mini-Game outcomes, 50/50 DK
  split and new DK Bonus results.
- **Bonus Stars:** three Bonus Stars drawn at random from a larger pool, including the new
  Unlucky Star. The Mini-game Star counts minigames won, not coins.
- **Orbs:** a new Star Trap orb that steals a Star.
- **Minigames:** a new 4-player minigame (Close Call, written in C), Battle and Duel copies of
  existing games, shorter 1v3 time limits, adjusted odds, excluded games, and every minigame
  unlocked.
- **Faire Square:** a Wheel of Fortune, Double or Nothing, Star Shuffle bets, Luck Wheel
  rewards, and a Whomp toll that turns back the leader.
- **Castaway Bay:** a Wheel o' Fortune, a broom ride space, the spare change guy, and a
  bridge troll.
- **E. Gadd's Garage:** a wheel, reworked Calamity Launcher, Shuffle-o-tron and Orb
  Morpher, robots, and a Miracle space.
- **Sound:** new Luigi and Waluigi voice clips and a new win sound (recorded for this mod),
  slightly quieter sound effects and music, and new music for Close Call. See
  [src/docs/audio.md](src/docs/audio.md).
- Smaller tweaks, such as Round of Miracles odds, Boo's house by day and CPU landing.

Each script in [src/tools](src/tools) starts with a docstring describing its change.
[src/tools/README.md](src/tools/README.md) explains the order the scripts run in, and
[src/README.md](src/README.md) has per-patch notes. To write your own patches, start with
[src/docs/patching-guide.md](src/docs/patching-guide.md), which covers code caves, REL hooks,
message banks, data archives and the rules that keep patches from breaking each other.

## Repository layout

| Folder | Contents |
|---|---|
| `src/` | The decomp project: `configure.py`, `config/` (symbols and splits), `src/` and `include/` (C code, including the Close Call minigame), `tools/` (patch scripts and their assets). |
| `src/orig/GP6P01/` | **You add this:** the disc extracted with Dolphin. The build reads it. Not tracked. |
| `root/` | **You add this:** the disc extracted with GameCube Rebuilder. The patches are copied in here and an ISO is rebuilt from it. Not tracked. |
| `boards/` | Design notes and reference images for the board changes. |
| `plans/` | Design and research notes: bonus stars, orbs, minigame pools, Faire Square. |
| `backups/` | Board scripts save copies of board files here before editing them. Not tracked. |

The scripts use these relative paths, so keep the folders side by side.

## Requirements

Everything you need to download. The tools in `src/tools/bin/` aren't tracked by git, so every
clone needs them. The scripts expect the exact file names shown.

**To build and play**

| What | Version | Where it goes | Get it from |
|---|---|---|---|
| Windows | 10 or 11 | — | The scripts call `.exe` tools |
| Your own Mario Party 6 **PAL** disc (GP6P01) | Retail | — | Dump it with a homebrew dumping tool on a Wii (e.g. CleanRip) or GameCube |
| Python | 3.11 or newer | on `PATH` | [python.org](https://www.python.org/downloads/) |
| Python packages (Pillow, requests) | see `requirements.txt` | — | `pip install -r requirements.txt` |
| decomp-toolkit | **v1.8.4** | `src/tools/bin/dtk-windows-x86_64.exe` | [GitHub release](https://github.com/encounter/decomp-toolkit/releases/tag/v1.8.4) |
| Ninja | **1.13.2** | `src/tools/bin/ninja.exe` | [GitHub release](https://github.com/ninja-build/ninja/releases/tag/v1.13.2) (`ninja-win.zip`) |
| VGAudio CLI | latest | `src/tools/bin/VGAudioCli.exe` | [GitHub releases](https://github.com/Thealexbarney/VGAudio/releases). Encodes Close Call's music; only the `closecall` step needs it. |
| Dolphin | any recent | anywhere | [dolphin-emu.org](https://dolphin-emu.org/). Extracts the disc and plays the result. |
| GameCube Rebuilder (GCR) | 1.1 | anywhere | romhacking.net. Exports `root/` and rebuilds the ISO. Needs .NET Framework 4.5.2 or newer (included in Windows 10 and 11). |

**Downloaded automatically.** The first `ninja` run fetches these into `src/build/`, so it needs
internet access:
- the Metrowerks GameCube compilers (`compilers` 20240706)
- sjiswrap 1.1.1
- binutils 2.42-1, which is fetched the first time a patch step needs the assembler

**For audio work (optional)**

| What | Where it goes | Use |
|---|---|---|
| [vgmstream](https://github.com/vgmstream/vgmstream/releases) CLI (Windows zip) | the whole zip in `src/tools/bin/vgmstream/` | Listen to the game's sounds: `tools/audio/msm_dump.py --wav` converts banks to WAV |
| An audio editor, e.g. [Audacity](https://www.audacityteam.org/) | anywhere | Record and edit replacement clips |
| VGAudio CLI (above) | `src/tools/bin/VGAudioCli.exe` | Encode new clips to DSP |

**For decompilation work (optional):** [objdiff](https://github.com/encounter/objdiff) to
compare decompiled functions with the original. `configure.py` writes its `objdiff.json`.

## Setup

1. **Dump your disc** to an ISO using a GameCube or Wii homebrew dumping tool, such as
   CleanRip.
2. **Extract it for the build.** In Dolphin, right-click the game, then choose
   *Properties > Filesystem*, right-click the disc and choose *Extract Entire Disc*. Extract
   into `src/orig/GP6P01/`, so that you get `src/orig/GP6P01/sys/main.dol` and
   `src/orig/GP6P01/files/...`.
3. **Extract it for playing.** Open the ISO in GameCube Rebuilder and export its root into
   `root/`, so that you get `root/&&systemdata/Start.dol`, `root/data/`, `root/dll/` and so on.
   Keep a copy of this clean `root/` somewhere else. You'll need it to undo the patches.

## Build and patch

From `src/`:

```powershell
python .\configure.py --version GP6P01 --dtk .\tools\bin\dtk-windows-x86_64.exe
.\tools\bin\ninja.exe
python .\tools\apply_all.py
```

`configure.py` and `ninja` split the game and build `src/build/GP6P01/`. The first build takes
a few minutes. At the end, ninja checks the output against the original hashes. **Expect it to
report `131 files OK` and `build/GP6P01/main.dol: FAILED`.** The rebuilt DOL is a known 32
bytes short (see [src/README.md](src/README.md)). Everything is still built, so carry on.

`apply_all.py` then applies every patch in the right order. Use `--list` to see the steps and
`--from NAME` to resume after a failure.

To apply only some of the changes, such as just the Bowser and DK spaces or just one board,
use `--only` with one of the tested bundles in
[src/tools/README.md](src/tools/README.md#choosing-which-patches-to-apply). That page also
lists which steps need which.

Then copy the outputs into `root/`. The table in
[src/tools/README.md](src/tools/README.md#deploying-to-the-game-folder) lists every file. In short:

| From `src/build/GP6P01/` | To `root/` |
|---|---|
| `main.dol` | `&&systemdata/Start.dol` |
| `files/dll/*.rel` | `dll/` |
| `files/data/*.bin` | `data/` |
| `files/mess/messdata*.bin` | `mess/` |
| `files/movie/*` | `movie/` |
| `files/sound/MP6_SND.msm`, `files/sound/MP6_Str.pdt` | `sound/` (sound effects, music) |

The board patches (Faire Square, Castaway Bay, E. Gadd's Garage) edit `root/data` directly.

## Play

Rebuild an ISO from `root/` with GameCube Rebuilder and open it in Dolphin. Play in English:
some patches change only the English message file.

GCR rebuilds using the disc's original file list, so it only keeps files that already exist on
the disc. The patches therefore replace or extend existing files and never add new ones.

## Status

This is a work in progress. Many patches are built but not yet tested in game, and the status
notes in [src/README.md](src/README.md) say which. The rebuilt unmodified DOL is not yet
byte-identical to the original. All 131 RELs match.

## Credits

- Built on the [Mario Party 6 decompilation](https://github.com/mariopartyrd/marioparty6)
  project template and [decomp-toolkit](https://github.com/encounter/decomp-toolkit).
- The Soluna orb model is from [MP6DX](https://github.com/furtabs/MP6DX) (MIT). See
  [src/tools/assets/NOTICE.md](src/tools/assets/NOTICE.md).
- The Luigi and Waluigi voice clips and the win sound were recorded by the mod's authors and
  friends.
- `src/tools/audio/musyxextract.py`, the MusyX sample extractor and packer, is by Nisto (pack mode
  with contributions from bobjrsenior), included with credit and locally modified.
- Audio tools used: [VGAudio](https://github.com/Thealexbarney/VGAudio) and
  [vgmstream](https://github.com/vgmstream/vgmstream).
