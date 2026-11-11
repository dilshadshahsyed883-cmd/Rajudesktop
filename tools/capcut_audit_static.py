"""Read-only CapCut installer/static PE audit. Never executes downloaded binaries."""
import json, os, re, struct, hashlib
from pathlib import Path

root=Path(os.environ.get("CAPCUT_AUDIT_DIR", "capcut-audit-report"))
root.mkdir(parents=True,exist_ok=True)
meta_path=root/"installer-metadata.json"
try: meta=json.loads(meta_path.read_text(encoding="utf-8-sig"))
except Exception as exc: meta={"error":str(exc)}

extract=root/"extracted"
files=[f for f in extract.rglob("*") if f.is_file()] if extract.exists() else []
exes=[f for f in files if f.suffix.lower()==".exe"]
dlls=[f for f in files if f.suffix.lower()==".dll"]
interesting=re.compile(r"capcut|render|export|engine|video|media|ffmpeg|draft|player|ffmpeg|codec|desktop",re.I)
targets=sorted(exes,key=lambda p:(not bool(re.search(r"^capcut(?:\.exe)?$",p.name,re.I)),not bool(interesting.search(p.name)),p.name))[:15]
targets+=sorted([f for f in dlls if interesting.search(f.name)],key=lambda p:p.name)[:25]
targets=list(dict.fromkeys(targets))
keywords=re.compile(rb"(?i)(?:--(?:export|render|headless|batch|draft|project)|/(?:export|render)|export[_ -]?(?:video|task|file|result)|render[_ -]?(?:task|engine|job)|headless|command.line|(?:draft|project)[_ -]?(?:content|json)|ffmpeg|video[_ -]?encoder|nvenc|qsv|amd[_ -]?amf|capcut://)")
findings=[]

def pe_header(path):
    try:
        with path.open("rb") as f:
            if f.read(2)!=b"MZ": return {"pe":False}
            f.seek(0x3c);ofs=struct.unpack("<I",f.read(4))[0]
            f.seek(ofs)
            if f.read(4)!=b"PE\\x00\\x00".replace(b"\\x00",b"\x00"):return {"pe":False}
            machine,section_count=struct.unpack("<HH",f.read(4))
        return {"pe":True,"machine":hex(machine),"section_count":section_count}
    except Exception as e: return {"error":str(e)}

def scan(path):
    hits=[]
    if path.stat().st_size>100*1024*1024:return [{"note":"skipped raw-string scan (file >100 MB)"}]
    with path.open("rb") as f:
        offset=0; prior=b""
        while True:
            chunk=f.read(4*1024*1024)
            if not chunk:break
            blob=prior+chunk
            for m in keywords.finditer(blob):
                lo=max(0,m.start()-55); hi=min(len(blob),m.end()+65)
                s=blob[lo:hi].replace(b"\x00",b"").decode("latin-1","replace")
                s="".join(c if 32<=ord(c)<127 else " " for c in s)
                if s not in hits:hits.append(s[:160])
                if len(hits)>=45:return hits
            prior=blob[-160:]
            offset+=len(chunk)
    return hits

for f in targets:
    try:
        rec={"file":str(f.relative_to(root)),"bytes":f.stat().st_size,**pe_header(f)}
        rec["strings_evidence"]=scan(f)
        findings.append(rec)
    except Exception as e:findings.append({"file":str(f),"error":str(e)})

report={
  "scope":"OFFLINE_STATIC_ONLY",
  "installer_executed":False,
  "metadata":meta,
  "extracted_file_count":len(files),
  "executable_count":len(exes),
  "dll_count":len(dlls),
  "pe_targets":findings,
  "automated_export_verified":False,
  "notes":"Keyword matches are leads, not proof of supported CLI flags or export APIs. No Windows runtime test was performed."
}
(root/"static-analysis.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
lines=["# CapCut.exe Installer Static Audit","",
       "- Scope: safe read-only static inspection; installer not executed.",
       f"- Version: {meta.get('advertised_version','unknown')}",
       f"- Download complete: {meta.get('downloaded',False)}",
       f"- SHA-256 verified against WinGet: {meta.get('sha256_verified',False)}",
       f"- Authenticode signature: {meta.get('signature_status','not available')}",
       f"- Signer: {meta.get('signature_subject','not available')}",
       f"- Extracted: {meta.get('extraction_success',False)}",
       f"- Extracted files: {len(files)}; EXEs: {len(exes)}; DLLs: {len(dlls)}",
       f"- PE files sampled: {len(findings)}",""]
if meta.get("error"):lines.append(f"- Download/extraction error: {meta['error']}")
lines+=["## Most relevant executable/module names",""]
for f in findings[:25]:
    lines.append(f"- `{f['file']}` ({f.get('bytes',0):,} bytes, PE={f.get('pe','?')})")
lines+=["","## Evidence snippets (not confirmed export interface)",""]
for f in findings:
    hs=f.get("strings_evidence",[])
    if hs:
        lines.append(f"### {f['file']}")
        for v in hs[:12]:lines.append("- "+v.replace("`","'"))
lines+=["","## Conclusion","",
"Installer authenticity, extracted PE evidence and internal strings are independent of runtime export functionality.",
"No supported headless video export interface has been confirmed by this static audit.",
"To verify CapCut-native export automation, an isolated Windows GUI/runtime test is still required.",
"Never interpret installer silent switches as render/export flags."]
(root/"audit-summary.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
print("Summary:",root/"audit-summary.md")
