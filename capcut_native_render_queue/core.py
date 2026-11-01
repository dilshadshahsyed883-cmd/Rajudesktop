"""CapCut 9.6 native IPC-only render queue logic. No FFmpeg and no GUI automation."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

VERSION = "9.7.0.4153"  # default when multiple installed; running version always wins
DLL_SHA256 = "8177f813b8c3ee1b58f36a2339c83691f0c7c53bac3d114cd4b66757e7f0879f"
SUPPORTED_DLLS = {
    "9.6.0.4097": "878df7053d8eb83bf2bf35621fbdc7652e80836680a658a786560689f788f9f7",
    "9.7.0.4153": DLL_SHA256,
}
CAPCUT_97_ARCHIVE_SHA256 = "a17790e03bf7ed2ffbaa2c32bab7a1ac96a5b8b75520904e7bd42e882bc9fff4"
REF = re.compile(r"^local://[A-Za-z0-9_%.:/+\-]+$")


class NativeUnavailable(RuntimeError):
    pass


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for b in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(b)
    return digest.hexdigest()


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".capcut-queue-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def candidate_roots(custom=""):
    roots = [Path(custom).expanduser()] if custom.strip() else []
    for key in ("LOCALAPPDATA", "APPDATA"):
        env = os.environ.get(key)
        if not env:
            continue
        for app in ("CapCut", "CapCutPro", "JianyingPro"):
            base = Path(env) / app / "User Data" / "Projects"
            roots.extend((base / "com.lveditor.draft", base))
    return list(dict.fromkeys(p for p in roots if p.is_dir()))


def _label(folder):
    for name in ("draft_meta_info.json", "draft_info.json"):
        f = folder / name
        try:
            if f.stat().st_size > 4_000_000: continue
            data = json.loads(f.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                for key in ("draft_name", "name", "title"):
                    if isinstance(data.get(key), str) and data[key].strip():
                        return data[key].strip()
        except (OSError, ValueError):
            pass
    return folder.name


def scan_drafts(roots, limit=3000):
    found = {}
    for root in roots:
        if not root.is_dir(): continue
        for parent, folders, filenames in os.walk(root):
            depth = len(Path(parent).relative_to(root).parts)
            if depth > 4:
                folders[:] = []
                continue
            if "draft_content.json" in filenames or "draft_info.json" in filenames:
                folder = Path(parent)
                main = next((folder / name for name in ("draft_content.json", "draft_info.json")
                             if (folder / name).is_file()), None)
                if main:
                    key = str(folder.resolve()).casefold()
                    found[key] = {
                        "key": key, "title": _label(folder), "folder": str(folder),
                        "updated": main.stat().st_mtime, "ref": None, "status": "Unbound"}
                folders[:] = []
            if len(found) >= limit: break
        if len(found) >= limit: break
    return sorted(found.values(), key=lambda x: (-x["updated"], x["title"].casefold()))


def _nested(value, depth=0):
    if depth > 7: return
    if isinstance(value, dict):
        yield value
        for val in value.values():
            if isinstance(val, (dict, list)):
                yield from _nested(val, depth + 1)
            elif isinstance(val, str) and val.strip().startswith(("[", "{")):
                try: yield from _nested(json.loads(val), depth + 1)
                except ValueError: pass
    elif isinstance(value, list):
        for val in value:
            yield from _nested(val, depth + 1)


def native_projects(stdout):
    """No guessed refs. Native must supply a project ref itself."""
    try:
        data = json.loads(stdout.strip())
    except ValueError:
        data = None
        for line in reversed(stdout.splitlines()):
            if not line.strip().startswith(("[", "{")): continue
            try:
                data = json.loads(line)
                break
            except ValueError: continue
        if data is None: raise NativeUnavailable("Native project listing was not valid JSON.")
    result = {}
    for obj in _nested(data):
        ref = obj.get("ref") or obj.get("draft_ref") or obj.get("draftRef")
        if not isinstance(ref, str) or not REF.fullmatch(ref): continue
        title = next((obj[k].strip() for k in ("name", "title", "draft_name", "draftName")
                      if isinstance(obj.get(k), str) and obj[k].strip()), ref.removeprefix("local://"))
        result[ref] = {"ref": ref, "title": title}
    if not result:
        raise NativeUnavailable("No confirmed local:// native project refs returned.")
    return list(result.values())


def bind_projects(local, native):
    names = {}
    for project in native:
        names.setdefault(project["title"].casefold(), []).append(project)
    rows, used = [], set()
    for project in local:
        item = dict(project)
        match = names.get(item["title"].casefold(), [])
        unique_local = sum(x["title"].casefold() == item["title"].casefold() for x in local) == 1
        if len(match) == 1 and unique_local:
            item["ref"] = match[0]["ref"]
            item["status"] = "Queued"
            used.add(item["ref"])
        else:
            item["status"] = "Needs native match"
        rows.append(item)
    for project in native:
        if project["ref"] not in used:
            rows.append({"key": "native:" + project["ref"], "title": project["title"],
                         "folder": "", "updated": 0, "ref": project["ref"], "status": "Queued"})
    return rows


def safe_filename(title, ref):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")[:100] or "draft"
    if name.upper() in {"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"}:
        name = "_" + name
    suffix = hashlib.sha256(ref.encode("utf-8")).hexdigest()[:8]
    return f"{name}--{suffix}.mp4"


def complete_mp4(path):
    """ISO BMFF top-level atom integrity only; no codec or visual parity claim."""
    try:
        size = Path(path).stat().st_size
        if size < 4096: return False
        pos, tags = 0, set()
        with Path(path).open("rb") as file:
            for _ in range(100000):
                if pos == size: break
                if pos + 8 > size: return False
                file.seek(pos)
                header = file.read(8)
                length = int.from_bytes(header[:4], "big")
                tag = header[4:]
                overhead = 8
                if length == 1:
                    extra = file.read(8)
                    if len(extra) != 8: return False
                    length = int.from_bytes(extra, "big")
                    overhead = 16
                elif length == 0: length = size - pos
                if length < overhead or pos + length > size: return False
                tags.add(tag)
                pos += length
        return pos == size and {b"ftyp", b"mdat", b"moov"} <= tags
    except (OSError, ValueError): return False


def verify_output(path, seconds=180, stop=None):
    deadline = time.monotonic() + seconds
    previous, stable = None, 0
    path = Path(path)
    while time.monotonic() < deadline:
        if stop is not None and stop.is_set():
            raise NativeUnavailable("Monitor stopped; native render may still be running.")
        if path.is_file():
            info = path.stat()
            current = (info.st_size, info.st_mtime_ns)
            stable = stable + 1 if current == previous else 0
            previous = current
            if stable >= 3 and complete_mp4(path):
                return {"path": str(path), "size": info.st_size, "sha256": sha256(path)}
        time.sleep(2)
    raise NativeUnavailable("Output not finalized. Manual review required; no automatic retry.")


def locate_capcut():
    """Prefer one active pinned CapCut installation; otherwise select newest installed.

    The launcher executable under Apps/ is NOT the versioned renderer.
    """
    active = {}
    try:
        import psutil
        for proc in psutil.process_iter(["name", "exe"]):
            try:
                if (proc.info["name"] or "").casefold() != "capcut.exe":
                    continue
                exe_path = proc.info["exe"]
                if not exe_path:
                    continue
                exe = Path(exe_path)
                if exe.parent.name in SUPPORTED_DLLS:
                    active[str(exe).casefold()] = exe
            except (OSError, psutil.Error):
                continue
    except ImportError:
        pass
    if len(active) > 1:
        raise NativeUnavailable("Multiple supported CapCut versions are running. Close one, then Refresh. No engine was selected.")
    if active:
        return next(iter(active.values()))
    candidates = []
    for key in ("LOCALAPPDATA",):
        base = os.environ.get(key)
        if not base:
            continue
        for version in SUPPORTED_DLLS:
            p = Path(base) / "CapCut" / "Apps" / version / "CapCut.exe"
            if p.is_file():
                candidates.append(p)
    if candidates:
        return sorted(candidates, key=lambda p: tuple(int(n) for n in p.parent.name.split(".")))[-1]
    raise NativeUnavailable("CapCut 9.6/9.7 installation not found. Start CapCut 9.7, then Refresh.")


class NativeIPC:
    def __init__(self, capcut_exe):
        self.exe = Path(capcut_exe)
        self.root = self.exe.parent
        self.dll = self.root / "lyra_cli_client.dll"
        self.bun = self.root / "bun.exe"
        self.script = self.root / "Resources/common_agent/resources/lyra-cli-ipc/lyraCliIpcClient.mjs"

    def validate(self):
        if self.exe.name.casefold() != "capcut.exe" or self.root.name not in SUPPORTED_DLLS:
            raise NativeUnavailable("Expected CapCut.exe in supported 9.6.0.4097 or 9.7.0.4153 version folder.")
        if any(not f.is_file() for f in (self.exe, self.dll, self.bun, self.script)):
            raise NativeUnavailable("Required CapCut native IPC files are missing.")
        if sha256(self.dll) != SUPPORTED_DLLS[self.root.name]:
            raise NativeUnavailable("Native DLL fingerprint differs from verified " + self.root.name + " archive; no unverified execution.")
        return True

    def command(self, arguments, timeout=60):
        self.validate()
        command = [str(self.bun), str(self.script), "--product", "capcut",
                   "--socket-timeout-seconds", str(timeout), "--", *arguments]
        try:
            result = subprocess.run(command, cwd=str(self.root), shell=False, capture_output=True,
                        text=True, encoding="utf-8", errors="replace", timeout=timeout,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        env=dict(os.environ, AGENT_RUNTIME_BUN_COMMAND=str(self.bun)))
        except subprocess.TimeoutExpired as exc:
            raise NativeUnavailable("Native IPC timeout: state uncertain. Do not retry blindly.") from exc
        except OSError as exc:
            raise NativeUnavailable(f"CapCut native IPC could not start: {exc}") from exc
        if result.returncode:
            detail = (result.stderr or result.stdout)[-700:]
            if "host project adapter is unavailable" in detail.casefold():
                raise NativeUnavailable(
                    "CapCut " + self.root.name +
                    " native IPC is reachable, but the host ProjectAdapter is NOT registered. "
                    "Its bundled lyra-cli cannot list or export existing local drafts in this "
                    "host state. This is a CapCut-side binding issue, not a corrupt draft or "
                    "DLL version mismatch. The queue remains read-only/disabled; "
                    "no ref guessing, FFmpeg, GUI macro, or automatic retry. Raw error: " + detail)
            raise NativeUnavailable("CapCut " + self.root.name + " native IPC returned an error: " + detail)
        return result.stdout

    def list(self):
        return native_projects(self.command(["draft", "project", "list"], timeout=45))

    def render(self, ref, output, minutes=180):
        if not REF.fullmatch(ref): raise NativeUnavailable("Unverified native draft reference.")
        output = Path(output)
        if output.exists(): raise NativeUnavailable("Refusing overwrite: " + str(output))
        output.parent.mkdir(parents=True, exist_ok=True)
        # Only CapCut's own export command; no FFmpeg, no codec/FPS overrides.
        return self.command(["draft", "export", "--ref", ref, "--output", str(output),
                             "--timeout", f"{minutes}min"], timeout=minutes * 60 + 120)
