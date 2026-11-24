import argparse
import struct
import sys
from pathlib import Path

from tools.audio.musyxextract import samples_to_bytes


HEADER_SIZE = 0x48
BANK_ENTRY_SIZE = 0x20
SDIR_ENTRY_SIZE = 0x20
SDIR_META_SIZE = 0x28


def parse_bank_id(value):
    try:
        return int(value.removeprefix("0x").removeprefix("0X"), 16)
    except ValueError as error:
        raise argparse.ArgumentTypeError("bank ID must be hexadecimal, e.g. 000C") from error


def read_sdir_records(sdir_data):
    records = []
    position = 0

    while True:
        if position + 4 > len(sdir_data):
            raise ValueError("SDIR is missing its end-of-table marker")

        if sdir_data[position:position + 4] == b"\xFF\xFF\xFF\xFF":
            break

        if position + SDIR_ENTRY_SIZE > len(sdir_data):
            raise ValueError("SDIR contains a truncated sample entry")

        sample_id = struct.unpack_from(">H", sdir_data, position)[0]
        sample_offset = struct.unpack_from(">I", sdir_data, position + 4)[0]
        sample_rate = struct.unpack_from(">H", sdir_data, position + 0x0E)[0]
        sample_count = struct.unpack_from(">I", sdir_data, position + 0x10)[0]
        metadata_offset = struct.unpack_from(">I", sdir_data, position + 0x1C)[0]

        if metadata_offset + SDIR_META_SIZE > len(sdir_data):
            raise ValueError("SDIR sample metadata points outside the directory")

        records.append((sample_id, sample_offset, sample_rate, sample_count))
        position += SDIR_ENTRY_SIZE

    if not records:
        raise ValueError("SDIR contains no sample entries")

    return records


def validate_sample_bank(sdir_data, samp_data):
    records = read_sdir_records(sdir_data)
    sample_ids = set()
    ranges = []

    for sample_id, offset, rate, sample_count in records:
        if sample_id in sample_ids:
            raise ValueError(f"SDIR contains duplicate sample ID {sample_id:04X}")
        sample_ids.add(sample_id)

        if rate == 0 or sample_count == 0:
            raise ValueError(f"Sample {sample_id:04X} has an invalid rate or sample count")
        if offset % 32 != 0:
            raise ValueError(f"Sample {sample_id:04X} offset is not 32-byte aligned")

        size = samples_to_bytes(sample_count)
        end = offset + size
        if end > len(samp_data):
            raise ValueError(f"Sample {sample_id:04X} extends past the SAMP data")
        ranges.append((offset, end, sample_id))

    ranges.sort()
    for previous, current in zip(ranges, ranges[1:]):
        if previous[1] > current[0]:
            raise ValueError(
                f"Sample ranges overlap: {previous[2]:04X} and {current[2]:04X}"
            )

    return records


def patch_archive(input_path, bank_id, bank_directory, output_path):
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {output_path}")
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output archive paths must be different")

    bank_name = f"{bank_id:04X}"
    sdir_path = bank_directory / f"{bank_name}.sdir"
    samp_path = bank_directory / f"{bank_name}.samp"
    if not sdir_path.is_file() or not samp_path.is_file():
        raise FileNotFoundError(
            f"Expected {sdir_path.name} and {samp_path.name} in {bank_directory}"
        )

    archive = input_path.read_bytes()
    if len(archive) < HEADER_SIZE or archive[:4] != b"GSND":
        raise ValueError("Input is not a valid GSND/MSM archive")
    if struct.unpack_from(">I", archive, 8)[0] != len(archive):
        raise ValueError("MSM header file size does not match the archive size")

    bank_table_offset, bank_table_size = struct.unpack_from(">II", archive, 0x20)
    group_chunk_offset, group_chunk_size = struct.unpack_from(">II", archive, 0x38)
    sample_chunk_offset, sample_chunk_size = struct.unpack_from(">II", archive, 0x40)

    if bank_table_size % BANK_ENTRY_SIZE:
        raise ValueError("MSM bank table size is not a multiple of its entry size")
    if bank_table_offset + bank_table_size > len(archive):
        raise ValueError("MSM bank table extends past the archive")
    if group_chunk_offset + group_chunk_size > len(archive):
        raise ValueError("MSM group-data chunk extends past the archive")
    if sample_chunk_offset + sample_chunk_size > len(archive):
        raise ValueError("MSM sample-data chunk extends past the archive")

    bank_entries = []
    for index in range(bank_table_size // BANK_ENTRY_SIZE):
        entry_offset = bank_table_offset + index * BANK_ENTRY_SIZE
        entry_id = struct.unpack_from(">H", archive, entry_offset)[0]
        if entry_id == bank_id:
            bank_entries.append((entry_offset, *struct.unpack_from(">IIII", archive, entry_offset + 4)))

    if len(bank_entries) != 1:
        raise ValueError(f"Expected one bank entry for {bank_name}; found {len(bank_entries)}")

    entry_offset, group_offset, group_size, sample_offset, sample_size = bank_entries[0]
    if group_offset + group_size > group_chunk_size:
        raise ValueError(f"Bank {bank_name} group data exceeds its chunk")
    if sample_offset + sample_size > sample_chunk_size:
        raise ValueError(f"Bank {bank_name} sample data exceeds its chunk")

    group_start = group_chunk_offset + group_offset
    pool_offset, project_offset, sdir_offset, sequence_offset = struct.unpack_from(
        ">IIII", archive, group_start
    )
    if not (
        0 <= pool_offset <= project_offset <= sdir_offset
        <= sequence_offset == group_size
    ):
        raise ValueError(f"Bank {bank_name} has invalid internal group offsets")

    sdir_capacity = sequence_offset - sdir_offset
    sdir_start = group_start + sdir_offset
    samp_start = sample_chunk_offset + sample_offset
    new_sdir = sdir_path.read_bytes()
    new_samp = samp_path.read_bytes()

    if len(new_sdir) > sdir_capacity:
        raise ValueError(
            f"Rebuilt SDIR is too large ({len(new_sdir)} bytes; capacity {sdir_capacity})"
        )
    if len(new_samp) > sample_size:
        raise ValueError(
            f"Rebuilt SAMP is too large ({len(new_samp)} bytes; capacity {sample_size})"
        )

    records = validate_sample_bank(new_sdir, new_samp)
    patched = bytearray(archive)
    patched[sdir_start:sdir_start + sdir_capacity] = (
        new_sdir + bytes(sdir_capacity - len(new_sdir))
    )
    patched[samp_start:samp_start + sample_size] = (
        new_samp + bytes(sample_size - len(new_samp))
    )

    if len(patched) != len(archive):
        raise AssertionError("Patching unexpectedly changed the archive size")
    if patched[:HEADER_SIZE] != archive[:HEADER_SIZE]:
        raise AssertionError("Patching unexpectedly changed the MSM header")
    if patched[bank_table_offset:bank_table_offset + bank_table_size] != (
        archive[bank_table_offset:bank_table_offset + bank_table_size]
    ):
        raise AssertionError("Patching unexpectedly changed the bank table")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("xb") as output:
        output.write(patched)

    return len(records), sdir_capacity, sample_size, len(new_sdir), len(new_samp)


def main():
    parser = argparse.ArgumentParser(
        description="Patch a rebuilt MusyX SDIR/SAMP bank into a copy of a GSND MSM archive."
    )
    parser.add_argument("--input", required=True, type=Path, help="Source MSM archive")
    parser.add_argument("--bank", required=True, type=parse_bank_id, help="Hex bank ID, e.g. 000C")
    parser.add_argument("--bank-dir", required=True, type=Path, help="Folder containing BANK.sdir and BANK.samp")
    parser.add_argument("--output", required=True, type=Path, help="New output MSM path (must not exist)")
    args = parser.parse_args()

    try:
        count, sdir_capacity, sample_capacity, sdir_size, sample_size = patch_archive(
            args.input, args.bank, args.bank_dir, args.output
        )
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(f"Created {args.output}")
    print(f"Patched bank {args.bank:04X}: {count} samples")
    print(f"SDIR: {sdir_size}/{sdir_capacity} bytes; SAMP: {sample_size}/{sample_capacity} bytes")
    print("The archive header, bank table, file size, and other banks are preserved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
