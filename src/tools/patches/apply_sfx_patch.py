"""Sound effects: new voice clips and a quieter mix in sound/MP6_SND.msm.

What changes:
  * Bank 000C (character voices): 22 samples are replaced by new recordings. 4 Luigi clips
    (sample ids 0x01DD-0x01E0) and 18 Waluigi clips (0x0277-0x028D).
  * Bank 000E: the win sound 0x0280 is replaced.
  * Every other bank is made about 2 dB quieter (gain SFX_GAIN, see scale_msm_volume.py), so
    the voices stand out. Sample counts, loop points and bank sizes are unchanged.

How: the replacement clips are GameCube DSP files in tools/assets/sfx/<bank>/, named like the
extracted samples ("NNNNN (0xIIII).dsp": index in the bank, sample id). For each bank, the
retail bank is unpacked with musyxextract.py, the replacements are dropped in, the bank is
repacked and written back with patch_msm_bank.py. Then scale_msm_volume.py runs on the
other banks.

Input: orig/GP6P01/files/sound/MP6_SND.msm, which must be the retail file (checked by SHA-1).
Output: build/GP6P01/files/sound/MP6_SND.msm, rebuilt from scratch on every run (idempotent).
Independent of every other step.

To add or change a clip, see docs/audio.md.
"""
import contextlib
import hashlib
import io
import shutil
import sys
import tempfile
from pathlib import Path

from tools.audio import musyxextract
from tools.audio import patch_msm_bank
from tools.audio import scale_msm_volume as scale

from tools.lib.paths import TOOLS
ROOT = TOOLS.parent
MSM_ORIG = ROOT / "orig" / "GP6P01" / "files" / "sound" / "MP6_SND.msm"
MSM_OUT = ROOT / "build" / "GP6P01" / "files" / "sound" / "MP6_SND.msm"
ASSETS = TOOLS / "assets" / "sfx"
RETAIL_SHA1 = "5a1eebea57b73f0c657d32f06caad41a58f9eefe"  # GP6P01 MP6_SND.msm


def replacement_banks():
    banks = {}
    for folder in sorted(p for p in ASSETS.iterdir() if p.is_dir()):
        clips = sorted(folder.glob("*.dsp"))
        if clips:
            banks[int(folder.name, 16)] = clips
    if set(banks) != set(scale.EXCLUDED_BANKS):
        raise RuntimeError(f"scale_msm_volume.EXCLUDED_BANKS {scale.EXCLUDED_BANKS} must list exactly the "
                           f"replaced banks {sorted(banks)}, or the volume pass would re-encode the new clips")
    return banks


def rebuild_bank(archive_path, bank_id, clips, work, output_path):
    """Unpack bank_id from archive_path, swap in clips, repack, and write a patched archive."""
    name = f"{bank_id:04X}"
    archive = archive_path.read_bytes()
    bank = scale.read_banks(archive)[bank_id]
    packed_dir = work / f"bank_{name}"
    packed_dir.mkdir()
    (packed_dir / f"{name}.sdir").write_bytes(archive[bank["sdir_start"]:bank["sdir_start"] + bank["sdir_size"]])
    (packed_dir / f"{name}.samp").write_bytes(archive[bank["samp_start"]:bank["samp_start"] + bank["samp_size"]])
    dsp_root = work / f"dsp_{name}"
    dsp_root.mkdir()
    with contextlib.redirect_stdout(io.StringIO()):  # musyxextract prints a line per sample
        musyxextract.extract_samples(str(packed_dir), str(dsp_root))
    dsp_dir = dsp_root / name
    for clip in clips:
        if not (dsp_dir / clip.name).exists():
            raise RuntimeError(f"{clip.relative_to(TOOLS)}: no sample with this index and id in bank {name}")
        shutil.copyfile(clip, dsp_dir / clip.name)
    rebuilt = work / f"rebuilt_{name}"
    rebuilt.mkdir()
    with contextlib.redirect_stdout(io.StringIO()):
        musyxextract.pack_samples(str(dsp_dir), str(rebuilt))
    count, *_ = patch_msm_bank.patch_archive(archive_path, bank_id, rebuilt, output_path)
    print(f"Bank {name}: {len(clips)} of {count} samples replaced")


def main():
    if not MSM_ORIG.exists():
        raise SystemExit(f"{MSM_ORIG} is missing: extract your disc into orig/GP6P01 first")
    if hashlib.sha1(MSM_ORIG.read_bytes()).hexdigest() != RETAIL_SHA1:
        raise SystemExit(f"{MSM_ORIG} is not the retail GP6P01 file. Restore sound/MP6_SND.msm from your "
                         "disc (Dolphin: Extract Entire Disc) and run this again.")
    banks = replacement_banks()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        current = MSM_ORIG
        for step, (bank_id, clips) in enumerate(banks.items()):
            nxt = work / f"step{step}.msm"
            rebuild_bank(current, bank_id, clips, work, nxt)
            current = nxt
        scaled = work / "scaled.msm"
        if scale.main(["--input", str(current), "--output", str(scaled)]) != 0:
            raise SystemExit("scale_msm_volume failed")
        MSM_OUT.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(scaled, MSM_OUT)
    print(f"Wrote {MSM_OUT}")


if __name__ == "__main__":
    sys.exit(main())
