"""Build the Pagoda Peak board REL (board 11) from C, outside ninja: python -m tools.pagoda.build_pagoda_rel

Sources: src/REL/w07Dll/*.c. Same toolchain and flags as Close Call (tools/closecall/build_closecall_rel.py):
p01_names.h, mwcceppc GC/1.3.2, mwldeppc GC/2.6, then `dtk rel make` against build/GP6P01/main.elf.
Board RELs are all module 1, like the w07dll.rel it replaces (only one board REL is loaded at a time).

Writes build/GP6P01/pagoda/w07dll.rel only. The step pagoda_board installs it as files/dll/w07dll.rel.
Never runs ninja, so it is safe after mgtable_move. If main.elf is missing, run apply_all.py --ninja once.
"""
import shutil
import struct
import subprocess
import sys

from tools.closecall.build_closecall_rel import CC, CFLAGS, DTK, LCF, LD, LDFLAGS, MAIN_ELF
from tools.lib.paths import BUILD, ROOT

SRC_DIR = ROOT / "src" / "REL" / "w07Dll"
WORK = BUILD / "pagoda"
MODULE_NAME = "w07dll"
MODULE_ID = 1
OUT_REL = WORK / f"{MODULE_NAME}.rel"


def run(args):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True)


def build():
    if not MAIN_ELF.exists():
        raise SystemExit(f"{MAIN_ELF} is missing: run ninja once (python tools/apply_all.py --ninja)")
    run([sys.executable, "-m", "tools.closecall.p01_names"])
    WORK.mkdir(parents=True, exist_ok=True)
    objs = []
    for src in sorted(SRC_DIR.glob("*.c")):
        obj = WORK / (src.stem + ".o")
        run([CC, *CFLAGS, "-i", SRC_DIR.relative_to(ROOT), "-c", src.relative_to(ROOT), "-o", obj.relative_to(ROOT)])
        objs.append(obj)
    if not objs:
        raise SystemExit(f"no sources in {SRC_DIR}")
    lcf = WORK / "ldscript.lcf"
    lcf.write_text(LCF, encoding="ascii")
    plf = WORK / f"{MODULE_NAME}.plf"
    run([LD, *LDFLAGS, "-r1", "-lcf", lcf, "-m", "_prolog", "-o", plf, *objs])
    made = ROOT / f"{MODULE_NAME}.rel"          # dtk writes next to the working directory
    for stale in (made, OUT_REL):
        if stale.exists():
            stale.unlink()
    run([DTK, "rel", "make", "-n", "main", "-n", MODULE_NAME, MAIN_ELF, plf])
    produced = next((p for p in (made, WORK / f"{MODULE_NAME}.rel") if p.exists()), None)
    if produced is None:
        raise SystemExit("dtk did not write the REL")
    data = produced.read_bytes()
    module_id = struct.unpack_from(">I", data, 0)[0]
    if module_id != MODULE_ID:
        raise SystemExit(f"{produced}: module id {module_id}, expected {MODULE_ID}")
    if produced != OUT_REL:
        shutil.move(produced, OUT_REL)
    print(f"{OUT_REL} ({len(data)} bytes, module {module_id})")
    return OUT_REL


if __name__ == "__main__":
    build()
