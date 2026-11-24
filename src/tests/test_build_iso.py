"""tools.scripts.build_iso: GCR extract paths, and a rebuild that adds and replaces files."""
import pytest

from tests.builders import make_dol, make_gcm
from tools.scripts import build_iso

gcm_module = pytest.importorskip("gclib.gcm")

DISC = {
    "data/w01.bin": b"board one",
    "data/w02.bin": b"board two",
    "dll/w01Dll.rel": b"rel",
    "meminfo.bin": b"meminfo",
}


@pytest.mark.parametrize("relative, expected", [
    ("&&systemdata/Start.dol", "sys/main.dol"),
    ("&&systemdata/Game.toc", None),
    ("&&systemdata/ISO.hdr", None),
    ("README.md", None),
    ("data/README.md", "files/data/README.md"),
    ("data/w01.bin", "files/data/w01.bin"),
    ("meminfo.bin", "files/meminfo.bin"),
])
def test_disc_path(relative, expected):
    assert build_iso.disc_path(relative) == expected


def make_extract(folder, files, dol):
    (folder / "&&systemdata").mkdir(parents=True)
    (folder / "&&systemdata" / "Start.dol").write_bytes(dol)
    (folder / "&&systemdata" / "Game.toc").write_bytes(b"ignored")
    (folder / "README.md").write_text("not a game file")
    for path, data in files.items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_bytes(data)


def test_rebuild_adds_and_replaces(tmp_path):
    dol = make_dol([("text", 0x80003100, b"\x60\x00\x00\x00" * 8)])
    base = tmp_path / "base.iso"
    base.write_bytes(make_gcm(DISC, dol=dol))

    new_dol = make_dol([("text", 0x80003100, b"\x4e\x80\x00\x20" * 64)])
    extract = dict(DISC)
    extract["data/w02.bin"] = b"board two, patched and longer"   # replaced, grows
    extract["data/w07.bin"] = b"a new board"                     # added
    extract["dll/w07Dll.rel"] = b"a new rel"                     # added
    del extract["meminfo.bin"]                                   # kept from the base
    folder = tmp_path / "root"
    make_extract(folder, extract, new_dol)

    out = tmp_path / "out" / "new.iso"
    build_iso.main(["--base", str(base), "--out", str(out), "--folder", str(folder), "--add-test-file"])

    disc = gcm_module.GCM(str(out))
    disc.read_entire_disc()
    for path, data in extract.items():
        assert disc.read_file_raw_data("files/" + path) == data
    assert disc.read_file_raw_data("files/meminfo.bin") == DISC["meminfo.bin"]
    assert disc.read_file_raw_data(build_iso.TEST_FILE) == build_iso.TEST_FILE_DATA
    assert disc.read_file_raw_data("sys/main.dol") == new_dol
    assert disc.read_file_raw_data("sys/boot.bin")[:6] == b"GP6P01"
    assert "files/README.md" not in disc.files_by_path
    assert "files/&&systemdata/Game.toc" not in disc.files_by_path

    again = tmp_path / "out" / "again.iso"
    build_iso.main(["--base", str(base), "--out", str(again), "--folder", str(folder), "--add-test-file"])
    assert again.read_bytes() == out.read_bytes()


def test_unchanged_files_are_not_staged(tmp_path):
    base = tmp_path / "base.iso"
    dol = make_dol([("text", 0x80003100, b"\x60\x00\x00\x00" * 8)])
    base.write_bytes(make_gcm(DISC, dol=dol))
    folder = tmp_path / "root"
    make_extract(folder, DISC, dol)

    gcm = gcm_module.GCM(str(base))
    gcm.read_entire_disc()
    replaced, added, kept = build_iso.stage_changes(gcm, build_iso.folder_files(folder))
    assert (replaced, added, kept) == ([], [], [])
    assert gcm.changed_files == {}


def test_rejects_other_games(tmp_path):
    base = tmp_path / "base.iso"
    base.write_bytes(make_gcm(DISC, game_id=b"GP6E01"))
    folder = tmp_path / "root"
    make_extract(folder, DISC, make_dol([("text", 0x80003100, b"\0" * 4)]))
    with pytest.raises(SystemExit, match="expected b'GP6P01'"):
        build_iso.main(["--base", str(base), "--out", str(tmp_path / "new.iso"), "--folder", str(folder)])
