"""mp7_rel_coverage: masking relocated fields, and the anchor chain."""
from tools.scripts.mp7_rel_coverage import increasing_chain, normalize


def test_normalize_masks_relocated_fields():
    a = [0x48000001 | 0x1234, 0x3C608028, 0x38633290, 0x88030008, 0x800D9930]   # bl; lis r3; addi r3,r3; lbz r0,8(r3); lwz r0,sda(r13)
    b = [0x48000001 | 0x5678, 0x3C60802B, 0x38634018, 0x88030008, 0x800D9A00]
    assert normalize(a) == normalize(b)
    assert normalize([0x38600003]) != normalize([0x38600004])                    # li r3: a real constant, kept
    assert normalize([0x3C608028, 0x88030008]) == normalize([0x3C608028, 0x8803000C])  # lbz lo(r3): the low half
    field = [0x3C608028, 0x38633290, 0x8803000C]                                  # lis; addi; lbz r0,0xC(r3)
    assert normalize(field) != normalize(field[:2] + [0x88030008])                # a struct field: kept


def test_increasing_chain_drops_out_of_order_matches():
    pairs = [(1, 10), (2, 20), (3, 5), (4, 30), (5, 40)]
    assert increasing_chain(pairs) == [(1, 10), (2, 20), (4, 30), (5, 40)]
    assert increasing_chain([]) == []
