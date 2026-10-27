"""Z Builder: V25 plan, persistent local media catalog and deterministic shot binding.
No Pexels scraping; an unresolved stock fallback is a visible blocking decision.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
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

    def _connect(self):
        return sqlite3.connect(self.db_path)

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
            result = [dict(r) for r in c.execute('SELECT * FROM assets ORDER BY kind, filename COLLATE NOCASE, id')]
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
            c.execute('DELETE FROM assets WHERE id=?', (identity,))

    def summary(self) -> str:
        assets = self.assets()
        lines = ['Z Builder - Scene Media Library Summary',
                 f'Images: {sum(a["kind"] == "image" for a in assets)}',
                 f'Videos: {sum(a["kind"] == "video" for a in assets)}',
                 f'Approved: {sum(a["approved"] for a in assets)}',
                 'Only approved and existing files can be selected.', '']
        for kind in ('image', 'video'):
            lines.append(kind.upper() + 'S')
            for a in assets:
                if a['kind'] == kind:
                    lines.append(f'- {a["filename"]} | id={a["id"]} | approved={a["approved"]} | exists={a["exists"]} | tags={a["tags"]}')
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
        return round(sum(s.duration for s in self.shots), 3)

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
                          kv.get('motion', 'none'), kv.get('transition_out', 'hard_cut')))
    if not shots:
        raise ValueError('Director V25 plan contains no [INTRO.SHOT_XX] or [SCENE_NNN.SHOT_XX]')
    return Plan(p.get('name', 'Z Builder Project'), mode, w, h, fps, shots, blocks, warnings)


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
        shot.warning = ''
        if selected:
            shot.assigned_id = selected['id']
            shot.assigned_path = selected['path']
            shot.source = 'library'
        else:
            shot.assigned_id = shot.assigned_path = ''
            shot.source = 'unresolved'
            if len(matches) > 1:
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
    if not plan.shots:
        issues.append('No scene shots')
    for shot in plan.shots:
        if not shot.assigned_path or not Path(shot.assigned_path).is_file():
            issues.append(f'{shot.section}: unresolved or missing media')
        elif kind_of(shot.assigned_path) != shot.media_type:
            issues.append(f'{shot.section}: kind mismatch')
        if not 0.1 <= shot.duration <= 1800:
            issues.append(f'{shot.section}: invalid duration')
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
        writer.writerow(['shot', 'start_seconds', 'duration_seconds', 'filename', 'source', 'narration', 'animation', 'transition'])
        t = 0.0
        for shot in plan.shots:
            writer.writerow([shot.section, round(t, 3), round(shot.duration, 3),
                             shot.assigned_path, shot.source, shot.narration, shot.animation, shot.transition])
            t += shot.duration
