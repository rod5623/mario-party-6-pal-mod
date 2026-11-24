"""Build the Close Call minigame REL from C, outside ninja.

The new minigame lives in src/REL/closecallDll/*.c. It ships in the overlay slot of jbtestdll (ovl index 5,
module id 1), an empty debug stub in the retail game, so the DOL's fixed overlay table is untouched.

Steps (all from decompiling/src):
  1. tools/closecall/p01_names.py writes build/GP6P01/include/p01_names.h (US names -> P01 symbols).
  2. mwcceppc (GC/1.3.2, the REL flags from configure.py) compiles each .c file.
  3. mwldeppc (GC/2.6) links a relocatable .plf with build/GP6P01/closecall/ldscript.lcf.
  4. dtk rel make links it against build/GP6P01/main.elf as module "jbtestdll" and writes
     build/GP6P01/files/dll/jbtestdll.rel.

It never runs ninja, so it is safe after mgtable_move. main.elf is only used for symbol addresses; none of the
binary DOL patches move functions or the data the REL uses. If main.elf is missing, run ninja once first
(apply_all.py --ninja).

Usage: python -m tools.closecall.build_closecall_rel
       CLOSECALL_DEBUG=1 python -m tools.closecall.build_closecall_rel   (draws a bar at each player's computed head top)
"""
import os
import shutil
import struct
import subprocess
import sys

from tools.lib.paths import ROOT
SRC_DIR = ROOT / "src" / "REL" / "closecallDll"
WORK = ROOT / "build" / "GP6P01" / "closecall"
MAIN_ELF = ROOT / "build" / "GP6P01" / "main.elf"
OUT_REL = ROOT / "build" / "GP6P01" / "files" / "dll" / "jbtestdll.rel"
CC = ROOT / "build" / "compilers" / "GC" / "1.3.2" / "mwcceppc.exe"
LD = ROOT / "build" / "compilers" / "GC" / "2.6" / "mwldeppc.exe"
DTK = ROOT / "tools" / "bin" / "dtk-windows-x86_64.exe"
MODULE_NAME = "jbtestdll"
MODULE_ID = 1

CFLAGS = [
    "-nodefaults", "-proc", "gekko", "-align", "powerpc", "-enum", "int", "-fp", "hardware",
    "-Cpp_exceptions", "off", "-O4,p", "-inline", "auto", "-pragma", "cats off", "-pragma", "warn_notinlined off",
    "-maxerrors", "1", "-nosyspath", "-RTTI", "off", "-fp_contract", "off", "-str", "reuse", "-multibyte",
    "-i", "include", "-i", "build/GP6P01/include", "-DMUSY_TARGET=MUSY_TARGET_DOLPHIN", "-DVERSION=1",
    "-DNDEBUG=1", "-char", "unsigned", "-sdata", "0", "-sdata2", "0", "-pool", "off",
]
LDFLAGS = ["-fp", "hardware", "-nodefaults", "-sdata", "0", "-sdata2", "0"]

LCF = """SECTIONS
{
    GROUP:
    {
        .init :{}
        .text ALIGN(0x4):{}
        .ctors ALIGN(0x4):{}
        .dtors ALIGN(0x4):{}
        .rodata ALIGN(0x8):{}
        .data ALIGN(0x8):{ *(.data) *(extabindex) *(extab) }
        .bss ALIGN(0x8):{}
    }
}

FORCEACTIVE
{
    _prolog
    _epilog
    _unresolved
}
"""


def run(args):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True)


def main():
    if not MAIN_ELF.exists():
        raise SystemExit(f"{MAIN_ELF} is missing: run ninja once (python tools/apply_all.py --ninja)")
    run([sys.executable, "-m", "tools.closecall.p01_names"])
    run([sys.executable, "-m", "tools.closecall.closecall_assets"])
    WORK.mkdir(parents=True, exist_ok=True)
    objs = []
    for src in sorted(SRC_DIR.glob("*.c")):
        obj = WORK / (src.stem + ".o")
        debug = ["-DCLOSECALL_DEBUG_HITBOX"] if os.environ.get("CLOSECALL_DEBUG") == "1" else []
        run([CC, *CFLAGS, *debug, "-c", src.relative_to(ROOT), "-o", obj.relative_to(ROOT)])
        objs.append(obj)
    if not objs:
        raise SystemExit(f"no sources in {SRC_DIR}")
    lcf = WORK / "ldscript.lcf"
    lcf.write_text(LCF, encoding="ascii")
    plf = WORK / f"{MODULE_NAME}.plf"
    run([LD, *LDFLAGS, "-r1", "-lcf", lcf, "-m", "_prolog", "-o", plf, *objs])
    rel = WORK / f"{MODULE_NAME}.rel"
    if rel.exists():
        rel.unlink()
    # No -c config: the config would force the retail stub's section count and alignments onto the new module.
    # Without it dtk numbers modules in argument order, so this one is module 1, jbtestdll's id.
    run([DTK, "rel", "make", "-n", "main", "-n", MODULE_NAME, MAIN_ELF, plf])
    if not rel.exists():
        raise SystemExit(f"dtk did not write {rel}")
    data = rel.read_bytes()
    module_id = struct.unpack_from(">I", data, 0)[0]
    if module_id != MODULE_ID:
        raise SystemExit(f"{rel}: module id {module_id}, expected {MODULE_ID}")
    OUT_REL.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(rel, OUT_REL)
    print(f"{OUT_REL} ({len(data)} bytes, module {module_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
