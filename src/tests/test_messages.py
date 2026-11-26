"""tools.lib.messages: text encoding, records, bank splicing and the chained bank edits."""
import pytest

from tests.builders import make_messdata, read_bank, read_banks
from tools.lib.messages import (append_records, bank_records, edit_bank, encode, record, set_bank, splice_bank,
                                 write_bank)


def rec(text):
    return record("0B", encode(text), b"\x00")


BANKS = [
    [rec("zero a"), rec("zero b")],
    [rec("one a"), rec("one b"), rec("one c")],
    [rec("two a")],
]


def vanilla():
    return bytes(make_messdata(BANKS))


def test_builder_round_trip():
    assert read_banks(vanilla()) == BANKS


@pytest.mark.parametrize("text, encoded", [
    ("Hi!?", b"Hi\xc2\xc3"),
    ("a b", b"a\x10b"),
    ("a,b", b"a\x82b"),
    ("a\nb", b"a\x0ab"),
    ("<N>x", b"\x1f\x01x"),
    ("<", b"<"),
])
def test_encode(text, encoded):
    assert encode(text) == encoded


@pytest.mark.parametrize("body", [b"", b"a", b"ab", b"abc", b"abcd"])
def test_record_is_padded(body):
    data = record("0B", body, b"\x00")
    assert len(data) % 4 == 0
    assert data.startswith(b"\x0b" + body + b"\x00")
    assert data[2 + len(body):] == b"\0" * (len(data) - 2 - len(body))


def test_splice_bank():
    donor_banks = [list(b) for b in BANKS]
    donor_banks[1] = [rec("replaced, and longer than before"), rec("x")]
    donor = make_messdata(donor_banks)
    out = splice_bank(vanilla(), donor, 1)
    assert read_banks(out) == [BANKS[0], donor_banks[1], BANKS[2]]
    assert len(out) == len(donor)


def test_splice_bank_bank_count_mismatch():
    with pytest.raises(RuntimeError):
        splice_bank(make_messdata(BANKS[:2]), vanilla(), 1)


def test_write_bank_uses_output_if_present(tmp_path):
    source, output = tmp_path / "src.bin", tmp_path / "out" / "messdata.bin"
    source.write_bytes(vanilla())
    donor_a = [list(b) for b in BANKS]
    donor_a[0] = [rec("patch A")]
    donor_b = [list(b) for b in BANKS]
    donor_b[2] = [rec("patch B")]

    write_bank(output, source, make_messdata(donor_a), 0)     # no output yet: starts from source
    assert read_banks(output.read_bytes()) == [donor_a[0], BANKS[1], BANKS[2]]
    write_bank(output, source, make_messdata(donor_b), 2)     # keeps patch A's bank
    assert read_banks(output.read_bytes()) == [donor_a[0], BANKS[1], donor_b[2]]


OURS = [rec("ours 1"), rec("ours 2")]
LATER = [rec("a later patch")]
OLD_OURS = [rec("our old version")]


def test_edit_bank_append():
    out = edit_bank(vanilla(), {}, "test", 1, 3, append=OURS)
    assert read_banks(out) == [BANKS[0], BANKS[1] + OURS, BANKS[2]]


def test_edit_bank_rerun_is_identical():
    once = edit_bank(vanilla(), {}, "test", 1, 3, append=OURS)
    assert edit_bank(once, {}, "test", 1, 3, append=OURS) == once


def test_edit_bank_later_tail_needs_known_tails():
    ours = edit_bank(vanilla(), {}, "ours", 1, 3, append=OURS)
    both = edit_bank(ours, {}, "later", 1, 5, append=LATER)
    with pytest.raises(RuntimeError):
        edit_bank(both, {}, "ours", 1, 3, append=OURS)
    # with the later patch's records listed, ours is rebuilt and the later records are dropped
    rebuilt = edit_bank(both, {}, "ours", 1, 3, append=OURS, known_tails=[OURS + LATER])
    assert rebuilt == ours


def test_edit_bank_rebuilds_old_version():
    old = edit_bank(vanilla(), {}, "old", 1, 3, append=OLD_OURS)
    new = edit_bank(old, {}, "new", 1, 3, append=OURS, known_tails=[OLD_OURS])
    assert read_bank(new, 1) == BANKS[1] + OURS


def test_edit_bank_unknown_extras():
    other = edit_bank(vanilla(), {}, "other", 1, 3, append=LATER)
    with pytest.raises(RuntimeError):
        edit_bank(other, {}, "ours", 1, 3, append=OURS)


def test_edit_bank_replacements():
    out = edit_bank(vanilla(), {0: rec("new zero, a lot longer"), 2: rec("c")}, "test", 1, 3)
    assert read_bank(out, 1) == [rec("new zero, a lot longer"), BANKS[1][1], rec("c")]


def test_edit_bank_shifts_later_banks():
    out = edit_bank(vanilla(), {}, "test", 0, 2, append=OURS)
    assert read_banks(out) == [BANKS[0] + OURS, BANKS[1], BANKS[2]]
    assert len(out) == len(vanilla()) + 4 * len(OURS) + sum(map(len, OURS))


def test_edit_bank_last_bank():
    out = edit_bank(vanilla(), {}, "test", 2, 1, append=OURS)
    assert read_banks(out) == [BANKS[0], BANKS[1], BANKS[2] + OURS]


def test_append_records():
    out = append_records(vanilla(), {1: (3, OURS), 2: (1, LATER)}, "test")
    assert read_banks(out) == [BANKS[0], BANKS[1] + OURS, BANKS[2] + LATER]
    assert append_records(out, {1: (3, OURS), 2: (1, LATER)}, "test") == out
    with pytest.raises(RuntimeError):
        append_records(out, {1: (3, OLD_OURS + [rec("x")])}, "test")    # same count, other records
    with pytest.raises(RuntimeError):
        append_records(out, {1: (2, OURS)}, "test")                     # unexpected count


def test_bank_out_of_range():
    with pytest.raises(RuntimeError):
        splice_bank(vanilla(), vanilla(), 3)


NEW = [rec("new a"), rec("new b")]


def test_set_bank_appends_and_is_idempotent():
    once = set_bank(vanilla(), 3, NEW, "test")
    assert read_banks(once) == BANKS + [NEW]
    assert set_bank(once, 3, NEW, "test") == once


def test_set_bank_rebuilds_a_known_older_version():
    old = set_bank(vanilla(), 3, [rec("old")], "test")
    assert read_banks(set_bank(old, 3, NEW, "test", known=[[rec("old")]])) == BANKS + [NEW]
    with pytest.raises(RuntimeError, match="different"):
        set_bank(old, 3, NEW, "test")


def test_set_bank_rejects_another_bank_count():
    with pytest.raises(RuntimeError, match="banks"):
        set_bank(vanilla(), 4, NEW, "test")


def test_bank_records():
    assert bank_records(vanilla(), 1) == BANKS[1]


def test_splice_bank_keeps_appended_banks():
    target = set_bank(vanilla(), 3, NEW, "test")
    donor = make_messdata([BANKS[0], [rec("spliced")], BANKS[2]])
    assert read_banks(splice_bank(target, donor, 1)) == [BANKS[0], [rec("spliced")], BANKS[2], NEW]
    with pytest.raises(RuntimeError):
        splice_bank(vanilla(), bytes(target), 1)    # the donor may not have more banks than the target
