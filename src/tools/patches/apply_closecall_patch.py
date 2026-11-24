"""Add Close Call, a new 4-player minigame (drop from a tall wall, press A to stop closest to the floor).

The game is a new REL written in C (src/REL/closecallDll/closecall.c), built by build_closecall_rel.py and
shipped as dll/jbtestdll.rel: the retail jbtestdll is an empty debug stub, so its overlay slot (ovl 5, module 1)
is reused and the DOL's fixed overlay table is untouched.

Run after mgtable_move (it adds an entry to the relocated MgDataTbl) and after battle_ports / daft_rafts_duel /
lift_leapers_duel, which take entries 82-87. Re-runnable: every output is rebuilt from orig/ or checked in place.

Writes:
  build/GP6P01/files/dll/jbtestdll.rel   the game (replaces the stub)
  build/GP6P01/files/data/saf.bin        + wall, floor, ledge and debug-marker models (files 5-8; saf is a debug archive)
  build/GP6P01/files/data/instpic.bin    + instruction picture (file 127)
  build/GP6P01/files/movie/dummy         Free Play preview movie (drawn animation, video only). It replaces
                                         the retail 0-byte placeholder movie/dummy, which nothing references.
                                         Never add new files: the ISO is rebuilt (GCR) from the existing
                                         Game.toc, so a new file is left off the disc, and a movie that cannot
                                         be opened makes the THP player retry forever while the instruction
                                         screen waits for it to close (black screen). Copy files/movie/ to
                                         root/movie too.
  build/GP6P01/files/sound/MP6_Str.pdt   the original stream archive + track 110 = tools/assets/closecall_music.wav
                                         (32000 Hz 16-bit stereo, loops whole), which closecall.c plays
                                         (BGM_STREAM). Rebuilt from orig every run. Copy files/sound/ to root/sound.
  build/GP6P01/files/mess/messdata*.bin  bank 5 record 82 (name), bank 65 records 479-481 (instructions);
                                         this script owns banks 5 and 65 (whole-bank splice, from orig)
  build/GP6P01/main.dol                  MgDataTbl entry 88 (4P), terminator moved to 89; the movie path string
                                         at MOVIE_PATH_ADDR (free gap between the battle thumbnail table and the
                                         Daft Rafts hook in the relocated table section)

Minigame Mode's Free Play builds its category lists from the table (type 0 = 4-player, up to 32 games, 100
entries scanned), so entry 88 is listed with the 4-player games; its preview plays movie/dummy.
"""
import struct
import subprocess
import sys

from tools.lib.paths import BUILD, DOL, ROOT
from tools.lib.dol import dol_offset
from tools.lib.minigames import ENTRY_SIZE, NEW_BASE
from tools.closecall import closecall_assets as assets
from tools.lib import mpdata
from tools.lib.messages import write_bank

NEW_INDEX = 88
TEMPLATE_INDEX = 15        # m616 (Same Is Lame): 4P entry used as the template for the movie fields
OVL_JBTEST = 5             # _ovltbl index of dll/jbtestdll.rel
MG_TYPE_4P = 0
MG_FLAG_PACK_SKILL, MG_FLAG_PACK_EASY, MG_FLAG_4P = 1 << 1, 1 << 3, 1 << 4
RECORD_NONE = 0xFF

DATA_ORIG = ROOT / "orig" / "GP6P01" / "files" / "data"
DATA_OUT = BUILD / "files" / "data"
MESS_ORIG = ROOT / "orig" / "GP6P01" / "files" / "mess"
MESS_OUT = BUILD / "files" / "mess"
MESS_NAMES = ("messdata.bin", "messdata_eng.bin", "messdata_fra.bin", "messdata_ger.bin", "messdata_ita.bin",
              "messdata_spa.bin")

DIR_INSTPIC = 48 << 16     # P01 data directory numbers (tools/closecall/p01_names.py prints them all)
DIR_SAF = 214 << 16
INSTPIC_TEMPLATE = 0x20    # m616's picture: same 256x256 CMPR layout
INSTPIC_VANILLA_FILES = 127

MOVIE_NAME = "dummy"          # an existing disc file (see the docstring): never add new files
MOVIE_PATH = b"movie/" + MOVIE_NAME.encode("ascii") + b"\0"
MOVIE_PATH_ADDR = 0x802F7A80  # NEW_BASE + 0x30E0, ends before the Daft Rafts hook at NEW_BASE + 0x3100
MOVIE_SLOT = 0x20             # bytes reserved for the path
OLD_MOVIE_PATHS = (b"movie/closecall.thp\0",)  # written by an earlier version of this patch
MOVIE_OUT = BUILD / "files" / "movie"

MUSIC_WAV = ROOT / "tools" / "assets" / "closecall_music.wav"
MUSIC_LOOP_START = 0          # sample the loop jumps back to (0 = loop the whole song)
# Loudness: the track volume byte (retail tracks use 72-108, max MSM_VOL_MAX 127) times a gain on the samples.
# 127 / 97 (the usual retail value) = 1.31x, and 1.07x on the samples = about 1.4x overall. The WAV already
# peaks at 0 dBFS, so the sample gain goes through a soft limiter (only the loudest peaks are rounded off).
MUSIC_VOLUME = 127
MUSIC_GAIN = 1.07
MUSIC_LIMIT_KNEE = 0.9        # fraction of full scale where the soft limiter starts
MUSIC_TRACK = 110             # first id after the 110 retail tracks; must match BGM_STREAM in closecall.c
PDT_ORIG = ROOT / "orig" / "GP6P01" / "files" / "sound" / "MP6_Str.pdt"
PDT_OUT = BUILD / "files" / "sound" / "MP6_Str.pdt"
VGAUDIO_PATHS = (ROOT / "tools" / "bin" / "VGAudioCli.exe", ROOT.parent.parent / "VGAudioCli.exe")  # second: the old workspace spot


def vgaudio():
    for path in VGAUDIO_PATHS:
        if path.exists():
            return path
    raise SystemExit("VGAudioCli.exe not found: put it in tools/bin/ (https://github.com/Thealexbarney/VGAudio/releases)")

NAME_BANK, NAME_COUNT = 5, 82
INST_BANK, INST_COUNT = 65, 479


def text(s):
    """Game text: space 0x10, '.' 0x85, ',' 0x82, '!' 0xC2, apostrophe '\\', {A} = the A button icon."""
    out = s.replace("{A}", "\x0e\x03").replace(" ", "\x10").replace(".", "\x85").replace(",", "\x82")
    out = out.replace("!", "\xc2").replace("'", "\\")
    return out.encode("latin-1")


def record(header, body):
    rec = struct.pack(">HH", *header) + text(body) + b"\0"
    return rec + b"\0" * (-len(rec) % 4)


NAME_RECORDS = [record((0x0C, 1), "Close Call")]
INST_RECORDS = [
    record((0x12, 4), "Everyone drops from the top of the\n"
                      "wall. Press {A} to stop as close to\n"
                      "the floor as you can. Hit the floor\n"
                      "and you're out! Closest player wins!"),
    record((0x12, 4), "{A} Stop"),
    record((0x12, 4), "The floor stays out of sight until\n"
                      "the very end, so remember how far\n"
                      "down it was in the opening view!"),
]
NAME_MES = (NAME_BANK << 16) | NAME_COUNT
INST_MES = [(INST_BANK << 16) | (INST_COUNT + i) for i in range(3)]


def run_build():
    subprocess.run([sys.executable, "-m", "tools.closecall.build_closecall_rel"], cwd=ROOT, check=True)


def append_to_archive(name, vanilla_count, payloads):
    data, offsets = mpdata.read_archive(DATA_ORIG / f"{name}.bin")
    if len(offsets) != vanilla_count:
        raise RuntimeError(f"orig {name}.bin has {len(offsets)} files, expected {vanilla_count}")
    out, _ = mpdata.append_files(data, offsets, payloads)
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    (DATA_OUT / f"{name}.bin").write_bytes(out)
    print(f"{name}.bin: files {vanilla_count}-{vanilla_count + len(payloads) - 1} added")
    return out


def write_data():
    models = assets.models()
    if sorted(models) != list(range(assets.SAF_VANILLA_FILES, assets.SAF_VANILLA_FILES + len(models))):
        raise RuntimeError("closecall_assets file numbers must follow the vanilla saf files")
    append_to_archive("saf", assets.SAF_VANILLA_FILES, [models[k] for k in sorted(models)])
    data, offsets = mpdata.read_archive(DATA_ORIG / "instpic.bin")
    picture = assets.instpic_anm(mpdata.read_file(data, offsets, INSTPIC_TEMPLATE))
    append_to_archive("instpic", INSTPIC_VANILLA_FILES, [picture])


def bank_records(data, bank):
    start = 4 + struct.unpack_from(">I", data, 4 + 4 * bank)[0]
    count = struct.unpack_from(">I", data, start)[0]
    return start, count


def with_records(data, bank, expected, extra):
    """data with `extra` appended to bank `bank` (which must hold `expected` records)."""
    data = bytearray(data)
    banks = struct.unpack_from(">I", data, 0)[0]
    start, count = bank_records(data, bank)
    if count != expected:
        raise RuntimeError(f"bank {bank}: {count} records, expected {expected}")
    end = 4 + struct.unpack_from(">I", data, 8 + 4 * bank)[0] if bank + 1 < banks else len(data)
    offsets = [struct.unpack_from(">I", data, start + 4 + 4 * i)[0] for i in range(count)]
    bounds = [start + 4 + o for o in offsets] + [end]
    records = [bytes(data[bounds[i]:bounds[i + 1]]) for i in range(count)] + list(extra)
    position = 4 + 4 * len(records)
    new_offsets = []
    for rec in records:
        new_offsets.append(position - 4)
        position += len(rec)
    block = struct.pack(">I", len(records)) + struct.pack(f">{len(records)}I", *new_offsets) + b"".join(records)
    delta = len(block) - (end - start)
    data[start:end] = block
    for index in range(bank + 1, banks):
        pos = 4 + 4 * index
        struct.pack_into(">I", data, pos, struct.unpack_from(">I", data, pos)[0] + delta)
    return bytes(data)


def write_messages():
    """Own banks 5 and 65: rebuild them from orig with our records, splice them into the current outputs.
    Every language gets the English text."""
    for name in MESS_NAMES:
        source = MESS_ORIG / name
        donor = with_records(source.read_bytes(), NAME_BANK, NAME_COUNT, NAME_RECORDS)
        donor = with_records(donor, INST_BANK, INST_COUNT, INST_RECORDS)
        output = MESS_OUT / name
        write_bank(output, source, donor, NAME_BANK)
        write_bank(output, source, donor, INST_BANK)
    print(f"messages: bank {NAME_BANK} record {NAME_COUNT}, bank {INST_BANK} records "
          f"{INST_COUNT}-{INST_COUNT + len(INST_RECORDS) - 1} in {len(MESS_NAMES)} files")


def build_entry(dol):
    table = dol_offset(dol, NEW_BASE)
    entry = bytearray(dol[table + TEMPLATE_INDEX * ENTRY_SIZE:table + (TEMPLATE_INDEX + 1) * ENTRY_SIZE])
    if struct.unpack_from(">H", entry, 0)[0] != 0x15:  # m616 is ovl 0x15
        raise RuntimeError("template entry is not m616")
    struct.pack_into(">HBB", entry, 0, OVL_JBTEST, MG_TYPE_4P, 0)
    struct.pack_into(">HbB", entry, 4, MG_FLAG_4P | MG_FLAG_PACK_SKILL | MG_FLAG_PACK_EASY, -1, 0)
    struct.pack_into(">II", entry, 8, NAME_MES, DIR_SAF)
    pic = DIR_INSTPIC | INSTPIC_VANILLA_FILES
    struct.pack_into(">6I", entry, 0x10, pic, 0, 0, pic, 0, 0)
    # movie[day][0] and movie[night][0]; the other movie slots keep m616's pointers to ""
    struct.pack_into(">I", entry, 0x28, MOVIE_PATH_ADDR)
    struct.pack_into(">I", entry, 0x34, MOVIE_PATH_ADDR)
    pages = [INST_MES[0], INST_MES[1], 0, INST_MES[2], 0]
    struct.pack_into(">15I", entry, 0x40, *(pages * 3))  # day, night, decathlon
    return bytes(entry)


def write_table_entry(dol):
    table = dol_offset(dol, NEW_BASE)
    slot = table + NEW_INDEX * ENTRY_SIZE
    if NEW_BASE + (NEW_INDEX + 2) * ENTRY_SIZE > NEW_BASE + 0x3000:  # battle_thumbs owns NEW_BASE+0x3000..
        raise RuntimeError("table entry would run into the battle thumbnail table")
    entry = build_entry(dol)
    for i in range(NEW_INDEX):
        if struct.unpack_from(">H", dol, table + i * ENTRY_SIZE)[0] == 0xFFFF:
            raise RuntimeError(f"table ends at {i}: run the earlier table patches first (entries up to 87)")
    current = bytes(dol[slot:slot + ENTRY_SIZE])
    if struct.unpack_from(">H", current, 0)[0] == 0xFFFF:
        terminator = current
        dol[slot:slot + ENTRY_SIZE] = entry
        dol[slot + ENTRY_SIZE:slot + 2 * ENTRY_SIZE] = terminator
        print(f"MgDataTbl entry {NEW_INDEX} added at {NEW_BASE + NEW_INDEX * ENTRY_SIZE:#010x}")
    elif current == entry:
        print(f"MgDataTbl entry {NEW_INDEX} already present")
    elif struct.unpack_from(">H", current, 0)[0] == OVL_JBTEST:
        dol[slot:slot + ENTRY_SIZE] = entry
        print(f"MgDataTbl entry {NEW_INDEX} updated")
    else:
        raise RuntimeError(f"MgDataTbl slot {NEW_INDEX} is used by something else")


def write_movie(dol):
    from tools.audio import thp
    MOVIE_OUT.mkdir(parents=True, exist_ok=True)
    (MOVIE_OUT / MOVIE_NAME).write_bytes(thp.build(assets.preview_frames(), assets.PREVIEW_FPS))
    if not NEW_BASE + 0x3078 <= MOVIE_PATH_ADDR or MOVIE_PATH_ADDR + MOVIE_SLOT > NEW_BASE + 0x3100:
        raise RuntimeError("movie path must sit between the thumbnail table and the Daft Rafts hook")
    position = dol_offset(dol, MOVIE_PATH_ADDR)
    current = bytes(dol[position:position + MOVIE_SLOT])
    known = [p.ljust(MOVIE_SLOT, b"\0") for p in (MOVIE_PATH,) + OLD_MOVIE_PATHS] + [bytes(MOVIE_SLOT)]
    if current not in known:
        raise RuntimeError(f"{MOVIE_PATH_ADDR:#010x} is not free")
    dol[position:position + MOVIE_SLOT] = known[0]
    stale = MOVIE_OUT / "closecall.thp"  # written by an earlier version
    if stale.exists():
        stale.unlink()
    print(f"movie/{MOVIE_NAME} written, path at {MOVIE_PATH_ADDR:#010x}")


def apply_gain(src, dst, gain, knee):
    """Write src (16-bit WAV) scaled by gain to dst; samples above knee * full scale are bent smoothly towards
    full scale (tanh) instead of clipping. Returns how many samples the limiter touched."""
    import wave
    import numpy as np
    with wave.open(str(src)) as w:
        params = w.getparams()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768.0
    y = x * gain
    over = np.abs(y) > knee
    y[over] = np.sign(y[over]) * (knee + (1 - knee) * np.tanh((np.abs(y[over]) - knee) / (1 - knee)))
    out = np.clip(np.round(y * 32767.0), -32768, 32767).astype("<i2")
    with wave.open(str(dst), "wb") as w:
        w.setparams(params)
        w.writeframes(out.tobytes())
    return int(over.sum())


def write_music():
    """Encode the song (each channel to mono DSP ADPCM with VGAudioCli) and append it to the stream archive."""
    import wave
    from tools.audio import pdt
    with wave.open(str(MUSIC_WAV)) as w:
        fmt = (w.getframerate(), w.getnchannels(), w.getsampwidth())
        frames = w.getnframes()
    if fmt != (32000, 2, 2):
        raise RuntimeError(f"{MUSIC_WAV.name} must be 32000 Hz, stereo, 16-bit (it is {fmt[0]} Hz, "
                           f"{fmt[1]} ch, {8 * fmt[2]}-bit)")
    work = BUILD / "closecall"
    work.mkdir(parents=True, exist_ok=True)
    source = work / "music_gain.wav"
    limited = apply_gain(MUSIC_WAV, source, MUSIC_GAIN, MUSIC_LIMIT_KNEE)
    blobs = []
    encoder = vgaudio()
    for ch in (0, 1):
        dsp = work / f"music_{ch}.dsp"
        # the loop end is exclusive: 0-frames keeps every sample and loops at the end, like the retail tracks
        subprocess.run([str(encoder), "-c", f"-i:{ch}", str(source), "-o", str(dsp),
                        "-l", f"{MUSIC_LOOP_START}-{frames}"], check=True, stdout=subprocess.DEVNULL)
        blobs.append(dsp.read_bytes())
    track = pdt.track_from_dsp(blobs[0], blobs[1], volume=MUSIC_VOLUME)
    print(f"music: volume {MUSIC_VOLUME}, gain x{MUSIC_GAIN}, {limited} samples soft-limited")
    if pdt.read_header(PDT_ORIG)[1] != MUSIC_TRACK:
        raise RuntimeError("the original stream archive does not have 110 tracks")
    PDT_OUT.parent.mkdir(parents=True, exist_ok=True)
    first = pdt.append_tracks(PDT_ORIG, PDT_OUT, [track])
    print(f"sound/MP6_Str.pdt: track {first} added ({frames / 32000:.1f} s)")


def main():
    run_build()
    write_data()
    write_music()
    write_messages()
    dol = bytearray(DOL.read_bytes())
    write_movie(dol)
    write_table_entry(dol)
    DOL.write_bytes(dol)
    print("Close Call installed (table entry 88, overlay jbtestdll)")


if __name__ == "__main__":
    main()
