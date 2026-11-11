"""Read-only hash compatibility comparison against published CapCut 9.5.0.4050 native adapter.
Never loads, attaches, patches or executes any CapCut binaries.
"""
import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ.get("CAPCUT_AUDIT_DIR", "capcut-audit-report"))
extracted = root / "extracted" / "JYPacket"
pins = {
    "lyra_cli_client.dll": "1760a1d8752c2cba1c3ea572f3c1ec0ce4e8ca0da90b0bb8032d297804bcde97",
    "videoeditor.dll": "029986c9a26f3db4222402d00283cc610c81247b50ee9827e281daf626426b90",
    "VECreator.dll": "576bc1f51c0e81d50369e2ee69c157389a310151f1e75ea79813d9753be2db77",
    "Qt6Core.dll": "88f0da8219ab163c2949cb862fc00356e9c96df3bd4a0013bde14aa285bbc925",
}
versions = sorted(p for p in extracted.iterdir() if p.is_dir()) if extracted.exists() else []
out = {
    "method": "offline_SHA256_comparison_only",
    "reference": "leileqiTHU/reverse-cli-anything (capcut_cli_worker.py and capcut_store_worker.py), verified build 9.5.0.4050",
    "versions": []
}
for folder in versions:
    rows = []
    for name, expected in pins.items():
        candidate = folder/name
        if candidate.is_file():
            with candidate.open("rb") as f:
                actual = hashlib.file_digest(f, "sha256").hexdigest()
            rows.append({"name":name, "exists":True, "sha256":actual, "pin_match":actual==expected})
        else:
            rows.append({"name":name, "exists":False, "sha256":None, "pin_match":False})
    out["versions"].append({"version":folder.name, "modules":rows, "adapter_pin_match":all(r["pin_match"] for r in rows)})
root.mkdir(exist_ok=True,parents=True)
(root/"native-bridge-compatibility.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
lines=["# Native bridge compatibility probe","",f"Reference: {out['reference']}","",
       "An adapter hash mismatch is an intentional refusal to run on an unverified build.",
       "This is a read-only version check, **not** a native export success test.",""]
for v in out["versions"]:
    lines += [f"## CapCut {v['version']}", "",
             f"Exact pinned adapter compatible: **{v['adapter_pin_match']}**", "",
             "| Native module | Present | SHA pin match |", "|---|---|---|"]
    lines += [f"| `{r['name']}` | {r['exists']} | {r['pin_match']} |" for r in v["modules"]]
    lines += [""]
if not out['versions']:
    lines+=["No extracted version directory found; download or extraction may have failed.",""]
(root/"native-bridge-compatibility.md").write_text("\n".join(lines),encoding="utf-8")
print("\n".join(lines))
