"""Read-only PE/installer fingerprinting. Never runs or unpacks the input."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

MARKERS = (b"Nullsoft", b"NSIS", b"app.asar", b"pyinstaller", b"capcut")


def _at(data: bytes, offset: int, fmt: str):
    size = struct.calcsize(fmt)
    if offset < 0 or offset + size > len(data):
        raise ValueError("Truncated or invalid PE header")
    values = struct.unpack_from(fmt, data, offset)
    return values[0] if len(values) == 1 else values


def inspect(path: str | Path) -> dict:
    """Return reproducible metadata, without executing the supplied executable."""
    source = Path(path)
    size = source.stat().st_size
    if size < 128:
        raise ValueError("File too small for a PE executable")
    digest = hashlib.sha256()
    found = set()
    carry = b""
    with source.open("rb") as handle:
        header = handle.read(min(size, 1024 * 1024))
        handle.seek(0)
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            probe = (carry + chunk).lower()
            for marker in MARKERS:
                if marker.lower() in probe:
                    found.add(marker.decode("ascii"))
            carry = chunk[-32:]
    if header[:2] != b"MZ":
        raise ValueError("Not a Windows PE executable (missing MZ)")
    pe_offset = _at(header, 0x3C, "<I")
    if pe_offset > 512 * 1024 or header[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise ValueError("Invalid or inaccessible PE signature")
    coff = pe_offset + 4
    machine, section_count, _, _, _, optional_size, _ = _at(header, coff, "<HHIIIHH")
    optional = coff + 20
    pe_magic = _at(header, optional, "<H")
    if pe_magic not in (0x10B, 0x20B):
        raise ValueError("Unexpected PE optional header type")
    subsystem = _at(header, optional + 68, "<H")
    dir_offset = optional + (96 if pe_magic == 0x10B else 112)
    # IMAGE_DIRECTORY_ENTRY_SECURITY is a file offset, not a virtual address.
    signed_offset = signed_size = 0
    if optional_size >= (dir_offset - optional) + 40:
        signed_offset, signed_size = _at(header, dir_offset + 32, "<II")
    raw_end = 0
    sections = []
    for i in range(section_count):
        offset = optional + optional_size + i * 40
        name, _, _, raw_size, raw_offset, _, _, _, _, _ = _at(
            header, offset, "<8sIIIIIIHHI"
        )
        section_name = name.rstrip(b"\0").decode("ascii", errors="replace")
        sections.append(section_name)
        if raw_size:
            raw_end = max(raw_end, raw_offset + raw_size)
    if raw_end > size:
        raise ValueError("Section data extends beyond file")
    return {
        "filename": source.name,
        "size_bytes": size,
        "sha256": digest.hexdigest(),
        "format": "Windows PE",
        "machine_hex": f"0x{machine:04x}",
        "pe_type": "PE32+" if pe_magic == 0x20B else "PE32",
        "subsystem": subsystem,
        "sections": sections,
        "possible_installer": "NSIS" if "Nullsoft" in found and "NSIS" in found else "unknown",
        "embedded_marker_hits": sorted(found),
        "authenticode_certificate_table_present": bool(signed_offset and signed_size),
        "signature_verified": False,
        "possible_appended_payload_bytes": size - raw_end,
        "note": "Static metadata only. No installer execution, source recovery, or malware verdict.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer", help="Path to an EXE you own or are authorized to inspect")
    parser.add_argument("--output", help="Optional output JSON file (omit to print to stdout)")
    args = parser.parse_args()
    result = json.dumps(inspect(args.installer), indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(result, encoding="utf-8")
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
