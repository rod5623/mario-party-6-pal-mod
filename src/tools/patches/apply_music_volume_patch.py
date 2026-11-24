"""Lower the streamed music (MP6_Str.pdt) volume slightly.

msmStreamInit (fn_801440D8) starts the msm stream master volume at 0x7F. That
master is multiplied into the final level of every stream voice (see
fn_80144FF0 / fn_80143420), fades included, while sound effects (MP6_SND.msm)
are untouched. The patch changes the initial `li r0,0x7f` to MUSIC_VOLUME.
Independent of the other patches; edits build/GP6P01/main.dol only.
"""
from tools.lib.paths import DOL
from tools.lib.dol import dol_offset

STREAM_INIT_LI = 0x801440E4
MUSIC_VOLUME = 100  # 0-127, original 127 (100 is about 79%, -2 dB)
ORIGINAL = bytes.fromhex("3800007F")  # li r0,0x7f


def main():
    dol = bytearray(DOL.read_bytes())
    offset = dol_offset(dol, STREAM_INIT_LI)
    patched = bytes.fromhex("38000000")[:3] + bytes([MUSIC_VOLUME])
    current = bytes(dol[offset:offset + 4])
    if current == ORIGINAL or (current[:3] == ORIGINAL[:3] and current != patched):
        if current[:2] != ORIGINAL[:2]:
            raise SystemExit(f"Unexpected msmStreamInit instruction: {current.hex()}")
        dol[offset:offset + 4] = patched
    elif current != patched:
        raise SystemExit(f"Unexpected msmStreamInit instruction: {current.hex()}")
    DOL.write_bytes(dol)
    print(f"Music stream master volume set to {MUSIC_VOLUME}/127")
    print(f"Built DOL: {DOL}")


if __name__ == "__main__":
    main()
