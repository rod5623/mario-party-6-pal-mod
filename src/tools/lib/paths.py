"""Paths shared by the patch scripts. ROOT is src/; the game folders sit next to it."""
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parent                      # src/
REPO = ROOT.parent
BUILD = ROOT / "build" / "GP6P01"
ORIG = ROOT / "orig" / "GP6P01"
DOL = BUILD / "main.dol"

ASM_TEXT = BUILD / "asm" / "auto_03_800EF6C8_text.s"
ASM_DATA = BUILD / "asm" / "auto_07_80259D80_data.s"
ASM_SDATA = BUILD / "asm" / "auto_09_802DCE00_sdata.s"
ASM_INIT = BUILD / "asm" / "auto_00_80003100_init.s"

MESS_SOURCE_DIR = ORIG / "files" / "mess"
MESS_OUTPUT_DIR = BUILD / "files" / "mess"
MESS_SOURCE = MESS_SOURCE_DIR / "messdata_eng.bin"
MESS_OUTPUT = MESS_OUTPUT_DIR / "messdata_eng.bin"
MESS_NAMES = (
    "messdata.bin", "messdata_eng.bin", "messdata_fra.bin",
    "messdata_ger.bin", "messdata_ita.bin", "messdata_spa.bin",
)

REL_DIR = BUILD / "files" / "dll"        # patched REL copies
REL_ORIG = ORIG / "files" / "dll"
DATA_ORIG = ORIG / "files" / "data"
DATA_OUT = BUILD / "files" / "data"

GAME_ROOT = REPO / "root"                # the user's GCR extract
GAME_DATA = GAME_ROOT / "data"           # board files are edited here directly
BACKUPS = REPO / "backups"               # board file backups
ASSETS = TOOLS / "assets"
BIN = TOOLS / "bin"
