"""Dump the sample banks of MP6_SND.msm as DSP files (and optionally WAV) for listening and editing.

    python -m tools.audio.msm_dump                       # every bank of the retail file -> build/sfx_dump/
    python -m tools.audio.msm_dump --bank 000C 000E      # only these banks
    python -m tools.audio.msm_dump --wav                 # also convert to WAV (tools/bin/vgmstream/vgmstream-cli.exe)
    python -m tools.audio.msm_dump --input build/GP6P01/files/sound/MP6_SND.msm   # inspect the patched file

Each bank becomes a folder <out>/<bank>/ of "NNNNN (0xIIII).dsp" files (index in the bank, sample
id), the naming apply_sfx_patch.py expects in tools/assets/sfx/<bank>/.
"""
import argparse
import contextlib
import io
import subprocess
import sys
import tempfile
from pathlib import Path

from tools.audio import musyxextract
from tools.audio.scale_msm_volume import read_banks

from tools.lib.paths import TOOLS
ROOT = TOOLS.parent
VGMSTREAM = TOOLS / "bin" / "vgmstream" / "vgmstream-cli.exe"  # the whole release zip: the exe needs its DLLs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=ROOT / "orig" / "GP6P01" / "files" / "sound" / "MP6_SND.msm")
    ap.add_argument("--output", type=Path, default=ROOT / "build" / "sfx_dump")
    ap.add_argument("--bank", type=lambda v: int(v, 16), nargs="+", help="hex bank ids, e.g. 000C")
    ap.add_argument("--wav", action="store_true", help="also write WAVs next to the DSPs (needs vgmstream-cli)")
    args = ap.parse_args(argv)

    archive = args.input.read_bytes()
    banks = read_banks(archive)
    todo = args.bank or sorted(banks)
    if args.wav and not VGMSTREAM.exists():
        raise SystemExit(f"--wav needs {VGMSTREAM} (https://github.com/vgmstream/vgmstream/releases)")
    args.output.mkdir(parents=True, exist_ok=True)
    for bank_id in todo:
        if bank_id not in banks:
            raise SystemExit(f"no bank {bank_id:04X} in {args.input}")
        name, b = f"{bank_id:04X}", banks[bank_id]
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)
            (src / f"{name}.sdir").write_bytes(archive[b["sdir_start"]:b["sdir_start"] + b["sdir_size"]])
            (src / f"{name}.samp").write_bytes(archive[b["samp_start"]:b["samp_start"] + b["samp_size"]])
            with contextlib.redirect_stdout(io.StringIO()):
                musyxextract.extract_samples(str(src), str(args.output))
        dsps = sorted((args.output / name).glob("*.dsp"))
        if args.wav:
            for dsp in dsps:
                subprocess.run([str(VGMSTREAM), "-o", str(dsp.with_suffix(".wav")), str(dsp)],
                               check=True, stdout=subprocess.DEVNULL)
        print(f"bank {name}: {len(dsps)} samples -> {args.output / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
