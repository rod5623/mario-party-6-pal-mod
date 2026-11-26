"""tools.lib.mp7: reads from the MP7 extract first, else from the MP7 ISO."""
import pytest

from tests.builders import make_gcm
from tools.lib import mp7


def test_reads_the_extract_first(tmp_path):
    extract = tmp_path / "GP7P01"
    (extract / "files" / "mess").mkdir(parents=True)
    (extract / "files" / "mess" / "messdata_eng.bin").write_bytes(b"from the extract")
    assert mp7.read("files/mess/messdata_eng.bin", extract=extract, iso=tmp_path / "missing.iso") == b"from the extract"


def test_missing_disc_says_where_to_put_it(tmp_path):
    with pytest.raises(SystemExit, match="GP7P01"):
        mp7.read("files/mess/messdata_eng.bin", extract=tmp_path / "none", iso=tmp_path / "GP7P01.iso")


def test_reads_the_iso(tmp_path):
    pytest.importorskip("gclib.gcm")
    iso = tmp_path / "GP7P01.iso"
    iso.write_bytes(make_gcm({"mess/messdata_eng.bin": b"from the iso"}, game_id=b"GP7P01"))
    assert mp7.read("files/mess/messdata_eng.bin", extract=tmp_path / "none", iso=iso) == b"from the iso"


def test_rejects_another_game(tmp_path):
    pytest.importorskip("gclib.gcm")
    iso = tmp_path / "other.iso"
    iso.write_bytes(make_gcm({"a.bin": b"x"}, game_id=b"GP6P01"))
    with pytest.raises(SystemExit, match="Mario Party 7"):
        mp7.read("files/a.bin", extract=tmp_path / "none", iso=iso)
