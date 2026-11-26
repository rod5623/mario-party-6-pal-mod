"""Disassemble a Mario Party 7 REL with its main.dol calls named by their MP6 PAL match.

    python -m tools.scripts.mp7_rel_dis w02dll 0x100c4             # the function containing .text 0x100C4
    python -m tools.scripts.mp7_rel_dis w02dll 0x100c4 0x10200     # a .text range
    python -m tools.scripts.mp7_rel_dis w02dll --high 0x14         # where ids 0x14nnnn are built (messages)
    python -m tools.scripts.mp7_rel_dis w02dll --high 0xfe         # data numbers 0xFEnnnn (w02.bin files)

Reads files/dll/<name>.rel and sys/main.dol from the user's MP7 disc (tools.lib.mp7) and orig/GP6P01.
Each module-0 call is shown as `MP7 0x8017062c -> MP6 0x801687f4 mbObjCreate (near 0.97)`: the match comes
from tools.scripts.mp7_rel_coverage (exact / near / missing; a "near" or "missing" match needs checking by
hand) and the name from build/GP6P01/include/p01_names.h when it exists. Data relocations show the MP7
address, and calls and pointers into the REL itself show their .text offset.

Notes:
  * Words are disassembled one at a time. capstone stops a run at the first word it can't decode (Gekko
    paired-single instructions), which would hide the rest of a function. Undecodable words print as
    .word.
  * Function bounds are found from stack frames: back to the `stwu r1` prologue, forward to a `blr`
    followed by the next prologue. A leaf function with no frame needs an explicit range.
  * Calls inside the REL itself aren't relocated, so their `bl` shows the .text offset directly.
  * MP7 builds 32-bit ids as `lis rX, high` then `addi`/`ori` with the low half; --high finds those.
Needs capstone (requirements.txt). Read-only.
"""
import argparse
import re
import struct
import sys
from collections import defaultdict

from tools.lib import mp7
from tools.lib.paths import BUILD, ORIG
from tools.lib.rel import R_PPC_REL24, import_blocks, text_base, walk_relocs
from tools.scripts.mp7_rel_coverage import Dol, match

BLR = 0x4E800020
STWU_R1 = 0x9421          # stwu r1, -n(r1): the start of a stack frame
OP_LIS, OP_ADDI, OP_ORI = 15, 14, 24
NAMES_HEADER = BUILD / "include" / "p01_names.h"


def text_words(rel):
    """(file offset of .text, its words as a list)."""
    base = text_base(rel)
    count, table = struct.unpack_from(">II", rel, 0x0C)
    sections = [struct.unpack_from(">II", rel, table + 8 * i) for i in range(count)]
    size = next(size for offset, size in sections if offset & 1)
    return base, list(struct.unpack_from(f">{size // 4}I", rel, base))


def function_bounds(words, index):
    """(first, end) word indices of the function around words[index], from its stack frame."""
    start = index
    while start > 0 and words[start] >> 16 != STWU_R1:
        start -= 1
    end = index + 1
    while end < len(words) and not (words[end - 1] == BLR and words[end] >> 16 == STWU_R1):
        end += 1
    return start, end


def high_low_refs(words, high, window=4):
    """{value: [word index of the lis]} for `lis rX, high` followed by addi/ori rY, rX, low."""
    refs = defaultdict(list)
    for i, w in enumerate(words):
        if w >> 26 != OP_LIS or (w >> 16) & 31 or w & 0xFFFF != high:
            continue
        reg = (w >> 21) & 31
        for w2 in words[i + 1:i + 1 + window]:
            if w2 >> 26 in (OP_ADDI, OP_ORI) and (w2 >> 16) & 31 == reg:
                low = w2 & 0xFFFF
                if w2 >> 26 == OP_ADDI and low & 0x8000:
                    low -= 0x10000
                refs[(high << 16) + low].append(i)
                break
    return dict(refs)


def p01_names(path=NAMES_HEADER):
    """{address: name} from p01_names.h (empty if it hasn't been generated)."""
    names = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"#define (\w+) (?:fn|lbl)_([0-9A-F]{8})$", line.strip())
            if m:
                names.setdefault(int(m.group(2), 16), m.group(1))
    return names


def describe_call(target, matched, names):
    """`MP7 <target> -> MP6 <address> <name> (<kind> <similarity>)` for one module-0 call."""
    kind, mp6, score = matched.get(target, ("missing", None, 0.0))
    if mp6 is None or kind == "missing":
        return f"MP7 {target:#x} -> MP6 missing"
    return f"MP7 {target:#x} -> MP6 {mp6:#x} {names.get(mp6, '')} ({kind} {score:.2f})".replace("  ", " ")


class Rel:
    def __init__(self, name):
        self.name = name
        self.data = mp7.read(f"files/dll/{name}.rel")
        self.base, self.words = text_words(self.data)
        self.calls, self.data_refs, self.own = {}, {}, {}
        blocks = import_blocks(self.data)
        own_id = struct.unpack_from(">I", self.data, 0)[0]
        for module, block in blocks.items():
            for _, section, offset, kind, target_section, addend in walk_relocs(self.data, block):
                if section != 1:
                    continue
                at = offset & ~3
                if module == 0:
                    (self.calls if kind == R_PPC_REL24 else self.data_refs)[at] = addend
                elif module == own_id:
                    self.own[at] = (target_section, addend)
        self._matched = None
        self._names = None

    def matched(self):
        if self._matched is None:
            dol6 = Dol((ORIG / "sys" / "main.dol").read_bytes())
            dol7 = Dol(mp7.read("sys/main.dol"))
            self._matched, symbols, _ = match(dol6, dol7, sorted(set(self.calls.values())))
            self._names = {**symbols, **p01_names()}
        return self._matched

    def listing(self, first, end):
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_32 | capstone.CS_MODE_BIG_ENDIAN)
        matched = self.matched()
        lines = []
        for index in range(first, end):
            offset = 4 * index
            word = self.words[index]
            decoded = list(md.disasm(struct.pack(">I", word), offset))
            text = f"{decoded[0].mnemonic} {decoded[0].op_str}" if decoded else f".word {word:#010x}"
            if offset in self.calls:
                text = f"bl {describe_call(self.calls[offset], matched, self._names)}"
            elif offset in self.data_refs:
                text += f"    ; MP7 data {self.data_refs[offset]:#x}"
            elif offset in self.own:
                section, addend = self.own[offset]
                text += f"    ; {self.name} section {section} +{addend:#x}"
            lines.append(f"  {offset:05x}  {text.rstrip()}")
        return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("rel", help="MP7 REL name without .rel, e.g. w02dll")
    parser.add_argument("offsets", nargs="*", help=".text offset (its function) or a start and end offset")
    parser.add_argument("--high", help="list where ids with this high half are built (e.g. 0x14, 0xfe)")
    args = parser.parse_args(argv)
    rel = Rel(args.rel)
    if args.high:
        for value, indices in sorted(high_low_refs(rel.words, int(args.high, 0)).items()):
            print(f"{value:#010x}  " + " ".join(f"{4 * i:#x}" for i in indices))
        return
    if not args.offsets:
        parser.error("give a .text offset, a range, or --high")
    if len(args.offsets) == 1:
        first, end = function_bounds(rel.words, int(args.offsets[0], 0) // 4)
    else:
        first, end = int(args.offsets[0], 0) // 4, int(args.offsets[1], 0) // 4
    print(f"{args.rel} .text {4 * first:#x}-{4 * end:#x}")
    print(rel.listing(first, end))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
