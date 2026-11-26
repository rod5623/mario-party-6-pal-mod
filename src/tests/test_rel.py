"""tools.lib.rel: relocation walking, add_calls, retarget_call, check_words."""
import struct

import pytest

from tests.builders import SELF_MODULE, make_rel
from tools.lib.rel import (
    R_DOLPHIN_END, R_DOLPHIN_NOP, R_PPC_REL24, add_calls, check_words, import_blocks, retarget_call, text_base, walk_relocs,
)

R_PPC_ADDR16_HA = 6
TEXT = bytes.fromhex("38600000" * 16)   # 16 x li r3,0


def module0(rel):
    return [(section, cursor, kind, addend)
            for _, section, cursor, kind, _, addend in walk_relocs(rel, import_blocks(rel)[0])]


def text_word(rel, offset):
    return bytes(rel[text_base(rel) + offset:text_base(rel) + offset + 4])


def base_rel():
    return make_rel(TEXT, relocs=[(0x08, R_PPC_REL24, 0, 0x8017E03C), (0x20, R_PPC_ADDR16_HA, 0, 0x80300000)],
                    self_relocs=[(0x04, R_PPC_REL24, 1, 0x30)])


def test_text_base_and_import_blocks():
    rel = base_rel()
    assert text_base(rel) % 0x20 == 0
    assert text_word(rel, 0) == TEXT[:4]
    assert set(import_blocks(rel)) == {0, SELF_MODULE}


def test_walk_relocs():
    rel = base_rel()
    assert module0(rel) == [(1, 0x08, R_PPC_REL24, 0x8017E03C), (1, 0x20, R_PPC_ADDR16_HA, 0x80300000)]
    self_block = [(s, c, k, a) for _, s, c, k, _, a in walk_relocs(rel, import_blocks(rel)[SELF_MODULE])]
    assert self_block == [(1, 0x04, R_PPC_REL24, 0x30)]


def test_add_calls_one_site():
    rel = base_rel()
    size = len(rel)
    assert add_calls(rel, [(0x10, 0x80004000)]) == 1
    assert text_word(rel, 0x10) == bytes.fromhex("48000001")
    assert module0(rel)[-1] == (1, 0x10, R_PPC_REL24, 0x80004000)
    assert len(rel) == size + 16          # one R_DOLPHIN_SECTION + one REL24
    assert struct.unpack_from(">HBBI", rel, len(rel) - 8)[1] == R_DOLPHIN_END
    # the existing relocations are untouched
    assert module0(rel)[:2] == module0(base_rel())


def test_add_calls_is_idempotent():
    rel = base_rel()
    add_calls(rel, [(0x10, 0x80004000)])
    before = bytes(rel)
    assert add_calls(rel, [(0x10, 0x80004000)]) == 0
    assert rel == before


def test_add_calls_two_sites_sorted():
    rel = base_rel()
    assert add_calls(rel, [(0x30, 0x80004100), (0x0C, 0x80004000)]) == 2
    new = module0(rel)[2:]
    assert new == [(1, 0x0C, R_PPC_REL24, 0x80004000), (1, 0x30, R_PPC_REL24, 0x80004100)]
    # deltas: the first record counts from the R_DOLPHIN_SECTION reset, the second from the first
    deltas = [struct.unpack_from(">H", rel, len(rel) - 8 * n)[0] for n in (3, 2)]
    assert deltas == [0x0C, 0x30 - 0x0C]


def test_add_calls_long_gap_uses_nop_records():
    # the delta field is 16 bits: a site more than 0xFFFF bytes after the previous one needs NOPs
    rel = make_rel(bytes(0x20010), relocs=[(0x08, R_PPC_REL24, 0, 0x8017E03C)])
    assert add_calls(rel, [(0x1FFF0, 0x80004000), (0x8, 0x8017E03C)]) == 1
    assert module0(rel)[-1] == (1, 0x1FFF0, R_PPC_REL24, 0x80004000)
    kinds = [k for _, _, _, k, _, _ in walk_relocs(rel, import_blocks(rel)[0])]
    assert kinds.count(R_DOLPHIN_NOP) == 1
    assert add_calls(rel, [(0x1FFF0, 0x80004000)]) == 0


def test_add_calls_skips_only_the_existing_site():
    rel = base_rel()
    add_calls(rel, [(0x10, 0x80004000)])
    assert add_calls(rel, [(0x10, 0x80004000), (0x14, 0x80004000)]) == 1
    assert [r[1] for r in module0(rel)[2:]] == [0x10, 0x14]


def test_add_calls_needs_trailing_end_record():
    rel = base_rel() + b"\0" * 8          # something after the module-0 block
    with pytest.raises(RuntimeError):
        add_calls(rel, [(0x10, 0x80004000)])


def test_add_calls_rejects_module0_not_last():
    # another module's block also ends in R_DOLPHIN_END, so the file's last record alone proves nothing
    rel = make_rel(TEXT, relocs=[(0x08, R_PPC_REL24, 0, 0x8017E03C)],
                   self_relocs=[(0x04, R_PPC_REL24, 1, 0x30)], module0_last=False)
    before = bytes(rel)
    with pytest.raises(RuntimeError):
        add_calls(rel, [(0x10, 0x80004000)])
    assert rel == before          # nothing written, not even the bl at the site


def test_retarget_call():
    rel = base_rel()
    assert retarget_call(rel, 0x08, 0x8017E03C, 0x80005000) is True
    assert module0(rel)[0] == (1, 0x08, R_PPC_REL24, 0x80005000)
    before = bytes(rel)
    assert retarget_call(rel, 0x08, 0x8017E03C, 0x80005000) is False
    assert rel == before


def test_retarget_call_errors():
    rel = base_rel()
    with pytest.raises(RuntimeError):
        retarget_call(rel, 0x08, 0x80000000, 0x80005000)    # wrong old target
    with pytest.raises(RuntimeError):
        retarget_call(rel, 0x0C, 0x8017E03C, 0x80005000)    # no relocation there
    with pytest.raises(RuntimeError):
        retarget_call(rel, 0x20, 0x80300000, 0x80005000)    # relocation is not a REL24


def test_check_words():
    rel = base_rel()
    check_words(rel, 0x10, "38600000", "48000001")
    add_calls(rel, [(0x10, 0x80004000)])
    check_words(rel, 0x10, "38600000", "48000001")
    with pytest.raises(RuntimeError):
        check_words(rel, 0x10, "38600000")


def test_text_base_without_text_section():
    rel = base_rel()
    struct.pack_into(">I", rel, struct.unpack_from(">I", rel, 0x10)[0] + 8, 0)
    with pytest.raises(RuntimeError):
        text_base(rel)
