"""apply_party_pages_patch.py: the board select page hooks and the generated asm (no game files needed)."""
import re

import pytest

from tools.lib.board_tables import BOARD_NO_READS
from tools.patches import apply_party_pages_patch as pages


def listing(words):
    """A fake dtk listing: {text offset: instruction} as `/* OFFSET FILEOFF  BYTES */\tinsn` lines."""
    return "\n".join(f"/* {o:08X} {o + 0xE4:08X}  00 00 00 00 */\t{insn}" for o, insn in sorted(words.items()))


def vanilla_words():
    words = {o: v for o, v, _ in pages.HOOKS if v is not None}
    words.update({o: "li r0, 0x0" for o, v, _ in pages.HOOKS if v is None})
    return words


def test_hooks_replace_word_for_word():
    text = pages.hook_text(listing(vanilla_words()))
    lines = text.split("\n")
    assert len(lines) == len(pages.HOOKS)
    new = {int(line[3:11], 16): line.split("\t", 1)[1] for line in lines}
    assert new == {o: n for o, _, n in pages.HOOKS}


def test_hooks_refuse_unknown_words():
    words = vanilla_words()
    words[0x1954C] = "sth r4, 0x4(r3)"
    with pytest.raises(RuntimeError):
        pages.hook_text(listing(words))


def test_hooks_refuse_a_label_inside_a_block():
    text = listing(vanilla_words()).replace("/* 00018960", ".L_00018960:\n/* 00018960")
    with pytest.raises(RuntimeError):
        pages.hook_text(text)


def test_hooks_avoid_clone_board_sites():
    ours = {o for o, _, _ in pages.HOOKS}
    theirs = {read.where for read in BOARD_NO_READS if read.file == "mdpartydll.rel"}
    assert not ours & theirs
    assert len(ours) == len(pages.HOOKS)


def test_blocks_are_whole():
    for block in (pages.LEFT, pages.RIGHT):
        offsets = [o for o, _, _ in block]
        assert offsets == list(range(offsets[0], offsets[0] + 4 * len(block), 4))
        assert block[0][2].startswith("bl ") and all(n == "nop" for _, _, n in block[1:])


def test_generated_asm_defines_what_it_calls():
    defined = set(re.findall(r"^\.fn (\w+),", pages.TEXT_CODE, re.M))
    called = set(re.findall(r"\bb(?:l)? (fn_1_pg_\w+)", pages.TEXT_CODE))
    hooked = {n.split()[1] for _, _, n in pages.HOOKS if n.startswith("bl ")}
    assert called <= defined and hooked <= defined
    labels = re.findall(r"^(\.L_pg_\w+):", pages.TEXT_CODE, re.M)
    assert len(labels) == len(set(labels))
    for target in re.findall(r"\b(?:b|beq|bne|blt|bge|ble|bgt) (\.L_pg_\w+)", pages.TEXT_CODE):
        assert target in labels
    objects = set(re.findall(r"\.obj (\w+),", pages.data_text() + pages.bss_text()))
    used = set(re.findall(r"(lbl_1_(?:data|bss)_pg_\w+)@", pages.TEXT_CODE))
    assert used <= objects


def test_board_table_matches_the_data():
    rows = re.findall(r"\.4byte (0x[0-9A-F]+), (0x[0-9A-F]+), (0x[0-9A-F]+), (0x[0-9A-F]+), (0x[0-9A-F]+)",
                      pages.data_text())
    assert len(rows) == len(pages.EXTRA_BOARDS)
    for row, board in zip(rows, pages.EXTRA_BOARDS):
        values = [int(v, 16) for v in row]
        assert values[:2] == [board.board_no, board.overlay]
        assert values[2:] == [pages.MDPARTY_DIR | n for n in (board.icon, board.disc_day, board.disc_night)]
    files = [pages.EMPTY_ICON] + [n for b in pages.EXTRA_BOARDS for n in (b.icon, b.disc_day, b.disc_night)]
    assert files == list(range(pages.MDPARTY_FILES, pages.NEW_FILES))
