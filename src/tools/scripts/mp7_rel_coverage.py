"""Match a Mario Party 7 REL's main.dol calls to MP6 PAL functions: python -m tools.scripts.mp7_rel_coverage [w02dll]

For every module-0 relocation in MP7 files/dll/<name>.rel, the MP7 DOL target is matched to an MP6 PAL
function (orig/GP6P01/sys/main.dol, names and sizes from config/GP6P01/symbols.txt):
  * Code is compared with the relocated fields masked: b/bl and bc offsets, `lis` immediates and the
    low halves that use them, and r2/r13 offsets.
  * Pass 1 finds exact matches anywhere. The unique ones that keep the same order in both DOLs (the
    longest increasing chain) become anchors, since both games link the engine in the same order.
  * Pass 2 searches each other target only between its two neighbouring anchors' MP6 addresses:
    "exact", else "near" (difflib similarity of the masked words >= NEAR), else "missing".
MP7 function sizes come from the next bl target in the MP7 DOL (or a blr followed by a new stack frame).
A "near" or "missing" result can still be the same function compiled differently (MP6's code spills
arguments to the stack where MP7's doesn't), so it means "needs checking by hand".

Prints a Markdown report (plans/pagoda-peak/route-a-coverage.md is this output for w02dll). Read-only.
"""
import re
import struct
import sys
from bisect import bisect_left
from collections import Counter, defaultdict
from difflib import SequenceMatcher

from tools.lib import mp7
from tools.lib.paths import ORIG, ROOT
from tools.lib.rel import R_PPC_REL24, import_blocks, walk_relocs

NEAR = 0.6
D_FORM = {14, 24, *range(32, 56)}      # addi, ori, loads and stores
BLR, STWU_R1 = 0x4E800020, 0x9421


class Dol:
    def __init__(self, blob):
        self.sections = []
        for i in range(7):
            offset, address, size = (struct.unpack_from(">I", blob, base + 4 * i)[0] for base in (0, 0x48, 0x90))
            if size:
                self.sections.append((address, blob[offset:offset + size]))

    def word(self, address):
        for base, blob in self.sections:
            if base <= address < base + len(blob):
                return struct.unpack_from(">I", blob, address - base)[0]
        return None

    def words(self, address, count):
        return [self.word(address + 4 * i) or 0 for i in range(count)]

    def call_targets(self):
        out = set()
        for base, blob in self.sections:
            for i in range(0, len(blob), 4):
                w = struct.unpack_from(">I", blob, i)[0]
                if w >> 26 == 18 and w & 3 == 1:
                    offset = w & 0x03FFFFFC
                    out.add(base + i + offset - (0x04000000 if offset & 0x02000000 else 0))
        return sorted(out)


def normalize(words):
    """Mask what relocation and layout change: branch offsets, lis/low-half pairs and small-data offsets."""
    out, high = [], set()
    for w in words:
        op, rd, ra = w >> 26, (w >> 21) & 31, (w >> 16) & 31
        if op == 18:
            w &= 0xFC000003
        elif op == 16:
            w &= 0xFFFF0003
        elif op == 15 and ra == 0:
            w &= 0xFFFF0000
            high.add(rd)
        elif op in D_FORM and (ra in high or ra in (2, 13)):
            w &= 0xFFFF0000
            if op in (14, 24):           # addi/ori completes the address: offsets through it are real fields
                high.discard(rd)
        elif op in (14, 15, 21, 24, 31) and rd in high:
            high.discard(rd)
        out.append(w)
    return out


def mp6_functions(dol):
    functions = {}
    for line in open(ROOT / "config" / "GP6P01" / "symbols.txt", encoding="utf-8"):
        m = re.match(r"(\S+) = \.\w+:0x([0-9A-F]+); // type:function size:0x([0-9A-F]+)", line)
        if m:
            address, size = int(m.group(2), 16), int(m.group(3), 16)
            if dol.word(address) is not None:
                functions[address] = (m.group(1), normalize(dol.words(address, size // 4)))
    return functions


def mp7_size(dol, starts, address):
    i = bisect_left(starts, address + 1)
    end = starts[i] if i < len(starts) else address + 4
    for p in range(address, end, 4):
        if dol.word(p) == BLR and (dol.word(p + 4) or 0) >> 16 == STWU_R1:
            return p + 4 - address
    return end - address


def increasing_chain(pairs):
    """Longest chain of (mp7, mp6) pairs that increases in both."""
    pairs = sorted(pairs)
    length, prev = [1] * len(pairs), [-1] * len(pairs)
    for i in range(len(pairs)):
        for j in range(i):
            if pairs[j][1] < pairs[i][1] and length[j] + 1 > length[i]:
                length[i], prev[i] = length[j] + 1, j
    i = max(range(len(pairs)), key=length.__getitem__, default=-1)
    chain = []
    while i >= 0:
        chain.append(pairs[i])
        i = prev[i]
    return chain[::-1]


def match(dol6, dol7, targets):
    """{mp7 address: (kind, mp6 address or None, similarity)} for each target."""
    functions = mp6_functions(dol6)
    by_head = defaultdict(list)
    for address, (_, words) in functions.items():
        by_head[tuple(words[:4])].append(address)
    starts = dol7.call_targets()

    def exact_in(t, candidates):
        size = mp7_size(dol7, starts, t)
        mine = normalize(dol7.words(t, size // 4))
        return [a for a in candidates if functions[a][1] in (mine, normalize(dol7.words(t, len(functions[a][1]))))]

    unique = []
    for t in targets:
        found = exact_in(t, by_head.get(tuple(normalize(dol7.words(t, 4))), []))
        if len(found) == 1:
            unique.append((t, found[0]))
    anchors = increasing_chain(unique)
    ordered = sorted(functions)
    result = {}
    for t in targets:
        low = max((a for a in anchors if a[0] <= t), default=(0, ordered[0]))
        high = min((a for a in anchors if a[0] >= t), default=(0, ordered[-1]))
        window = ordered[bisect_left(ordered, low[1]):bisect_left(ordered, high[1]) + 1]
        found = exact_in(t, window)
        if found:
            guess = low[1] + (t - low[0])
            result[t] = ("exact", min(found, key=lambda a: abs(a - guess)), 1.0)
            continue
        mine = normalize(dol7.words(t, mp7_size(dol7, starts, t) // 4))
        best, score = None, 0.0
        for a in window:
            matcher = SequenceMatcher(None, functions[a][1], mine, autojunk=False)
            if matcher.quick_ratio() > score and matcher.ratio() > score:
                best, score = a, matcher.ratio()
        result[t] = ("near" if score >= NEAR else "missing", best, score)
    return result, {a: functions[a][0] for a in functions}, len(anchors)


def report(name):
    rel = mp7.read(f"files/dll/{name}.rel")
    dol6 = Dol((ORIG / "sys" / "main.dol").read_bytes())
    dol7 = Dol(mp7.read("sys/main.dol"))
    calls, data = Counter(), Counter()
    for _, _, _, kind, _, target in walk_relocs(rel, import_blocks(rel)[0]):
        (calls if kind == R_PPC_REL24 else data)[target] += 1
    result, names, anchors = match(dol6, dol7, sorted(calls))
    kinds, sites = Counter(), Counter()
    for t, (kind, _, _) in result.items():
        kinds[kind] += 1
        sites[kind] += calls[t]
    lines = [f"# MP7 `{name}.rel`: main.dol calls matched to MP6 PAL",
             "",
             f"Generated by `python -m tools.scripts.mp7_rel_coverage {name}` (see its docstring for the method).",
             "",
             f"- Module-0 relocations: {sum(calls.values())} calls to {len(calls)} functions, "
             f"{sum(data.values())} data relocations to {len(data)} addresses. Anchors: {anchors}.",
             "",
             "| Result | Functions | Call sites |", "|---|---|---|"]
    for kind in ("exact", "near", "missing"):
        lines.append(f"| {kind} | {kinds[kind]} ({100 * kinds[kind] // len(calls)}%) | "
                     f"{sites[kind]} ({100 * sites[kind] // sum(calls.values())}%) |")
    lines += ["", "## Data targets", "", "| MP7 address | Relocations |", "|---|---|"]
    lines += [f"| `{a:#010x}` | {n} |" for a, n in sorted(data.items())]
    lines += ["", "## Code targets", "",
              "| MP7 | Calls | Result | Similarity | MP6 PAL |", "|---|---|---|---|---|"]
    for t in sorted(result):
        kind, a, score = result[t]
        mp6 = f"`{a:#010x}` {names[a]}" if a and kind != "missing" else "missing"
        lines.append(f"| `{t:#010x}` | {calls[t]} | {kind} | {score:.2f} | {mp6} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(report(sys.argv[1] if len(sys.argv) > 1 else "w02dll"), end="")
