#!/usr/bin/env python3
"""draft_inspect.py - READ-ONLY view of CapCut desktop projects, for verifying UI edits.

Never writes to CapCut's project folders. Times in CapCut drafts are microseconds.

  draft_inspect.py list [--all]
  draft_inspect.py summary <project name|folder> [--json out.json] [--copy-json-to DIR]
  draft_inspect.py diff <before_summary.json> <after_summary.json>
  draft_inspect.py words <project> [--around SEC --window SEC]
  draft_inspect.py gaps <project> [--min 0.6 --keep 0.125]
  draft_inspect.py keyframes <project> [--json out.json]

diff ignores CapCut's float re-serialisation noise (values rounded to 6 places, times within 1 ms).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
QUIET_CATEGORIES = {"canvases", "placeholder_infos", "sound_channel_mappings", "material_colors", "speeds"}


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def tc(us: int | None, fps: float = 30.0) -> str:
    if us is None:
        return "-"
    s_total = us / 1_000_000
    h, rem = divmod(int(s_total), 3600)
    m, s = divmod(rem, 60)
    frame = int(round((s_total - int(s_total)) * fps))
    if frame >= round(fps):
        frame = 0
    return f"{h:02d}:{m:02d}:{s:02d}:{frame:02d} ({s_total:.3f}s)"


def load_index() -> list[dict]:
    idx = DEFAULT_ROOT / "root_meta_info.json"
    if not idx.exists():
        return []
    data = json.loads(idx.read_text(encoding="utf-8"))
    return data.get("all_draft_store", [])


def resolve_project(q: str) -> Path:
    p = Path(q)
    if p.is_dir() and (p / "draft_content.json").exists():
        return p
    drafts = [d for d in load_index() if not d.get("draft_is_invisible") and not d.get("tm_draft_removed")]
    exact = [d for d in drafts if d.get("draft_name") == q]
    if not exact:
        exact = [d for d in drafts if q.lower() in (d.get("draft_name") or "").lower()]
    if not exact:
        direct = DEFAULT_ROOT / q
        if (direct / "draft_content.json").exists():
            return direct
        die(f"No project matches '{q}'. Run: draft_inspect.py list")
    if len(exact) > 1:
        names = "\n  ".join(d["draft_name"] for d in exact)
        die(f"'{q}' matches several projects:\n  {names}")
    return Path(exact[0]["draft_fold_path"])


def cmd_list(a):
    rows = load_index()
    if not rows:
        die(f"No root_meta_info.json under {DEFAULT_ROOT}")
    rows.sort(key=lambda d: d.get("tm_draft_modified", 0), reverse=True)
    for d in rows:
        if not a.all and (d.get("draft_is_invisible") or d.get("tm_draft_removed")):
            continue
        mod = dt.datetime.fromtimestamp(d.get("tm_draft_modified", 0) / 1_000_000).strftime("%Y-%m-%d %H:%M:%S")
        flags = []
        if d.get("draft_is_invisible"):
            flags.append("invisible")
        if d.get("tm_draft_removed"):
            flags.append("removed")
        print(f"{mod}  {tc(d.get('tm_duration')):>28}  {d.get('draft_name')}"
              + (f"  [{', '.join(flags)}]" if flags else "") + f"\n    {d.get('draft_fold_path')}")


def _sig(obj: dict) -> str:
    clean = {k: v for k, v in obj.items() if k not in ("id",)}
    return hashlib.sha1(json.dumps(clean, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:8]


def _text_of(mat: dict) -> str:
    c = mat.get("content")
    if isinstance(c, str) and c.startswith("{"):
        try:
            return json.loads(c).get("text", "")
        except Exception:
            return c[:120]
    return mat.get("recognize_text") or ""


def _mat_label(cat: str, mat: dict, index: dict | None = None) -> str:
    if cat == "texts":
        return _text_of(mat)
    if cat == "material_animations":
        return ", ".join(x.get("name", "") for x in mat.get("animations", []) if x.get("name"))
    if cat == "text_templates" and index is not None:
        # Template segments point at the template; the words live in linked text materials.
        words = [_text_of(index[r["text_material_id"]][1]) for r in mat.get("text_info_resources") or []
                 if r.get("text_material_id") in index]
        tpl = mat.get("name") or ""
        return " / ".join(w for w in words if w) + (f" [template: {tpl}]" if tpl else "")
    name = mat.get("name") or mat.get("material_name") or ""
    if not name and cat in ("videos", "audios") and mat.get("path") and not str(mat["path"]).startswith("##"):
        name = Path(str(mat["path"])).name
    return name


def _kf_detail(s: dict) -> list[dict]:
    """A segment's keyframes on the timeline clock.

    CapCut stores keyframe time_offset on the segment's SOURCE clock (microseconds), so a keyframe on
    the first frame of a segment whose source starts at 328.267 s has time_offset 328266666.
    """
    tr = s.get("target_timerange") or {}
    sr = s.get("source_timerange") or {}
    speed = s.get("speed") or 1.0
    rows = []
    for g in s.get("common_keyframes") or []:
        for k in g.get("keyframe_list") or []:
            off = k.get("time_offset") or 0
            rows.append(dict(
                prop=g.get("property_type"), offset=off,
                time=(tr.get("start") or 0) + round((off - (sr.get("start") or 0)) / speed),
                values=k.get("values"), curve=k.get("curveType"),
                left=k.get("left_control"), right=k.get("right_control"),
                string=k.get("string_value") or None,
            ))
    return sorted(rows, key=lambda r: (r["prop"] or "", r["offset"]))


def _norm(v, nd: int = 6):
    """Round floats so CapCut's re-serialisation noise (1.0999999999999999 vs 1.1) doesn't show as a change."""
    if isinstance(v, float):
        return round(v, nd)
    if isinstance(v, dict):
        return {k: _norm(x, nd) for k, x in v.items()}
    if isinstance(v, list):
        return [_norm(x, nd) for x in v]
    return v


def _kf_line(r: dict, fps: float) -> str:
    ctl = ""
    if r.get("left") or r.get("right"):
        l, rt = r.get("left") or {}, r.get("right") or {}
        ctl = f" L({l.get('x', 0):.3g},{l.get('y', 0):.3g}) R({rt.get('x', 0):.3g},{rt.get('y', 0):.3g})"
    return f"{r['prop']} @ {tc(r['time'], fps)} = {_norm(r['values'], 4)} {r['curve']}{ctl}"


def summarize(folder: Path) -> dict:
    content = folder / "draft_content.json"
    raw = content.read_bytes()
    if not raw.lstrip().startswith(b"{"):
        die(f"{content} is not plaintext JSON (encrypted build?). Verify via UI/screenshots instead.", 4)
    d = json.loads(raw.decode("utf-8"))
    fps = float(d.get("fps") or 30.0)

    index: dict[str, tuple[str, dict]] = {}
    counts = {}
    for cat, items in (d.get("materials") or {}).items():
        if isinstance(items, list):
            if items:
                counts[cat] = len(items)
            for it in items:
                if isinstance(it, dict) and it.get("id"):
                    index[it["id"]] = (cat, it)

    tracks = []
    for ti, t in enumerate(d.get("tracks") or []):
        segs = []
        for si, s in enumerate(t.get("segments") or []):
            tr = s.get("target_timerange") or {}
            sr = s.get("source_timerange") or {}
            cat, mat = index.get(s.get("material_id"), ("?", {}))
            refs = []
            for rid in s.get("extra_material_refs") or []:
                rc, rm = index.get(rid, ("?", {}))
                if rc in QUIET_CATEGORIES:
                    continue
                refs.append(dict(cat=rc, name=_mat_label(rc, rm, index), sig=_sig(rm) if rm else "?"))
            clip = s.get("clip") or {}
            seg = dict(
                i=si, id=s.get("id"),
                start=tr.get("start"), duration=tr.get("duration"),
                end=(tr.get("start") or 0) + (tr.get("duration") or 0),
                src_start=sr.get("start"), src_duration=sr.get("duration"),
                speed=s.get("speed"), volume=s.get("volume"), visible=s.get("visible"),
                material=dict(cat=cat, type=mat.get("type"), name=_mat_label(cat, mat, index),
                              path=mat.get("path") if cat in ("videos", "audios") else None,
                              sig=_sig(mat) if mat else "?"),
                clip=dict(scale=clip.get("scale"), pos=clip.get("transform"), rotation=clip.get("rotation"),
                          alpha=clip.get("alpha"), flip=clip.get("flip")) if clip else None,
                keyframes=len(s.get("common_keyframes") or []),
                kf=_kf_detail(s),
                refs=sorted(refs, key=lambda r: (r["cat"], r["name"])),
            )
            segs.append(seg)
        tracks.append(dict(i=ti, id=t.get("id"), type=t.get("type"), name=t.get("name"),
                           flag=t.get("flag"), attribute=t.get("attribute"), segments=segs))

    kf = {k: len(v) for k, v in (d.get("keyframes") or {}).items() if v}
    return dict(
        project=folder.name, folder=str(folder), draft_id=d.get("id"),
        file_mtime=dt.datetime.fromtimestamp(content.stat().st_mtime).isoformat(timespec="seconds"),
        update_time=d.get("update_time"),
        canvas=d.get("canvas_config"), fps=fps, duration=d.get("duration"), duration_tc=tc(d.get("duration"), fps),
        track_count=len(tracks), segment_count=sum(len(t["segments"]) for t in tracks),
        material_counts=counts, keyframe_groups=kf, tracks=tracks,
    )


def print_summary(s: dict, max_segments: int):
    fps = s["fps"]
    c = s.get("canvas") or {}
    print(f"Project: {s['project']}\n  folder: {s['folder']}\n  saved: {s['file_mtime']}")
    print(f"  canvas {c.get('ratio')} {c.get('width')}x{c.get('height')} @ {fps}fps, duration {s['duration_tc']}")
    print(f"  {s['track_count']} tracks, {s['segment_count']} segments")
    print(f"  materials: {s['material_counts']}")
    if s["keyframe_groups"]:
        print(f"  keyframe groups: {s['keyframe_groups']}")
    for t in s["tracks"]:
        print(f"\nTrack {t['i']} [{t['type']}] name={t['name']!r} flag={t['flag']} attr={t['attribute']} ({len(t['segments'])} segs)")
        for seg in t["segments"][:max_segments]:
            m = seg["material"]
            extra = []
            if seg["speed"] not in (None, 1.0):
                extra.append(f"speed={seg['speed']}")
            if seg["volume"] not in (None, 1.0):
                extra.append(f"vol={seg['volume']}")
            cl = seg.get("clip") or {}
            if cl.get("scale") and cl["scale"] != {"x": 1.0, "y": 1.0}:
                extra.append(f"scale={cl['scale']}")
            if cl.get("pos") and cl["pos"] != {"x": 0.0, "y": 0.0}:
                extra.append(f"pos={cl['pos']}")
            if seg["keyframes"]:
                extra.append(f"kf={seg['keyframes']}")
            named = [f"{r['cat']}:{r['name']}" for r in seg["refs"] if r["name"]]
            if named:
                extra.append("refs=" + "; ".join(named))
            print(f"  [{seg['i']}] {tc(seg['start'], fps)} -> {tc(seg['end'], fps)}  "
                  f"src@{tc(seg['src_start'], fps) if seg['src_start'] is not None else '-'}  "
                  f"{m['cat']}:{(m['name'] or '')[:60]!r} " + " ".join(extra))
        if len(t["segments"]) > max_segments:
            print(f"  ... {len(t['segments']) - max_segments} more (use --max-segments)")


def cmd_summary(a):
    folder = resolve_project(a.project)
    s = summarize(folder)
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.copy_json_to:
        dst = Path(a.copy_json_to)
        dst.mkdir(parents=True, exist_ok=True)
        for f in ("draft_content.json", "draft_meta_info.json"):
            if (folder / f).exists():
                shutil.copy2(folder / f, dst / f)  # copy OUT of the project only
    print_summary(s, a.max_segments)


def _load_summary(p: str) -> dict:
    path = Path(p)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return summarize(resolve_project(p))


def cmd_diff(a):
    b, c = _load_summary(a.before), _load_summary(a.after)
    fps = c.get("fps") or 30.0
    changes = 0

    def say(line):
        nonlocal changes
        changes += 1
        print(line)

    for key in ("canvas", "fps", "duration", "track_count", "segment_count"):
        if b.get(key) != c.get(key):
            bv, cv = b.get(key), c.get(key)
            if key == "duration":
                bv, cv = tc(bv, fps), tc(cv, fps)
            say(f"{key}: {bv} -> {cv}")
    for cat in sorted(set(b["material_counts"]) | set(c["material_counts"])):
        if b["material_counts"].get(cat, 0) != c["material_counts"].get(cat, 0):
            say(f"materials.{cat}: {b['material_counts'].get(cat, 0)} -> {c['material_counts'].get(cat, 0)}")
    if b.get("keyframe_groups") != c.get("keyframe_groups"):
        say(f"keyframe groups: {b.get('keyframe_groups')} -> {c.get('keyframe_groups')}")

    bt = {t["id"]: t for t in b["tracks"]}
    ct = {t["id"]: t for t in c["tracks"]}
    for tid in ct.keys() - bt.keys():
        t = ct[tid]
        say(f"+ track {t['i']} [{t['type']}] added with {len(t['segments'])} segments")
    for tid in bt.keys() - ct.keys():
        t = bt[tid]
        say(f"- track {t['i']} [{t['type']}] removed ({len(t['segments'])} segments)")
    for tid in bt.keys() & ct.keys():
        t0, t1 = bt[tid], ct[tid]
        label = f"track {t1['i']} [{t1['type']}]"
        for k in ("flag", "attribute", "name"):
            if t0.get(k) != t1.get(k):
                say(f"~ {label} {k}: {t0.get(k)} -> {t1.get(k)}")
        s0 = {s["id"]: s for s in t0["segments"]}
        s1 = {s["id"]: s for s in t1["segments"]}
        for sid in sorted(s1.keys() - s0.keys(), key=lambda x: s1[x]["start"] or 0):
            s = s1[sid]
            say(f"+ {label} seg {tc(s['start'], fps)} -> {tc(s['end'], fps)} {s['material']['cat']}:{s['material']['name']!r}")
        for sid in sorted(s0.keys() - s1.keys(), key=lambda x: s0[x]["start"] or 0):
            s = s0[sid]
            say(f"- {label} seg {tc(s['start'], fps)} -> {tc(s['end'], fps)} {s['material']['cat']}:{s['material']['name']!r}")
        for sid in s0.keys() & s1.keys():
            x, y = s0[sid], s1[sid]
            diffs = []
            for k in ("start", "duration", "src_start", "src_duration"):
                xv, yv = x.get(k), y.get(k)
                # <=1 ms is CapCut float re-serialisation, not an edit (a frame is 33 ms at 30 fps)
                if (xv is None) != (yv is None) or (xv is not None and abs(xv - yv) > 1000):
                    diffs.append(f"{k} {tc(xv, fps)} -> {tc(yv, fps)}")
            for k in ("speed", "volume", "visible", "clip"):
                if _norm(x.get(k)) != _norm(y.get(k)):
                    diffs.append(f"{k} {_norm(x.get(k))} -> {_norm(y.get(k))}")
            if "kf" in x and "kf" in y:
                kx = {_kf_line(r, fps) for r in x["kf"]}
                ky = {_kf_line(r, fps) for r in y["kf"]}
                diffs += [f"+kf {line}" for line in sorted(ky - kx)] + [f"-kf {line}" for line in sorted(kx - ky)]
            elif x.get("keyframes") != y.get("keyframes"):
                diffs.append(f"keyframes {x.get('keyframes')} -> {y.get('keyframes')}")
            if x["material"]["sig"] != y["material"]["sig"]:
                diffs.append(f"material changed ({x['material']['name']!r} -> {y['material']['name']!r})")
            rx = {(r["cat"], r["name"], r["sig"]) for r in x["refs"]}
            ry = {(r["cat"], r["name"], r["sig"]) for r in y["refs"]}
            for r in sorted(ry - rx):
                diffs.append(f"+ref {r[0]}:{r[1]!r}")
            for r in sorted(rx - ry):
                diffs.append(f"-ref {r[0]}:{r[1]!r}")
            if diffs:
                say(f"~ {label} seg@{tc(y['start'], fps)}: " + "; ".join(diffs))
    if not changes:
        print("No differences.")
    else:
        print(f"-- {changes} difference(s)")


def _as_dict(v):
    if isinstance(v, str) and v.strip().startswith("{"):
        try:
            return json.loads(v)
        except Exception:
            return {}
    return v if isinstance(v, dict) else {}


def cmd_words(a):
    """Word-level timings of caption/text segments (e.g. from Auto captions), on the timeline clock."""
    folder = resolve_project(a.project)
    d = json.loads((folder / "draft_content.json").read_text(encoding="utf-8"))
    fps = float(d.get("fps") or 30.0)
    index = {}
    for cat, items in (d.get("materials") or {}).items():
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and it.get("id"):
                    index[it["id"]] = (cat, it)
    rows = []
    for t in d.get("tracks") or []:
        if t.get("type") != "text":
            continue
        for s in t.get("segments") or []:
            tr = s.get("target_timerange") or {}
            seg_start = (tr.get("start") or 0) / 1_000_000
            seg_end = seg_start + (tr.get("duration") or 0) / 1_000_000
            cat, mat = index.get(s.get("material_id"), ("?", {}))
            mats = [mat] if cat == "texts" else [
                index[r["text_material_id"]][1] for r in (mat.get("text_info_resources") or [])
                if r.get("text_material_id") in index]
            for tm in mats:
                sentence = _text_of(tm)
                w = _as_dict(tm.get("words"))
                starts, ends, texts = w.get("start_time") or [], w.get("end_time") or [], w.get("text") or []
                words = []
                for i, txt in enumerate(texts):
                    if not str(txt).strip():
                        continue  # CapCut stores inter-word spaces as zero-length tokens
                    ws = seg_start + (starts[i] if i < len(starts) else 0) / 1000
                    we = seg_start + (ends[i] if i < len(ends) else 0) / 1000
                    words.append((ws, we, txt))
                rows.append(dict(start=seg_start, end=seg_end, text=sentence, words=words))
    rows.sort(key=lambda r: r["start"])
    if a.around is not None:
        rows = [r for r in rows if r["end"] >= a.around - a.window and r["start"] <= a.around + a.window]
    if a.json:
        Path(a.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    if not rows:
        print("No text/caption segments with words found.")
    for r in rows:
        print(f"{tc(int(r['start'] * 1e6), fps)} -> {tc(int(r['end'] * 1e6), fps)}  {r['text']}")
        for ws, we, txt in r["words"]:
            print(f"    {tc(int(ws * 1e6), fps)} -> {tc(int(we * 1e6), fps)}  {txt}")


def cmd_gaps(a):
    """Silences between caption words (Auto captions) and proposed cut ranges that keep `--keep` s each side."""
    import io, contextlib
    folder = resolve_project(a.project)
    d = json.loads((folder / "draft_content.json").read_text(encoding="utf-8"))
    fps = float(d.get("fps") or 30.0)
    buf = io.StringIO()
    tmp = Path(folder.name + ".words.tmp.json") if not a.words_json else Path(a.words_json)
    ns = argparse.Namespace(project=str(folder), around=None, window=0, json=str(tmp))
    with contextlib.redirect_stdout(buf):
        cmd_words(ns)
    rows = json.loads(tmp.read_text(encoding="utf-8"))
    if not a.words_json:
        tmp.unlink(missing_ok=True)
    words = sorted((w for r in rows for w in r["words"]), key=lambda w: w[0])
    # Segment boundaries on non-text tracks: a "gap" that spans one is an edit join, not silence.
    joins = sorted({(s.get("target_timerange") or {}).get("start", 0) / 1_000_000
                    for t in d.get("tracks") or [] if t.get("type") != "text"
                    for s in t.get("segments") or []} - {0.0})
    frame = 1.0 / fps
    out_rows, total = [], 0.0
    for prev, nxt in zip(words, words[1:]):
        gap = nxt[0] - prev[1]
        if gap < a.min:
            continue
        cut_start = round((prev[1] + a.keep) / frame) * frame
        cut_end = round((nxt[0] - a.keep) / frame) * frame
        if cut_end - cut_start < frame:
            continue
        crosses = [j for j in joins if prev[1] - frame <= j <= nxt[0] + frame]
        if not crosses:
            total += cut_end - cut_start
        out_rows.append(dict(after=prev[2], before=nxt[2], gap=round(gap, 3),
                             cut_start=round(cut_start, 3), cut_end=round(cut_end, 3),
                             remove=round(cut_end - cut_start, 3),
                             crosses_join=[round(j, 3) for j in crosses]))
    if a.json:
        Path(a.json).write_text(json.dumps(out_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in out_rows:
        flag = f"  [SPANS EDIT JOIN @ {r['crosses_join']} - not real silence, skip]" if r["crosses_join"] else ""
        print(f"gap {r['gap']:6.3f}s  cut {tc(int(r['cut_start'] * 1e6), fps)} -> {tc(int(r['cut_end'] * 1e6), fps)}"
              f"  (-{r['remove']:.3f}s)  after «{r['after']}» before «{r['before']}»{flag}")
    real = sum(1 for r in out_rows if not r["crosses_join"])
    print(f"-- {real} real gap(s) >= {a.min}s (+{len(out_rows) - real} spanning edit joins); "
          f"removing the real ones would save {total:.3f}s (keep {a.keep}s each side)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("list", help="projects from CapCut's index, newest first")
    p.add_argument("--all", action="store_true", help="include invisible/removed entries")
    p.set_defaults(fn=cmd_list)
    p = sp.add_parser("summary", help="tracks, segments, materials of one project")
    p.add_argument("project")
    p.add_argument("--json")
    p.add_argument("--copy-json-to", help="copy the raw draft JSON files OUT to this folder")
    p.add_argument("--max-segments", type=int, default=40)
    p.set_defaults(fn=cmd_summary)
    p = sp.add_parser("diff", help="compare two summary JSON files (or project names = live)")
    p.add_argument("before")
    p.add_argument("after")
    p.set_defaults(fn=cmd_diff)
    p = sp.add_parser("words", help="caption/text segments with per-word timings (timeline clock)")
    p.add_argument("project")
    p.add_argument("--around", type=float, help="only rows near this timeline second")
    p.add_argument("--window", type=float, default=10.0)
    p.add_argument("--json")
    p.set_defaults(fn=cmd_words)
    p = sp.add_parser("gaps", help="silences between caption words, with proposed cut ranges")
    p.add_argument("project")
    p.add_argument("--min", type=float, default=0.6, help="only gaps at least this long (s)")
    p.add_argument("--keep", type=float, default=0.125, help="silence kept after/before each word (s)")
    p.add_argument("--words-json", help="also save the word list used")
    p.add_argument("--json")
    p.set_defaults(fn=cmd_gaps)
    p = sp.add_parser("keyframes", help="every segment keyframe on the timeline clock, with curve/easing data")
    p.add_argument("project")
    p.add_argument("--json")
    p.set_defaults(fn=cmd_keyframes)
    a = ap.parse_args()
    a.fn(a)


def cmd_keyframes(a):
    """Keyframes per segment: property, timeline time, offset into the segment, value, curve type, handles."""
    s = summarize(resolve_project(a.project))
    fps = s["fps"]
    rows = []
    for t in s["tracks"]:
        for seg in t["segments"]:
            if not seg["kf"]:
                continue
            rows.append(dict(track=t["i"], seg=seg["i"], start=seg["start"], end=seg["end"], keyframes=seg["kf"]))
            print(f"Track {t['i']} [{t['type']}] seg {seg['i']}  {tc(seg['start'], fps)} -> {tc(seg['end'], fps)}")
            for r in seg["kf"]:
                print(f"    +{(r['time'] - seg['start']) / 1e6:8.3f}s  {_kf_line(r, fps)}")
    if s["keyframe_groups"]:
        print(f"top-level keyframe groups: {s['keyframe_groups']}")
    if a.json:
        Path(a.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    n = sum(len(r["keyframes"]) for r in rows)
    print(f"-- {n} keyframe(s) on {len(rows)} segment(s)" if n else "No segment keyframes.")


if __name__ == "__main__":
    main()
