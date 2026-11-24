"""Reassemble an asm-split REL (default mdpresultdll) from its listings and relink it.

Ninja has no assemble edge for the split objects, so edits to
build/GP6P01/mdpresultdll/asm/*.s are not picked up by `ninja` alone. This
script assembles each listing into obj/, then runs ninja to relink the REL.
With unmodified asm the resulting REL is byte-identical to the original.
"""
import subprocess
import sys

from tools.lib.paths import ROOT
DLL = ROOT / "build/GP6P01/mdpresultdll"
AS = ROOT / "build/binutils/powerpc-eabi-as.exe"
DTK = ROOT / "tools/bin/dtk-windows-x86_64.exe"
NINJA = ROOT / "tools/bin/ninja.exe"
SECTIONS = ["00_00000000_text", "03_00000000_rodata", "04_00000000_data", "05_00000000_bss"]


def run(args):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True)


def ensure_binutils():
    """A plain `ninja` build never needs binutils, so fetch them through ninja's own download target."""
    if not AS.exists():
        run([NINJA, "build/binutils"])


def rebuild(dll="mdpresultdll"):
    """Assemble build/GP6P01/<dll>/asm/*.s into obj/ and relink <dll>.rel. Returns its path."""
    ensure_binutils()
    base = ROOT / "build/GP6P01" / dll
    for name in SECTIONS:
        obj = base / "obj" / f"auto_{name}.o"
        run([AS, "-mgekko", "--strip-local-absolute", "-I", "include",
             "-I", "build/GP6P01/include", "--defsym", "version=0",
             "-o", obj, base / "asm" / f"auto_{name}.s"])
        run([DTK, "elf", "fixup", obj, obj])
    rel = base / f"{dll}.rel"
    run([NINJA, f"build/GP6P01/{dll}/{dll}.rel"])
    print(rel)
    return rel


def main():
    rebuild("mdpresultdll")


if __name__ == "__main__":
    sys.exit(main())
