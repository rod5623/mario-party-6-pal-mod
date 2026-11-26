# Audio (GP6P01)

What the mod changes in the game's sound, how those changes are built, and how to make new ones.
Paths are relative to `src/`.

## What changes

| Change | Step | File | Details |
|---|---|---|---|
| New Luigi and Waluigi voice clips | `sfx` | `sound/MP6_SND.msm`, bank 000C | 22 samples replaced by recordings made for this mod (see below) |
| New win sound | `sfx` | `sound/MP6_SND.msm`, bank 000E | Sample `0x0280` replaced |
| Quieter sound effects | `sfx` | `sound/MP6_SND.msm`, all other banks | Every sample re-encoded at gain 0.80 (about −2 dB) so the voices stand out. Lengths and loop points unchanged. |
| Quieter music | `music_volume` | `main.dol` | Stream master volume 127 → 100 (about −2 dB). Affects all streamed music, not sound effects. |
| Pagoda Peak music | `pagoda_peak` | `sound/MP6_Str.pdt` | Track 111: Mario Party 7's track 12 copied unchanged from `MP7_Str.pdt` (same format) with `pdt.read_track` |
| Close Call music | `closecall` | `sound/MP6_Str.pdt` | New track 110 appended from `tools/assets/closecall_music.wav` (32000 Hz, 16-bit stereo), at volume 127 with ×1.07 gain and a soft limiter |

Play in English: some patches change only English text, but every audio change applies to all
languages.

## The two sound files

**`sound/MP6_Str.pdt`: streamed music.**
- 110 retail tracks of stereo DSP-ADPCM, all 32000 Hz.
- The game plays a track by its index (`HuAudSStreamPlay(id)`).
- `msmStreamInit` sizes its tables from the file header, so appended tracks just work.
- `tools/audio/pdt.py` reads the archive and appends tracks.

**`sound/MP6_SND.msm`: sound effects.**
- A GSND/MusyX archive with 114 banks.
- Each bank is a pool, project, sample directory (`.sdir`) and sample data (`.samp`).
- Samples are mono DSP-ADPCM, mostly 20000 or 22050 Hz.
- Each sample has an index in its bank and a 16-bit sample id.
- A bank's sample data has a **fixed capacity** in the archive. A rebuilt bank must fit, so a
  longer clip has to be balanced by shorter ones in the same bank. `patch_msm_bank.py` checks
  this.

Retail SHA-1s (GP6P01):
- `MP6_SND.msm`: `5a1eebea57b73f0c657d32f06caad41a58f9eefe`
- `MP6_Str.pdt`: `0be48c34a6acac3de50ecaedae13a8ed67396f51`

`apply_sfx_patch.py` refuses any other `MP6_SND.msm`.

## Replaced samples

The clips are recordings by the mod's authors and friends, stored as DSP in
`tools/assets/sfx/<bank>/`. The file names, `NNNNN (0xIIII).dsp`, are the sample's index in the
bank and its id.

| Bank | Samples | What |
|---|---|---|
| 000C | `00065`–`00068` (ids `0x01DD`–`0x01E0`) | Luigi voice clips |
| 000C | `00164`–`00181` (ids `0x0277`–`0x028D`) | Waluigi voice clips |
| 000E | `00018` (id `0x0280`) | Win sound |

Sample rates of the Waluigi originals: 20000 Hz, except `00168` and `00178`, which are 22050 Hz.

## How the `sfx` step builds `MP6_SND.msm`

`tools/patches/apply_sfx_patch.py`:
1. Checks that `orig/GP6P01/files/sound/MP6_SND.msm` is retail.
2. For each bank folder in `tools/assets/sfx/`:
   - unpacks the retail bank to DSP files (`musyxextract.extract_samples`)
   - copies the replacement DSPs over the matching files
   - repacks the bank (`musyxextract.pack_samples`)
   - writes it into a copy of the archive (`patch_msm_bank.patch_archive`)
3. Runs `scale_msm_volume.py` at `SFX_GAIN` = 0.80 on every bank **except**
   `EXCLUDED_BANKS` (000C, 000E), so the new clips keep their level.
4. Writes `build/GP6P01/files/sound/MP6_SND.msm`.

The output is rebuilt from the retail file on every run, so re-running it is safe. It takes
about 2 minutes, mostly the volume pass. Deploy it to `root/sound/MP6_SND.msm`.

## Replacing a clip

1. **Find it.** Dump the bank to DSP and WAV:
   ```powershell
   python -m tools.audio.msm_dump --bank 000C --wav     # -> build\sfx_dump\000C\
   ```
   Listen to the WAVs to find the clip. The tool needs `tools/bin/vgmstream/` for `--wav`.
2. **Record or edit the replacement** as a WAV:
   - Match the original's channel count (mono) and sample rate.
   - Keep the length close. The bank's total size can't grow past its capacity.
   - Normalise it to sit with the other voices: the step leaves replaced banks at full volume.
3. **Encode it to DSP** with the exact file name of the sample it replaces:
   ```powershell
   .\tools\bin\VGAudioCli.exe ".\my-clip.wav" ".\tools\assets\sfx\000C\00170 (0x027D).dsp"
   ```
   If the original loops, check its loop settings in the dumped DSP. `musyxextract.py` writes
   them into the header. Encode with VGAudioCli's `-l start-end`; the end is exclusive.
4. **A new bank?** Create `tools/assets/sfx/<bank>/` and add the bank to `EXCLUDED_BANKS` in
   `tools/audio/scale_msm_volume.py`. The step refuses to run if the two disagree.
5. **Build and deploy:**
   ```powershell
   python .\tools\apply_all.py --only sfx
   ```
   Copy `build\GP6P01\files\sound\MP6_SND.msm` to `root\sound\`, rebuild the ISO with `build_iso`, and
   test in Dolphin.

If `patch_msm_bank` reports that the rebuilt SAMP is too large, trim the new clips until the bank
fits.

## Adding music

Follow `apply_closecall_patch.py` (`write_music()`):
1. Use a 32000 Hz, 16-bit stereo WAV.
2. Encode each channel to mono DSP with `VGAudioCli -c -i:<channel> ... -l 0-<frames>`.
3. Append the pair with `pdt.append_tracks()`. Its track id is the next free index; 110 is the
   first.
4. Play it with `HuAudSStreamPlay(id)` from code. Close Call does this in
   `src/REL/closecallDll/` with `BGM_STREAM`.

The new track must be appended to the existing `MP6_Str.pdt`, not added as a new file: the game
plays streams by track number from that one file.

## Tools

| Tool | Use | Source |
|---|---|---|
| `tools/patches/apply_sfx_patch.py` | the `sfx` step | this mod |
| `tools/audio/msm_dump.py` | dump banks to DSP and WAV | this mod |
| `tools/audio/patch_msm_bank.py` | write a rebuilt `.sdir`/`.samp` into a copy of an MSM, with size and layout checks | this mod |
| `tools/audio/scale_msm_volume.py` | re-encode banks at a gain, keeping lengths and loops | this mod |
| `tools/audio/musyxextract.py` | MusyX `.sdir`/`.samp` ↔ DSP (extract and pack) | by Nisto, included with credit, locally modified |
| `tools/audio/pdt.py` | read `MP6_Str.pdt` and append tracks | this mod |
| `VGAudioCli.exe` | WAV → DSP-ADPCM | [VGAudio](https://github.com/Thealexbarney/VGAudio/releases) (download) |
| `vgmstream-cli.exe` | DSP/PDT → WAV, for listening | [vgmstream](https://github.com/vgmstream/vgmstream/releases) (download) |

To dump the whole music archive to WAV, run
`.\tools\bin\vgmstream\vgmstream-cli.exe -s 1 -S 0 -o "track_?03s.wav" <path to MP6_Str.pdt>`.
