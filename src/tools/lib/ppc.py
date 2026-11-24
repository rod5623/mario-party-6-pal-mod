"""PowerPC instruction encoders and the small Asm assembler used for code caves."""
import struct

from tools.lib.dol import encode_branch


class Asm:
    def __init__(self, base):
        self.base = base
        self.items = []  # ("w", word) | ("b", op, label) | ("bl", target) | ("l", name)
        self.labels = {}

    def word(self, w):
        self.items.append(("w", w & 0xFFFFFFFF))

    def label(self, name):
        self.items.append(("l", name))

    def branch(self, kind, label):
        self.items.append(("b", kind, label))

    def call(self, target):
        self.items.append(("bl", target))

    def assemble(self):
        pc = self.base
        for item in self.items:
            if item[0] == "l":
                self.labels[item[1]] = pc
            else:
                pc += 4
        out = []
        pc = self.base
        for item in self.items:
            if item[0] == "w":
                out.append(item[1])
            elif item[0] == "bl":
                out.append(encode_branch(pc, item[1], link=True))
            elif item[0] == "b":
                disp = self.labels[item[2]] - pc
                if item[1] == "b":
                    out.append(0x48000000 | (disp & 0x03FFFFFC))
                else:
                    bo, bi = {
                        "beq": (12, 2), "bne": (4, 2), "blt": (12, 0),
                        "bge": (4, 0), "ble": (4, 1), "bgt": (12, 1),
                    }[item[1]]
                    out.append((16 << 26) | (bo << 21) | (bi << 16) | (disp & 0xFFFC))
            if item[0] != "l":
                pc += 4
        return b"".join(struct.pack(">I", w) for w in out)


def ha(a):
    return ((a + 0x8000) >> 16) & 0xFFFF


def lo(a):
    return a & 0xFFFF


def i_addi(rd, ra, imm):
    return (14 << 26) | (rd << 21) | (ra << 16) | (imm & 0xFFFF)


def i_lis(rd, imm):
    return (15 << 26) | (rd << 21) | (imm & 0xFFFF)


def i_ori(ra, rs, imm):
    return (24 << 26) | (rs << 21) | (ra << 16) | (imm & 0xFFFF)


def i_mem(op, rt, ra, imm):
    return (op << 26) | (rt << 21) | (ra << 16) | (imm & 0xFFFF)

LWZ, STW, LBZ, LHZ, STH, STWU = 32, 36, 34, 40, 44, 37


def i_x(xo, rd, ra, rb):
    return (31 << 26) | (rd << 21) | (ra << 16) | (rb << 11) | (xo << 1)


def i_add(rd, ra, rb):
    return i_x(266, rd, ra, rb)


def i_lwzx(rd, ra, rb):
    return i_x(23, rd, ra, rb)


def i_cmpw(ra, rb):
    return i_x(0, 0, ra, rb)


def i_cmpwi(ra, imm):
    return (11 << 26) | (ra << 16) | (imm & 0xFFFF)


def i_cmplwi(ra, imm):
    return (10 << 26) | (ra << 16) | (imm & 0xFFFF)


def i_mulli(rd, ra, imm):
    return (7 << 26) | (rd << 21) | (ra << 16) | (imm & 0xFFFF)


def i_slwi(ra, rs, n):
    return (21 << 26) | (rs << 21) | (ra << 16) | (n << 11) | ((31 - n) << 1)


def i_clrlwi24(ra, rs):
    return (21 << 26) | (rs << 21) | (ra << 16) | (24 << 6) | (31 << 1)


def i_mr(ra, rs):
    return (24 << 26) | (rs << 21) | (ra << 16)  # ori ra,rs,0

MFLR = lambda r: 0x7C0802A6 | (r << 21)

MTLR = lambda r: 0x7C0803A6 | (r << 21)

MTCTR = lambda r: 0x7C0903A6 | (r << 21)

BCTR = 0x4E800420

BLR = 0x4E800020


def i_li(rd, imm):
    return i_addi(rd, 0, imm)


def i_rlwinm(ra, rs, sh, mb, me):
    return (21 << 26) | (rs << 21) | (ra << 16) | (sh << 11) | (mb << 6) | (me << 1)


def i_extsb(ra, rs):
    return i_x(954, rs, ra, 0)


def i_extsh(ra, rs):
    return i_x(922, rs, ra, 0)

LHA, STB, LFS = 42, 38, 48


def i_mullw(rd, ra, rb):
    return i_x(235, rd, ra, rb)


def i_divw(rd, ra, rb):
    return i_x(491, rd, ra, rb)


def i_subf(rd, ra, rb):
    return i_x(40, rd, ra, rb)


def i_or(ra, rs, rb):
    return i_x(444, rs, ra, rb)


def i_srawi(ra, rs, sh):
    return i_x(824, rs, ra, sh)


def i_lbzx(rd, ra, rb):
    return i_x(87, rd, ra, rb)


def i_addis(rd, ra, imm):
    return (15 << 26) | (rd << 21) | (ra << 16) | (imm & 0xFFFF)


def b_to(address, target):
    return encode_branch(address, target)


def prologue(a, frame, saved):
    """stwu / mflr, then save the callee-saved registers `saved` just below the back-chain slot."""
    a.word(i_mem(STWU, 1, 1, -frame))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, frame + 4))
    for r in saved:
        a.word(i_mem(STW, r, 1, frame - 4 * (32 - r)))


def epilogue(a, frame, saved):
    a.word(i_mem(LWZ, 0, 1, frame + 4))
    for r in saved:
        a.word(i_mem(LWZ, r, 1, frame - 4 * (32 - r)))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, frame))
    a.word(BLR)


def i_fadds(rd, ra, rb):
    return (59 << 26) | (rd << 21) | (ra << 16) | (rb << 11) | (21 << 1)
