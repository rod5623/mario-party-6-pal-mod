"""Read files from the user's Mario Party 7 PAL disc (GP7P01), for content ported into MP6.

read("files/sound/MP7_Str.pdt") or read("sys/main.dol") returns the file's bytes. The Dolphin extract
in src/orig/GP7P01/ (sys/, files/) is used when the file is there; otherwise the file is read out of
src/orig/GP7P01.iso with gclib (requirements.txt). Nothing is written.
"""
from functools import lru_cache

from tools.lib.paths import MP7_ISO, MP7_ORIG

GAME_ID = b"GP7P01"


@lru_cache(maxsize=1)
def _disc(iso_path):
    try:
        from gclib.gcm import GCM
    except ImportError:
        raise SystemExit("gclib is missing (pip install -r requirements.txt), or extract the MP7 disc to "
                         f"{MP7_ORIG}")
    disc = GCM(str(iso_path))
    disc.read_entire_disc()
    game_id = disc.read_file_raw_data("sys/boot.bin")[:6]
    if game_id != GAME_ID:
        raise SystemExit(f"{iso_path} is {game_id!r}, expected {GAME_ID!r} (Mario Party 7 PAL)")
    return disc


def read(path, extract=MP7_ORIG, iso=MP7_ISO):
    """Bytes of `path` ("files/..." or "sys/...") from the MP7 extract, else the MP7 ISO."""
    local = extract / path
    if local.is_file():
        return local.read_bytes()
    if not iso.is_file():
        raise SystemExit(f"Mario Party 7 not found: put your GP7P01 disc image at {iso} or extract it to {extract}")
    return _disc(iso).read_file_raw_data(path)
