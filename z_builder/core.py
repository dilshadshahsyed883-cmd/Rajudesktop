"""Z Builder: V25 plan, persistent local media catalog and deterministic shot binding.
No Pexels scraping; an unresolved stock fallback is a visible blocking decision.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from contextlib import contextmanager
from pathlib import Path
import csv
import hashlib
import json
import re
import sqlite3
import unicodedata
from typing import Optional

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
VIDEO_EXTS = {'.mp4', '.m4v', '.mov', '.mkv', '.webm', '.avi'}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS
NONE_VALUES = {'', 'none', 'null', 'n/a', 'na'}
SOURCE_MODES = {'library_only', 'scene_first'}
MAX_VIDEO_CLIP_SECONDS = 4.0
TIMING_EPSILON = 0.0005


def kind_of(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in IMAGE_EXTS:
        return 'image'
    if suffix in VIDEO_EXTS:
        return 'video'
    raise ValueError(f'Unsupported media extension: {suffix}')


def tokenize(value: str) -> list[str]:
    value = unicodedata.normalize('NFKC', value).casefold()
    return re.findall(r'[^\W_]+', value, re.UNICODE)


def stable_id(path: str) -> str:
    return hashlib.sha256(str(Path(path).resolve()).casefold().encode('utf-8')).hexdigest()[:24]


class Catalog:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, filename TEXT NOT NULL,
                kind TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '', approved INTEGER NOT NULL DEFAULT 1,
                size_bytes INTEGER NOT NULL DEFAULT 0
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS media_exports (
                asset_id TEXT PRIMARY KEY, exported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                times_exported INTEGER NOT NULL DEFAULT 1
            )''')

    @contextmanager
    def _connect(self):
        # sqlite3.Connection.__exit__ commits but DOES NOT close on Windows.
        # Explicitly close to release database-file locks on import/test cleanup.
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def add(self, path: str | Path) -> str:
        p = Path(path).expanduser().resolve(strict=True)
        if not p.is_file():
            raise ValueError('Not a regular media file')
        kind = kind_of(p)
        identity = stable_id(str(p))
        with self._connect() as c:
            c.execute('''INSERT INTO assets(id,path,filename,kind,tags,approved,size_bytes)
                VALUES(?,?,?,?,?,1,?) ON CONFLICT(id) DO UPDATE SET
                size_bytes=excluded.size_bytes, filename=excluded.filename, kind=excluded.kind''',
                (identity, str(p), p.name, kind, '', p.stat().st_size))
        return identity

    def add_folder(self, folder: str | Path) -> tuple[int, list[str]]:
        folder = Path(folder).expanduser().resolve(strict=True)
        if not folder.is_dir():
            raise ValueError('Choose an existing folder')
        count = 0
        errors = []
        for p in sorted(folder.rglob('*')):
            if p.is_file() and p.suffix.lower() in MEDIA_EXTS:
                try:
                    self.add(p)
                    count += 1
                except (OSError, ValueError) as e:
                    errors.append(f'{p.name}: {e}')
        return count, errors

    def assets(self, include_missing=True) -> list[dict]:
        with self._connect() as c:
            c.row_factory = sqlite3.Row
            result = [dict(r) for r in c.execute('''SELECT a.*, COALESCE(e.times_exported, 0) AS export_count,
                e.exported_at AS last_exported_at
                FROM assets AS a LEFT JOIN media_exports AS e ON e.asset_id = a.id
                ORDER BY a.kind, a.filename COLLATE NOCASE, a.id''')]
        for a in result:
            a['approved'] = bool(a['approved'])
            a['exists'] = Path(a['path']).is_file()
        return result if include_missing else [a for a in result if a['exists']]

    def update_tags(self, identity: str, tags: str):
        with self._connect() as c:
            if not c.execute('SELECT 1 FROM assets WHERE id=?', (identity,)).fetchone():
                raise KeyError(identity)
            c.execute('UPDATE assets SET tags=? WHERE id=?', (tags.strip(), identity))

    def remove(self, identity: str):
        """Forget a catalog entry, never delete a user's original file."""
        with self._connect() as c:
            c.execute('DELETE FROM media_exports WHERE asset_id=?', (identity,))
            c.execute('DELETE FROM assets WHERE id=?', (identity,))

    def clear_library_records(self) -> int:
        """Remove every library entry and its export-history metadata; keep PC files."""
        with self._connect() as c:
            count = c.execute('SELECT COUNT(*) FROM assets').fetchone()[0]
            c.execute('DELETE FROM media_exports')
            c.execute('DELETE FROM assets')
        return count

    def recycle_entire_library(self, recycle=None) -> tuple[list[str], list[str], list[str]]:
        """Explicit bulk operation: recycle all cataloged original media files.

        Missing originals are only forgotten. Failed/unsafe files remain in the
        catalog for manual review; no CapCut draft or rendered output is touched
        unless it was separately imported into the library.
        The UI must require confirmation before calling this method.
        """
        if recycle is None:
            from send2trash import send2trash
            recycle = send2trash
        moved, missing, failures = [], [], []
        for asset in self.assets():
            path = Path(asset['path'])
            identity = asset['id']
            if not path.exists() and not path.is_symlink():
                self.remove(identity)
                missing.append(str(path))
                continue
            if (not path.is_file() or path.is_symlink() or
                    stable_id(str(path)) != identity):
                failures.append(f'{path}: unsafe file type, link, or changed path; skipped')
                continue
            try:
                recycle(str(path))
            except Exception as exc:
                failures.append(f'{path.name}: {exc}')
                continue
            try:
                self.remove(identity)
            except Exception as exc:
                failures.append(f'{path.name}: recycled, but catalog record could not be removed: {exc}')
            moved.append(str(path))
        return moved, missing, failures

    def record_successful_export(self, paths) -> int:
        """Mark only catalog items used in a fully verified CapCut export.

        Matching uses canonical source paths and stable IDs, never just filenames.
        A scene being matched does NOT count as an export.
        """
        marked = 0
        with self._connect() as c:
            for raw in set(str(p) for p in paths if p):
                path = str(Path(raw).resolve())
                identity = stable_id(path)
                found = c.execute('SELECT 1 FROM assets WHERE id=? AND path=?',
                                  (identity, path)).fetchone()
                if found:
                    c.execute('''INSERT INTO media_exports(asset_id, times_exported)
                                 VALUES (?, 1)
                                 ON CONFLICT(asset_id) DO UPDATE SET
                                 times_exported=media_exports.times_exported+1,
                                 exported_at=CURRENT_TIMESTAMP''', (identity,))
                    marked += 1
        return marked

    def recycle_exported_media(self, identities, recycle=None) -> tuple[list[str], list[str]]:
        """Explicitly move selected exported originals to Windows Recycle Bin.

        Never silently delete or touch unexported files. The UI must obtain final
        render confirmation first; an exported CapCut draft is not a rendered video.
        """
        if recycle is None:
            from send2trash import send2trash
            recycle = send2trash
        moved, failures = [], []
        for identity in dict.fromkeys(identities):
            with self._connect() as c:
                row = c.execute('''SELECT a.path FROM assets AS a
                    INNER JOIN media_exports AS e ON e.asset_id = a.id
                    WHERE a.id=?''', (identity,)).fetchone()
            if row is None:
                failures.append(f'{identity}: not marked as exported (not eligible)')
                continue
            path = Path(row[0])
            if (not path.is_file() or path.is_symlink() or
                    stable_id(str(path)) != identity):
                failures.append(f'{path}: missing or changed path; skipped')
                continue
            try:
                recycle(str(path))
            except Exception as exc:
                failures.append(f'{path.name}: {exc}')
                continue
            with self._connect() as c:
                c.execute('DELETE FROM media_exports WHERE asset_id=?', (identity,))
                c.execute('DELETE FROM assets WHERE id=? AND path=?', (identity, str(path)))
            moved.append(str(path))
        return moved, failures

    def summary(self) -> str:
        assets = self.assets()
        lines = ['Z Builder - Scene Media Library Summary',
                 f'Images: {sum(a["kind"] == "image" for a in assets)}',
                 f'Videos: {sum(a["kind"] == "video" for a in assets)}',
                 f'Approved: {sum(a["approved"] for a in assets)}',
                 f'Used in verified CapCut exports: {sum(a["export_count"] > 0 for a in assets)}',
                 f'Never used in verified CapCut exports: {sum(a["export_count"] == 0 for a in assets)}',
                 'Usage: used=0 means not used; used=N means included in N verified CapCut exports.',
                 'Repeated appearances within the same export count once per media file.',
                 'Only approved and existing files can be selected.', '']
        for kind in ('image', 'video'):
            lines.append(kind.upper() + 'S')
            for a in assets:
                if a['kind'] == kind:
                    lines.append(f'- {a["filename"]} | id={a["id"]} | used={a["export_count"]} | approved={a["approved"]} | exists={a["exists"]} | tags={a["tags"]}')
            lines.append('')
        return '\n'.join(lines)


@dataclass
class Shot:
    section: str
    filename: str
    media_type: str
    keyword: str
    pexels_keyword: str
    duration: float
    narration: str = ''
    animation: str = 'none'
    motion: str = 'none'
    transition: str = 'hard_cut'
    assigned_id: str = ''
    assigned_path: str = ''
    source: str = 'unresolved'
    warning: str = ''
    start_seconds: float = -1.0  # -1 means legacy sequential V25 timeline
    source_in_seconds: float = 0.0  # non-destructive trim of original 4-second video
    native_combo: str = ''  # native Combo preset: none, random_saved, id:<resource_id>, or exact name
    native_transition_after: str = ''  # native same-track cut transition after shot


@dataclass
class Plan:
    name: str
    source_mode: str
    width: int
    height: int
    fps: int
    shots: list[Shot]
    sections: dict[str, dict[str, str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    narration_path: str = ''

    @property
    def duration(self):
        return round(max((end for _, end, _ in timeline(self)), default=0.0), 3)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(name=d['name'], source_mode=d['source_mode'], width=d['width'],
                   height=d['height'], fps=d['fps'],
                   shots=[Shot(**s) for s in d['shots']], sections=d.get('sections', {}),
                   warnings=d.get('warnings', []), narration_path=d.get('narration_path', ''))


def parse_ini(text: str) -> dict[str, dict[str, str]]:
    """Strict V25 multi-block parser, accepting pre-section SCENE_PLAN_VERSION=2."""
    blocks = {'_ROOT': {}}
    current = '_ROOT'
    for num, line in enumerate(text.lstrip('\ufeff').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith(('#', ';')):
            continue
        if line.startswith('['):
            if not line.endswith(']'):
                raise ValueError(f'Line {num}: malformed section header')
            current = line[1:-1].strip().upper()
            if current in blocks:
                raise ValueError(f'Line {num}: duplicate section {current}')
            blocks[current] = {}
        elif '=' in line:
            key, value = line.split('=', 1)
            key = key.strip().lower()
            if not key:
                raise ValueError(f'Line {num}: empty key')
            if key in blocks[current]:
                raise ValueError(f'Line {num}: duplicate key {key}')
            blocks[current][key] = value.strip()
        else:
            raise ValueError(f'Line {num}: expected section or key=value')
    if blocks['_ROOT'].get('scene_plan_version') != '2':
        raise ValueError('Z Builder requires SCENE_PLAN_VERSION=2')
    return blocks


def _number(value: str, label: str, minimum: float, maximum: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{label}: invalid number {value!r}')
    if not minimum <= result <= maximum:
        raise ValueError(f'{label} must be between {minimum} and {maximum}')
    return result


def load_plan(text: str) -> Plan:
    if 'SCENE_PLAN_VERSION=2' not in text.lstrip('\ufeff'):
        return load_simple_plan(text)
    blocks = parse_ini(text)
    p = blocks.get('PROJECT', {})
    media = blocks.get('MEDIA', {})
    out = blocks.get('OUTPUT', {})
    mode = media.get('source_mode', 'library_only').casefold()
    if mode not in SOURCE_MODES:
        raise ValueError('MEDIA.source_mode must be library_only or scene_first')
    res = out.get('resolution', '1080p')
    if res not in {'1080p', '720p'}:
        raise ValueError('Supported resolutions are 1080p and 720p')
    aspect = out.get('aspect_ratio', '16:9')
    if aspect not in {'16:9', '9:16'}:
        raise ValueError('Supported aspect ratios are 16:9 and 9:16')
    w, h = (1920, 1080) if res == '1080p' else (1280, 720)
    if aspect == '9:16':
        w, h = h, w
    fps = int(_number(out.get('fps', '30'), 'fps', 24, 60))
    if fps not in {24, 25, 30, 60}:
        raise ValueError('Supported FPS: 24, 25, 30, 60')
    shots = []
    warnings = []
    for section, kv in blocks.items():
        if not re.fullmatch(r'(INTRO|SCENE_\d+)\.SHOT_\d+', section):
            continue
        name = kv.get('library_filename', '').strip()
        if name.casefold() in NONE_VALUES:
            name = ''
        kind = kv.get('media_type', 'video').casefold()
        if kind not in {'image', 'video'}:
            raise ValueError(f'{section}: media_type must be image or video')
        explicit = kv.get('shot_duration_seconds') or kv.get('duration_seconds')
        if explicit:
            duration = _number(explicit, section + ' duration', 0.1, 1800)
        elif kv.get('animation_duration'):
            duration = _number(kv['animation_duration'], section + ' animation_duration', 0.1, 1800)
            warnings.append(f'{section}: animation_duration used as provisional shot duration; voice-sync not performed')
        else:
            duration = 3.0
            warnings.append(f'{section}: missing duration; provisional 3.0s used, verify timing')
        shots.append(Shot(section, name, kind, kv.get('library_keyword', ''),
                          kv.get('pexels_primary_keyword', ''), duration,
                          kv.get('narration', ''), kv.get('animation', 'none'),
                          kv.get('motion', 'none'), kv.get('transition_out', 'hard_cut'),
                           native_combo=kv.get('native_combo', ''),
                           native_transition_after=kv.get('native_transition_after', '')))
    if not shots:
        raise ValueError('Director V25 plan contains no [INTRO.SHOT_XX] or [SCENE_NNN.SHOT_XX]')
    return Plan(p.get('name', 'Z Builder Project'), mode, w, h, fps, shots, blocks, warnings)



def parse_time(value: str) -> float:
    """Accept SS.mmm, MM:SS.mmm or HH:MM:SS.mmm; exact ms precision."""
    text = value.strip()
    segments = text.split(':')
    if not 1 <= len(segments) <= 3:
        raise ValueError(f'Invalid Scene Plan time: {value}')
    if any(not re.fullmatch(r'\d+(?:\.\d{1,3})?', p) for p in segments):
        raise ValueError(f'Invalid Scene Plan time: {value}')
    if any('.' in p for p in segments[:-1]):
        raise ValueError(f'Invalid Scene Plan time: {value}')
    if len(segments) >= 2 and float(segments[-1]) >= 60:
        raise ValueError(f'Seconds must be below 60: {value}')
    if len(segments) == 3 and int(segments[1]) >= 60:
        raise ValueError(f'Minutes must be below 60: {value}')
    result = 0.0
    for part in segments:
        result = result * 60 + float(part)
    return round(result, 3)


def timeline(plan: Plan):
    """Return (start, end, shot); no cumulative drift for explicit simple plans."""
    cursor = 0.0
    for shot in plan.shots:
        start = cursor if shot.start_seconds < 0 else round(shot.start_seconds, 3)
        end = round(start + shot.duration, 3)
        yield start, end, shot
        cursor = end


def load_simple_plan(text: str) -> Plan:
    """Simple input: 00:00 --> 00:02.500 | video | clip.mp4 | in=0.5

    Media may alternatively be `keyword: tennis`, resolved from approved library
    names/tags. Rows must be gapless and begin at zero to protect voice sync.
    """
    options = {'name': 'Z Builder Project', 'aspect_ratio': '16:9',
               'resolution': '1080p', 'fps': '30',
               'combo_default': 'none', 'transition_default': 'none',
               'combo_seed': '42', 'transition_seed': '43'}
    names = {'project': 'name', 'name': 'name', 'aspect': 'aspect_ratio',
             'aspect_ratio': 'aspect_ratio', 'resolution': 'resolution', 'fps': 'fps',
             'combo_default': 'combo_default', 'transition_default': 'transition_default',
             'combo_seed': 'combo_seed', 'transition_seed': 'transition_seed'}
    row_pattern = re.compile(r'^(.*?)\s*-->\s*(.*?)\s*\|\s*(image|video)\s*\|\s*([^|]+)(.*)$', re.I)
    shots = []
    prev = 0.0
    for line_no, raw in enumerate(text.lstrip('\ufeff').splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(('#', ';')):
            continue
        match = row_pattern.match(line)
        if not match:
            if '=' in line and '-->' not in line:
                key, value = (part.strip() for part in line.split('=', 1))
                key = names.get(key.casefold())
                if not key or shots:
                    raise ValueError(f'Line {line_no}: unknown setting or setting after shots')
                options[key] = value
                continue
            raise ValueError(f'Line {line_no}: use START --> END | video/image | filename or keyword')
        begin, end, kind, target, tail = match.groups()
        start, stop = parse_time(begin), parse_time(end)
        if not 0 < stop - start <= 1800:
            raise ValueError(f'Line {line_no}: end must be after start')
        if abs(start - prev) > TIMING_EPSILON:
            raise ValueError(f'Line {line_no}: gap/overlap at {start:g}s (expected {prev:g}s); voice timeline must be continuous')
        extras = {}
        for part in tail.split('|'):
            part = part.strip()
            if not part:
                continue
            if '=' not in part:
                raise ValueError(f'Line {line_no}: expected option key=value, found {part}')
            k, v = (p.strip() for p in part.split('=', 1))
            if k.casefold() not in {'in', 'text', 'combo', 'transition_after'}:
                raise ValueError(f'Line {line_no}: unknown media option {k}')
            extras[k.casefold()] = v
        target = target.strip()
        keyword = ''
        name = ''
        if target.casefold().startswith('keyword:'):
            keyword = target.split(':', 1)[1].strip()
        elif Path(target).suffix.casefold() in MEDIA_EXTS:
            name = target
        else:
            keyword = target
        if not (name or keyword):
            raise ValueError(f'Line {line_no}: media filename/keyword is empty')
        in_sec = _number(extras.get('in', '0'), f'Line {line_no} video in', 0, 4)
        if kind.casefold() == 'image' and in_sec:
            raise ValueError(f'Line {line_no}: in= applies only to videos')
        shots.append(Shot(f'SCENE_{len(shots)+1:03d}.SHOT_01', name, kind.casefold(),
                          keyword, '', round(stop-start, 3), extras.get('text', ''),
                          start_seconds=start, source_in_seconds=in_sec,
                           native_combo=extras.get('combo', ''),
                           native_transition_after=extras.get('transition_after', '')))
        prev = stop
    if not shots:
        raise ValueError('Scene Plan has no timed shots')
    aspect = options['aspect_ratio']
    if aspect not in {'16:9', '9:16'}:
        raise ValueError('aspect_ratio must be 16:9 or 9:16')
    resolution = options['resolution']
    if resolution not in {'1080p', '720p'}:
        raise ValueError('resolution must be 1080p or 720p')
    fps = int(_number(options['fps'], 'fps', 24, 60))
    if fps not in {24, 25, 30, 60}:
        raise ValueError('fps must be 24, 25, 30 or 60')
    width, height = (1920, 1080) if resolution == '1080p' else (1280, 720)
    if aspect == '9:16':
        width, height = height, width
    return Plan(options['name'], 'library_only', width, height, fps, shots,
                sections={'_FORMAT': {'type': 'simple_timed_v1'},
                           'CAPCUT_EFFECTS': {key: options[key] for key in
                               ('combo_default', 'transition_default', 'combo_seed', 'transition_seed')}})


def bind_media(plan: Plan, assets: list[dict]) -> list[str]:
    """Exact filename has priority, no fabricated IDs, no Pexels silent substitution."""
    issues = []
    available = [a for a in assets if a['approved'] and a['exists']]
    lookup = {}
    for a in available:
        lookup.setdefault(a['filename'].casefold(), []).append(a)
    for shot in plan.shots:
        # Preserve manual selections after a rebind if they are still valid.
        manual = next((a for a in available if a['id'] == shot.assigned_id), None)
        matches = lookup.get(shot.filename.casefold(), []) if shot.filename else []
        selected = manual if manual and manual['kind'] == shot.media_type else None
        if not selected and len(matches) == 1 and matches[0]['kind'] == shot.media_type:
            selected = matches[0]
        keyword_ambiguous = False
        if not selected and not shot.filename and shot.keyword:
            tokens = set(tokenize(shot.keyword))
            scored = []
            for asset in available:
                if asset['kind'] != shot.media_type:
                    continue
                indexed = set(tokenize(Path(asset['filename']).stem + ' ' + asset.get('tags', '')))
                common = len(indexed & tokens)
                if common and common == len(tokens):
                    scored.append((common, asset))
            if scored:
                scored.sort(key=lambda x: (-x[0], x[1]['filename'].casefold(), x[1]['id']))
                best = scored[0][0]
                ties = [asset for score, asset in scored if score == best]
                if len(ties) == 1:
                    selected = ties[0]
                else:
                    keyword_ambiguous = True
        shot.warning = ''
        if selected:
            shot.assigned_id = selected['id']
            shot.assigned_path = selected['path']
            shot.source = 'library'
        else:
            shot.assigned_id = shot.assigned_path = ''
            shot.source = 'unresolved'
            if keyword_ambiguous:
                problem = f'{shot.section}: multiple media match keyword {shot.keyword}; choose manually'
            elif len(matches) > 1:
                problem = f'{shot.section}: ambiguous duplicate filename {shot.filename}; choose file manually'
            elif matches and matches[0]['kind'] != shot.media_type:
                problem = f'{shot.section}: media type mismatch for {shot.filename}'
            elif plan.source_mode == 'scene_first' and shot.pexels_keyword:
                problem = f'{shot.section}: requires Pexels fallback: {shot.pexels_keyword} (download/import file manually)'
            else:
                problem = f'{shot.section}: local media missing: {shot.filename or "unspecified"}'
            shot.warning = problem
            issues.append(problem)
    return issues


def preflight(plan: Plan) -> list[str]:
    issues = []
    cursor = 0.0
    if not plan.shots:
        issues.append('No scene shots')
    for start, end, shot in timeline(plan):
        if abs(start - cursor) > TIMING_EPSILON:
            issues.append(f'{shot.section}: timeline gap/overlap at {start}s (expected {cursor}s)')
        cursor = end
        if shot.media_type == 'video':
            if shot.source_in_seconds < 0 or shot.source_in_seconds > MAX_VIDEO_CLIP_SECONDS:
                issues.append(f'{shot.section}: source in must be between 0 and 4 seconds')
            elif shot.source_in_seconds + shot.duration > MAX_VIDEO_CLIP_SECONDS + TIMING_EPSILON:
                issues.append(f'{shot.section}: {shot.duration:.3f}s video slot from in={shot.source_in_seconds:.3f}s exceeds a 4-second clip; split the slot or choose another item')
        if not shot.assigned_path or not Path(shot.assigned_path).is_file():
            issues.append(f'{shot.section}: unresolved or missing media')
        elif kind_of(shot.assigned_path) != shot.media_type:
            issues.append(f'{shot.section}: kind mismatch')
        if not 0.1 <= shot.duration <= 1800:
            issues.append(f'{shot.section}: invalid duration')
    # Voice is optional. Exact timed Scene Plan is the authority for visuals.
    if plan.narration_path and not Path(plan.narration_path).is_file():
        issues.append('Narration file not found')
    return issues


def save_project(plan: Plan, filename: str | Path):
    p = Path(filename)
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_suffix(p.suffix + '.tmp')
    temp.write_text(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False), encoding='utf-8')
    temp.replace(p)


def open_project(filename: str | Path) -> Plan:
    return Plan.from_dict(json.loads(Path(filename).read_text(encoding='utf-8')))


def write_timeline_csv(plan: Plan, filename: str | Path):
    with Path(filename).open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['shot', 'start_seconds', 'end_seconds', 'duration_seconds',
                         'source_in_seconds', 'source_out_seconds', 'filename', 'source', 'narration'])
        for start, end, shot in timeline(plan):
            writer.writerow([shot.section, start, end, shot.duration,
                             shot.source_in_seconds if shot.media_type == 'video' else 0,
                             round(shot.source_in_seconds + shot.duration, 3) if shot.media_type == 'video' else '',
                             shot.assigned_path, shot.source, shot.narration])
