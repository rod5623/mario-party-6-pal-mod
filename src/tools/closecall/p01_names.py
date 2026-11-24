"""Port US (GP6E01) symbol names onto Europe (GP6P01) addresses.

The P01 config names nearly every DOL symbol generically (fn_XXXXXXXX / lbl_XXXXXXXX). The E01 config has the
decomp's real names (Hu3DModelCreate, GwPlayer, ...). The two DOLs hold the same code in the same order with a few
insertions, so for each section the symbols are aligned by their size sequence (difflib) and a name is carried over
only inside a run of equal sizes.

Usage (from decompiling/src):
    python -m tools.closecall.p01_names                 write build/GP6P01/include/p01_names.h
    python -m tools.closecall.p01_names --check A B ... print the P01 symbol for each E01 name (non-zero exit if any is missing)

The header #defines each E01 name to its P01 symbol, so C code written against include/game/*.h links against the
P01 main.elf. Include it before any other header.
"""
import difflib
import struct
import re
import sys

from tools.lib.paths import ROOT
E01 = ROOT / "config" / "GP6E01" / "symbols.txt"
P01 = ROOT / "config" / "GP6P01" / "symbols.txt"
OUT = ROOT / "build" / "GP6P01" / "include" / "p01_names.h"

LINE = re.compile(r"^(\S+) = (\.[a-z0-9_]+):0x([0-9A-Fa-f]+); // type:(\w+)(?: size:0x([0-9A-Fa-f]+))?")
MIN_RUN = 2  # a data name is only trusted inside a run of at least this many equal sizes
GENERIC = re.compile(r"^(fn|lbl|jumptable|gap)_[0-9A-F]+")

# Known pairs, checked every run (from plans/minigame-pools/README.md and the patch scripts).
ANCHORS = {
    "GameMesCreate": "fn_80044488",
    "MgNoGet": "fn_8006A108",
    "GwPlayer": "lbl_80282E70",
    "GwPlayerConf": "lbl_80282E48",
}


# Names the alignment cannot recover (unnamed in E01 too), found by reading P01 disassembly.
EXTRA = {
    "fontcolor": "lbl_802DD948",  # pfInit (fn_8000C228) stores FONT_COLOR_WHITE (15) here
}


def load(path):
    sections = {}
    for line in path.read_text(encoding="utf8").splitlines():
        m = LINE.match(line)
        if not m:
            continue
        name, sec, addr, typ, size = m.groups()
        sections.setdefault(sec, []).append((name, int(addr, 16), typ, int(size or "0", 16)))
    for syms in sections.values():
        syms.sort(key=lambda s: s[1])
    return sections


def build_map():
    e, p = load(E01), load(P01)
    mapping = {}
    for sec in e:
        if sec not in p:
            continue
        a, b = e[sec], p[sec]
        sm = difflib.SequenceMatcher(None, [(t, s) for _, _, t, s in a], [(t, s) for _, _, t, s in b], autojunk=False)
        for blk in sm.get_matching_blocks():
            if blk.size == 0:
                continue
            if a[blk.a][2] != "function" and blk.size < MIN_RUN:
                continue
            for k in range(blk.size):
                ename = a[blk.a + k][0]
                pname = b[blk.b + k][0]
                if GENERIC.match(ename) or ename == pname or "@" in ename or "$" in ename:
                    continue
                mapping[ename] = pname
    mapping.update(EXTRA)
    for name, want in ANCHORS.items():
        got = mapping.get(name)
        if got != want:
            raise SystemExit(f"anchor {name}: expected {want}, alignment gave {got}")
    return mapping


DOL = ROOT / "orig" / "GP6P01" / "sys" / "main.dol"
DATADIR_PROBE = b"data/actman.bin\0"  # first entry of the data directory table


def eu_datadirs():
    """{name: index} of the P01 data directory table (8-byte entries: path pointer, -1). The EU table has extra
    language directories, so the indices differ from include/datadir_table.h (US): e.g. saf is 214, not 202."""
    dol = DOL.read_bytes()
    offs = struct.unpack_from(">18I", dol, 0)
    addrs = struct.unpack_from(">18I", dol, 0x48)
    sizes = struct.unpack_from(">18I", dol, 0x90)

    def to_addr(o):
        return next(a + o - f for f, a, s in zip(offs, addrs, sizes) if f <= o < f + s)

    def to_off(x):
        return next(f + x - a for f, a, s in zip(offs, addrs, sizes) if a <= x < a + s)

    start = dol.find(struct.pack(">I", to_addr(dol.find(DATADIR_PROBE))))
    out = {}
    for i in range(1000):
        ptr = struct.unpack_from(">I", dol, start + 8 * i)[0]
        if not 0x80000000 <= ptr < 0x81800000:
            break
        o = to_off(ptr)
        path = dol[o:dol.index(b"\0", o)].decode("ascii")
        m = re.fullmatch(r"data/(\w+)\.bin", path)
        if m:
            out[m.group(1)] = i
    return out


def header_macros():
    """Names the headers already #define (some E01 functions are macros in the decomp headers)."""
    names = set()
    for path in (ROOT / "include").rglob("*.h"):
        for m in re.finditer(r"^\s*#\s*define\s+(\w+)", path.read_text(encoding="utf8", errors="replace"), re.M):
            names.add(m.group(1))
    return names


def main(argv):
    mapping = build_map()
    for name in header_macros():
        mapping.pop(name, None)
    if argv[:1] == ["--check"]:
        missing = 0
        for name in argv[1:]:
            print(f"{name:32} {mapping.get(name, '<missing>')}")
            missing += name not in mapping
        return 1 if missing else 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = ["/* Generated by tools/closecall/p01_names.py: E01 names -> P01 symbols. Do not edit. */",
             "#ifndef P01_NAMES_H", "#define P01_NAMES_H"]
    lines += [f"#define {e} {p}" for e, p in sorted(mapping.items())]
    dirs = sorted(eu_datadirs().items(), key=lambda kv: kv[1])
    lines += ["", "/* P01 data directory numbers. */"]
    lines += [f"#define P01_DATA_{n} ({i} << 16)" for n, i in dirs]
    # Take over include/datadir_enum.h (US numbering: e.g. mariomot is 147 there, 155 on the Europe disc) so
    # DATA_* and everything built on it (datanum/*.h: MARIOMOT_HSF_*, CHARMOT_FILE, EFFECT_ANM_*) uses the
    # Europe directory table. A US-only directory name then fails to compile instead of loading a wrong file.
    lines += ["", "#ifndef DATADIR_ENUM", "#define DATADIR_ENUM", "enum {"]
    lines += [f"    DATA_{n} = {i} << 16," for n, i in dirs]
    lines += ["};", "#define DATANUM(dir, file) ((dir)|(file))", "#define FILENUM(dataNum) ((dataNum) & 0xFFFF)",
              "#define DIRNUM(dataNum) ((dataNum) & 0xFFFF0000)", "#endif"]
    lines += ["#endif", ""]
    OUT.write_text("\n".join(lines), encoding="utf8")
    print(f"{OUT} ({len(mapping)} names)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
