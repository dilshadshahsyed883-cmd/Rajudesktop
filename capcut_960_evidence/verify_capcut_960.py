#!/usr/bin/env python3
"""Rebuild and inspect the CapCut 9.6 ZIP without extracting/executing any app binaries.

Python >= 3.10; only stdlib. Outputs never overwrite existing files. Original pieces untouched.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import zipfile

EXPORT_DLL = "9.6.0.4097/lyra_cli_client.dll"
IPC_CMD = "9.6.0.4097/Resources/common_agent/bin/lyra-cli-ipc.cmd"
IPC_JS = "9.6.0.4097/Resources/common_agent/resources/lyra-cli-ipc/lyraCliIpcClient.mjs"

def rebuild(parts_dir, manifest, target):
    if not manifest.get("parts") or target.exists() or target.parent.resolve() == parts_dir.resolve():
        raise ValueError("Unsafe output location, empty manifest, or file exists")
    tmp = target.with_name(target.name + ".partial")
    if tmp.exists():
        raise ValueError("Leftover partial output must be reviewed manually")
    whole = hashlib.sha256()
    size = 0
    try:
        with tmp.open("xb") as output:
            for item in manifest["parts"]:
                src = parts_dir / item["name"]
                if not src.exists():
                    src = parts_dir / (item["name"] + ".bin")
                part = hashlib.sha256()
                n = 0
                with src.open("rb") as stream:
                    while block := stream.read(4 * 1024 * 1024):
                        n += len(block)
                        part.update(block)
                        whole.update(block)
                        output.write(block)
                if n != item["bytes"] or part.hexdigest() != item["sha256"]:
                    raise ValueError("Mismatched part: " + item["name"])
                size += n
        if size != manifest["source_bytes"] or whole.hexdigest() != manifest["source_sha256"]:
            raise ValueError("Reassembled archive checksum mismatch")
        tmp.rename(target)
        return whole.hexdigest()
    finally:
        if tmp.exists():
            tmp.unlink()  # own temporary output only

def inventory(zip_path, csv_path):
    if csv_path.exists():
        raise ValueError("Will not overwrite existing inventory")
    tmp = csv_path.with_name(csv_path.name + ".partial")
    if tmp.exists():
        raise ValueError("Partial inventory exists")
    summary = {"files": 0, "folders": 0, "uncompressed_bytes": 0, "key_files": {}}
    try:
        with zipfile.ZipFile(zip_path) as z, tmp.open("x", encoding="utf-8", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(["path", "uncompressed_bytes", "compressed_bytes", "crc32_hex", "sha256", "is_directory"])
            for info in z.infolist():
                digest = ""
                if info.is_dir():
                    summary["folders"] += 1
                else:
                    h = hashlib.sha256()
                    with z.open(info) as stream:
                        while block := stream.read(4 * 1024 * 1024):
                            h.update(block)  # ZipFile.open checks CRC while reading
                    digest = h.hexdigest()
                    summary["files"] += 1
                    summary["uncompressed_bytes"] += info.file_size
                    if info.filename in (EXPORT_DLL, IPC_CMD, IPC_JS):
                        summary["key_files"][info.filename] = {"bytes": info.file_size, "sha256": digest}
                writer.writerow([info.filename, info.file_size, info.compress_size,
                                 f"{info.CRC:08x}", digest, info.is_dir()])
        tmp.rename(csv_path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return summary

def static_evidence(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        dll = z.read(EXPORT_DLL)
        wrapper = z.read(IPC_CMD)
        ipc = z.read(IPC_JS)
    keys = (b"lyra-cli draft export", b"exportStart", b"ExportService",
            b"prepareExportCover", b"--audio-output", b"--gif-output")
    return {"dll_export_markers": {k.decode(): k in dll for k in keys},
            "ipc_wrapper_mentions_bun": b"bun.exe" in wrapper,
            "ipc_client_has_legacy_routing": b"legacy" in ipc,
            "native_export_tested_on_windows": False}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parts-dir", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--zip-output", type=Path, required=True)
    ap.add_argument("--inventory-output", type=Path, required=True)
    args = ap.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    digest = rebuild(args.parts_dir, manifest, args.zip_output)
    result = inventory(args.zip_output, args.inventory_output)
    result["archive_sha256"] = digest
    result["static_evidence"] = static_evidence(args.zip_output)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
