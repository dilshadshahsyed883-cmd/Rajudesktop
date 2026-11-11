"""Read-only, version-locked Qt meta-object analysis of original CapCut 9.7.

This is NOT a live native bridge, a DLL patch, a renderer, or an exporter.
Only a SHA256-verified 9.7.0.4153 VECreator.dll is inspected. File offsets
below are NEVER suitable as addresses or pointers for calling functions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import mmap
from pathlib import Path
import struct

CAPCUT_VERSION = "9.7.0.4153"
EXPECTED_DLL_SHA256 = "967fd06e60a1c68c055278cf6bb1ecd1bb078277d58167fcf6b4cfa2a1a27cf9"
EXPECTED_DLL_SIZE = 281017256
MODEL_STRINGS_OFFSET = 212657504
MODEL_META_OFFSET = 212658112
HOME_EXPORT_STRINGS_OFFSET = 212600152
HOME_EXPORT_META_OFFSET = 212601744
HOME_EXPORT_STRING_END_MARKER = b"videoEnhanceExportButtonEnable\x00"
MOC_HEADER_COUNT = 14
REQUIRED_METHOD = "clickBackgroudExport"


class MOCError(ValueError):
    pass


@dataclass(frozen=True)
class MethodEvidence:
    name: str
    argument_count: int
    return_metatype_id: int
    method_flags: int
    is_public: bool
    is_signal: bool
    is_slot: bool


def _uint(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise MOCError("Truncated Qt meta-object data")
    return struct.unpack_from("<I", data, offset)[0]


def parse_original_export_meta(
    string_block: bytes, metadata: bytes, *,
    expected_model: str = "ExportCompileBottomViewModel",
    required_method: str = REQUIRED_METHOD,
) -> dict:
    """Validate bounded Qt6 MOC metadata; never infer a live QObject.

    Qt MOC flags: access 0x03 (2=public), method type 0x0c
    (0=plain Q_INVOKABLE, 4=signal, 8=slot). Qt metatype 43=void.
    """
    if not string_block.startswith(expected_model.encode("ascii") + b"\x00"):
        raise MOCError("Original Qt export panel model name absent")
    try:
        names = [part.decode("utf-8") for part in
                 string_block.rstrip(b"\x00").split(b"\x00")]
    except UnicodeDecodeError as exc:
        raise MOCError("Corrupt Qt meta strings") from exc
    if not names or len(names) > 128:
        raise MOCError("Unexpected Qt meta string count")

    u = lambda ix: _uint(metadata, ix * 4)
    (version, class_name, classinfo_count, classinfo_offset,
     method_count, method_offset, property_count, property_offset,
     enum_count, enum_offset, ctor_count, ctor_offset, flags,
     signal_count) = (u(i) for i in range(MOC_HEADER_COUNT))
    if (version != 10 or class_name != 0 or classinfo_count != 0 or
            method_offset != MOC_HEADER_COUNT or
            not 1 <= method_count <= 64 or
            signal_count > method_count or property_count > 64):
        raise MOCError("Qt version or moc structure mismatch")
    if property_offset < method_offset + 6 * method_count:
        raise MOCError("Property data overlaps method records")
    if enum_count != 0 or ctor_count != 0 or flags != 0:
        raise MOCError("Unexpected Qt export class structure")

    methods = []
    for i in range(method_count):
        ix = method_offset + 6 * i
        name_idx, argc, params_idx, tag_idx, method_flags, metatype_idx = (
            u(ix + j) for j in range(6))
        if name_idx >= len(names) or argc > 16 or params_idx >= len(metadata) // 4:
            raise MOCError("Qt method descriptor invalid")
        methods.append(MethodEvidence(
            name=names[name_idx], argument_count=argc,
            return_metatype_id=u(params_idx), method_flags=method_flags,
            is_public=(method_flags & 3) == 2,
            is_signal=(method_flags & 12) == 4,
            is_slot=(method_flags & 12) == 8,
        ))
    candidates = [method for method in methods if method.name == required_method]
    if len(candidates) != 1:
        raise MOCError("Expected exactly one original Qt export method")
    method = candidates[0]
    if not (method.is_public and not method.is_signal and
            method.argument_count == 0 and method.return_metatype_id == 43):
        raise MOCError("Qt export method not a public zero-argument void callable")
    return {
        "source": "version-pinned original DLL Qt6 MOC record (offline)",
        "capcut_version": CAPCUT_VERSION,
        "model": names[0],
        "qt_moc_revision": version,
        "method": asdict(method),
        "method_count": method_count,
        "signal_count": signal_count,
        "live_qobject_instance_verified": False,
        "home_draft_mapping_verified": False,
        "native_queue_admission_verified": False,
        "original_engine_automatic_mp4_verified": False,
        "meaning": ("Original export-panel view model declares a public zero-arg "
                    "Qt method; a live CapCut object and arbitrary Home draft "
                    "dispatch are not established."),
    }


def analyze_dll(dll: Path) -> dict:
    dll = Path(dll)
    if dll.stat().st_size != EXPECTED_DLL_SIZE:
        raise MOCError("Unrecognized original DLL size")
    sha = hashlib.sha256()
    with dll.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            sha.update(block)
    if sha.hexdigest() != EXPECTED_DLL_SHA256:
        raise MOCError("Unrecognized original DLL hash")
    with dll.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        strings = bytes(mm[MODEL_STRINGS_OFFSET:MODEL_META_OFFSET])
        metadata = bytes(mm[MODEL_META_OFFSET:MODEL_META_OFFSET + 1200])
        home_window = bytes(mm[HOME_EXPORT_STRINGS_OFFSET:HOME_EXPORT_STRINGS_OFFSET + 1200])
        home_end = home_window.find(HOME_EXPORT_STRING_END_MARKER)
        if home_end < 0:
            raise MOCError("Original export Home Qt string table missing")
        home_strings = home_window[:home_end + len(HOME_EXPORT_STRING_END_MARKER)]
        home_metadata = bytes(mm[HOME_EXPORT_META_OFFSET:HOME_EXPORT_META_OFFSET + 1800])
    result = parse_original_export_meta(strings, metadata)
    home = parse_original_export_meta(
        home_strings, home_metadata,
        expected_model="ExportHomeBottomViewModel",
        required_method="compileClick",
    )
    home["dll_sha256_verified"] = True
    result["export_home_bottom_model"] = home
    result["dll_sha256_verified"] = True
    return result


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-dll", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    result = json.dumps(analyze_dll(args.original_dll), indent=2) + "\n"
    if args.output_json:
        args.output_json.write_text(result, encoding="utf-8")
    else:
        print(result)


if __name__ == "__main__":
    main()
